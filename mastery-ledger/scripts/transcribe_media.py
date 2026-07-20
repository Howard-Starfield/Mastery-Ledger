#!/usr/bin/env python3
"""Transcribe an authorized local media file with optional faster-whisper.

Existing SRT/VTT captions should be preferred. This script does not download
remote media and never handles credentials or cookies.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from normalize_subtitles import ms_to_timestamp, write_outputs


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def transcribe_with_faster_whisper(
    path: Path,
    *,
    model_name: str,
    language: str | None,
    device: str,
    compute_type: str,
) -> tuple[list[dict[str, Any]], str | None, str]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Install it in an isolated environment or provide SRT/VTT captions."
        ) from exc

    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segment_iter, info = model.transcribe(
        str(path),
        language=language,
        beam_size=5,
        vad_filter=True,
        word_timestamps=False,
    )
    segments: list[dict[str, Any]] = []
    for index, segment in enumerate(segment_iter, start=1):
        start_ms = max(0, int(round(float(segment.start) * 1000)))
        end_ms = max(start_ms + 1, int(round(float(segment.end) * 1000)))
        text = str(segment.text).strip()
        if not text:
            continue
        segments.append(
            {
                "segment_id": f"SEG-{index:04d}",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "cue_ids": [f"ASR-{index:04d}"],
                "speaker": None,
                "text": text,
                "confidence": None,
                "avg_logprob": getattr(segment, "avg_logprob", None),
                "no_speech_prob": getattr(segment, "no_speech_prob", None),
            }
        )
    detected_language = getattr(info, "language", None)
    version = importlib.metadata.version("faster-whisper")
    return segments, detected_language, version


def write_asr_outputs(
    *,
    media_path: Path,
    output_dir: Path,
    source_id: str,
    item_id: str,
    model_name: str,
    language: str | None,
    segments: list[dict[str, Any]],
    model_version: str,
) -> tuple[Path, Path]:
    cues = [
        {
            "cue_id": segment["cue_ids"][0],
            "start_ms": segment["start_ms"],
            "end_ms": segment["end_ms"],
            "text": segment["text"],
        }
        for segment in segments
    ]
    return write_outputs(
        cues=cues,
        segments=segments,
        output_dir=output_dir,
        source_id=source_id,
        item_id=item_id,
        origin="local_asr",
        source_path=str(media_path.resolve()),
        language=language,
        source_hash=sha256_file(media_path),
        transcription_model=model_name,
        model_version=model_version,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Authorized local video or audio file")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--model", default="small")
    parser.add_argument("--language", default=None)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--compute-type", default="default")
    parser.add_argument(
        "--rights-basis",
        choices=["user_owned", "platform_permitted_download", "public_license", "explicit_permission"],
        default="user_owned",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"Input media does not exist: {args.input}")

    try:
        segments, detected_language, version = transcribe_with_faster_whisper(
            args.input,
            model_name=args.model,
            language=args.language,
            device=args.device,
            compute_type=args.compute_type,
        )
    except RuntimeError as exc:
        print(json.dumps({"status": "failed", "code": "missing_asr_dependency", "message": str(exc)}))
        return 2

    if not segments:
        print(json.dumps({"status": "failed", "code": "empty_transcript", "message": "ASR produced no segments"}))
        return 3

    language = args.language or detected_language
    json_path, md_path = write_asr_outputs(
        media_path=args.input,
        output_dir=args.output_dir,
        source_id=args.source_id,
        item_id=args.item_id,
        model_name=args.model,
        language=language,
        segments=segments,
        model_version=version,
    )
    print(
        json.dumps(
            {
                "status": "complete",
                "rights_basis": args.rights_basis,
                "language": language,
                "segments": len(segments),
                "json": str(json_path),
                "markdown": str(md_path),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
