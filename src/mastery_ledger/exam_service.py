from __future__ import annotations

import hashlib
import itertools
import json
import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from mastery_ledger.dashboard import (
    DEFAULT_REVIEW_INTERVALS,
    _course_roots,
    _inside,
    _list_records,
    _manifest,
    _read_json,
    _read_yaml,
    _valid_intervals,
)
from mastery_ledger.database import read_setting
from mastery_ledger.models import (
    ExamAttemptStart,
    ExamCompletion,
    ExamOption,
    ExamQuestionView,
    QuestionFeedback,
    QuestionReview,
    SourceDisclosure,
    WorkspaceState,
)

MAX_QUESTIONS = 500
MAX_ATTEMPTS = 100
MAX_ATTEMPT_FILES = 2_000


class ExamNotFoundError(LookupError):
    pass


class ExamValidationError(ValueError):
    pass


class AttemptNotFoundError(LookupError):
    pass


class AttemptConflictError(RuntimeError):
    pass


class AttemptStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class LoadedQuestion:
    view: ExamQuestionView
    correct_option_id: str
    explanation: str
    sources: list[SourceDisclosure]
    version: int


@dataclass(frozen=True)
class LoadedExam:
    exam_id: str
    course_id: str
    course_title: str
    title: str
    estimated_minutes: int
    questions: list[LoadedQuestion]
    course_root: Path
    content_hash: str


@dataclass(frozen=True)
class AttemptSubmission:
    option_id: str
    status: str
    submitted_at: str


@dataclass
class AttemptState:
    attempt_id: str
    exam: LoadedExam
    path: Path
    started_at: str
    updated_at: str
    submissions: dict[str, AttemptSubmission] = field(default_factory=dict)
    finished: bool = False
    completion: ExamCompletion | None = None
    completed_at: str | None = None


def _source_manifest(course_root: Path) -> dict[str, Any] | None:
    for path in (
        course_root / "source" / "source-manifest.yaml",
        course_root / "source-manifest.yaml",
    ):
        if path.is_file():
            payload = _read_yaml(path, course_root)
            if payload is not None:
                return payload
    return None


def _source_index(course_root: Path) -> dict[str, dict[str, Any]]:
    sources = _list_records(_source_manifest(course_root), "sources")
    return {
        str(source["source_id"]): source
        for source in sources
        if isinstance(source.get("source_id"), (str, int))
    }


