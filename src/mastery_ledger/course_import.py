from __future__ import annotations

import io
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from mastery_ledger.course_discovery import course_roots


BUNDLE_SCHEMA = "mastery-ledger-course-bundle-v1"
LAYOUT_SCHEMA = "course-layout-v2"
MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_ENTRIES = 500
MAX_ENTRY_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
ROOT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PATH_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ALLOWED_SUFFIXES = {".json", ".jsonl", ".md", ".txt", ".yaml", ".yml"}
ALLOWED_ROOT_FILES = {"index.md", "study.yaml"}
ALLOWED_ROOT_DIRECTORIES = {"lessons", "progress", "questions", "records"}
REQUIRED_FILES = {
    "study.yaml",
    "index.md",
    "lessons/glossary.json",
    "questions/question-bank.json",
    "questions/question-bank.md",
    "progress/learner-progress.json",
    "records/source-manifest.yaml",
    "records/evidence/approved-claims.json",
    "records/evidence/contradictions.json",
    "records/evidence/gaps.json",
    "records/evidence/validation/assessment-check.json",
    "records/evidence/validation/citation-check.json",
    "records/evidence/validation/contradiction-check.json",
    "records/evidence/validation/lesson-check.json",
    "records/logs/events.jsonl",
}
REQUIRED_ARTIFACT_PATHS = {
    "course_index": "index.md",
    "source_manifest": "records/source-manifest.yaml",
    "source": "records/source",
    "lessons": "lessons",
    "question_bank": "questions/question-bank.json",
    "question_bank_review": "questions/question-bank.md",
    "learner_progress": "progress/learner-progress.json",
    "approved_claims": "records/evidence/approved-claims.json",
    "contradictions": "records/evidence/contradictions.json",
    "gaps": "records/evidence/gaps.json",
    "validation": "records/evidence/validation",
    "action_log": "records/logs/events.jsonl",
}


class CourseImportError(ValueError):
    pass


class CourseImportConflictError(CourseImportError):
    pass


