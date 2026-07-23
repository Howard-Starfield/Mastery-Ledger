from __future__ import annotations

import itertools
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from mastery_ledger.course_import import CourseImportError, validate_course_folder
from mastery_ledger.course_discovery import course_roots as _course_roots
from mastery_ledger.database import read_setting
from mastery_ledger.models import (
    DashboardCourse,
    DashboardExam,
    DashboardResult,
    OwnershipStage,
    WorkspaceState,
)
from mastery_ledger.settings_service import DEFAULT_REVIEW_INTERVALS, valid_intervals

MAX_EXAMS_PER_COURSE = 2_000
MAX_ATTEMPTS_PER_COURSE = 2_000


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except (OSError, ValueError):
        return False


def _read_json(path: Path, root: Path) -> dict[str, Any] | None:
    if not _inside(root, path):
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_yaml(path: Path, root: Path) -> dict[str, Any] | None:
    if not _inside(root, path):
        return None
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        return None
    return payload if isinstance(payload, dict) else None


def _manifest(course_root: Path) -> dict[str, Any] | None:
    for name in ("course.yaml", "study.yaml"):
        path = course_root / name
        if path.is_file():
            return _read_yaml(path, course_root)
    return None


def _list_records(payload: dict[str, Any] | None, *keys: str) -> list[dict[str, Any]]:
    if not payload:
        return []
    for key in keys:
        records = payload.get(key)
        if isinstance(records, list):
            return [record for record in records if isinstance(record, dict)]
    return []


def _question_count(course_root: Path) -> int:
    payload = _read_json(course_root / "questions" / "question-bank.json", course_root)
    if payload is None:
        payload = _read_json(course_root / "question-bank.json", course_root)
    return len(_list_records(payload, "questions"))


def _concept_counts(course_root: Path) -> tuple[int, int]:
    payload = _read_json(
        course_root / "progress" / "learner-progress.json",
        course_root,
    )
    if payload is None:
        payload = _read_json(course_root / "learner-progress.json", course_root)
    concepts = _list_records(payload, "concepts")
    proficient = sum(
        1
        for concept in concepts
        if str(concept.get("status", "")).casefold() in {"proficient", "stable"}
    )
    return len(concepts), proficient


def _review_records(course_root: Path) -> list[dict[str, Any]]:
    payload = _read_json(course_root / "progress" / "review-queue.json", course_root)
    if payload is None:
        payload = _read_json(course_root / "review-queue.json", course_root)
    return _list_records(payload, "questions", "entries", "items")


def _in_progress_exam_ids(course_root: Path) -> set[str]:
    attempts_root = course_root / "attempts"
    if not attempts_root.is_dir() or attempts_root.is_symlink():
        return set()
    try:
        paths = list(itertools.islice(attempts_root.iterdir(), MAX_ATTEMPTS_PER_COURSE))
    except OSError:
        return set()
    exam_ids: set[str] = set()
    for path in paths:
        if not path.is_file() or path.is_symlink() or path.suffix.casefold() != ".json":
            continue
        payload = _read_json(path, course_root)
        if not payload or payload.get("status") != "in_progress":
            continue
        exam_id = payload.get("exam_id")
        if isinstance(exam_id, str) and exam_id:
            exam_ids.add(exam_id)
    return exam_ids


def _is_due(value: object, now: datetime) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC) <= now


