#!/usr/bin/env python3
"""Safely add the canonical study layout to an existing application-created course."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import yaml

from course_paths import (
    APPROVED_CLAIMS,
    ATTEMPTS,
    CONTRADICTIONS,
    COURSE_LAYOUT,
    DRAFTS,
    EVIDENCE,
    EVENT_LOG,
    EXAMS,
    GAPS,
    INDEX,
    INGESTION,
    LESSONS,
    ORCHESTRATION,
    PROGRESS,
    QUESTIONS,
    RUNS,
    SCRATCH,
    SOURCE_MANIFEST,
    SOURCE_MEDIA,
    STAGING,
    VALIDATION,
    layout_payload,
    relative_text,
)
from init_study import replace_tokens
from migrate_course_layout import migrate
from record_action import append_event


DIRECTORIES = (
    SOURCE_MEDIA,
    LESSONS,
    QUESTIONS,
    PROGRESS,
    EXAMS,
    ATTEMPTS,
    EVENT_LOG.parent,
    EVIDENCE,
    VALIDATION,
    INGESTION,
    ORCHESTRATION,
    RUNS,
    STAGING,
    DRAFTS,
    SCRATCH,
)

TEMPLATES = {
    "study.yaml": "study.yaml",
    "source-manifest.yaml": relative_text(SOURCE_MANIFEST),
    "index.md": relative_text(INDEX),
    "question-bank.json": "questions/question-bank.json",
    "question-bank.md": "questions/question-bank.md",
    "lesson.md": "lessons/CH-001.md",
    "approved-claims.json": relative_text(APPROVED_CLAIMS),
    "learner-progress.json": "progress/learner-progress.json",
    "run-plan.yaml": ".work/orchestration/run-plan.yaml",
    "task-brief.yaml": ".work/orchestration/task-template.yaml",
}


def _safe_root(value: Path) -> Path:
    if value.is_symlink():
        raise ValueError("Course root cannot be a symbolic link.")
    root = value.resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Course root must be a regular existing directory.")
    return root


def _write_if_missing(path: Path, content: str, created: list[str], root: Path) -> None:
    if path.exists():
        if path.is_symlink():
            raise ValueError(f"Refused symbolic-link artifact: {path.relative_to(root)}")
        return
    path.write_text(content, encoding="utf-8")
    created.append(path.relative_to(root).as_posix())


def adopt(root: Path) -> dict[str, object]:
    root = _safe_root(root)
    existing_study = root / "study.yaml"
    if existing_study.is_symlink():
        raise ValueError("study.yaml cannot be a symbolic link.")
    if existing_study.is_file() and not existing_study.is_symlink():
        return {"status": "complete", "course_root": str(root), "created": [], "already_initialized": True}
    course_path = root / "course.yaml"
    if not course_path.is_file() or course_path.is_symlink():
        raise ValueError("Adoption requires a regular course.yaml when study.yaml is absent.")
    try:
        course = yaml.safe_load(course_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ValueError(f"Cannot read course.yaml: {error}") from error
    if not isinstance(course, dict):
        raise ValueError("course.yaml must contain an object.")
    study_id = str(course.get("course_id") or "").strip()
    title = str(course.get("title") or "").strip()
    if not study_id or not title:
        raise ValueError("course.yaml requires course_id and title before adoption.")

    legacy_paths = [root / name for name in ("source-manifest.yaml", "source", "evidence", "logs", "study-guide.md", "wiki")]
    if any(path.exists() for path in legacy_paths):
        migrate(root)

    for relative in DIRECTORIES:
        path = root / relative
        if path.exists() and (not path.is_dir() or path.is_symlink()):
            raise ValueError(f"Expected a regular directory: {relative}")
        path.mkdir(parents=True, exist_ok=True)

    skill_root = Path(__file__).resolve().parents[1]
    assets = skill_root / "assets"
    created: list[str] = []
    for source_name, target_name in TEMPLATES.items():
        target = root / target_name
        text = replace_tokens(
            (assets / source_name).read_text(encoding="utf-8"),
            study_id=study_id,
            title=title,
        )
        _write_if_missing(target, text, created, root)
    if "study.yaml" in created:
        study = yaml.safe_load((root / "study.yaml").read_text(encoding="utf-8"))
        source_manifest = yaml.safe_load((root / SOURCE_MANIFEST).read_text(encoding="utf-8"))
        sources = source_manifest.get("sources", []) if isinstance(source_manifest, dict) else []
        study["mode"] = "provided-material-only" if sources else "topic-research"
        study["source_policy"] = study["mode"]
        (root / "study.yaml").write_text(
            yaml.safe_dump(study, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    _write_if_missing(root / CONTRADICTIONS, "{\n  \"contradictions\": []\n}\n", created, root)
    _write_if_missing(root / GAPS, "{\n  \"gaps\": []\n}\n", created, root)
    _write_if_missing(
        root / COURSE_LAYOUT,
        json.dumps(layout_payload(), ensure_ascii=False, indent=2) + "\n",
        created,
        root,
    )
    append_event(root, {
        "action": "course.adopted",
        "actor": "initializer",
        "status": "complete",
        "summary": "Added the canonical study layout while preserving existing course and source artifacts.",
        "artifacts": ["course.yaml", "study.yaml", relative_text(COURSE_LAYOUT)],
        "justification": "Application-created courses must use the same deterministic skill workflow before publication.",
    })
    return {
        "status": "complete",
        "course_root": str(root),
        "study_id": study_id,
        "created": created,
        "already_initialized": False,
        "adopted_at": date.today().isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    args = parser.parse_args()
    try:
        payload = adopt(args.course_root)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
