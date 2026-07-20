from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TIMESTAMP_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?[,.]\d{3})\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?[,.]\d{3})"
)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


class TranscriptError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _timestamp_to_ms(value: str) -> int:
    parts = value.strip().replace(",", ".").split(":")
    if len(parts) == 2:
        hours, minutes, seconds = "0", *parts
    elif len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        raise TranscriptError(f"Unsupported caption timestamp: {value}")
    second, millis = seconds.split(".", 1)
    return ((int(hours) * 60 + int(minutes)) * 60 + int(second)) * 1000 + int(
        (millis + "000")[:3]
    )


def _format_timestamp(value: int) -> str:
    hours, remainder = divmod(value, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def _clean(value: str) -> str:
    return SPACE_RE.sub(" ", html.unescape(TAG_RE.sub("", value))).strip()


def parse_captions(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    content = ""
    for encoding in ("utf-8-sig", "utf-8", "utf-16"):
        try:
            content = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if not content:
        content = raw.decode("utf-8", errors="replace")
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    content = re.sub(r"^WEBVTT[^\n]*\n", "", content.lstrip("\ufeff"))
    content = re.sub(r"(?ms)^NOTE(?:\s[^\n]*)?\n.*?(?:\n\n|\Z)", "", content)
    cues: list[dict[str, Any]] = []
    for index, block in enumerate(re.split(r"\n{2,}", content.strip()), start=1):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timestamp_index = next((position for position, line in enumerate(lines) if "-->" in line), None)
        if timestamp_index is None:
            continue
        match = TIMESTAMP_RE.search(lines[timestamp_index])
        if match is None:
            continue
        start_ms = _timestamp_to_ms(match.group("start"))
        end_ms = _timestamp_to_ms(match.group("end"))
        text = _clean(" ".join(lines[timestamp_index + 1 :]))
        if text and end_ms > start_ms >= 0:
            cues.append(
                {
                    "cue_id": lines[0] if timestamp_index else str(index),
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "text": text,
                }
            )
    cues.sort(key=lambda item: (item["start_ms"], item["end_ms"]))
    if not cues:
        raise TranscriptError("No valid caption cues were found.")
    return cues


def _segments(cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for index, cue in enumerate(cues, start=1):
        segments.append(
            {
                "segment_id": f"SEG-{index:04d}",
                "start_ms": cue["start_ms"],
                "end_ms": cue["end_ms"],
                "cue_ids": [cue["cue_id"]],
                "speaker": None,
                "text": cue["text"],
                "confidence": None,
            }
        )
    return segments


def write_transcript(
    caption_path: Path,
    output_dir: Path,
    *,
    source_id: str,
    item_id: str,
    origin: str,
    language: str,
) -> tuple[Path, Path, int]:
    cues = parse_captions(caption_path)
    segments = _segments(cues)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "transcript-v1",
        "source_id": source_id,
        "item_id": item_id,
        "origin": origin,
        "language": language,
        "source_path": caption_path.name,
        "source_hash": sha256_file(caption_path),
        "transcription_model": None,
        "model_version": None,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "raw_cues": cues,
        "segments": segments,
    }
    json_path = output_dir / "transcript.json"
    markdown_path = output_dir / "transcript.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown: list[str] = [
        f"# Transcript: {item_id}",
        "",
        f"- Source: `{source_id}`",
        f"- Origin: `{origin}`",
        f"- Language: `{language}`",
        "",
    ]
    for segment in segments:
        markdown.extend(
            [
                f"## {segment['segment_id']} · {_format_timestamp(segment['start_ms'])}–{_format_timestamp(segment['end_ms'])}",
                "",
                segment["text"],
                "",
            ]
        )
    markdown_path.write_text("\n".join(markdown).rstrip() + "\n", encoding="utf-8")
    return json_path, markdown_path, len(segments)


def write_asr_transcript(
    media_path: Path,
    output_dir: Path,
    *,
    source_id: str,
    item_id: str,
    language: str,
    model_path: str,
) -> tuple[Path, Path, int]:
    try:
        from faster_whisper import WhisperModel, __version__ as faster_whisper_version
    except ImportError as error:
        raise TranscriptError("Local transcription support is not installed.") from error
    model = WhisperModel(model_path, device="cpu", compute_type="int8")
    segment_iter, info = model.transcribe(str(media_path), language=language or None, vad_filter=True)
    segments: list[dict[str, Any]] = []
    for index, segment in enumerate(segment_iter, start=1):
        text = _clean(segment.text)
        start_ms = max(0, int(segment.start * 1000))
        end_ms = max(start_ms + 1, int(segment.end * 1000))
        if not text:
            continue
        segments.append(
            {
                "segment_id": f"SEG-{index:04d}",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "cue_ids": [],
                "speaker": None,
                "text": text,
                "confidence": None,
            }
        )
    if not segments:
        raise TranscriptError("Local transcription produced no readable segments.")
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "transcript-v1",
        "source_id": source_id,
        "item_id": item_id,
        "origin": "local_asr",
        "language": getattr(info, "language", None) or language,
        "source_path": media_path.name,
        "source_hash": sha256_file(media_path),
        "transcription_model": Path(model_path).name,
        "model_version": faster_whisper_version,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "raw_cues": [],
        "segments": segments,
    }
    json_path = output_dir / "transcript.json"
    markdown_path = output_dir / "transcript.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown: list[str] = [
        f"# Transcript: {item_id}",
        "",
        f"- Source: `{source_id}`",
        "- Origin: `local_asr`",
        f"- Model: `{Path(model_path).name}`",
        "",
    ]
    for segment in segments:
        markdown.extend(
            [
                f"## {segment['segment_id']} · {_format_timestamp(segment['start_ms'])}–{_format_timestamp(segment['end_ms'])}",
                "",
                segment["text"],
                "",
            ]
        )
    markdown_path.write_text("\n".join(markdown).rstrip() + "\n", encoding="utf-8")
    return json_path, markdown_path, len(segments)
