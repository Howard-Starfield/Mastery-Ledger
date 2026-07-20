from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import shutil
import socket
import threading
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

from mastery_ledger.database import (
    claim_next_job,
    get_job,
    read_setting,
    recover_interrupted_jobs,
    update_job,
)
from mastery_ledger.media_processing import (
    TranscriptError,
    sha256_file,
    write_asr_transcript,
    write_transcript,
)
from mastery_ledger.models import WorkspaceState
from mastery_ledger.source_service import (
    SourceIntakeError,
    _course_by_id,
    append_event,
    atomic_json,
    update_source_record,
)

MAX_REMOTE_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000
SUPPORTED_TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".rst", ".csv", ".json", ".yaml", ".yml"}


class IngestionFailure(RuntimeError):
    def __init__(self, code: str, message: str, suggestion: str) -> None:
        super().__init__(message)
        self.code = code
        self.suggestion = suggestion


class _HTMLExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._title_parts: list[str] = []
        self._active_tag: str | None = None
        self._parts: list[str] = []
        self._ignored_depth = 0
        self.blocks: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in {"script", "style", "noscript", "svg", "template"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "title":
            self._active_tag = "title"
            self._parts = []
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "pre", "td", "th"}:
            self._active_tag = tag
            self._parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg", "template"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if self._ignored_depth or tag != self._active_tag:
            return
        text = " ".join("".join(self._parts).split())
        if tag == "title":
            self.title = text
        elif text:
            self.blocks.append((tag, text))
        self._active_tag = None
        self._parts = []

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and self._active_tag:
            self._parts.append(data)


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        request: urllib.request.Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> urllib.request.Request | None:
        _validate_public_url(urljoin(request.full_url, new_url))
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


class _QuietYtdlpLogger:
    def debug(self, message: str) -> None:
        del message

    def info(self, message: str) -> None:
        del message

    def warning(self, message: str) -> None:
        del message

    def error(self, message: str) -> None:
        del message


def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise IngestionFailure("invalid_url", "The source URL is invalid.", "Use a public HTTP or HTTPS URL.")
    if parsed.username or parsed.password:
        raise IngestionFailure("credentials_not_allowed", "Credentials are not accepted in source URLs.", "Remove credentials and use a public source.")
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
        }
    except socket.gaierror as error:
        raise IngestionFailure("dns_failed", "The source hostname could not be resolved.", "Check the URL and try again.") from error
    if not addresses:
        raise IngestionFailure("dns_failed", "The source hostname returned no addresses.", "Check the URL and try again.")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if not ip.is_global:
            raise IngestionFailure("private_network_blocked", "Private or local network URLs are not accepted.", "Provide a public URL or import a local file explicitly.")


def _fetch_web(url: str) -> tuple[bytes, str, str]:
    _validate_public_url(url)
    opener = urllib.request.build_opener(_SafeRedirect())
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MasteryLedger/0.1 source-ingestion",
            "Accept": "text/html,text/plain,text/markdown;q=0.9,*/*;q=0.1",
        },
    )
    try:
        with opener.open(request, timeout=25) as response:
            final_url = response.geturl()
            _validate_public_url(final_url)
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "text/plain", "text/markdown", "application/xhtml+xml"}:
                raise IngestionFailure(
                    "unsupported_content_type",
                    f"The URL returned {content_type}, which is not an article format.",
                    "Import the file locally or choose the video source type.",
                )
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_REMOTE_BYTES:
                raise IngestionFailure("source_too_large", "The remote article exceeds the ingestion limit.", "Save the material locally and import a bounded file.")
            data = response.read(MAX_REMOTE_BYTES + 1)
            if len(data) > MAX_REMOTE_BYTES:
                raise IngestionFailure("source_too_large", "The remote article exceeds the ingestion limit.", "Save the material locally and import a bounded file.")
            charset = response.headers.get_content_charset() or "utf-8"
            return data, content_type, final_url
    except IngestionFailure:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise IngestionFailure("retrieval_failed", "The article could not be retrieved.", "Check that the public URL is reachable and retry once.") from error