def _exam_summaries(
    course_root: Path,
    course_id: str,
    course_title: str,
    manifest: dict[str, Any],
) -> list[DashboardExam]:
    exams_root = course_root / "exams"
    if not exams_root.is_dir() or exams_root.is_symlink():
        return []
    try:
        directories = sorted(exams_root.iterdir(), key=lambda item: item.name.casefold())
    except OSError:
        return []

    exams: list[DashboardExam] = []
    in_progress_exam_ids = _in_progress_exam_ids(course_root)
    for exam_root in directories[:MAX_EXAMS_PER_COURSE]:
        if not exam_root.is_dir() or exam_root.is_symlink():
            continue
        payload = _read_json(exam_root / "exam.json", course_root)
        if not payload:
            continue
        status = str(payload.get("status", "")).casefold()
        if status == "ready":
            assessment_kind = "exam"
            mastery_eligible = True
        elif status == "practice_ready":
            if (
                manifest.get("bundle_schema") != "mastery-ledger-course-bundle-v1"
                or manifest.get("layout_schema") != "course-layout-v2"
                or manifest.get("workflow_state") != "STUDY_PACK_DRAFTED"
                or manifest.get("publication_status") != "DRAFT_UNVERIFIED"
                or payload.get("verification_status") != "self_checked"
                or payload.get("mastery_eligible") is not False
            ):
                continue
            try:
                validate_course_folder(
                    course_root,
                    allow_runtime_state=True,
                    require_practice=True,
                )
            except (CourseImportError, OSError, UnicodeError):
                continue
            assessment_kind = "practice"
            mastery_eligible = False
        else:
            continue
        questions = payload.get("questions")
        fallback_count = len(questions) if isinstance(questions, list) else 0
        question_count = payload.get("question_count", fallback_count)
        estimated_minutes = payload.get("estimated_minutes", max(5, round(fallback_count * 1.5)))
        if not isinstance(question_count, int) or question_count < 0:
            question_count = fallback_count
        if not isinstance(estimated_minutes, int) or estimated_minutes < 0:
            estimated_minutes = max(5, round(question_count * 1.5))
        raw_concepts = payload.get("concepts", payload.get("concept_ids", []))
        concepts = [str(item) for item in raw_concepts if isinstance(item, (str, int))][:12] if isinstance(raw_concepts, list) else []
        source_value = str(payload.get("source_status", payload.get("verification_status", "ready"))).casefold()
        source_status = "self_checked" if assessment_kind == "practice" else "verified" if source_value in {"verified", "passed", "approved"} else "review_needed" if source_value in {"review_needed", "changes_required", "warning"} else "ready"
        exams.append(
            DashboardExam(
                exam_id=str(payload.get("exam_id") or exam_root.name),
                course_id=str(payload.get("course_id") or course_id),
                course_title=course_title,
                title=str(payload.get("title") or exam_root.name.replace("-", " ").title()),
                question_count=question_count,
                estimated_minutes=estimated_minutes,
                concepts=concepts,
                created_at=str(payload["created_at"]) if payload.get("created_at") else None,
                source_status=source_status,
                assessment_kind=assessment_kind,
                mastery_eligible=mastery_eligible,
                resume_available=str(payload.get("exam_id") or exam_root.name) in in_progress_exam_ids,
            )
        )
    return exams


def _valid_intervals(value: object) -> list[int]:
    return valid_intervals(value)


def build_dashboard(workspace: WorkspaceState, *, now: datetime | None = None) -> DashboardResult:
    workspace_root = Path(workspace.path)
    current_time = now or datetime.now(UTC)
    intervals = _valid_intervals(read_setting("review_intervals", DEFAULT_REVIEW_INTERVALS))
    stage_counts = [0 for _ in intervals]
    ready_exams: list[DashboardExam] = []
    courses: list[DashboardCourse] = []
    warnings: list[str] = []

    for course_root in _course_roots(workspace_root):
        manifest = _manifest(course_root)
        if manifest is None:
            warnings.append(f"Skipped unreadable course manifest: {course_root.name}")
            continue
        course_id = str(manifest.get("course_id") or manifest.get("study_id") or course_root.name)
        title = str(manifest.get("title") or course_root.name.replace("-", " ").title())
        reviews = _review_records(course_root)
        due_count = sum(1 for record in reviews if _is_due(record.get("next_due_at"), current_time))
        for record in reviews:
            stage = record.get("stage_index")
            if isinstance(stage, int) and 0 <= stage < len(stage_counts):
                stage_counts[stage] += 1
        exams = _exam_summaries(course_root, course_id, title, manifest)
        ready_exams.extend(exams)
        concept_count, proficient_concept_count = _concept_counts(course_root)
        courses.append(
            DashboardCourse(
                course_id=course_id,
                title=title,
                question_count=_question_count(course_root),
                ready_exam_count=len(exams),
                due_count=due_count,
                concept_count=concept_count,
                proficient_concept_count=proficient_concept_count,
                updated_at=str(manifest["updated_at"]) if manifest.get("updated_at") else None,
            )
        )

    ready_exams.sort(key=lambda exam: exam.created_at or "", reverse=True)
    courses.sort(key=lambda course: course.updated_at or "", reverse=True)
    ownership_curve = [
        OwnershipStage(stage_index=index, interval_days=days, question_count=stage_counts[index])
        for index, days in enumerate(intervals)
    ]
    return DashboardResult(
        workspace=workspace,
        due_now=sum(course.due_count for course in courses),
        ready_exams=ready_exams,
        recent_courses=courses,
        ownership_curve=ownership_curve,
        warnings=warnings,
    )
