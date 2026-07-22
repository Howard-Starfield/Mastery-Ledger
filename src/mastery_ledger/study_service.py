from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from mastery_ledger.course_discovery import course_roots as _course_roots
from mastery_ledger.models import (
    GlossaryChapterLink,
    GlossaryCourseSummary,
    GlossaryIndexResult,
    GlossaryIndexTerm,
    StudyChapter,
    StudyCourse,
    StudyGlossaryResult,
    StudyGlossaryTerm,
    StudyLessonResult,
    StudyLibraryResult,
    WorkspaceState,
)

MAX_LESSON_BYTES = 2 * 1024 * 1024
MAX_GLOSSARY_BYTES = 2 * 1024 * 1024
WORD_PATTERN = re.compile(r"\b[\w'-]+\b", re.UNICODE)


class StudyMaterialNotFoundError(LookupError):
    pass


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except (OSError, ValueError):
        return False


def _read_yaml(path: Path, root: Path) -> dict[str, Any] | None:
    if not _inside(root, path) or not path.is_file() or path.is_symlink():
        return None
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_json(path: Path, root: Path) -> dict[str, Any] | None:
    if not _inside(root, path) or not path.is_file() or path.is_symlink():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _manifest(course_root: Path) -> dict[str, Any] | None:
    for name in ("study.yaml", "course.yaml"):
        payload = _read_yaml(course_root / name, course_root)
        if payload is not None:
            return payload
    return None


def _published(manifest: dict[str, Any]) -> bool:
    return str(manifest.get("workflow_state", "")).strip().casefold() == "learning_active"


def _draft_preview(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("bundle_schema") == "mastery-ledger-course-bundle-v1"
        and manifest.get("layout_schema") == "course-layout-v2"
        and str(manifest.get("workflow_state", "")).strip().casefold() == "study_pack_drafted"
        and str(manifest.get("publication_status", "")).strip().casefold() == "draft_unverified"
    )


def _lesson_body(content: str) -> tuple[dict[str, Any] | None, str]:
    """Return lesson metadata and the Markdown intended for learners."""
    normalized = content.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return None, content
    boundary = normalized.find("\n---\n", 4)
    if boundary < 0:
        return None, content
    try:
        metadata = yaml.safe_load(normalized[4:boundary])
    except yaml.YAMLError:
        return None, content
    if not isinstance(metadata, dict):
        return None, content
    return metadata, normalized[boundary + 5 :].lstrip("\n")


def _lesson_text(
    course_root: Path,
    lesson_path: object,
    *,
    require_validated: bool = False,
) -> str | None:
    if not isinstance(lesson_path, str):
        return None
    normalized = lesson_path.replace("\\", "/")
    if not normalized.startswith("lessons/") or not normalized.casefold().endswith(".md"):
        return None
    lesson = (course_root / normalized).resolve(strict=False)
    lessons_root = (course_root / "lessons").resolve(strict=False)
    try:
        lesson.relative_to(lessons_root)
    except ValueError:
        return None
    try:
        if not lesson.is_file() or lesson.is_symlink() or lesson.stat().st_size > MAX_LESSON_BYTES:
            return None
        content = lesson.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    metadata, body = _lesson_body(content)
    if require_validated and (
        metadata is None
        or metadata.get("schema_version") != "lesson-v1"
        or str(metadata.get("status", "")).strip().casefold() != "validated"
    ):
        return None
    return body if len(body.strip()) >= 100 else None


def _word_count(content: str) -> int:
    return len(WORD_PATTERN.findall(content))