def _hash_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _markdown_document(
    *,
    source_id: str,
    title: str,
    source_type: str,
    original_location: str,
    rights_basis: str,
    content_hash: str,
    blocks: list[tuple[str, str]],
    extra: list[str] | None = None,
) -> str:
    lines = [
        f"# {title}",
        "",
        f"- Source ID: `{source_id}`",
        f"- Type: `{source_type}`",
        f"- Original: {original_location}",
        f"- Rights basis: `{rights_basis}`",
        f"- Content hash: `{content_hash}`",
        "- Processing: deterministic extraction; source content is treated as untrusted data",
    ]
    if extra:
        lines.extend(extra)
    lines.extend(["", "## Extracted knowledge", ""])
    for index, (kind, text) in enumerate(blocks[:10_000], start=1):
        locator = f"BLOCK-{index:05d}"
        safe_text = text.replace("\x00", "").strip()
        if not safe_text:
            continue
        if kind.startswith("h") and len(kind) == 2 and kind[1].isdigit():
            level = min(6, max(3, int(kind[1]) + 2))
            lines.extend([f"{'#' * level} {safe_text}", "", f"Locator: `{locator}`", ""])
        else:
            lines.extend([f"### {locator}", "", safe_text, ""])
    return "\n".join(lines).rstrip() + "\n"


