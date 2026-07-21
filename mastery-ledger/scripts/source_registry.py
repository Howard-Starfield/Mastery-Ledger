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

from course_paths import SOURCE, SOURCE_MANIFEST, relative_text


READABLE_SOURCE_ARTIFACT_KINDS = {
    "caption",
    "subtitle",
    "text",
    "transcript_json",
    "transcript_markdown",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def load_manifest(root: Path) -> dict[str, Any]:
    path = root / SOURCE_MANIFEST
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ValueError(f"Cannot read {relative_text(SOURCE_MANIFEST)}: {error}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise ValueError(f"{relative_text(SOURCE_MANIFEST)} must contain a sources list")
    return payload


def safe_knowledge_path(root: Path, relative: object) -> Path | None:
    source_prefix = relative_text(SOURCE) + "/"
    if not isinstance(relative, str) or not relative.startswith(source_prefix) or not relative.endswith(".md"):
        return None
    candidate = (root / relative).resolve(strict=False)
    try:
        candidate.relative_to((root / SOURCE).resolve())
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


def safe_source_artifact_path(root: Path, source_id: str, relative: object) -> Path | None:
    """Resolve one durable per-source media artifact without leaving its bundle."""
    prefix = f"{relative_text(SOURCE)}/media/{source_id}/"
    if not isinstance(relative, str) or not relative.startswith(prefix):
        return None
    bundle = (root / SOURCE / "media" / source_id).resolve(strict=False)
    candidate = (root / relative).resolve(strict=False)
    try:
        candidate.relative_to(bundle)
    except (OSError, ValueError):
        return None
    if not candidate.is_file() or candidate.is_symlink() or candidate.stat().st_size <= 0:
        return None
    return candidate


def readable_source_artifacts(source: dict[str, Any]) -> list[str]:
    """Return textual evidence artifacts that workers may read in addition to knowledge Markdown."""
    result: list[str] = []
    for artifact in source.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        kind = str(artifact.get("kind") or "")
        path = artifact.get("path")
        if kind in READABLE_SOURCE_ARTIFACT_KINDS and isinstance(path, str):
            result.append(path)
    return result


def source_errors(root: Path, manifest: dict[str, Any], *, require_nonempty: bool = True) -> list[str]:
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        return [f"{relative_text(SOURCE_MANIFEST)} must contain a sources list"]
    if require_nonempty and not sources:
        return [f"No source candidates are recorded in {relative_text(SOURCE_MANIFEST)}."]
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
        artifacts = source.get("artifacts", [])
        if not isinstance(artifacts, list):
            errors.append(f"{source_id or f'sources[{index}]'} artifacts must be a list")
            continue
        seen_artifacts: set[str] = set()
        for artifact_index, artifact in enumerate(artifacts):
            artifact_prefix = f"{source_id or f'sources[{index}]'} artifacts[{artifact_index}]"
            if not isinstance(artifact, dict):
                errors.append(f"{artifact_prefix} is not an object")
                continue
            kind = str(artifact.get("kind") or "").strip()
            path = artifact.get("path")
            if not kind or not isinstance(path, str) or not path:
                errors.append(f"{artifact_prefix} requires kind and path")
                continue
            if path in seen_artifacts:
                errors.append(f"{source_id or f'sources[{index}]'} has duplicate artifact path: {path}")
                continue
            seen_artifacts.add(path)
            if kind == "extracted_knowledge":
                if path != source.get("knowledge_path"):
                    errors.append(f"{artifact_prefix} must match knowledge_path")
                candidate = knowledge
            else:
                candidate = safe_source_artifact_path(root, source_id, path)
                if candidate is None:
                    errors.append(f"{artifact_prefix} is missing or outside the durable source bundle")
            artifact_digest = artifact.get("content_hash")
            if artifact_digest is not None:
                if re.fullmatch(r"sha256:[0-9a-fA-F]{64}", str(artifact_digest)) is None:
                    errors.append(f"{artifact_prefix} has an invalid content_hash")
                elif candidate is not None and str(artifact_digest).casefold() != sha256_file(candidate).casefold():
                    errors.append(f"{artifact_prefix} content_hash does not match its file")
    return errors


def atomic_manifest(root: Path, payload: dict[str, Any]) -> Path:
    path = root / SOURCE_MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
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
