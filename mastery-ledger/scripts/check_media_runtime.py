#!/usr/bin/env python3
"""Report media capabilities from the active application or fallback Python runtime."""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _package(name: str, import_name: str) -> dict[str, Any]:
    spec = importlib.util.find_spec(import_name)
    if spec is None:
        return {"status": "not_installed", "version": None, "module_path": None}
    try:
        version = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    return {
        "status": "ready",
        "version": version,
        "module_path": str(Path(spec.origin).resolve()) if spec.origin else None,
    }


def _resolve_tool(name: str, location: Path | None) -> str | None:
    if location is None:
        return shutil.which(name)
    candidate = location.resolve(strict=False)
    if candidate.is_dir():
        for filename in (name, f"{name}.exe"):
            tool = candidate / filename
            if tool.is_file():
                return str(tool)
        return None
    if candidate.is_file():
        if candidate.stem.casefold() == name.casefold():
            return str(candidate)
        for filename in (name, f"{name}.exe"):
            sibling = candidate.parent / filename
            if sibling.is_file():
                return str(sibling)
    return None


def _native_tool(name: str, location: Path | None) -> dict[str, Any]:
    executable = _resolve_tool(name, location)
    if executable is None:
        return {"status": "unavailable", "path": None, "version_line": None}
    try:
        completed = subprocess.run(
            [executable, "-version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        line = (completed.stdout or completed.stderr).splitlines()[0].strip()
    except (OSError, subprocess.SubprocessError, IndexError):
        return {"status": "unavailable", "path": executable, "version_line": None}
    return {"status": "ready", "path": executable, "version_line": line}


def inspect_runtime(ffmpeg_location: Path | None = None) -> dict[str, Any]:
    yt_dlp = _package("yt-dlp", "yt_dlp")
    faster_whisper = _package("faster-whisper", "faster_whisper")
    ffmpeg = _native_tool("ffmpeg", ffmpeg_location)
    ffprobe = _native_tool("ffprobe", ffmpeg_location)
    yt_ready = yt_dlp["status"] == "ready"
    merge_ready = yt_ready and ffmpeg["status"] == "ready" and ffprobe["status"] == "ready"
    return {
        "schema_version": "media-runtime-v1",
        "status": "ready" if yt_ready else "degraded",
        "python": {"executable": sys.executable, "version": sys.version.split()[0]},
        "packages": {"yt_dlp": yt_dlp, "faster_whisper": faster_whisper},
        "native_tools": {"ffmpeg": ffmpeg, "ffprobe": ffprobe},
        "capabilities": {
            "metadata_probe": yt_ready,
            "caption_acquisition": yt_ready,
            "single_stream_audio_acquisition": yt_ready,
            "separate_stream_merge": merge_ready,
            "local_asr": faster_whisper["status"] == "ready",
        },
        "ownership": {
            "yt_dlp": "Mastery Ledger release-locked Python environment when invoked by the app; otherwise the reported active Python fallback",
            "ffmpeg": "optional audited native media-export profile or explicit existing path",
            "updates": "application installer or explicit application update; never an individual skill run",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ffmpeg-location",
        type=Path,
        help="Existing ffmpeg executable or directory containing ffmpeg and ffprobe",
    )
    args = parser.parse_args()
    print(json.dumps(inspect_runtime(args.ffmpeg_location), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