def _course_record(course_root: Path) -> tuple[StudyCourse | None, list[str]]:
    warnings: list[str] = []
    manifest = _manifest(course_root)
    if manifest is None:
        return None, warnings
    published = _published(manifest)
    draft_preview = _draft_preview(manifest)
    course_id = str(manifest.get("course_id") or manifest.get("study_id") or course_root.name)
    title = str(manifest.get("title") or course_root.name.replace("-", " ").title())
    question_bank = _read_json(course_root / "questions" / "question-bank.json", course_root)
    if question_bank is None or question_bank.get("schema_version") != "question-bank-v2":
        warnings.append(f"Skipped published course with no readable question bank: {course_root.name}")
        return None, warnings
    raw_chapters = question_bank.get("chapters")
    if not isinstance(raw_chapters, list):
        warnings.append(f"Skipped published course with no chapter catalog: {course_root.name}")
        return None, warnings
    chapters: list[StudyChapter] = []
    seen_ids: set[str] = set()
    for raw in raw_chapters:
        if not isinstance(raw, dict):
            continue
        chapter_id = str(raw.get("chapter_id") or "").strip()
        if not chapter_id or chapter_id in seen_ids:
            continue
        content = _lesson_text(
            course_root,
            raw.get("lesson_path"),
            require_validated=not published and not draft_preview,
        )
        if content is None:
            warnings.append(f"Skipped unreadable lesson {chapter_id} in {course_root.name}")
            continue
        seen_ids.add(chapter_id)
        chapters.append(
            StudyChapter(
                chapter_id=chapter_id,
                title=str(raw.get("title") or chapter_id.replace("-", " ").title()),
                chapter_class=str(raw.get("class") or "core"),
                lesson_path=str(raw["lesson_path"]).replace("\\", "/"),
                word_count=_word_count(content),
            )
        )
    if not chapters:
        warnings.append(f"Skipped published course with no readable lessons: {course_root.name}")
        return None, warnings
    return (
        StudyCourse(
            course_id=course_id,
            title=title,
            updated_at=str(manifest["updated_at"]) if manifest.get("updated_at") else None,
            publication_status=str(manifest.get("publication_status") or "UNSPECIFIED"),
            chapters=chapters,
        ),
        warnings,
    )


def study_library(workspace: WorkspaceState) -> StudyLibraryResult:
    courses: list[StudyCourse] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    for course_root in _course_roots(Path(workspace.path)):
        course, course_warnings = _course_record(course_root)
        warnings.extend(course_warnings)
        if course is None:
            continue
        if course.course_id in seen_ids:
            warnings.append(f"Skipped duplicate published course ID: {course.course_id}")
            continue
        seen_ids.add(course.course_id)
        courses.append(course)
    courses.sort(key=lambda course: course.updated_at or "", reverse=True)
    return StudyLibraryResult(workspace=workspace, courses=courses, warnings=warnings)


def study_lesson(workspace: WorkspaceState, course_id: str, chapter_id: str) -> StudyLessonResult:
    for course_root in _course_roots(Path(workspace.path)):
        course, _ = _course_record(course_root)
        if course is None or course.course_id != course_id:
            continue
        chapter = next((item for item in course.chapters if item.chapter_id == chapter_id), None)
        if chapter is None:
            break
        manifest = _manifest(course_root)
        content = _lesson_text(
            course_root,
            chapter.lesson_path,
            require_validated=not _published(manifest or {}) and not _draft_preview(manifest or {}),
        )
        if content is None:
            break
        return StudyLessonResult(
            course_id=course.course_id,
            course_title=course.title,
            chapter_id=chapter.chapter_id,
            title=chapter.title,
            lesson_path=chapter.lesson_path,
            content=content,
            word_count=_word_count(content),
        )
    raise StudyMaterialNotFoundError("Published study material was not found.")


