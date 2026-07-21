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
from source_registry import atomic_manifest, load_manifest, safe_knowledge_path, sha256_file, source_errors


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
    args = parser.parse_args()

    if not args.source_id.strip() or not args.title.strip() or not args.location.strip():
        parser.error("--source-id, --title, and --location must be non-empty")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", args.source_id.strip()) is None:
        parser.error("--source-id must be a filesystem-safe identifier of at most 64 characters")

    root = args.course_root.resolve()
    knowledge = safe_knowledge_path(root, args.knowledge_path)
    if knowledge is None:
        parser.error("--knowledge-path must identify non-empty Markdown under COURSE_ROOT/records/source")
    manifest = load_manifest(root)
    sources = manifest["sources"]
    try:
        study = yaml.safe_load((root / "study.yaml").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        study = {}
    contract = study.get("learning_contract", {}) if isinstance(study, dict) else {}
    approved_limit = contract.get("source_limit") if isinstance(contract, dict) and contract.get("status") == "approved" else None
    if isinstance(approved_limit, int) and len(sources) >= approved_limit:
        parser.error(f"Registering another source would exceed the approved source limit of {approved_limit}")
    if any(isinstance(item, dict) and item.get("source_id") == args.source_id for item in sources):
        parser.error(f"Source ID already exists: {args.source_id}")
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "source_id": args.source_id.strip(),
        "title": args.title.strip(),
        "author": args.author,
        "publisher": args.publisher,
        "provider": args.provider,
        "source_type": args.source_type,
        "original_location": args.location,
        "local_path": None,
        "knowledge_path": args.knowledge_path.replace("\\", "/"),
        "retrieved_at": now,
        "content_hash": sha256_file(knowledge),
        "language": args.language,
        "primary_or_secondary": "primary",
        "authority_notes": args.authority_notes,
        "license_or_usage_notes": "Registered for source-grounded personal study.",
        "rights_basis": args.rights_basis,
        "permitted_uses": ["personal_study", "derived_notes"],
        "processing_mode": "cloud_allowed",
        "included_sections": ["all"],
        "excluded_sections": [],
        "processing_status": "ready",
        "supersedes": None,
        "superseded_by": None,
        "items": [],
        "artifacts": [{"kind": "extracted_knowledge", "path": args.knowledge_path.replace("\\", "/")}],
    }
    sources.append(record)
    errors = source_errors(root, manifest, require_nonempty=True)
    if errors:
        parser.error("; ".join(errors))
    atomic_manifest(root, manifest)
    append_event(root, {
        "action": "source.registered",
        "actor": "main-agent",
        "status": "complete",
        "summary": f"Registered extracted source {args.source_id}.",
        "artifacts": [relative_text(SOURCE_MANIFEST), record["knowledge_path"]],
        "decision": "retained",
        "justification": "The extracted Markdown and content hash passed the deterministic source gate.",
    })
    print(json.dumps({"status": "complete", "source": record}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
