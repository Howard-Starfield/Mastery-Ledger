from __future__ import annotations

import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mastery_ledger.dashboard import _course_roots, _list_records, _manifest, _read_json, _read_yaml
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


class ExamNotFoundError(LookupError):
    pass


class ExamValidationError(ValueError):
    pass


class AttemptNotFoundError(LookupError):
    pass


class AttemptConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class LoadedQuestion:
    view: ExamQuestionView
    correct_option_id: str
    explanation: str
    sources: list[SourceDisclosure]


@dataclass(frozen=True)
class LoadedExam:
    exam_id: str
    course_id: str
    course_title: str
    title: str
    estimated_minutes: int
    questions: list[LoadedQuestion]


@dataclass
class AttemptState:
    attempt_id: str
    exam: LoadedExam
    submissions: dict[str, str] = field(default_factory=dict)
    finished: bool = False


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
            raise ExamValidationError(f"Question {question_id} references unknown source {source_id or '<missing>'}.")
        locator = ref.get("locator")
        if not isinstance(locator, dict) or not isinstance(locator.get("kind"), str):
            raise ExamValidationError(f"Question {question_id} has a malformed source locator.")
        label = locator.get("label")
        if not isinstance(label, str) or not label.strip():
            raise ExamValidationError(f"Question {question_id} has a source locator without a label.")
        supports = ref.get("supports")
        if not isinstance(supports, list) or not supports:
            raise ExamValidationError(f"Question {question_id} has a source reference without support targets.")
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
    concepts = [str(value) for value in raw_concepts if isinstance(value, (str, int))][:20] if isinstance(raw_concepts, list) else []
    difficulty = raw.get("difficulty")
    if not isinstance(difficulty, (str, int)):
        difficulty = None
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
    )


def load_exam(workspace: WorkspaceState, course_id: str, exam_id: str) -> LoadedExam:
    workspace_root = Path(workspace.path)
    for course_root in _course_roots(workspace_root):
        manifest = _manifest(course_root)
        if manifest is None:
            continue
        manifest_course_id = str(manifest.get("course_id") or manifest.get("study_id") or course_root.name)
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
            payload = _read_json(exam_root / "exam.json", course_root)
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
                raise ExamValidationError(f"This exam exceeds the {MAX_QUESTIONS}-question delivery limit.")
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
            return LoadedExam(
                exam_id=payload_exam_id,
                course_id=manifest_course_id,
                course_title=str(manifest.get("title") or course_root.name.replace("-", " ").title()),
                title=str(payload.get("title") or exam_root.name.replace("-", " ").title()),
                estimated_minutes=estimate,
                questions=questions,
            )
        break
    raise ExamNotFoundError("The requested exam was not found in the active workspace.")


class ExamSessionStore:
    def __init__(self) -> None:
        self._attempts: OrderedDict[str, AttemptState] = OrderedDict()
        self._lock = threading.Lock()

    def start(self, workspace: WorkspaceState, course_id: str, exam_id: str) -> ExamAttemptStart:
        exam = load_exam(workspace, course_id, exam_id)
        attempt_id = f"ATTEMPT-{secrets.token_urlsafe(18)}"
        with self._lock:
            self._attempts[attempt_id] = AttemptState(attempt_id=attempt_id, exam=exam)
            while len(self._attempts) > MAX_ATTEMPTS:
                self._attempts.popitem(last=False)
        return ExamAttemptStart(
            attempt_id=attempt_id,
            exam_id=exam.exam_id,
            course_id=exam.course_id,
            course_title=exam.course_title,
            title=exam.title,
            estimated_minutes=exam.estimated_minutes,
            questions=[question.view for question in exam.questions],
        )

    def submit(
        self,
        attempt_id: str,
        course_id: str,
        exam_id: str,
        question_id: str,
        option_id: str,
    ) -> QuestionFeedback:
        with self._lock:
            attempt = self._attempts.get(attempt_id)
            if attempt is None:
                raise AttemptNotFoundError("The active exam attempt no longer exists.")
            if not secrets.compare_digest(attempt.exam.course_id, course_id) or not secrets.compare_digest(
                attempt.exam.exam_id, exam_id
            ):
                raise AttemptNotFoundError("The active exam attempt does not match this exam.")
            if attempt.finished:
                raise AttemptConflictError("This exam attempt is already complete.")
            question = next(
                (item for item in attempt.exam.questions if item.view.question_id == question_id),
                None,
            )
            if question is None:
                raise AttemptNotFoundError("The requested question is not part of this attempt.")
            if question_id in attempt.submissions:
                raise AttemptConflictError("This question is already locked for this attempt.")
            if option_id not in {option.option_id for option in question.view.options}:
                raise ExamValidationError("Select one of the question's available options.")
            attempt.submissions[question_id] = option_id
            correct = secrets.compare_digest(option_id, question.correct_option_id)
            return QuestionFeedback(
                question_id=question_id,
                selected_option_id=option_id,
                status="correct" if correct else "incorrect",
                correct=correct,
                explanation=question.explanation if correct else None,
                sources=question.sources if correct else [],
            )

    def finish(self, attempt_id: str, course_id: str, exam_id: str) -> ExamCompletion:
        with self._lock:
            attempt = self._attempts.get(attempt_id)
            if attempt is None:
                raise AttemptNotFoundError("The active exam attempt no longer exists.")
            if not secrets.compare_digest(attempt.exam.course_id, course_id) or not secrets.compare_digest(
                attempt.exam.exam_id, exam_id
            ):
                raise AttemptNotFoundError("The active exam attempt does not match this exam.")
            attempt.finished = True
            reviews: list[QuestionReview] = []
            for question in attempt.exam.questions:
                selected = attempt.submissions.get(question.view.question_id)
                if selected is None:
                    result = "unanswered"
                elif secrets.compare_digest(selected, question.correct_option_id):
                    result = "correct"
                else:
                    result = "incorrect"
                reviews.append(
                    QuestionReview(
                        question_id=question.view.question_id,
                        selected_option_id=selected,
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
                attempt_id=attempt_id,
                question_count=question_count,
                answered_count=question_count - unanswered_count,
                correct_count=correct_count,
                incorrect_count=incorrect_count,
                unanswered_count=unanswered_count,
                score_percent=round((correct_count / question_count) * 100, 1) if question_count else 0,
                questions=reviews,
            )
