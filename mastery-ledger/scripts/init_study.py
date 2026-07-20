#!/usr/bin/env python3
"""Create a project-local study workspace from bundled templates."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from record_action import append_event


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return value or "study"


def replace_tokens(text: str, *, study_id: str, title: str) -> str:
    text = text.replace("STUDY-001", study_id)
    text = text.replace("Example study", title)
    text = text.replace("2026-07-19", date.today().isoformat())
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title")
    parser.add_argument("--studies-dir", type=Path, default=Path("studies"))
    args = parser.parse_args()

    skill_root = Path(__file__).resolve().parents[1]
    assets = skill_root / "assets"
    study_id = f"STUDY-{uuid.uuid4().hex[:8].upper()}"
    target = args.studies_dir / slugify(args.title)
    if target.exists() and any(target.iterdir()):
        parser.error(f"Target is not empty: {target}")

    target.mkdir(parents=True, exist_ok=True)
    for directory in (
        "source/media",
        "lessons",
        "wiki/pages",
        "questions",
        "progress",
        "exams",
        "attempts",
        "logs",
        "evidence",
        ".work/ingestion",
        ".work/orchestration",
        ".work/runs",
        ".work/drafts",
        ".work/scratch",
    ):
        (target / directory).mkdir(parents=True, exist_ok=True)

    mapping = {
        "study.yaml": "study.yaml",
        "source-manifest.yaml": "source-manifest.yaml",
        "study-guide.md": "study-guide.md",
        "question-bank.json": "questions/question-bank.json",
        "question-bank.md": "questions/question-bank.md",
        "lesson.md": "lessons/CH-001.md",
        "approved-claims.json": "evidence/approved-claims.json",
        "learner-progress.json": "progress/learner-progress.json",
        "wiki.json": "wiki/wiki.json",
        "wiki-page.md": "wiki/pages/concept-id.md",
        "run-plan.yaml": ".work/orchestration/run-plan.yaml",
        "task-brief.yaml": ".work/orchestration/task-template.yaml",
    }
    for source_name, target_name in mapping.items():
        text = (assets / source_name).read_text(encoding="utf-8")
        (target / target_name).write_text(
            replace_tokens(text, study_id=study_id, title=args.title),
            encoding="utf-8",
        )
    (target / "concept-map.md").write_text(f"# Concept map: {args.title}\n\n", encoding="utf-8")
    (target / "glossary.md").write_text(f"# Glossary: {args.title}\n\n", encoding="utf-8")
    (target / "evidence" / "contradictions.json").write_text("{\n  \"contradictions\": []\n}\n", encoding="utf-8")
    (target / "evidence" / "gaps.json").write_text("{\n  \"gaps\": []\n}\n", encoding="utf-8")
    (target / ".work" / "course-layout.json").write_text(
        json.dumps(
            {
                "schema_version": "course-layout-v1",
                "durable_roots": [
                    "source",
                    "lessons",
                    "wiki",
                    "questions",
                    "progress",
                    "exams",
                    "attempts",
                    "logs",
                    "evidence",
                ],
                "disposable_root": ".work",
                "worker_root_pattern": ".work/runs/<run-id>/tasks/<task-id>",
                "canonical_event_log": "logs/events.jsonl",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    append_event(
        target,
        {
            "action": "course.initialized",
            "actor": "initializer",
            "status": "complete",
            "summary": "Created the canonical course layout and empty learning artifacts.",
            "artifacts": ["study.yaml", "source-manifest.yaml", ".work/course-layout.json"],
            "justification": "Initialization creates structure only; substantive knowledge still requires evidence approval.",
        },
    )

    print(
        json.dumps(
            {
                "status": "complete",
                "study_id": study_id,
                "workspace": str(target),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