def _safe_href(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = urlparse(value.strip())
    return value.strip() if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _validate_sources(
    refs: object,
    source_index: dict[str, dict[str, Any]],
    question_id: str,
) -> list[SourceDisclosure]:
    if not isinstance(refs, list) or not refs:
        raise ExamValidationError(f"Question {question_id} has no source references.")
    disclosures: list[SourceDisclosure] = []
    for ref in refs:
        if not isinstance(ref, dict):
            raise ExamValidationError(f"Question {question_id} has a malformed source reference.")
        source_id = str(ref.get("source_id") or "")
        source = source_index.get(source_id)
        if source is None:
            raise ExamValidationError(
                f"Question {question_id} references unknown source {source_id or '<missing>'}."
            )
        locator = ref.get("locator")
        if not isinstance(locator, dict) or not isinstance(locator.get("kind"), str):
            raise ExamValidationError(f"Question {question_id} has a malformed source locator.")
        label = locator.get("label")
        if not isinstance(label, str) or not label.strip():
            raise ExamValidationError(
                f"Question {question_id} has a source locator without a label."
            )
        supports = ref.get("supports")
        if not isinstance(supports, list) or not supports:
            raise ExamValidationError(
                f"Question {question_id} has a source reference without support targets."
            )
        strength = ref.get("support_strength")
        if strength not in {"direct", "partial", "contextual"}:
            raise ExamValidationError(f"Question {question_id} has an invalid support strength.")
        disclosures.append(
            SourceDisclosure(
                source_id=source_id,
                title=str(source.get("title") or source_id),
                locator_label=label.strip(),
                support_strength=strength,
                href=_safe_href(ref.get("href")),
            )
        )
    return disclosures


def _load_question(
    raw: dict[str, Any],
    source_index: dict[str, dict[str, Any]],
) -> LoadedQuestion:
    question_id = str(raw.get("question_id") or "").strip()
    prompt = raw.get("prompt")
    if not question_id or not isinstance(prompt, str) or not prompt.strip():
        raise ExamValidationError("Every exam question needs a question_id and prompt.")
    raw_options = raw.get("options")
    if not isinstance(raw_options, list) or not 2 <= len(raw_options) <= 12:
        raise ExamValidationError(f"Question {question_id} needs between 2 and 12 options.")
    options: list[ExamOption] = []
    option_ids: set[str] = set()
    for raw_option in raw_options:
        if not isinstance(raw_option, dict):
            raise ExamValidationError(f"Question {question_id} has a malformed option.")
        option_id = str(raw_option.get("option_id") or "").strip()
        text = raw_option.get("text")
        if not option_id or option_id in option_ids or not isinstance(text, str) or not text.strip():
            raise ExamValidationError(f"Question {question_id} has a missing or duplicate option.")
        option_ids.add(option_id)
        options.append(ExamOption(option_id=option_id, text=text.strip()))

    correct_option_id = str(raw.get("correct_option_id") or "").strip()
    if correct_option_id not in option_ids:
        raise ExamValidationError(f"Question {question_id} has an invalid answer key.")
    explanation = raw.get("correct_explanation", raw.get("explanation"))
    if not isinstance(explanation, str) or not explanation.strip():
        raise ExamValidationError(f"Question {question_id} has no supported explanation.")
    sources = _validate_sources(raw.get("source_refs"), source_index, question_id)
    raw_concepts = raw.get("concept_ids", [])
    concepts = (
        [str(value) for value in raw_concepts if isinstance(value, (str, int))][:20]
        if isinstance(raw_concepts, list)
        else []
    )
    difficulty = raw.get("difficulty")
    if not isinstance(difficulty, (str, int)):
        difficulty = None
    version = raw.get("version", raw.get("question_version", 1))
    if not isinstance(version, int) or version < 1:
        version = 1
    return LoadedQuestion(
        view=ExamQuestionView(
            question_id=question_id,
            prompt=prompt.strip(),
            options=options,
            difficulty=difficulty,
            concept_ids=concepts,
            source_count=len(sources),
            source_status="verified",
        ),
        correct_option_id=correct_option_id,
        explanation=explanation.strip(),
        sources=sources,
        version=version,
    )


def load_exam(workspace: WorkspaceState, course_id: str, exam_id: str) -> LoadedExam:
    workspace_root = Path(workspace.path)
    for course_root in _course_roots(workspace_root):
        manifest = _manifest(course_root)
        if manifest is None:
            continue
        manifest_course_id = str(
            manifest.get("course_id") or manifest.get("study_id") or course_root.name
        )
        if not secrets.compare_digest(manifest_course_id, course_id):
            continue
        exams_root = course_root / "exams"
        if not exams_root.is_dir() or exams_root.is_symlink():
            break
        try:
            candidates = list(exams_root.iterdir())
        except OSError:
            break
        for exam_root in candidates:
            if not exam_root.is_dir() or exam_root.is_symlink():
                continue
            exam_path = exam_root / "exam.json"
            payload = _read_json(exam_path, course_root)
            if payload is None:
                continue
            payload_exam_id = str(payload.get("exam_id") or exam_root.name)
            if not secrets.compare_digest(payload_exam_id, exam_id):
                continue
            if str(payload.get("status", "")).casefold() != "ready":
                raise ExamValidationError("Only a validated ready exam can be started.")
            raw_questions = payload.get("questions")
            if not isinstance(raw_questions, list) or not raw_questions:
                raise ExamValidationError("This exam has no embedded questions to deliver.")
            if len(raw_questions) > MAX_QUESTIONS:
                raise ExamValidationError(
                    f"This exam exceeds the {MAX_QUESTIONS}-question delivery limit."
                )
            source_index = _source_index(course_root)
            questions = [
                _load_question(raw, source_index)
                for raw in raw_questions
                if isinstance(raw, dict)
            ]
            if len(questions) != len(raw_questions):
                raise ExamValidationError("This exam contains a malformed question record.")
            question_ids = [question.view.question_id for question in questions]
            if len(question_ids) != len(set(question_ids)):
                raise ExamValidationError("This exam contains duplicate question IDs.")
            estimate = payload.get("estimated_minutes", max(5, round(len(questions) * 1.5)))
            if not isinstance(estimate, int) or estimate < 0:
                estimate = max(5, round(len(questions) * 1.5))
            canonical = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            return LoadedExam(
                exam_id=payload_exam_id,
                course_id=manifest_course_id,
                course_title=str(
                    manifest.get("title") or course_root.name.replace("-", " ").title()
                ),
                title=str(payload.get("title") or exam_root.name.replace("-", " ").title()),
                estimated_minutes=estimate,
                questions=questions,
                course_root=course_root,
                content_hash=f"sha256:{hashlib.sha256(canonical).hexdigest()}",
            )
        break
    raise ExamNotFoundError("The requested exam was not found in the active workspace.")


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _ensure_artifact_directory(course_root: Path, name: str) -> Path:
    directory = course_root / name
    if not _inside(course_root, directory):
        raise AttemptStorageError("The course artifact directory escaped the course root.")
    if directory.exists() and (not directory.is_dir() or directory.is_symlink()):
        raise AttemptStorageError(f"The course {name} path is not a safe directory.")
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise AttemptStorageError(f"The course {name} directory could not be created.") from error
    return directory


def _atomic_write_json(path: Path, payload: dict[str, Any], course_root: Path) -> None:
    if not _inside(course_root, path) or path.parent.is_symlink():
        raise AttemptStorageError("The course artifact path is not safe to write.")
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError as error:
        raise AttemptStorageError(f"Could not write {path.name} atomically.") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _question_for(exam: LoadedExam, question_id: str) -> LoadedQuestion | None:
    return next(
        (item for item in exam.questions if item.view.question_id == question_id),
        None,
    )


def _feedback(question: LoadedQuestion, submission: AttemptSubmission) -> QuestionFeedback:
    correct = submission.status == "correct"
    return QuestionFeedback(
        question_id=question.view.question_id,
        selected_option_id=submission.option_id,
        status="correct" if correct else "incorrect",
        correct=correct,
        explanation=question.explanation if correct else None,
        sources=question.sources if correct else [],
    )


def _build_completion(state: AttemptState) -> ExamCompletion:
    reviews: list[QuestionReview] = []
    for question in state.exam.questions:
        submission = state.submissions.get(question.view.question_id)
        result = submission.status if submission is not None else "unanswered"
        reviews.append(
            QuestionReview(
                question_id=question.view.question_id,
                selected_option_id=submission.option_id if submission else None,
                correct_option_id=question.correct_option_id,
                status=result,
                explanation=question.explanation,
                sources=question.sources,
            )
        )
    correct_count = sum(review.status == "correct" for review in reviews)
    incorrect_count = sum(review.status == "incorrect" for review in reviews)
    unanswered_count = sum(review.status == "unanswered" for review in reviews)
    question_count = len(reviews)
    return ExamCompletion(
        attempt_id=state.attempt_id,
        question_count=question_count,
        answered_count=question_count - unanswered_count,
        correct_count=correct_count,
        incorrect_count=incorrect_count,
        unanswered_count=unanswered_count,
        score_percent=round((correct_count / question_count) * 100, 1)
        if question_count
        else 0,
        questions=reviews,
    )


def _attempt_payload(state: AttemptState) -> dict[str, Any]:
    responses = []
    for question in state.exam.questions:
        submission = state.submissions.get(question.view.question_id)
        if submission is None:
            continue
        responses.append(
            {
                "question_id": question.view.question_id,
                "selected_option_id": submission.option_id,
                "status": submission.status,
                "submitted_at": submission.submitted_at,
            }
        )
    payload: dict[str, Any] = {
        "schema_version": "exam-attempt-v1",
        "attempt_id": state.attempt_id,
        "course_id": state.exam.course_id,
        "exam_id": state.exam.exam_id,
        "exam_content_hash": state.exam.content_hash,
        "exam_title": state.exam.title,
        "status": "complete" if state.finished else "in_progress",
        "started_at": state.started_at,
        "updated_at": state.updated_at,
        "question_order": [
            question.view.question_id for question in state.exam.questions
        ],
        "responses": responses,
    }
    if state.finished and state.completion is not None:
        payload["completed_at"] = state.completed_at
        payload["result"] = state.completion.model_dump(mode="json")
    return payload


def _load_resumable_attempt(exam: LoadedExam) -> AttemptState | None:
    attempts_root = exam.course_root / "attempts"
    if not attempts_root.exists():
        return None
    if not attempts_root.is_dir() or attempts_root.is_symlink():
        raise AttemptStorageError("The course attempts path is not a safe directory.")
    try:
        paths = [
            path
            for path in itertools.islice(attempts_root.iterdir(), MAX_ATTEMPT_FILES)
            if path.is_file() and not path.is_symlink() and path.suffix.casefold() == ".json"
        ]
    except OSError as error:
        raise AttemptStorageError("The course attempts could not be inspected.") from error

    candidates: list[tuple[str, Path, dict[str, Any]]] = []
    for path in paths:
        payload = _read_json(path, exam.course_root)
        if not payload or payload.get("status") != "in_progress":
            continue
        if payload.get("course_id") != exam.course_id or payload.get("exam_id") != exam.exam_id:
            continue
        if payload.get("exam_content_hash") != exam.content_hash:
            continue
        updated_at = payload.get("updated_at")
        if not isinstance(updated_at, str):
            continue
        candidates.append((updated_at, path, payload))
    if not candidates:
        return None

    _, path, payload = max(candidates, key=lambda item: item[0])
    attempt_id = payload.get("attempt_id")
    started_at = payload.get("started_at")
    updated_at = payload.get("updated_at")
    if (
        not isinstance(attempt_id, str)
        or not attempt_id
        or not isinstance(started_at, str)
        or _parse_timestamp(started_at) is None
        or not isinstance(updated_at, str)
        or _parse_timestamp(updated_at) is None
    ):
        raise AttemptStorageError("The resumable attempt metadata is malformed.")

    submissions: dict[str, AttemptSubmission] = {}
    responses = payload.get("responses", [])
    if not isinstance(responses, list):
        raise AttemptStorageError("The resumable attempt responses are malformed.")
    for response in responses:
        if not isinstance(response, dict):
            raise AttemptStorageError("The resumable attempt contains an invalid response.")
        question_id = response.get("question_id")
        option_id = response.get("selected_option_id")
        submitted_at = response.get("submitted_at")
        question = _question_for(exam, question_id) if isinstance(question_id, str) else None
        if (
            question is None
            or not isinstance(option_id, str)
            or option_id not in {option.option_id for option in question.view.options}
            or not isinstance(submitted_at, str)
            or _parse_timestamp(submitted_at) is None
            or question_id in submissions
        ):
            raise AttemptStorageError("The resumable attempt contains an invalid response.")
        expected = "correct" if secrets.compare_digest(option_id, question.correct_option_id) else "incorrect"
        if response.get("status") != expected:
            raise AttemptStorageError("The resumable attempt contains inconsistent grading.")
        submissions[question_id] = AttemptSubmission(
            option_id=option_id,
            status=expected,
            submitted_at=submitted_at,
        )
    return AttemptState(
        attempt_id=attempt_id,
        exam=exam,
        path=path,
        started_at=started_at,
        updated_at=updated_at,
        submissions=submissions,
    )


def _review_queue_payload(course_root: Path) -> tuple[Path, dict[str, Any]]:
    progress_root = _ensure_artifact_directory(course_root, "progress")
    path = progress_root / "review-queue.json"
    if not path.exists():
        return path, {}
    payload = _read_json(path, course_root)
    if payload is None:
        raise AttemptStorageError("The existing review queue is not valid JSON.")
    return path, payload


def _update_review_queue(
    state: AttemptState,
    completion: ExamCompletion,
    completed_at: datetime,
    intervals: list[int],
) -> None:
    path, existing = _review_queue_payload(state.exam.course_root)
    applied = existing.get("applied_attempt_ids", [])
    if not isinstance(applied, list):
        raise AttemptStorageError("The review queue applied-attempt ledger is malformed.")
    applied_ids = [str(value) for value in applied if isinstance(value, str)]
    if state.attempt_id in applied_ids:
        return
    records = _list_records(existing, "questions", "entries", "items")
    if any(key in existing and not isinstance(existing[key], list) for key in ("questions", "entries", "items")):
        raise AttemptStorageError("The review queue question records are malformed.")
    indexed = {
        str(record["question_id"]): record
        for record in records
        if isinstance(record.get("question_id"), (str, int))
    }
    if len(indexed) != len(records):
        raise AttemptStorageError("The review queue has missing or duplicate question IDs.")
    timestamp = _timestamp(completed_at)

    for question, review in zip(state.exam.questions, completion.questions, strict=True):
        record = indexed.get(question.view.question_id)
        if record is None:
            answered = review.status != "unanswered"
            record = {
                "question_id": question.view.question_id,
                "question_version": question.version,
                "concept_ids": question.view.concept_ids,
                "stage_index": 0,
                "interval_days": intervals[0],
                "last_due_at": None,
                "last_reviewed_at": timestamp if answered else None,
                "next_due_at": _timestamp(completed_at + timedelta(days=intervals[0])),
                "due_success_count": 0,
                "lapse_count": 0,
                "early_practice_count": 1 if answered else 0,
                "last_result": review.status,
                "last_attempt_id": state.attempt_id,
                "status": "learning",
            }
            records.append(record)
            indexed[question.view.question_id] = record
            continue

        stage = record.get("stage_index", 0)
        if not isinstance(stage, int):
            stage = 0
        stage = min(max(stage, 0), len(intervals) - 1)
        next_due = _parse_timestamp(record.get("next_due_at"))
        if next_due is None:
            raise AttemptStorageError(
                f"Review record {question.view.question_id} has an invalid next due date."
            )
        is_due = next_due is not None and next_due <= completed_at
        record["question_version"] = question.version
        record["concept_ids"] = question.view.concept_ids
        record["last_result"] = review.status
        record["last_attempt_id"] = state.attempt_id

        if review.status == "correct":
            record["last_reviewed_at"] = timestamp
            if is_due:
                stage = min(stage + 1, len(intervals) - 1)
                record["last_due_at"] = _timestamp(next_due)
                record["due_success_count"] = int(record.get("due_success_count", 0)) + 1
                record["next_due_at"] = _timestamp(
                    completed_at + timedelta(days=intervals[stage])
                )
            else:
                record["early_practice_count"] = int(
                    record.get("early_practice_count", 0)
                ) + 1
        elif review.status == "incorrect":
            record["last_reviewed_at"] = timestamp
            if is_due:
                stage = 0
                record["last_due_at"] = _timestamp(next_due)
                record["lapse_count"] = int(record.get("lapse_count", 0)) + 1
                record["next_due_at"] = _timestamp(
                    completed_at + timedelta(days=intervals[0])
                )
            else:
                record["early_practice_count"] = int(
                    record.get("early_practice_count", 0)
                ) + 1
        record["stage_index"] = stage
        record["interval_days"] = intervals[stage]
        record["status"] = (
            "maintenance"
            if stage == len(intervals) - 1 and review.status == "correct" and is_due
            else "learning"
        )

    preserved = {
        key: value
        for key, value in existing.items()
        if key not in {"questions", "entries", "items"}
    }
    payload = {
        **preserved,
        "schema_version": "review-queue-v1",
        "course_id": state.exam.course_id,
        "curve_intervals": intervals,
        "updated_at": timestamp,
        "applied_attempt_ids": [*applied_ids, state.attempt_id],
        "questions": records,
    }
    _atomic_write_json(path, payload, state.exam.course_root)


class ExamSessionStore:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._attempts: OrderedDict[str, AttemptState] = OrderedDict()
        self._lock = threading.Lock()
        self._clock = clock or (lambda: datetime.now(UTC))

    def _remember(self, state: AttemptState) -> None:
        self._attempts[state.attempt_id] = state
        self._attempts.move_to_end(state.attempt_id)
        while len(self._attempts) > MAX_ATTEMPTS:
            self._attempts.popitem(last=False)

    def _start_payload(self, state: AttemptState, *, resumed: bool) -> ExamAttemptStart:
        return ExamAttemptStart(
            attempt_id=state.attempt_id,
            exam_id=state.exam.exam_id,
            course_id=state.exam.course_id,
            course_title=state.exam.course_title,
            title=state.exam.title,
            estimated_minutes=state.exam.estimated_minutes,
            started_at=state.started_at,
            resumed=resumed,
            questions=[question.view for question in state.exam.questions],
            answers=[
                _feedback(question, state.submissions[question.view.question_id])
                for question in state.exam.questions
                if question.view.question_id in state.submissions
            ],
        )

    def start(self, workspace: WorkspaceState, course_id: str, exam_id: str) -> ExamAttemptStart:
        exam = load_exam(workspace, course_id, exam_id)
        with self._lock:
            state = _load_resumable_attempt(exam)
            if state is not None:
                self._remember(state)
                return self._start_payload(state, resumed=True)

            now = _timestamp(self._clock())
            attempt_id = f"ATTEMPT-{secrets.token_urlsafe(18)}"
            attempts_root = _ensure_artifact_directory(exam.course_root, "attempts")
            state = AttemptState(
                attempt_id=attempt_id,
                exam=exam,
                path=attempts_root / f"{attempt_id}.json",
                started_at=now,
                updated_at=now,
            )
            _atomic_write_json(state.path, _attempt_payload(state), exam.course_root)
            self._remember(state)
            return self._start_payload(state, resumed=False)

    def _attempt(
        self,
        attempt_id: str,
        course_id: str,
        exam_id: str,
    ) -> AttemptState:
        attempt = self._attempts.get(attempt_id)
        if attempt is None:
            raise AttemptNotFoundError("The active exam attempt no longer exists.")
        if not secrets.compare_digest(
            attempt.exam.course_id, course_id
        ) or not secrets.compare_digest(attempt.exam.exam_id, exam_id):
            raise AttemptNotFoundError("The active exam attempt does not match this exam.")
        return attempt

    def submit(
        self,
        attempt_id: str,
        course_id: str,
        exam_id: str,
        question_id: str,
        option_id: str,
    ) -> QuestionFeedback:
        with self._lock:
            attempt = self._attempt(attempt_id, course_id, exam_id)
            if attempt.finished:
                raise AttemptConflictError("This exam attempt is already complete.")
            question = _question_for(attempt.exam, question_id)
            if question is None:
                raise AttemptNotFoundError("The requested question is not part of this attempt.")
            if question_id in attempt.submissions:
                raise AttemptConflictError("This question is already locked for this attempt.")
            if option_id not in {option.option_id for option in question.view.options}:
                raise ExamValidationError("Select one of the question's available options.")
            submitted_at = _timestamp(self._clock())
            status = (
                "correct"
                if secrets.compare_digest(option_id, question.correct_option_id)
                else "incorrect"
            )
            submission = AttemptSubmission(
                option_id=option_id,
                status=status,
                submitted_at=submitted_at,
            )
            attempt.submissions[question_id] = submission
            previous_updated_at = attempt.updated_at
            attempt.updated_at = submitted_at
            try:
                _atomic_write_json(
                    attempt.path,
                    _attempt_payload(attempt),
                    attempt.exam.course_root,
                )
            except AttemptStorageError:
                del attempt.submissions[question_id]
                attempt.updated_at = previous_updated_at
                raise
            return _feedback(question, submission)

    def finish(self, attempt_id: str, course_id: str, exam_id: str) -> ExamCompletion:
        with self._lock:
            attempt = self._attempt(attempt_id, course_id, exam_id)
            if attempt.finished and attempt.completion is not None:
                return attempt.completion

            completed_at = self._clock().astimezone(UTC)
            completion = _build_completion(attempt)
            intervals = _valid_intervals(
                read_setting("review_intervals", DEFAULT_REVIEW_INTERVALS)
            )
            _update_review_queue(
                attempt,
                completion,
                completed_at,
                intervals,
            )
            timestamp = _timestamp(completed_at)
            previous_updated_at = attempt.updated_at
            attempt.finished = True
            attempt.completion = completion
            attempt.completed_at = timestamp
            attempt.updated_at = timestamp
            try:
                _atomic_write_json(
                    attempt.path,
                    _attempt_payload(attempt),
                    attempt.exam.course_root,
                )
            except AttemptStorageError:
                attempt.finished = False
                attempt.completion = None
                attempt.completed_at = None
                attempt.updated_at = previous_updated_at
                raise
            return completion
