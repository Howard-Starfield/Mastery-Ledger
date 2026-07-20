#!/usr/bin/env python3
"""Normalize SRT/VTT captions while preserving citation locators.

Outputs a JSON transcript with raw cues and normalized segments plus a readable
Markdown transcript. The standard library is sufficient.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

TIMESTAMP_RE = re.compile(r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?[,.]\d{3})\s*-->\s*(?P<end>\d{1,2}:\d{2}(?::\d{2})?[,.]\d{3})")
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def timestamp_to_ms(value: str) -> int:
    value = value.strip().replace(",", ".")
    parts = value.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours = "0"
        minutes, seconds = parts
    else:
        raise ValueError(f"Unsupported timestamp: {value}")
    sec, millis = seconds.split(".", 1)
    millis = (millis + "000")[:3]
    return ((int(hours) * 60 + int(minutes)) * 60 + int(sec)) * 1000 + int(millis)


def ms_to_timestamp(value: int) -> str:
    if value < 0:
        raise ValueError("Timestamp cannot be negative")
    hours, remainder = divmod(value, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def clean_text(value: str) -> str:
    value = html.unescape(TAG_RE.sub("", value))
    value = value.replace("\u200b", "").replace("\ufeff", "")
    return SPACE_RE.sub(" ", value).strip()


def _parse_blocks(content: str, *, vtt: bool) -> list[dict[str, Any]]:
    content = content.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    if vtt:
        content = re.sub(r"^WEBVTT[^\n]*\n", "", content)
        content = re.sub(r"(?ms)^NOTE(?:\s[^\n]*)?\n.*?(?:\n\n|\Z)", "", content)
        content = re.sub(r"(?ms)^STYLE\n.*?(?:\n\n|\Z)", "", content)
        content = re.sub(r"(?ms)^REGION\n.*?(?:\n\n|\Z)", "", content)

    cues: list[dict[str, Any]] = []
    blocks = re.split(r"\n{2,}", content.strip())
    auto_id = 1
    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        timestamp_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timestamp_index is None:
            continue
        match = TIMESTAMP_RE.search(lines[timestamp_index])
        if not match:
            continue
        cue_id = lines[0] if timestamp_index > 0 else str(auto_id)
        text = clean_text(" ".join(lines[timestamp_index + 1 :]))
        if not text:
            continue
        start_ms = timestamp_to_ms(match.group("start"))
        end_ms = timestamp_to_ms(match.group("end"))
        if start_ms < 0 or end_ms <= start_ms:
            continue
        cues.append(
            {
                "cue_id": str(cue_id),
                "start_ms": start_ms,
                "end_ms": end_ms,
                "text": text,
            }
        )
        auto_id += 1
    return sorted(cues, key=lambda item: (item["start_ms"], item["end_ms"], item["cue_id"]))


def parse_srt(content: str) -> list[dict[str, Any]]:
    return _parse_blocks(content, vtt=False)


def parse_vtt(content: str) -> list[dict[str, Any]]:
    return _parse_blocks(content, vtt=True)


def _merge_word_overlap(previous: str, current: str) -> str:
    previous = clean_text(previous)
    current = clean_text(current)
    if not previous:
        return current
    if not current:
        return previous

    prev_fold = previous.casefold()
    curr_fold = current.casefold()
    if curr_fold.startswith(prev_fold):
        return current
    if prev_fold.startswith(curr_fold):
        return previous

    prev_words = previous.split()
    curr_words = current.split()
    max_overlap = min(len(prev_words), len(curr_words), 20)
    for size in range(max_overlap, 0, -1):
        if [word.casefold() for word in prev_words[-size:]] == [word.casefold() for word in curr_words[:size]]:
            return " ".join(prev_words + curr_words[size:])

    max_chars = min(len(previous), len(current), 120)
    for size in range(max_chars, 5, -1):
        if prev_fold[-size:] == curr_fold[:size]:
            return previous + current[size:]

    return f"{previous} {current}".strip()


def build_segments(
    cues: Iterable[dict[str, Any]],
    *,
    max_segment_ms: int = 30_000,
    max_gap_ms: int = 1_500,
) -> list[dict[str, Any]]:
    ordered = sorted(cues, key=lambda item: (item["start_ms"], item["end_ms"]))
    if not ordered:
        return []

    segments: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for cue in ordered:
        if current is None:
            current = {
                "start_ms": cue["start_ms"],
                "end_ms": cue["end_ms"],
                "cue_ids": [cue["cue_id"]],
                "speaker": None,
                "text": cue["text"],
                "confidence": None,
            }
            continue

        gap = cue["start_ms"] - current["end_ms"]
        proposed_end = max(current["end_ms"], cue["end_ms"])
        proposed_duration = proposed_end - current["start_ms"]
        can_merge = gap <= max_gap_ms and proposed_duration <= max_segment_ms

        if can_merge:
            current["end_ms"] = proposed_end
            current["cue_ids"].append(cue["cue_id"])
            current["text"] = _merge_word_overlap(current["text"], cue["text"])
        else:
            segments.append(current)
            current = {
                "start_ms": cue["start_ms"],
                "end_ms": cue["end_ms"],
                "cue_ids": [cue["cue_id"]],
                "speaker": None,
                "text": cue["text"],
                "confidence": None,
            }

    if current is not None:
        segments.append(current)

    for index, segment in enumerate(segments, start=1):
        segment["segment_id"] = f"SEG-{index:04d}"
    return segments


def write_outputs(
    *,
    cues: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    output_dir: Path,
    source_id: str,
    item_id: str,
    origin: str,
    source_path: str,
    language: str | None = None,
    source_hash: str | None = None,
    transcription_model: str | None = None,
    model_version: str | None = None,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "source_id": source_id,
        "item_id": item_id,
        "origin": origin,
        "language": language,
        "source_path": source_path,
        "source_hash": source_hash,
        "transcription_model": transcription_model,
        "model_version": model_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "raw_cues": cues,
        "segments": segments,
    }

    json_path = output_dir / "transcript.json"
    md_path = output_dir / "transcript.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    markdown = [
        f"# Transcript: {item_id}",
        "",
        f"- Source: `{source_id}`",
        f"- Origin: `{origin}`",
        f"- Original: `{source_path}`",
        "",
    ]
    for segment in segments:
        start = ms_to_timestamp(segment["start_ms"])
        end = ms_to_timestamp(segment["end_ms"])
        markdown.extend(
            [
                f"## {segment['segment_id']} · {start}–{end}",
                "",
                segment["text"],
                "",
                f"Cue IDs: {', '.join(segment['cue_ids'])}",
                "",
            ]
        )
    md_path.write_text("\n".join(markdown).rstrip() + "\n", encoding="utf-8")
    return json_path, md_path


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "utf-16"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="SRT or VTT file")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--item-id", required=True)
    parser.add_argument(
        "--origin",
        choices=["human_caption", "platform_caption", "auto_caption", "user_transcript"],
        default="user_transcript",
    )
    parser.add_argument("--language")
    parser.add_argument("--max-segment-seconds", type=float, default=30.0)
    parser.add_argument("--max-gap-seconds", type=float, default=1.5)
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"Input file does not exist: {args.input}")
    content = read_text(args.input)
    is_vtt = args.input.suffix.lower() == ".vtt" or content.lstrip().startswith("WEBVTT")
    cues = parse_vtt(content) if is_vtt else parse_srt(content)
    if not cues:
        parser.error("No valid subtitle cues were found")
    segments = build_segments(
        cues,
        max_segment_ms=max(1, int(args.max_segment_seconds * 1000)),
        max_gap_ms=max(0, int(args.max_gap_seconds * 1000)),
    )
    json_path, md_path = write_outputs(
        cues=cues,
        segments=segments,
        output_dir=args.output_dir,
        source_id=args.source_id,
        item_id=args.item_id,
        origin=args.origin,
        source_path=str(args.input.resolve()),
        language=args.language,
        source_hash=sha256_file(args.input),
    )
    print(json.dumps({"status": "complete", "json": str(json_path), "markdown": str(md_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
