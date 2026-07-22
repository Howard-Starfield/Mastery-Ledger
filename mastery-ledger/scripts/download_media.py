#!/usr/bin/env python3
"""Acquire permitted captions or media through the yt-dlp Python API.

This helper never reads a user's global yt-dlp configuration, never accepts
cookies or credentials, and defaults to one remote item. Metadata-only probing
needs no rights declaration; the caller must confirm authorization before any
caption, audio, or video file is saved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ALLOWED_RIGHTS = {
    "user_owned",
    "platform_permitted_download",
    "public_license",
    "explicit_permission",
    "user_attested_authorized_use",
}
MODES = {"probe", "human_subtitles", "automatic_subtitles", "audio", "video"}


def resolve_rights_basis(mode: str, rights_basis: str | None) -> str:
    """Keep metadata probing separate from authorized media acquisition."""
    if mode == "probe":
        return "not_applicable_metadata_probe"
    if rights_basis not in ALLOWED_RIGHTS:
        raise ValueError("remote caption, audio, or video acquisition requires learner-confirmed authorization")
    return rights_basis


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def validate_source_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", value):
        raise ValueError("source ID must be 1-80 safe filename characters")
    return value


def build_options(
    *, output_dir: Path, source_id: str, mode: str, languages: list[str], playlist: bool,
    ffmpeg_location: Path | None = None,
) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"Unsupported mode: {mode}")
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "ignoreconfig": True,
        "noplaylist": not playlist,
        "paths": {"home": str(output_dir)},
        "outtmpl": {"default": f"{source_id}.%(id)s.%(ext)s"},
        "overwrites": False,
        "writeinfojson": mode != "probe",
    }
    if ffmpeg_location is not None:
        options["ffmpeg_location"] = str(ffmpeg_location.resolve(strict=False))
    if mode == "probe":
        options["skip_download"] = True
    elif mode == "human_subtitles":
        options.update(
            skip_download=True,
            writesubtitles=True,
            writeautomaticsub=False,
            subtitleslangs=languages,
            subtitlesformat="vtt/srt/best",
        )
    elif mode == "automatic_subtitles":
        options.update(
            skip_download=True,
            writesubtitles=False,
            writeautomaticsub=True,
            subtitleslangs=languages,
            subtitlesformat="vtt/srt/best",
        )
    elif mode == "audio":
        options["format"] = "bestaudio/best"
    else:
        options.update(format="bv*+ba/b", merge_output_format="mp4")
    return options


def collect_files(output_dir: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name == "download-job.json":
            continue
        files.append(
            {
                "path": str(path.relative_to(output_dir)).replace("\\", "/"),
                "size_bytes": path.stat().st_size,
                "content_hash": sha256_file(path),
            }
        )
    return files


def probe_record(info: dict[str, Any], *, submitted_url: str, version: str) -> dict[str, Any]:
    return {
        "schema_version": "media-probe-v1",
        "submitted_url": submitted_url,
        "webpage_url": info.get("webpage_url") or submitted_url,
        "extractor": info.get("extractor"),
        "extractor_key": info.get("extractor_key"),
        "remote_id": info.get("id"),
        "title": info.get("title"),
        "duration": info.get("duration"),
        "live_status": info.get("live_status"),
        "subtitle_languages": sorted(str(key) for key in (info.get("subtitles") or {})),
        "automatic_caption_languages": sorted(
            str(key) for key in (info.get("automatic_captions") or {})
        ),
        "yt_dlp_version": version,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--rights-basis", choices=sorted(ALLOWED_RIGHTS))
    parser.add_argument("--mode", choices=sorted(MODES), default="probe")
    parser.add_argument("--languages", default="en.*,en")
    parser.add_argument("--playlist", action="store_true")
    parser.add_argument(
        "--ffmpeg-location",
        type=Path,
        help="Existing ffmpeg executable or directory; the skill never downloads it",
    )
    args = parser.parse_args(argv)

    try:
        rights_basis = resolve_rights_basis(args.mode, args.rights_basis)
    except ValueError as error:
        parser.error(str(error))
    if not args.url.startswith(("https://", "http://")):
        parser.error("URL must use http or https")
    try:
        source_id = validate_source_id(args.source_id)
    except ValueError as error:
        parser.error(str(error))

    if args.ffmpeg_location is not None and not args.ffmpeg_location.exists():
        parser.error("--ffmpeg-location must name an existing executable or directory")
    if args.mode == "video" and args.ffmpeg_location is None and not shutil.which("ffmpeg"):
        print(json.dumps({
            "status": "failed",
            "code": "missing_ffmpeg_for_video_merge",
            "message": "Video mode may require native FFmpeg to merge separate streams. Use an existing audited FFmpeg path; the skill will not download it.",
        }))
        return 2

    try:
        import yt_dlp
        from yt_dlp.utils import DownloadError, UnsupportedError
    except ImportError:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "code": "missing_ytdlp",
                    "message": "Install the optional Mastery Ledger media dependencies in the Python environment running this helper; no standalone executable is used.",
                }
            )
        )
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    options = build_options(
        output_dir=args.output_dir,
        source_id=source_id,
        mode=args.mode,
        languages=[item.strip() for item in args.languages.split(",") if item.strip()],
        playlist=args.playlist,
        ffmpeg_location=args.ffmpeg_location,
    )
    state = "failed"
    error_code: str | None = None
    message: str | None = None
    info: dict[str, Any] = {}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            raw_info = ydl.extract_info(args.url, download=args.mode != "probe")
            sanitized = ydl.sanitize_info(raw_info)
        if not isinstance(sanitized, dict):
            raise RuntimeError("yt-dlp returned no usable metadata")
        info = sanitized
        if not args.playlist and (info.get("entries") or info.get("_type") in {"playlist", "multi_video"}):
            raise RuntimeError("playlist scope requires --playlist")
        if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
            raise RuntimeError("live or upcoming media is not a stable source")
        state = "complete"
    except UnsupportedError:
        error_code, message = "unsupported_url", "No installed yt-dlp extractor accepted this URL."
    except DownloadError:
        error_code, message = "acquisition_failed", "yt-dlp could not acquire the requested public item."
    except RuntimeError as error:
        error_code, message = "unstable_or_unbounded_source", str(error)

    version = getattr(yt_dlp.version, "__version__", "unknown")
    probe = probe_record(info, submitted_url=args.url, version=version)
    probe_path = args.output_dir / "probe.json"
    probe_path.write_text(json.dumps(probe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "media-download-v2",
        "kind": "media_probe" if args.mode == "probe" else "media_acquisition",
        "state": state,
        "source_id": source_id,
        "rights_basis": rights_basis,
        "mode": args.mode,
        "url": args.url,
        "yt_dlp_version": version,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "files": collect_files(args.output_dir),
        "error_code": error_code,
        "message": message,
    }
    manifest_path = args.output_dir / "download-job.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": state,
                "manifest": str(manifest_path),
                "files": len(manifest["files"]),
                "error_code": error_code,
            }
        )
    )
    return 0 if state == "complete" else 3


if __name__ == "__main__":
    raise SystemExit(main())
