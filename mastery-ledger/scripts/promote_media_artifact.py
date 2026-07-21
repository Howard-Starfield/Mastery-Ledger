#!/usr/bin/env python3
"""Copy one verified staged media artifact into a durable per-source bundle."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from course_paths import SOURCE, relative_text
from source_registry import sha256_file


def promote(root: Path, source_id: str, source: Path, filename: str) -> tuple[Path, bool]:
    root = root.resolve()
    source = source.resolve()
    if not source.is_file() or source.is_symlink() or source.stat().st_size <= 0:
        raise ValueError("--input must identify a non-empty regular file")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", source_id) is None:
        raise ValueError("--source-id must be a filesystem-safe identifier of at most 64 characters")
    if Path(filename).name != filename or filename in {".", ".."}:
        raise ValueError("--filename must be one safe file name without directories")

    bundle = root / SOURCE / "media" / source_id
    bundle.mkdir(parents=True, exist_ok=True)
    if bundle.is_symlink():
        raise ValueError("Durable media bundle cannot be a symbolic link")
    destination = bundle / filename
    source_hash = sha256_file(source)
    if destination.exists():
        if destination.is_file() and not destination.is_symlink() and sha256_file(destination) == source_hash:
            return destination, True
        raise ValueError(f"Destination already exists with different content: {destination}")

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{filename}.", suffix=".tmp", dir=bundle)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output, source.open("rb") as input_handle:
            shutil.copyfileobj(input_handle, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination, False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--filename", required=True)
    parser.add_argument("--kind", required=True)
    args = parser.parse_args()
    try:
        destination, idempotent = promote(
            args.course_root,
            args.source_id.strip(),
            args.input,
            args.filename.strip(),
        )
    except ValueError as error:
        parser.error(str(error))
    relative = destination.relative_to(args.course_root.resolve()).as_posix()
    print(json.dumps({
        "status": "complete",
        "idempotent": idempotent,
        "path": relative,
        "content_hash": sha256_file(destination),
        "artifact_argument": f"{args.kind.strip()}={relative}",
        "source_root": relative_text(SOURCE),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
