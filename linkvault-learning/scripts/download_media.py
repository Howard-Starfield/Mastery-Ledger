#!/usr/bin/env python3
"""Rights-aware wrapper around yt-dlp for permitted media acquisition.

The script refuses unknown rights, does not accept cookies or credentials, and
writes a manifest of produced files. Prefer an audited LinkVault backend when
one is available.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ALLOWED_RIGHTS = {
    "user_owned",
    "platform_permitted_download",
    "public_license",
    "explicit_permission",
}
MIN_SAFE_YTDLP = (2024, 7, 1)


def version_tuple(value: str) -> tuple[int, int, int]:
    match = re.search(r"(\d{4})[.-](\d{1,2})[.-](\d{1,2})", value)
    if not match:
        raise ValueError(f"Unrecognized yt-dlp version: {value!r}")
    return tuple(int(part) for part in match.groups())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def build_command(
    *,
    executable: str,
    url: str,
    output_dir: Path,
    mode: str,
    languages: str,
    playlist: bool,
) -> list[str]:
    output_template = "%(playlist_index)03d - %(title).180B [%(id)s].%(ext)s"
    command = [
        executable,
        "--no-overwrites",
        "--write-info-json",
        "--paths",
        str(output_dir),
        "--output",
        output_template,
    ]
    command.append("--yes-playlist" if playlist else "--no-playlist")

    if mode == "subtitles":
        command.extend(
            [
                "--skip-download",
                "--write-subs",
                "--write-auto-subs",
                "--sub-langs",
                languages,
                "--sub-format",
                "srt/vtt/best",
            ]
        )
    elif mode == "audio":
        command.extend(["--format", "bestaudio/best", "--extract-audio", "--audio-format", "m4a"])
    elif mode == "video":
        command.extend(["--format", "bv*+ba/b", "--merge-output-format", "mp4"])
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    command.append(url)
    return command


def collect_files(output_dir: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name == "download-job.json":
            continue
        files.append(
            {
                "path": str(path.relative_to(output_dir)),
                "size_bytes": path.stat().st_size,
                "content_hash": sha256_file(path),
            }
        )
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--rights-basis", required=True)
    parser.add_argument("--mode", choices=["subtitles", "audio", "video"], default="subtitles")
    parser.add_argument("--languages", default="en.*,zh.*")
    parser.add_argument("--playlist", action="store_true")
    args = parser.parse_args()

    if args.rights_basis not in ALLOWED_RIGHTS:
        parser.error(
            "Remote media requires --rights-basis user_owned, platform_permitted_download, public_license, or explicit_permission"
        )
    if not args.url.startswith(("https://", "http://")):
        parser.error("URL must use http or https")

    executable = shutil.which("yt-dlp")
    if executable is None:
        print(json.dumps({"status": "failed", "code": "missing_ytdlp", "message": "yt-dlp is not installed"}))
        return 2

    version_result = subprocess.run([executable, "--version"], capture_output=True, text=True, check=False)
    if version_result.returncode != 0:
        print(json.dumps({"status": "failed", "code": "ytdlp_version_failed", "message": version_result.stderr.strip()}))
        return 2
    try:
        installed_version = version_tuple(version_result.stdout.strip())
    except ValueError as exc:
        print(json.dumps({"status": "failed", "code": "unknown_ytdlp_version", "message": str(exc)}))
        return 2
    if installed_version < MIN_SAFE_YTDLP:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "code": "unsafe_ytdlp_version",
                    "message": "Update yt-dlp to version 2024.07.01 or newer before downloading subtitles or media.",
                }
            )
        )
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    command = build_command(
        executable=executable,
        url=args.url,
        output_dir=args.output_dir,
        mode=args.mode,
        languages=args.languages,
        playlist=args.playlist,
    )
    started_at = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    files = collect_files(args.output_dir)
    manifest = {
        "schema_version": "1.0",
        "kind": "media_download",
        "state": "complete" if result.returncode == 0 else "failed",
        "rights_basis": args.rights_basis,
        "mode": args.mode,
        "url": args.url,
        "yt_dlp_version": version_result.stdout.strip(),
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "return_code": result.returncode,
        "files": files,
        "stderr_tail": result.stderr[-4000:],
    }
    manifest_path = args.output_dir / "download-job.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["state"], "manifest": str(manifest_path), "files": len(files)}))
    return 0 if result.returncode == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
