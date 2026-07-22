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
    GLOSSARY,
    INDEX,
    INGESTION,
    LESSONS,
    ORCHESTRATION,
    PROGRESS,
    QUESTIONS,
    RECORDS,
    RUNS,
    SCRATCH,
    SOURCE,
    SOURCE_MANIFEST,
    SOURCE_MEDIA,
    STAGING,
    VALIDATION,
    layout_payload,
    relative_text,
)
from record_action import append_event


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return value or "study"


MODES = ("provided-material-only", "existing-library", "local-media", "topic-research", "hybrid")


def replace_tokens(text: str, *, study_id: str, title: str, mode: str) -> str:
    text = text.replace("STUDY-001", study_id)
    text = text.replace("Example study", title)
    text = text.replace("2026-07-19", date.today().isoformat())
    text = text.replace("__STUDY_MODE__", mode)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title")
    parser.add_argument(
        "--mode",
        choices=MODES,
        required=True,
        help="Approved source workflow. Supplied-source courses default to provided-material-only unless corroboration is authorized.",
    )
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
    ):
        (target / directory).mkdir(parents=True, exist_ok=True)

    mapping = {
        "study.yaml": "study.yaml",
        "source-manifest.yaml": relative_text(SOURCE_MANIFEST),
        "index.md": relative_text(INDEX),
        "question-bank.json": "questions/question-bank.json",
        "question-bank.md": "questions/question-bank.md",
        "lesson.md": "lessons/CH-001.md",
        "glossary.json": relative_text(GLOSSARY),
        "approved-claims.json": relative_text(APPROVED_CLAIMS),
        "learner-progress.json": "progress/learner-progress.json",
        "run-plan.yaml": ".work/orchestration/run-plan.yaml",
        "task-brief.yaml": ".work/orchestration/task-template.yaml",
    }
    for source_name, target_name in mapping.items():
        text = (assets / source_name).read_text(encoding="utf-8")
        (target / target_name).write_text(
            replace_tokens(text, study_id=study_id, title=args.title, mode=args.mode),
            encoding="utf-8",
        )
    (target / CONTRADICTIONS).write_text("{\n  \"contradictions\": []\n}\n", encoding="utf-8")
    (target / GAPS).write_text("{\n  \"gaps\": []\n}\n", encoding="utf-8")
    (target / COURSE_LAYOUT).write_text(
        json.dumps(layout_payload(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    append_event(
        target,
        {
            "action": "course.initialized",
            "actor": "initializer",
            "status": "complete",
            "summary": "Created the canonical course layout and empty learning artifacts.",
            "artifacts": ["study.yaml", relative_text(SOURCE_MANIFEST), relative_text(COURSE_LAYOUT)],
            "justification": "Initialization creates structure only; substantive knowledge still requires evidence approval.",
        },
    )

    print(
        json.dumps(
            {
                "status": "complete",
                "study_id": study_id,
                "mode": args.mode,
                "workspace": str(target),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
