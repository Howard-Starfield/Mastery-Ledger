#!/usr/bin/env python3
"""Shared validation and atomic persistence for course source manifests."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def load_manifest(root: Path) -> dict[str, Any]:
    path = root / "source-manifest.yaml"
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ValueError(f"Cannot read source-manifest.yaml: {error}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise ValueError("source-manifest.yaml must contain a sources list")
    return payload


def safe_knowledge_path(root: Path, relative: object) -> Path | None:
    if not isinstance(relative, str) or not relative.startswith("source/") or not relative.endswith(".md"):
        return None
    candidate = (root / relative).resolve(strict=False)
    try:
        candidate.relative_to((root / "source").resolve())
    except (OSError, ValueError):
        return None
    if not candidate.is_file() or candidate.is_symlink():
        return None
    try:
        if len(candidate.read_text(encoding="utf-8").strip()) < 20:
            return None
    except (OSError, UnicodeError):
        return None
    return candidate


def source_errors(root: Path, manifest: dict[str, Any], *, require_nonempty: bool = True) -> list[str]:
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        return ["source-manifest.yaml must contain a sources list"]
    if require_nonempty and not sources:
        return ["No source candidates are recorded in source-manifest.yaml."]
    errors: list[str] = []
    seen: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            errors.append(f"sources[{index}] is not an object")
            continue
        source_id = str(source.get("source_id") or "").strip()
        if not source_id:
            errors.append(f"sources[{index}] has no source_id")
        elif re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", source_id) is None:
            errors.append(f"Invalid filesystem-safe source_id: {source_id}")
        elif source_id in seen:
            errors.append(f"Duplicate source_id: {source_id}")
        seen.add(source_id)
        if source.get("processing_status") != "ready":
            errors.append(f"{source_id or f'sources[{index}]'} is not ready")
        knowledge = safe_knowledge_path(root, source.get("knowledge_path"))
        if knowledge is None:
            errors.append(f"{source_id or f'sources[{index}]'} has no safe non-empty knowledge Markdown")
        digest = str(source.get("content_hash") or "")
        if re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest) is None:
            errors.append(f"{source_id or f'sources[{index}]'} has no real sha256 content hash")
        elif knowledge is not None and digest.casefold() != sha256_file(knowledge).casefold():
            errors.append(f"{source_id or f'sources[{index}]'} content hash does not match its knowledge Markdown")
    return errors


def atomic_manifest(root: Path, payload: dict[str, Any]) -> Path:
    path = root / "source-manifest.yaml"
    descriptor, name = tempfile.mkstemp(prefix=".source-manifest.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path
