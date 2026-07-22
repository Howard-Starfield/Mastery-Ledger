"""Canonical Mastery Ledger course-layout v2 paths."""

from __future__ import annotations

from pathlib import Path


LAYOUT_SCHEMA = "course-layout-v2"

INDEX = Path("index.md")
LESSONS = Path("lessons")
GLOSSARY = LESSONS / "glossary.json"
QUESTIONS = Path("questions")
QUESTION_BANK = QUESTIONS / "question-bank.json"
QUESTION_BANK_REVIEW = QUESTIONS / "question-bank.md"
EXAMS = Path("exams")
ATTEMPTS = Path("attempts")
PROGRESS = Path("progress")

RECORDS = Path("records")
SOURCE_MANIFEST = RECORDS / "source-manifest.yaml"
SOURCE = RECORDS / "source"
SOURCE_MEDIA = SOURCE / "media"
EVIDENCE = RECORDS / "evidence"
APPROVED_CLAIMS = EVIDENCE / "approved-claims.json"
CONTRADICTIONS = EVIDENCE / "contradictions.json"
GAPS = EVIDENCE / "gaps.json"
VALIDATION = EVIDENCE / "validation"
PUBLICATION_RECEIPT = VALIDATION / "publication-receipt.json"
EVENT_LOG = RECORDS / "logs" / "events.jsonl"

WORK = Path(".work")
INGESTION = WORK / "ingestion"
ORCHESTRATION = WORK / "orchestration"
RUNS = WORK / "runs"
STAGING = WORK / "staging"
DRAFTS = WORK / "drafts"
SCRATCH = WORK / "scratch"
COURSE_LAYOUT = WORK / "course-layout.json"


def relative_text(path: Path) -> str:
    return path.as_posix()


def layout_payload() -> dict[str, object]:
    return {
        "schema_version": LAYOUT_SCHEMA,
        "durable_roots": [
            relative_text(LESSONS),
            relative_text(QUESTIONS),
            relative_text(PROGRESS),
            relative_text(EXAMS),
            relative_text(ATTEMPTS),
            relative_text(RECORDS),
        ],
        "disposable_root": relative_text(WORK),
        "worker_root_pattern": ".work/runs/<run-id>/tasks/<task-id>",
        "canonical_event_log": relative_text(EVENT_LOG),
        "source_manifest": relative_text(SOURCE_MANIFEST),
        "source_root": relative_text(SOURCE),
        "validation_root": relative_text(VALIDATION),
    }