def _text_blocks(content: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    for chunk in content[:MAX_TEXT_CHARS].replace("\r\n", "\n").replace("\r", "\n").split("\n\n"):
        text = " ".join(chunk.split())
        if text:
            blocks.append(("p", text))
    return blocks


def _extract_local_document(path: Path) -> tuple[list[tuple[str, str]], str | None]:
    suffix = path.suffix.casefold()
    if suffix in SUPPORTED_TEXT_SUFFIXES:
        return _text_blocks(_decode_text(path.read_bytes())), None
    if suffix in {".html", ".htm"}:
        parser = _HTMLExtractor()
        parser.feed(_decode_text(path.read_bytes())[:MAX_TEXT_CHARS])
        return parser.blocks, parser.title or None
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise IngestionFailure("missing_pdf_support", "PDF extraction support is not installed.", "Repair the Mastery Ledger core runtime and retry.") from error
        reader = PdfReader(str(path))
        blocks = [("p", f"[Page {index}] {text}") for index, page in enumerate(reader.pages, start=1) if (text := " ".join((page.extract_text() or "").split()))]
        return blocks, str(reader.metadata.title) if reader.metadata and reader.metadata.title else None
    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError as error:
            raise IngestionFailure("missing_docx_support", "DOCX extraction support is not installed.", "Repair the Mastery Ledger core runtime and retry.") from error
        document = Document(str(path))
        return [("p", paragraph.text.strip()) for paragraph in document.paragraphs if paragraph.text.strip()], document.core_properties.title or None
    return [], None


def _select_language(captions: object, requested: str) -> str | None:
    if not isinstance(captions, dict):
        return None
    languages = [str(key) for key in captions]
    if requested in languages:
        return requested
    prefix = requested.split("-", 1)[0].casefold()
    return next((language for language in languages if language.casefold().split("-", 1)[0] == prefix), None)


def _cancel_requested(job_id: str) -> bool:
    current = get_job(job_id)
    payload = current.get("payload") if current else None
    return bool(isinstance(payload, dict) and payload.get("cancellation_requested"))


def _job_progress(job: dict[str, object], stage: str, progress: float) -> dict[str, object]:
    payload = job.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    payload["stage"] = stage
    payload["progress"] = max(0.0, min(1.0, progress))
    update_job(str(job["job_id"]), state="running", payload=payload)
    job["payload"] = payload
    return payload


def _artifact_records(directory: Path, *, prefix: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    if not directory.exists():
        return records
    for path in sorted(directory.rglob("*")):
        if path.is_file() and not path.is_symlink():
            records.append(
                {
                    "kind": path.suffix.lstrip(".") or "file",
                    "local_path": str(Path(prefix) / path.relative_to(directory)).replace("\\", "/"),
                    "size_bytes": path.stat().st_size,
                    "content_hash": sha256_file(path),
                }
            )
    return records


def _promote(staging: Path, course_root: Path, source_id: str) -> tuple[str, list[dict[str, object]]]:
    source_root = course_root / "source"
    media_destination = source_root / "media" / source_id
    source_root.mkdir(parents=True, exist_ok=True)
    media_destination.mkdir(parents=True, exist_ok=True)
    knowledge_source = staging / f"{source_id}.md"
    if not knowledge_source.is_file():
        raise IngestionFailure("missing_knowledge_record", "The worker did not produce a knowledge record.", "Inspect the preserved staging folder and retry.")
    os.replace(knowledge_source, source_root / f"{source_id}.md")
    media_source = staging / "media"
    if media_source.is_dir():
        for item in sorted(media_source.rglob("*")):
            if item.is_dir():
                continue
            relative = item.relative_to(media_source)
            destination = media_destination / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(item, destination)
    artifacts = _artifact_records(media_destination, prefix=f"source/media/{source_id}")
    return f"source/{source_id}.md", artifacts


def _web_article(job: dict[str, object], staging: Path) -> dict[str, object]:
    payload = job["payload"]
    data, content_type, final_url = _fetch_web(str(payload["location"]))
    title = str(payload["title"])
    if content_type in {"text/html", "application/xhtml+xml"}:
        parser = _HTMLExtractor()
        parser.feed(_decode_text(data)[:MAX_TEXT_CHARS])
        blocks = parser.blocks
        title = parser.title or title
    else:
        blocks = _text_blocks(_decode_text(data))
    if not blocks:
        raise IngestionFailure("empty_extraction", "The article contained no readable text.", "Try a printable article URL or import a local copy.")
    content_hash = _hash_bytes(data)
    knowledge = _markdown_document(
        source_id=str(payload["source_id"]),
        title=title,
        source_type="web_article",
        original_location=final_url,
        rights_basis=str(payload["rights_basis"]),
        content_hash=content_hash,
        blocks=blocks,
        extra=[f"- Retrieved URL: {final_url}"],
    )
    (staging / f"{payload['source_id']}.md").write_text(knowledge, encoding="utf-8")
    return {"status": "complete", "title": title, "content_hash": content_hash, "original_location": final_url}


def _local_source(job: dict[str, object], staging: Path) -> dict[str, object]:
    payload = job["payload"]
    path = Path(str(payload["location"]))
    if not path.is_file() or path.is_symlink():
        raise IngestionFailure("local_source_missing", "The local source is no longer available.", "Restore the file at its recorded path and retry.")
    media = staging / "media"
    media.mkdir(parents=True)
    copied = media / f"original{path.suffix.casefold()}"
    shutil.copy2(path, copied)
    content_hash = sha256_file(copied)
    source_type = str(payload["source_type"])
    title = str(payload["title"])

    if source_type == "local_subtitle" or path.suffix.casefold() in {".srt", ".vtt"}:
        _, _, segment_count = write_transcript(
            copied,
            media,
            source_id=str(payload["source_id"]),
            item_id="ITEM-001",
            origin="user_transcript",
            language=str(payload["language"]),
        )
        blocks = [("p", f"A timestamped transcript with {segment_count} segments is available under `source/media/{payload['source_id']}/transcript.md`.")]
        status, code, suggestion = "complete", None, None
    elif source_type == "local_media":
        model_path = read_setting("asr_model_path", None)
        if payload.get("allow_transcription") and isinstance(model_path, str) and Path(model_path).exists():
            _, _, segment_count = write_asr_transcript(
                copied,
                media,
                source_id=str(payload["source_id"]),
                item_id="ITEM-001",
                language=str(payload["language"]),
                model_path=model_path,
            )
            blocks = [("p", f"A local-ASR transcript with {segment_count} segments is available under `source/media/{payload['source_id']}/transcript.md`.")]
            status, code, suggestion = "complete", None, None
        else:
            blocks = [("p", "The authorized media file is preserved, but no transcript has been generated.")]
            status = "needs_user_action"
            code = "asr_model_not_configured" if payload.get("allow_transcription") else "transcription_not_approved"
            suggestion = "Approve and configure a local ASR model, then retry this source." if payload.get("allow_transcription") else "Enable local transcription for this source or add an SRT/VTT file."
    else:
        blocks, extracted_title = _extract_local_document(copied)
        title = extracted_title or title
        if blocks:
            status, code, suggestion = "complete", None, None
        else:
            blocks = [("p", "The original file is preserved, but this format has no deterministic text extractor in the current runtime.")]
            status, code, suggestion = "partial", "unsupported_document_format", "Convert the source to PDF, DOCX, Markdown, HTML, or plain text and add that copy."

    knowledge = _markdown_document(
        source_id=str(payload["source_id"]),
        title=title,
        source_type=source_type,
        original_location=str(path),
        rights_basis=str(payload["rights_basis"]),
        content_hash=content_hash,
        blocks=blocks,
        extra=[f"- Preserved original: `source/media/{payload['source_id']}/{copied.name}`"],
    )
    (staging / f"{payload['source_id']}.md").write_text(knowledge, encoding="utf-8")
    return {"status": status, "title": title, "content_hash": content_hash, "error_code": code, "recovery_suggestion": suggestion}


def _remote_video(job: dict[str, object], staging: Path) -> dict[str, object]:
    payload = job["payload"]
    try:
        import yt_dlp
        from yt_dlp.utils import DownloadError, UnsupportedError
    except ImportError as error:
        raise IngestionFailure("missing_ytdlp", "The yt-dlp Python package is not installed.", "Repair the Mastery Ledger core runtime and retry.") from error
    url = str(payload["location"])
    _validate_public_url(url)
    common: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "ignoreconfig": True,
        "noplaylist": True,
        "logger": _QuietYtdlpLogger(),
    }
    try:
        with yt_dlp.YoutubeDL({**common, "skip_download": True}) as ydl:
            raw_info = ydl.extract_info(url, download=False)
            info = ydl.sanitize_info(raw_info)
    except UnsupportedError as error:
        raise IngestionFailure("unsupported_url", "No installed yt-dlp extractor accepted this URL.", "Use a direct article/file import or update Mastery Ledger through an official release.") from error
    except DownloadError as error:
        raise IngestionFailure("video_probe_failed", "The video metadata probe failed.", "Confirm the URL is public, not DRM-protected, and permitted, then retry once.") from error
    if not isinstance(info, dict):
        raise IngestionFailure("video_probe_failed", "The video probe returned no usable metadata.", "Check the URL and retry.")
    if info.get("_type") in {"playlist", "multi_video"} or info.get("entries"):
        raise IngestionFailure("playlist_scope_required", "Playlist ingestion requires an explicit bounded scope.", "Add one video URL at a time in this preview.")
    if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
        raise IngestionFailure("live_or_upcoming", "Live or upcoming media cannot be ingested as a stable source.", "Wait for a stable recording or provide captions later.")
    media = staging / "media"
    media.mkdir(parents=True)
    atomic_json(media / "probe.json", {
        "schema_version": "media-probe-v1",
        "submitted_url": url,
        "webpage_url": info.get("webpage_url") or url,
        "extractor": info.get("extractor"),
        "extractor_key": info.get("extractor_key"),
        "remote_id": info.get("id"),
        "title": info.get("title"),
        "duration": info.get("duration"),
        "live_status": info.get("live_status"),
        "subtitle_languages": sorted(str(key) for key in (info.get("subtitles") or {})),
        "automatic_caption_languages": sorted(str(key) for key in (info.get("automatic_captions") or {})),
        "yt_dlp_version": getattr(yt_dlp.version, "__version__", "unknown"),
    }, staging)
    language = str(payload["language"])
    human_language = _select_language(info.get("subtitles"), language)
    auto_language = _select_language(info.get("automatic_captions"), language)
    selected_language = human_language or auto_language
    origin = "platform_caption" if human_language else "auto_caption"
    remote_id = str(info.get("id") or "media")
    if selected_language:
        options = {
            **common,
            "skip_download": True,
            "writesubtitles": bool(human_language),
            "writeautomaticsub": not bool(human_language),
            "subtitleslangs": [selected_language],
            "subtitlesformat": "vtt/srt/best",
            "paths": {"home": str(media)},
            "outtmpl": {"default": f"{payload['source_id']}.{remote_id}.%(ext)s"},
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.extract_info(url, download=True)
        except DownloadError as error:
            raise IngestionFailure("caption_download_failed", "Available captions could not be downloaded.", "Retry once or add an authorized SRT/VTT file directly.") from error
        captions = sorted([*media.glob("*.vtt"), *media.glob("*.srt")])
        if not captions:
            raise IngestionFailure("caption_download_failed", "yt-dlp reported captions but produced no caption file.", "Add an authorized SRT/VTT file directly.")
        _, _, segment_count = write_transcript(
            captions[0], media, source_id=str(payload["source_id"]), item_id=remote_id,
            origin=origin, language=selected_language,
        )
        status, code, suggestion = "complete", None, None
        note = f"A {origin.replace('_', ' ')} transcript with {segment_count} timestamped segments was acquired without downloading the video."
    else:
        model_path = read_setting("asr_model_path", None)
        if payload.get("allow_transcription") and isinstance(model_path, str) and Path(model_path).exists():
            options = {
                **common,
                "format": "bestaudio/best",
                "paths": {"home": str(media)},
                "outtmpl": {"default": f"{payload['source_id']}.{remote_id}.%(ext)s"},
            }
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    ydl.extract_info(url, download=True)
            except DownloadError as error:
                raise IngestionFailure("audio_download_failed", "Authorized audio acquisition failed.", "Check source availability and retry once.") from error
            candidates = [path for path in media.iterdir() if path.is_file() and path.suffix.casefold() not in {".json", ".vtt", ".srt", ".md"}]
            if not candidates:
                raise IngestionFailure("audio_download_failed", "No audio file was produced.", "Try adding captions or a local media file.")
            _, _, segment_count = write_asr_transcript(
                candidates[0], media, source_id=str(payload["source_id"]), item_id=remote_id,
                language=language, model_path=model_path,
            )
            status, code, suggestion = "complete", None, None
            note = f"Authorized audio was transcribed locally into {segment_count} timestamped segments."
        else:
            status = "needs_user_action"
            code = "captions_unavailable"
            suggestion = "Add an authorized subtitle file, or approve local transcription after configuring an ASR model."
            note = "Metadata was verified, but no matching captions were available and no authorized configured ASR path could run."
    title = str(info.get("title") or payload["title"])
    probe_hash = sha256_file(media / "probe.json")
    knowledge = _markdown_document(
        source_id=str(payload["source_id"]), title=title, source_type="remote_video",
        original_location=str(info.get("webpage_url") or url), rights_basis=str(payload["rights_basis"]),
        content_hash=probe_hash, blocks=[("p", note)],
        extra=[f"- Provider: `{info.get('extractor_key') or info.get('extractor') or 'unknown'}`", f"- Remote item ID: `{remote_id}`"],
    )
    (staging / f"{payload['source_id']}.md").write_text(knowledge, encoding="utf-8")
    return {"status": status, "title": title, "content_hash": probe_hash, "original_location": str(info.get("webpage_url") or url), "error_code": code, "recovery_suggestion": suggestion}


class IngestionWorker:
    def __init__(self, workspace_provider: Callable[[], WorkspaceState | None], *, poll_seconds: float = 0.35) -> None:
        self._workspace_provider = workspace_provider
        self._poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        recover_interrupted_jobs()
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="mastery-ledger-ingestion", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            processed = self.process_once()
            if not processed:
                self._stop.wait(self._poll_seconds)

    def process_once(self) -> bool:
        job = claim_next_job()
        if job is None:
            return False
        self._process(job)
        return True

    def _process(self, job: dict[str, object]) -> None:
        payload = job.get("payload")
        if not isinstance(payload, dict):
            update_job(str(job["job_id"]), state="failed", payload={"stage": "failed", "progress": 1.0, "error_code": "invalid_job_payload"})
            return
        workspace = self._workspace_provider()
        if workspace is None or workspace.workspace_id != payload.get("workspace_id"):
            payload.update({"stage": "needs_user_action", "progress": 1.0, "error_code": "workspace_changed", "recovery_suggestion": "Switch back to the workspace that owns this source and retry."})
            update_job(str(job["job_id"]), state="needs_user_action", payload=payload)
            return
        found = _course_by_id(Path(workspace.path), str(payload.get("course_id") or ""))
        if found is None:
            payload.update({"stage": "failed", "progress": 1.0, "error_code": "course_missing", "recovery_suggestion": "Restore the course folder before retrying."})
            update_job(str(job["job_id"]), state="failed", payload=payload)
            return
        course_root, _ = found
        source_id = str(payload["source_id"])
        staging = course_root / ".work" / "ingestion" / str(job["job_id"])
        if staging.exists() and staging.is_dir() and not staging.is_symlink():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=False)
        try:
            payload["attempt_count"] = int(payload.get("attempt_count", 0)) + 1
            _job_progress(job, "preparing", 0.08)
            update_source_record(course_root, source_id, {"processing_status": "processing", "error_code": None, "recovery_suggestion": None})
            append_event(course_root, {"action": "source.ingest.started", "actor": "application-worker", "status": "running", "summary": "Started deterministic source processing.", "artifacts": [f".work/ingestion/{job['job_id']}"], "source_id": source_id, "job_id": job["job_id"]})
            if _cancel_requested(str(job["job_id"])):
                raise IngestionFailure("cancelled", "The ingestion was cancelled.", "Queue the source again if it is still needed.")
            _job_progress(job, "extracting", 0.3)
            source_type = str(payload["source_type"])
            if source_type == "web_article":
                result = _web_article(job, staging)
            elif source_type == "remote_video":
                result = _remote_video(job, staging)
            else:
                result = _local_source(job, staging)
            if _cancel_requested(str(job["job_id"])):
                payload.update({"stage": "cancelled", "progress": 1.0, "error_code": "cancelled"})
                update_source_record(course_root, source_id, {"processing_status": "cancelled", "error_code": "cancelled"})
                update_job(str(job["job_id"]), state="cancelled", payload=payload)
                append_event(course_root, {"action": "source.ingest.cancelled", "actor": "application-worker", "status": "cancelled", "summary": "Cancelled before artifact promotion.", "artifacts": [f".work/ingestion/{job['job_id']}"], "source_id": source_id, "job_id": job["job_id"]})
                return
            _job_progress(job, "promoting", 0.86)
            knowledge_path, artifacts = _promote(staging, course_root, source_id)
            status = str(result.get("status") or "complete")
            source_status = "ready" if status == "complete" else status
            updates = {
                "title": result.get("title") or payload["title"],
                "original_location": result.get("original_location") or payload["location"],
                "processing_status": source_status,
                "retrieved_at": _timestamp_for_record(),
                "content_hash": result.get("content_hash"),
                "knowledge_path": knowledge_path,
                "local_path": f"source/media/{source_id}" if artifacts else None,
                "artifacts": artifacts,
                "error_code": result.get("error_code"),
                "recovery_suggestion": result.get("recovery_suggestion"),
            }
            update_source_record(course_root, source_id, updates)
            payload.update({"stage": status, "progress": 1.0, "error_code": result.get("error_code"), "recovery_suggestion": result.get("recovery_suggestion"), "output_manifest": "source-manifest.yaml"})
            update_job(str(job["job_id"]), state=status, payload=payload)
            append_event(course_root, {"action": f"source.ingest.{status}", "actor": "application-worker", "status": status, "summary": "Source processing finished with promoted, inspectable artifacts.", "artifacts": [knowledge_path, *[str(item["local_path"]) for item in artifacts]], "source_id": source_id, "job_id": job["job_id"]})
            shutil.rmtree(staging, ignore_errors=True)
        except IngestionFailure as error:
            state = "cancelled" if error.code == "cancelled" else "failed"
            payload.update({"stage": state, "progress": 1.0, "error_code": error.code, "recovery_suggestion": error.suggestion})
            update_job(str(job["job_id"]), state=state, payload=payload)
            update_source_record(course_root, source_id, {"processing_status": state, "error_code": error.code, "recovery_suggestion": error.suggestion})
            append_event(course_root, {"action": f"source.ingest.{state}", "actor": "application-worker", "status": state, "summary": str(error), "artifacts": [f".work/ingestion/{job['job_id']}"], "source_id": source_id, "job_id": job["job_id"], "error_code": error.code, "short_justification": error.suggestion})
        except (OSError, ValueError, SourceIntakeError, TranscriptError) as error:
            payload.update({"stage": "failed", "progress": 1.0, "error_code": "processing_failed", "recovery_suggestion": "Inspect the preserved staging folder and retry after correcting the source."})
            update_job(str(job["job_id"]), state="failed", payload=payload)
            update_source_record(course_root, source_id, {"processing_status": "failed", "error_code": "processing_failed", "recovery_suggestion": payload["recovery_suggestion"]})
            append_event(course_root, {"action": "source.ingest.failed", "actor": "application-worker", "status": "failed", "summary": f"Source processing failed: {type(error).__name__}", "artifacts": [f".work/ingestion/{job['job_id']}"], "source_id": source_id, "job_id": job["job_id"], "error_code": "processing_failed", "short_justification": "See the job recovery suggestion; raw stack traces are not written to learner artifacts."})
        except Exception as error:
            del error
            payload.update({"stage": "failed", "progress": 1.0, "error_code": "worker_error", "recovery_suggestion": "Restart Mastery Ledger. If the job fails again, inspect application diagnostics."})
            update_job(str(job["job_id"]), state="failed", payload=payload)
            try:
                update_source_record(course_root, source_id, {"processing_status": "failed", "error_code": "worker_error", "recovery_suggestion": payload["recovery_suggestion"]})
                append_event(course_root, {"action": "source.ingest.failed", "actor": "application-worker", "status": "failed", "summary": "The ingestion worker encountered an internal error.", "artifacts": [f".work/ingestion/{job['job_id']}"], "source_id": source_id, "job_id": job["job_id"], "error_code": "worker_error"})
            except Exception:
                pass


def _timestamp_for_record() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