def _load_yaml(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise CourseImportError(f"{label} is not valid UTF-8 YAML: {error}") from error
    if not isinstance(payload, dict):
        raise CourseImportError(f"{label} must contain a YAML object")
    return payload


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CourseImportError(f"{label} is not valid UTF-8 JSON: {error}") from error
    if not isinstance(payload, dict):
        raise CourseImportError(f"{label} must contain a JSON object")
    return payload


def _lesson_metadata(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeError) as error:
        raise CourseImportError(f"{label} is not valid UTF-8 Markdown: {error}") from error
    if not content.startswith("---\n"):
        raise CourseImportError(f"{label} must begin with YAML frontmatter")
    boundary = content.find("\n---\n", 4)
    if boundary < 0:
        raise CourseImportError(f"{label} has unterminated YAML frontmatter")
    try:
        metadata = yaml.safe_load(content[4:boundary])
    except yaml.YAMLError as error:
        raise CourseImportError(f"{label} has invalid YAML frontmatter: {error}") from error
    if not isinstance(metadata, dict):
        raise CourseImportError(f"{label} frontmatter must be an object")
    return metadata, content[boundary + 5 :].strip()


def _safe_archive_files(archive: zipfile.ZipFile) -> tuple[str, list[zipfile.ZipInfo]]:
    infos = archive.infolist()
    if not infos or len(infos) > MAX_ENTRIES:
        raise CourseImportError(f"ZIP must contain 1-{MAX_ENTRIES} entries")
    roots: set[str] = set()
    seen: set[str] = set()
    files: list[zipfile.ZipInfo] = []
    uncompressed = 0
    for info in infos:
        if info.flag_bits & 0x1:
            raise CourseImportError("Encrypted ZIP entries are not supported")
        if "\\" in info.filename or "\x00" in info.filename:
            raise CourseImportError(f"Unsafe ZIP path: {info.filename!r}")
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise CourseImportError(f"Unsafe ZIP path: {info.filename!r}")
        if any(not PATH_COMPONENT.fullmatch(part) for part in path.parts):
            raise CourseImportError(f"ZIP path contains an unsupported name: {info.filename!r}")
        roots.add(path.parts[0])
        if info.is_dir():
            continue
        if len(path.parts) < 2:
            raise CourseImportError("Every file must be inside one top-level course folder")
        relative = PurePosixPath(*path.parts[1:])
        if any(part.startswith(".") for part in relative.parts):
            raise CourseImportError(f"Hidden files and directories are not allowed: {relative}")
        if relative.parts[0] not in ALLOWED_ROOT_DIRECTORIES and relative.as_posix() not in ALLOWED_ROOT_FILES:
            raise CourseImportError(f"Unexpected file outside the canonical course layout: {relative}")
        if relative.suffix.casefold() not in ALLOWED_SUFFIXES:
            raise CourseImportError(f"Unsupported file type in course ZIP: {relative}")
        unix_mode = (info.external_attr >> 16) & 0o170000
        if unix_mode == 0o120000:
            raise CourseImportError(f"Symlinks are not allowed in course ZIPs: {relative}")
        key = path.as_posix().casefold()
        if key in seen:
            raise CourseImportError(f"Duplicate or case-colliding ZIP path: {relative}")
        seen.add(key)
        if info.file_size > MAX_ENTRY_BYTES:
            raise CourseImportError(f"ZIP entry exceeds {MAX_ENTRY_BYTES} bytes: {relative}")
        uncompressed += info.file_size
        if uncompressed > MAX_UNCOMPRESSED_BYTES:
            raise CourseImportError("ZIP exceeds the uncompressed size limit")
        files.append(info)
    if len(roots) != 1:
        raise CourseImportError("ZIP must contain exactly one top-level course folder")
    root_name = next(iter(roots))
    if not ROOT_NAME.fullmatch(root_name) or root_name in {".", ".."}:
        raise CourseImportError("The top-level course folder must use letters, digits, dots, underscores, or hyphens")
    return root_name, files


def _extract(archive: zipfile.ZipFile, files: list[zipfile.ZipInfo], staging: Path) -> None:
    for info in files:
        relative = PurePosixPath(*PurePosixPath(info.filename).parts[1:])
        target = staging.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = archive.read(info)
        if len(data) != info.file_size:
            raise CourseImportError(f"ZIP entry size changed while reading: {relative}")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise CourseImportError(f"Course ZIP files must be UTF-8 text: {relative}") from error
        target.write_bytes(data)


def _validate_course(root: Path) -> dict[str, str]:
    present = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    missing = sorted(REQUIRED_FILES - present)
    if missing:
        raise CourseImportError("Course ZIP is missing required files: " + ", ".join(missing))

    study = _load_yaml(root / "study.yaml", "study.yaml")
    if study.get("schema_version") != "1.0":
        raise CourseImportError("study.yaml schema_version must be \"1.0\"")
    if study.get("layout_schema") != LAYOUT_SCHEMA:
        raise CourseImportError(f"study.yaml layout_schema must be {LAYOUT_SCHEMA}")
    if study.get("bundle_schema") != BUNDLE_SCHEMA:
        raise CourseImportError(f"study.yaml bundle_schema must be {BUNDLE_SCHEMA}")
    if study.get("workflow_state") != "STUDY_PACK_DRAFTED":
        raise CourseImportError("Imported ChatGPT courses must use workflow_state STUDY_PACK_DRAFTED")
    if study.get("publication_status") != "DRAFT_UNVERIFIED":
        raise CourseImportError("Imported ChatGPT courses must remain DRAFT_UNVERIFIED")
    study_id = str(study.get("study_id") or "").strip()
    title = str(study.get("title") or "").strip()
    if not study_id or not title:
        raise CourseImportError("study.yaml requires study_id and title")
    artifact_paths = study.get("artifact_paths")
    if not isinstance(artifact_paths, dict):
        raise CourseImportError("study.yaml artifact_paths must be an object")
    for key, expected in REQUIRED_ARTIFACT_PATHS.items():
        if artifact_paths.get(key) != expected:
            raise CourseImportError(f"study.yaml artifact_paths.{key} must be {expected}")

    index = (root / "index.md").read_text(encoding="utf-8").strip()
    if len(index) < 100:
        raise CourseImportError("index.md must be a substantive course map")

    bank = _load_json(root / "questions/question-bank.json", "questions/question-bank.json")
    if bank.get("schema_version") != "question-bank-v2":
        raise CourseImportError("question-bank.json schema_version must be question-bank-v2")
    if bank.get("source_ref_schema") != "source-ref-v1":
        raise CourseImportError("question-bank.json source_ref_schema must be source-ref-v1")
    if bank.get("study_id") != study_id:
        raise CourseImportError("question-bank.json study_id must match study.yaml")
    chapters = bank.get("chapters")
    questions = bank.get("questions")
    if not isinstance(chapters, list) or not chapters:
        raise CourseImportError("question-bank.json must contain at least one chapter")
    if not isinstance(questions, list):
        raise CourseImportError("question-bank.json questions must be a list")
    seen_chapters: set[str] = set()
    for index_number, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            raise CourseImportError(f"question-bank.json chapters[{index_number}] must be an object")
        chapter_id = str(chapter.get("chapter_id") or "").strip()
        lesson_path = str(chapter.get("lesson_path") or "").replace("\\", "/")
        if not chapter_id or chapter_id in seen_chapters:
            raise CourseImportError(f"question-bank.json chapters[{index_number}] has a missing or duplicate chapter_id")
        seen_chapters.add(chapter_id)
        if not re.fullmatch(r"lessons/[A-Za-z0-9._-]+\.md", lesson_path):
            raise CourseImportError(f"question-bank.json chapters[{index_number}].lesson_path is unsafe")
        lesson = root / lesson_path
        if not lesson.is_file():
            raise CourseImportError(f"Missing declared lesson: {lesson_path}")
        metadata, body = _lesson_metadata(lesson, lesson_path)
        if metadata.get("schema_version") != "lesson-v1" or metadata.get("chapter_id") != chapter_id:
            raise CourseImportError(f"{lesson_path} must be lesson-v1 for {chapter_id}")
        if metadata.get("status") != "draft":
            raise CourseImportError(f"{lesson_path} must remain status: draft")
        if len(body) < 100:
            raise CourseImportError(f"{lesson_path} must contain a substantive lesson")

    glossary = _load_json(root / "lessons/glossary.json", "lessons/glossary.json")
    if glossary.get("schema_version") != "course-glossary-v1" or glossary.get("course_id") != study_id:
        raise CourseImportError("lessons/glossary.json must be course-glossary-v1 for this study_id")
    if not isinstance(glossary.get("terms"), list):
        raise CourseImportError("lessons/glossary.json terms must be a list")

    progress = _load_json(root / "progress/learner-progress.json", "progress/learner-progress.json")
    if progress.get("schema_version") != "1.0" or progress.get("study_id") != study_id:
        raise CourseImportError("learner-progress.json must use schema 1.0 and the same study_id")
    if not isinstance(progress.get("concepts"), list):
        raise CourseImportError("learner-progress.json concepts must be a list")

    manifest = _load_yaml(root / "records/source-manifest.yaml", "records/source-manifest.yaml")
    if manifest.get("schema_version") != "1.0" or manifest.get("study_id") != study_id:
        raise CourseImportError("source-manifest.yaml must use schema 1.0 and the same study_id")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise CourseImportError("source-manifest.yaml must contain at least one inspected source")
    source_ids: set[str] = set()
    for index_number, source in enumerate(sources):
        if not isinstance(source, dict):
            raise CourseImportError(f"source-manifest.yaml sources[{index_number}] must be an object")
        source_id = str(source.get("source_id") or "").strip()
        knowledge_path = str(source.get("knowledge_path") or "").replace("\\", "/")
        if not source_id or source_id in source_ids:
            raise CourseImportError(f"source-manifest.yaml sources[{index_number}] has a missing or duplicate source_id")
        source_ids.add(source_id)
        if not re.fullmatch(r"records/source/[A-Za-z0-9._-]+\.md", knowledge_path):
            raise CourseImportError(f"source-manifest.yaml sources[{index_number}].knowledge_path is unsafe")
        source_file = root / knowledge_path
        if not source_file.is_file() or len(source_file.read_text(encoding="utf-8").strip()) < 20:
            raise CourseImportError(f"Missing substantive extracted source: {knowledge_path}")

    for relative in (
        "records/evidence/approved-claims.json",
        "records/evidence/contradictions.json",
        "records/evidence/gaps.json",
        "records/evidence/validation/assessment-check.json",
        "records/evidence/validation/citation-check.json",
        "records/evidence/validation/contradiction-check.json",
        "records/evidence/validation/lesson-check.json",
    ):
        _load_json(root / relative, relative)

    review_copy = (root / "questions/question-bank.md").read_text(encoding="utf-8").strip()
    if len(review_copy) < 20:
        raise CourseImportError("questions/question-bank.md must be a non-empty review copy")
    events = (root / "records/logs/events.jsonl").read_text(encoding="utf-8").splitlines()
    if not events:
        raise CourseImportError("records/logs/events.jsonl must contain at least one event")
    for line_number, line in enumerate(events, 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise CourseImportError(f"events.jsonl line {line_number} is invalid JSON") from error
        if not isinstance(event, dict) or event.get("schema_version") != "action-event-v1":
            raise CourseImportError(f"events.jsonl line {line_number} must be an action-event-v1 object")
    return {"course_id": study_id, "title": title}


def _existing_course_ids(workspace: Path) -> set[str]:
    identifiers: set[str] = set()
    for course in course_roots(workspace):
        for manifest_name in ("study.yaml", "course.yaml"):
            manifest_path = course / manifest_name
            if not manifest_path.is_file():
                continue
            try:
                payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, yaml.YAMLError):
                break
            if isinstance(payload, dict):
                identifier = str(payload.get("study_id") or payload.get("course_id") or "").strip()
                if identifier:
                    identifiers.add(identifier)
            break
    return identifiers


def import_course_zip(workspace: Path, archive_bytes: bytes, *, filename: str) -> dict[str, object]:
    if not filename.casefold().endswith(".zip"):
        raise CourseImportError("Select a .zip course bundle")
    if not archive_bytes:
        raise CourseImportError("Course ZIP is empty")
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise CourseImportError(f"Course ZIP exceeds {MAX_ARCHIVE_BYTES} bytes")
    if not workspace.is_dir() or workspace.is_symlink():
        raise CourseImportError("The active workspace is not an importable directory")
    if (workspace / "study.yaml").is_file() or (workspace / "course.yaml").is_file():
        raise CourseImportError("Select a collection workspace before importing another course")
    existing_course_ids = _existing_course_ids(workspace)

    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as error:
        raise CourseImportError("The selected file is not a valid ZIP archive") from error

    courses_dir = workspace / "courses"
    if courses_dir.exists() and (not courses_dir.is_dir() or courses_dir.is_symlink()):
        raise CourseImportError("workspace/courses must be a normal directory")
    courses_dir.mkdir(exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".course-import-", dir=courses_dir))
    try:
        with archive:
            root_name, files = _safe_archive_files(archive)
            target = courses_dir / root_name
            if target.exists():
                raise CourseImportConflictError(f"A course folder named {root_name} already exists")
            try:
                _extract(archive, files, staging)
            except (OSError, RuntimeError, zipfile.BadZipFile) as error:
                raise CourseImportError(f"Course ZIP could not be read safely: {error}") from error
        try:
            metadata = _validate_course(staging)
        except CourseImportError:
            raise
        except (OSError, UnicodeError) as error:
            raise CourseImportError(f"Course bundle contains unreadable text: {error}") from error
        if str(metadata["course_id"]) in existing_course_ids:
            raise CourseImportConflictError(f"Course ID {metadata['course_id']} already exists in this workspace")
        try:
            staging.rename(target)
        except FileExistsError as error:
            raise CourseImportConflictError(f"A course folder named {root_name} already exists") from error
        return {
            "schema_version": "course-import-v1",
            "status": "imported",
            "course_id": metadata["course_id"],
            "title": metadata["title"],
            "publication_status": "DRAFT_UNVERIFIED",
            "relative_path": f"courses/{root_name}",
        }
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