def _course_glossary(course_root: Path, course: StudyCourse) -> tuple[list[StudyGlossaryTerm], list[str]]:
    glossary_path = course_root / "lessons" / "glossary.json"
    try:
        too_large = glossary_path.stat().st_size > MAX_GLOSSARY_BYTES
    except OSError:
        too_large = False
    payload = None if too_large else _read_json(glossary_path, course_root)
    if payload is None or payload.get("schema_version") != "course-glossary-v1":
        return [], ["No readable glossary has been published for this course."]

    known_chapters = {chapter.chapter_id for chapter in course.chapters}
    terms: list[StudyGlossaryTerm] = []
    seen: set[str] = set()
    raw_terms = payload.get("terms")
    if not isinstance(raw_terms, list):
        raw_terms = []
    for index, raw in enumerate(raw_terms[:500]):
        if not isinstance(raw, dict):
            continue
        term = str(raw.get("term") or "").strip()
        definition = str(raw.get("definition") or "").strip()
        key = term.casefold()
        if not term or not definition or key in seen:
            continue
        aliases = raw.get("aliases")
        chapter_ids = raw.get("chapter_ids")
        source_refs = raw.get("source_refs")
        terms.append(
            StudyGlossaryTerm(
                term_id=str(raw.get("term_id") or f"TERM-{index + 1:03d}"),
                term=term,
                definition=definition,
                aliases=[str(alias).strip() for alias in aliases if str(alias).strip()][:12]
                if isinstance(aliases, list)
                else [],
                chapter_ids=[str(chapter_id) for chapter_id in chapter_ids if str(chapter_id) in known_chapters]
                if isinstance(chapter_ids, list)
                else [],
                source_count=sum(isinstance(ref, dict) for ref in source_refs)
                if isinstance(source_refs, list)
                else 0,
            )
        )
        seen.add(key)
    terms.sort(key=lambda item: item.term.casefold())
    return terms, []


def study_glossary(workspace: WorkspaceState, course_id: str) -> StudyGlossaryResult:
    for course_root in _course_roots(Path(workspace.path)):
        course, _ = _course_record(course_root)
        if course is None or course.course_id != course_id:
            continue
        terms, warnings = _course_glossary(course_root, course)
        return StudyGlossaryResult(
            course_id=course.course_id,
            course_title=course.title,
            terms=terms,
            warnings=warnings,
        )
    raise StudyMaterialNotFoundError("Published course glossary was not found.")


def glossary_index(
    workspace: WorkspaceState,
    *,
    course_id: str | None = None,
    query: str = "",
    offset: int = 0,
    limit: int = 100,
) -> GlossaryIndexResult:
    courses: list[GlossaryCourseSummary] = []
    terms: list[GlossaryIndexTerm] = []
    warnings: list[str] = []
    matched_course = course_id is None
    for course_root in _course_roots(Path(workspace.path)):
        course, course_warnings = _course_record(course_root)
        warnings.extend(course_warnings)
        if course is None:
            continue
        course_terms, glossary_warnings = _course_glossary(course_root, course)
        courses.append(
            GlossaryCourseSummary(course_id=course.course_id, title=course.title, term_count=len(course_terms))
        )
        warnings.extend(f"{course.title}: {warning}" for warning in glossary_warnings)
        if course.course_id != course_id and course_id is not None:
            continue
        matched_course = True
        chapter_titles = {chapter.chapter_id: chapter.title for chapter in course.chapters}
        terms.extend(
            GlossaryIndexTerm(
                **term.model_dump(),
                course_id=course.course_id,
                course_title=course.title,
                chapters=[
                    GlossaryChapterLink(chapter_id=chapter_id, title=chapter_titles[chapter_id])
                    for chapter_id in term.chapter_ids
                    if chapter_id in chapter_titles
                ],
            )
            for term in course_terms
        )
    if not matched_course:
        raise StudyMaterialNotFoundError("Published course glossary was not found.")

    normalized_query = query.strip().casefold()
    if normalized_query:
        terms = [
            term
            for term in terms
            if normalized_query in " ".join([term.term, term.definition, *term.aliases]).casefold()
        ]
    courses.sort(key=lambda item: item.title.casefold())
    terms.sort(key=lambda item: (item.term.casefold(), item.course_title.casefold()))
    total_terms = len(terms)
    page = terms[offset : offset + limit]
    return GlossaryIndexResult(
        workspace=workspace,
        courses=courses,
        selected_course_id=course_id,
        query=query.strip(),
        total_terms=total_terms,
        offset=offset,
        limit=limit,
        has_more=offset + len(page) < total_terms,
        terms=page,
        warnings=warnings,
    )
