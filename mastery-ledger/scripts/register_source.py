#!/usr/bin/env python3
"""Atomically register one extracted, course-local source."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from course_paths import SOURCE_MANIFEST, relative_text
from record_action import append_event
from source_registry import (
    atomic_manifest,
    load_manifest,
    safe_knowledge_path,
    safe_source_artifact_path,
    sha256_file,
    source_errors,
)


def parse_artifacts(root: Path, source_id: str, values: list[str]) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in values:
        if "=" not in value:
            raise ValueError("--artifact must use KIND=COURSE_RELATIVE_PATH")
        kind, relative = (item.strip() for item in value.split("=", 1))
        relative = relative.replace("\\", "/")
        if not kind or kind == "extracted_knowledge":
            raise ValueError("--artifact kind must be non-empty and cannot be extracted_knowledge")
        path = safe_source_artifact_path(root, source_id, relative)
        if path is None:
            raise ValueError(
                f"Artifact must be a non-empty regular file under records/source/media/{source_id}: {relative}"
            )
        if relative in seen:
            raise ValueError(f"Duplicate --artifact path: {relative}")
        seen.add(relative)
        artifacts.append({"kind": kind, "path": relative, "content_hash": sha256_file(path)})
    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument("--knowledge-path", required=True)
    parser.add_argument("--provider", default="web")
    parser.add_argument("--source-type", default="web_article")
    parser.add_argument("--author")
    parser.add_argument("--publisher")
    parser.add_argument("--authority-notes", default="")
    parser.add_argument("--rights-basis", default="web_reference")
    parser.add_argument("--language", default="en")
    parser.add_argument(
        "--processing-mode",
        choices=("local_only", "cloud_allowed"),
        default="cloud_allowed",
    )
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        metavar="KIND=PATH",
        help="Register a durable artifact already stored under records/source/media/SOURCE_ID/.",
    )
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="Refresh metadata and merge artifacts for the same source ID, location, and knowledge path.",
    )
    args = parser.parse_args()

    source_id = args.source_id.strip()
    if not source_id or not args.title.strip() or not args.location.strip():
        parser.error("--source-id, --title, and --location must be non-empty")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", source_id) is None:
        parser.error("--source-id must be a filesystem-safe identifier of at most 64 characters")

    root = args.course_root.resolve()
    knowledge = safe_knowledge_path(root, args.knowledge_path)
    if knowledge is None:
        parser.error("--knowledge-path must identify non-empty Markdown under COURSE_ROOT/records/source")
    try:
        extra_artifacts = parse_artifacts(root, source_id, args.artifact)
    except ValueError as error:
        parser.error(str(error))
    manifest = load_manifest(root)
    sources = manifest["sources"]
    try:
        study = yaml.safe_load((root / "study.yaml").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        study = {}
    contract = study.get("learning_contract", {}) if isinstance(study, dict) else {}
    approved_limit = contract.get("source_limit") if isinstance(contract, dict) and contract.get("status") == "approved" else None
    existing_index = next(
        (
            index
            for index, item in enumerate(sources)
            if isinstance(item, dict) and item.get("source_id") == source_id
        ),
        None,
    )
    if existing_index is None and isinstance(approved_limit, int) and len(sources) >= approved_limit:
        parser.error(f"Registering another source would exceed the approved source limit of {approved_limit}")
    existing = sources[existing_index] if existing_index is not None else None
    if existing is not None and not args.update_existing:
        parser.error(f"Source ID already exists: {source_id}")
    if existing is not None and (
        existing.get("original_location") != args.location
        or existing.get("knowledge_path") != args.knowledge_path.replace("\\", "/")
    ):
        parser.error("--update-existing cannot change original_location or knowledge_path")
    now = datetime.now(timezone.utc).isoformat()
    merged_artifacts = {
        str(item.get("path")): item
        for item in (existing.get("artifacts", []) if isinstance(existing, dict) else [])
        if isinstance(item, dict) and item.get("path")
    }
    knowledge_relative = args.knowledge_path.replace("\\", "/")
    merged_artifacts[knowledge_relative] = {
        "kind": "extracted_knowledge",
        "path": knowledge_relative,
        "content_hash": sha256_file(knowledge),
    }
    for artifact in extra_artifacts:
        merged_artifacts[artifact["path"]] = artifact
    record = {
        "source_id": source_id,
        "title": args.title.strip(),
        "author": args.author,
        "publisher": args.publisher,
        "provider": args.provider,
        "source_type": args.source_type,
        "original_location": args.location,
        "local_path": None,
        "knowledge_path": knowledge_relative,
        "retrieved_at": existing.get("retrieved_at", now) if isinstance(existing, dict) else now,
        "content_hash": sha256_file(knowledge),
        "language": args.language,
        "primary_or_secondary": "primary",
        "authority_notes": args.authority_notes,
        "license_or_usage_notes": "Registered for source-grounded personal study.",
        "rights_basis": args.rights_basis,
        "permitted_uses": [
            "personal_study",
            "derived_notes",
            *(
                ["transcription"]
                if any(token in args.source_type.casefold() for token in ("video", "audio"))
                else []
            ),
        ],
        "processing_mode": args.processing_mode,
        "included_sections": ["all"],
        "excluded_sections": [],
        "processing_status": "ready",
        "supersedes": existing.get("supersedes") if isinstance(existing, dict) else None,
        "superseded_by": existing.get("superseded_by") if isinstance(existing, dict) else None,
        "items": existing.get("items", []) if isinstance(existing, dict) else [],
        "artifacts": list(merged_artifacts.values()),
    }
    if existing_index is None:
        sources.append(record)
    else:
        sources[existing_index] = record
    errors = source_errors(root, manifest, require_nonempty=True)
    if errors:
        parser.error("; ".join(errors))
    atomic_manifest(root, manifest)
    append_event(root, {
        "action": "source.updated" if existing_index is not None else "source.registered",
        "actor": "main-agent",
        "status": "complete",
        "summary": f"{'Updated' if existing_index is not None else 'Registered'} extracted source {args.source_id}.",
        "artifacts": [relative_text(SOURCE_MANIFEST), *[item["path"] for item in record["artifacts"]]],
        "decision": "retained",
        "justification": "The extracted Markdown, durable artifacts, and content hashes passed the deterministic source gate.",
    })
    print(json.dumps({"status": "complete", "source": record}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
