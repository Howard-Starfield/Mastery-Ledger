from __future__ import annotations

import hashlib
import itertools
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mastery_ledger.dashboard import (
    _course_roots,
    _is_due,
    _list_records,
    _manifest,
    _read_json,
)
from mastery_ledger.exam_service import (
    ExamSessionStore,
    ExamValidationError,
    LoadedExam,
    LoadedQuestion,
    _load_question,
    _source_index,
)
from mastery_ledger.models import ExamAttemptStart, WorkspaceState

MAX_REVIEW_QUESTIONS = 100
MAX_EXAMS_TO_SCAN = 2_000


class ReviewNotFoundError(LookupError):
    pass


def _question_payloads(course_root: Path) -> dict[str, list[dict[str, Any]]]:
    candidates: dict[str, list[dict[str, Any]]] = {}
    for path in (
        course_root / "questions" / "question-bank.json",
        course_root / "question-bank.json",
    ):
        payload = _read_json(path, course_root)
        for question in _list_records(payload, "questions"):
            question_id = question.get("question_id")
            if isinstance(question_id, (str, int)):
                candidates.setdefault(str(question_id), []).append(question)

    exams_root = course_root / "exams"
    if not exams_root.is_dir() or exams_root.is_symlink():
        return candidates
    try:
        exam_roots = list(itertools.islice(exams_root.iterdir(), MAX_EXAMS_TO_SCAN))
    except OSError:
        return candidates
    for exam_root in exam_roots:
        if not exam_root.is_dir() or exam_root.is_symlink():
            continue
        payload = _read_json(exam_root / "exam.json", course_root)
        if not payload or str(payload.get("status", "")).casefold() != "ready":
            continue
        for question in _list_records(payload, "questions"):
            question_id = question.get("question_id")
            if isinstance(question_id, (str, int)):
                candidates.setdefault(str(question_id), []).append(question)
    return candidates


def _load_due_questions(
    course_root: Path,
    now: datetime,
) -> tuple[list[LoadedQuestion], str | None]:
    review_payload = _read_json(
        course_root / "progress" / "review-queue.json",
        course_root,
    )
    records = [
        record
        for record in _list_records(review_payload, "questions", "entries", "items")
        if _is_due(record.get("next_due_at"), now)
        and str(record.get("status", "learning")).casefold() not in {"archived", "superseded"}
    ]
    records.sort(key=lambda record: str(record.get("next_due_at") or ""))
    if not records:
        return [], None

    source_index = _source_index(course_root)
    payloads = _question_payloads(course_root)
    questions: list[LoadedQuestion] = []
    oldest_due: str | None = None
    for record in records:
        question_id = str(record.get("question_id") or "")
        expected_version = record.get("question_version")
        loaded: LoadedQuestion | None = None
        for raw in payloads.get(question_id, []):
            try:
                candidate = _load_question(raw, source_index)
            except ExamValidationError:
                continue
            if isinstance(expected_version, int) and candidate.version != expected_version:
                continue
            loaded = candidate
            break
        if loaded is None:
            continue
        due_at = str(record.get("next_due_at") or "")
        oldest_due = min(oldest_due, due_at) if oldest_due else due_at
        questions.append(loaded)
        if len(questions) >= MAX_REVIEW_QUESTIONS:
            break
    return questions, oldest_due


def load_due_review(
    workspace: WorkspaceState,
    *,
    course_id: str | None = None,
    now: datetime | None = None,
) -> LoadedExam:
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    choices: list[tuple[str, Path, dict[str, Any], list[LoadedQuestion]]] = []
    for course_root in _course_roots(Path(workspace.path)):
        manifest = _manifest(course_root)
        if manifest is None:
            continue
        manifest_course_id = str(
            manifest.get("course_id") or manifest.get("study_id") or course_root.name
        )
        if course_id is not None and manifest_course_id != course_id:
            continue
        questions, oldest_due = _load_due_questions(course_root, current_time)
        if questions and oldest_due is not None:
            choices.append((oldest_due, course_root, manifest, questions))
    if not choices:
        if course_id:
            raise ReviewNotFoundError(
                "This course has no deliverable multiple-choice questions due for review."
            )
        raise ReviewNotFoundError(
            "No deliverable multiple-choice questions are due in the active workspace."
        )

    _, course_root, manifest, questions = min(choices, key=lambda item: item[0])
    selected_course_id = str(
        manifest.get("course_id") or manifest.get("study_id") or course_root.name
    )
    snapshot = [
        {
            "question": question.view.model_dump(mode="json"),
            "version": question.version,
            "correct_option_id": question.correct_option_id,
            "explanation": question.explanation,
            "sources": [source.model_dump(mode="json") for source in question.sources],
        }
        for question in questions
    ]
    content = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return LoadedExam(
        exam_id="REVIEW-DUE",
        course_id=selected_course_id,
        course_title=str(
            manifest.get("title") or course_root.name.replace("-", " ").title()
        ),
        title="Due review",
        estimated_minutes=max(5, round(len(questions) * 1.5)),
        questions=questions,
        course_root=course_root,
        content_hash=f"sha256:{hashlib.sha256(content).hexdigest()}",
        kind="review",
    )


def start_due_review(
    sessions: ExamSessionStore,
    workspace: WorkspaceState,
    *,
    course_id: str | None = None,
) -> ExamAttemptStart:
    return sessions.start_loaded(
        load_due_review(workspace, course_id=course_id)
    )
