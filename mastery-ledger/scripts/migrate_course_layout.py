#!/usr/bin/env python3
"""Explicitly migrate one legacy course to the canonical v2 layout."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml

from course_paths import (
    APPROVED_CLAIMS,
    CONTRADICTIONS,
    COURSE_LAYOUT,
    EVENT_LOG,
    EVIDENCE,
    GAPS,
    INDEX,
    LAYOUT_SCHEMA,
    RECORDS,
    SOURCE,
    SOURCE_MANIFEST,
    VALIDATION,
    WORK,
    layout_payload,
    relative_text,
)
from record_action import append_event
from source_registry import atomic_manifest


def _safe_root(value: Path) -> Path:
    if value.is_symlink():
        raise ValueError("Course root cannot be a symbolic link.")
    root = value.resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Course root must be a regular existing directory.")
    return root


def _inside(root: Path, path: Path) -> Path:
    resolved = path.resolve(strict=False)
    resolved.relative_to(root)
    return resolved


def _move(root: Path, source: Path, target: Path, moved: dict[str, str]) -> None:
    source = _inside(root, source)
    target = _inside(root, target)
    if not source.exists():
        return
    if source.is_symlink():
        raise ValueError(f"Refused symbolic-link legacy artifact: {source.relative_to(root)}")
    if target.exists():
        raise ValueError(
            f"Cannot migrate {source.relative_to(root)} because {target.relative_to(root)} already exists."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    moved[source.relative_to(root).as_posix()] = target.relative_to(root).as_posix()


def _rewrite_manifest(root: Path) -> None:
    path = root / SOURCE_MANIFEST
    if not path.is_file():
        return
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise ValueError(f"{relative_text(SOURCE_MANIFEST)} must contain a sources list")
    for source in payload["sources"]:
        if not isinstance(source, dict):
            continue
        knowledge_path = source.get("knowledge_path")
        if isinstance(knowledge_path, str) and knowledge_path.startswith("source/"):
            source["knowledge_path"] = "records/" + knowledge_path
        media_paths = source.get("media_paths")
        if isinstance(media_paths, list):
            source["media_paths"] = [
                "records/" + item if isinstance(item, str) and item.startswith("source/") else item
                for item in media_paths
            ]
    atomic_manifest(root, payload)


def _rewrite_study(root: Path) -> None:
    path = root / "study.yaml"
    if not path.is_file():
        return
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("study.yaml must contain an object")
    payload["layout_schema"] = LAYOUT_SCHEMA
    payload["artifact_paths"] = {
        "course_index": relative_text(INDEX),
        "source_manifest": relative_text(SOURCE_MANIFEST),
        "source": relative_text(SOURCE),
        "lessons": "lessons",
        "question_bank": "questions/question-bank.json",
        "question_bank_review": "questions/question-bank.md",
        "learner_progress": "progress/learner-progress.json",
        "approved_claims": relative_text(APPROVED_CLAIMS),
        "contradictions": relative_text(CONTRADICTIONS),
        "gaps": relative_text(GAPS),
        "validation": relative_text(VALIDATION),
        "action_log": relative_text(EVENT_LOG),
        "calibration": "progress/calibration.json",
        "exams": "exams",
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def migrate(root_value: Path) -> dict[str, object]:
    root = _safe_root(root_value)
    layout_path = root / COURSE_LAYOUT
    if layout_path.is_file():
        try:
            current = json.loads(layout_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            current = {}
        if current.get("schema_version") == LAYOUT_SCHEMA:
            return {"status": "complete", "course_root": str(root), "already_migrated": True, "moved": {}}

    active_plan = root / WORK / "orchestration" / "run-plan.yaml"
    if active_plan.is_file():
        plan = yaml.safe_load(active_plan.read_text(encoding="utf-8"))
        tasks = plan.get("task_graph", []) if isinstance(plan, dict) else []
        unfinished = [
            str(task.get("task_id"))
            for task in tasks
            if isinstance(task, dict) and task.get("status") not in {"submitted", "verified", "approved", "merged"}
        ]
        if unfinished:
            raise ValueError("Close or repair the active run before layout migration: " + ", ".join(unfinished))

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = root / WORK / "migration-backup" / timestamp
    moved: dict[str, str] = {}

    (root / RECORDS).mkdir(parents=True, exist_ok=True)
    _move(root, root / "source-manifest.yaml", root / SOURCE_MANIFEST, moved)
    _move(root, root / "source", root / SOURCE, moved)
    _move(root, root / "evidence", root / EVIDENCE, moved)
    _move(root, root / "logs", root / EVENT_LOG.parent, moved)

    if not (root / INDEX).exists():
        _move(root, root / "study-guide.md", root / INDEX, moved)
    elif (root / "study-guide.md").exists():
        _move(root, root / "study-guide.md", backup / "study-guide.md", moved)
    for relative in ("concept-map.md", "glossary.md", "wiki"):
        _move(root, root / relative, backup / relative, moved)

    (root / SOURCE).mkdir(parents=True, exist_ok=True)
    (root / SOURCE / "media").mkdir(parents=True, exist_ok=True)
    (root / EVIDENCE).mkdir(parents=True, exist_ok=True)
    (root / VALIDATION).mkdir(parents=True, exist_ok=True)
    (root / EVENT_LOG.parent).mkdir(parents=True, exist_ok=True)
    _rewrite_manifest(root)
    _rewrite_study(root)

    layout_path.parent.mkdir(parents=True, exist_ok=True)
    layout_path.write_text(json.dumps(layout_payload(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt = {
        "schema_version": "layout-migration-receipt-v1",
        "from_layout": "legacy",
        "to_layout": LAYOUT_SCHEMA,
        "migrated_at": datetime.now(timezone.utc).isoformat(),
        "moved": moved,
        "backup_root": backup.relative_to(root).as_posix() if backup.exists() else None,
    }
    receipt_path = root / VALIDATION / "layout-migration.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    append_event(
        root,
        {
            "action": "course.layout_migrated",
            "actor": "migration",
            "status": "complete",
            "summary": "Migrated the course to the canonical v2 records layout.",
            "artifacts": [relative_text(COURSE_LAYOUT), receipt_path.relative_to(root).as_posix()],
            "justification": "The v2 layout separates learner material, durable provenance, and disposable worker state.",
        },
    )
    return {"status": "complete", "course_root": str(root), "already_migrated": False, "moved": moved}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    args = parser.parse_args()
    try:
        payload = migrate(args.course_root)
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.error(str(error))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

