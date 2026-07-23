from __future__ import annotations

import hashlib
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
MAX_RUNTIME_STATE_FILES = 2_000
MAX_ENTRY_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
ROOT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PATH_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ALLOWED_SUFFIXES = {".json", ".jsonl", ".md", ".txt", ".yaml", ".yml"}
ALLOWED_ROOT_FILES = {"index.md", "study.yaml"}
ALLOWED_ROOT_DIRECTORIES = {"exams", "lessons", "progress", "questions", "records"}
PRACTICE_EXAM_PATH = "exams/PRACTICE-001/exam.json"
ARTIFACT_HASH_MANIFEST_PATH = "records/evidence/validation/artifact-hashes.json"
VALIDATION_CHECK_PATHS = {
    "records/evidence/validation/assessment-check.json",
    "records/evidence/validation/citation-check.json",
    "records/evidence/validation/contradiction-check.json",
    "records/evidence/validation/lesson-check.json",
}
BASE_REQUIRED_FILES = {
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
REQUIRED_FILES = BASE_REQUIRED_FILES | {PRACTICE_EXAM_PATH}
REQUIRED_ARTIFACT_PATHS = {
    "course_index": "index.md",
    "source_manifest": "records/source-manifest.yaml",
    "source": "records/source",
    "lessons": "lessons",
    "question_bank": "questions/question-bank.json",
    "question_bank_review": "questions/question-bank.md",
    "practice_exam": PRACTICE_EXAM_PATH,
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


def _validate_artifact_hash_manifest(
    root: Path,
    present: set[str],
    artifact_paths: dict[str, Any],
    study_id: str,
) -> None:
    manifest_present = ARTIFACT_HASH_MANIFEST_PATH in present
    declared_path = artifact_paths.get("artifact_hashes")
    if not manifest_present:
        if declared_path is not None:
            raise CourseImportError(
                f"study.yaml artifact_paths.artifact_hashes declares missing {ARTIFACT_HASH_MANIFEST_PATH}"
            )
        return
    if declared_path != ARTIFACT_HASH_MANIFEST_PATH:
        raise CourseImportError(
            f"study.yaml artifact_paths.artifact_hashes must be {ARTIFACT_HASH_MANIFEST_PATH}"
        )

    manifest = _load_json(root / ARTIFACT_HASH_MANIFEST_PATH, ARTIFACT_HASH_MANIFEST_PATH)
    if manifest.get("schema_version") != "artifact-hash-manifest-v1":
        raise CourseImportError(f"{ARTIFACT_HASH_MANIFEST_PATH} has an unsupported schema_version")
    if manifest.get("study_id") != study_id:
        raise CourseImportError(f"{ARTIFACT_HASH_MANIFEST_PATH} study_id must match study.yaml")
    if manifest.get("hash_algorithm") != "sha256":
        raise CourseImportError(f"{ARTIFACT_HASH_MANIFEST_PATH} hash_algorithm must be sha256")
    if manifest.get("file_digest_recipe") != "sha256-raw-bytes-v1":
        raise CourseImportError(
            f"{ARTIFACT_HASH_MANIFEST_PATH} file_digest_recipe must be sha256-raw-bytes-v1"
        )
    if manifest.get("group_digest_recipe") != "sorted-path-tab-sha256-lf-v1":
        raise CourseImportError(
            f"{ARTIFACT_HASH_MANIFEST_PATH} group_digest_recipe must be sorted-path-tab-sha256-lf-v1"
        )
    groups = manifest.get("groups")
    if not isinstance(groups, list) or not groups:
        raise CourseImportError(f"{ARTIFACT_HASH_MANIFEST_PATH} groups must be a non-empty list")

    source_inputs = {
        relative for relative in present if relative.startswith("records/source/")
    } | {"records/source-manifest.yaml"}
    lesson_inputs = {
        relative
        for relative in present
        if relative.startswith("lessons/") and relative.endswith(".md")
    }
    required_members_by_check = {
        "records/evidence/validation/contradiction-check.json": source_inputs
        | {"records/evidence/claim-ledger.json"},
        "records/evidence/validation/citation-check.json": source_inputs
        | lesson_inputs
        | {
            "exams/PRACTICE-001/exam.json",
            "lessons/glossary.json",
            "questions/question-bank.json",
            "records/evidence/approved-claims.json",
        },
        "records/evidence/validation/lesson-check.json": source_inputs
        | lesson_inputs
        | {"records/evidence/approved-claims.json"},
        "records/evidence/validation/assessment-check.json": source_inputs
        | lesson_inputs
        | {
            "exams/PRACTICE-001/exam.json",
            "questions/question-bank.json",
            "records/evidence/approved-claims.json",
        },
    }

    by_check: dict[str, tuple[str, str]] = {}
    seen_group_ids: set[str] = set()
    for group_index, group in enumerate(groups):
        label = f"{ARTIFACT_HASH_MANIFEST_PATH} groups[{group_index}]"
        if not isinstance(group, dict):
            raise CourseImportError(f"{label} must be an object")
        group_id = str(group.get("group_id") or "").strip()
        check_path = str(group.get("check_path") or "").replace("\\", "/")
        if not group_id or group_id in seen_group_ids:
            raise CourseImportError(f"{label} has a missing or duplicate group_id")
        if check_path not in VALIDATION_CHECK_PATHS or check_path in by_check:
            raise CourseImportError(f"{label}.check_path must uniquely name one final validation check")
        seen_group_ids.add(group_id)
        members = group.get("members")
        if not isinstance(members, list) or not members:
            raise CourseImportError(f"{label}.members must be a non-empty list")

        member_lines: list[str] = []
        member_paths: list[str] = []
        for member_index, member in enumerate(members):
            member_label = f"{label}.members[{member_index}]"
            if not isinstance(member, dict):
                raise CourseImportError(f"{member_label} must be an object")
            raw_path = str(member.get("path") or "")
            path = PurePosixPath(raw_path)
            if (
                not raw_path
                or "\\" in raw_path
                or path.is_absolute()
                or ".." in path.parts
                or path.as_posix() != raw_path
                or raw_path not in present
            ):
                raise CourseImportError(f"{member_label}.path must name an existing safe course file")
            if raw_path == ARTIFACT_HASH_MANIFEST_PATH or raw_path in VALIDATION_CHECK_PATHS:
                raise CourseImportError(f"{member_label}.path may not create a hash cycle")
            digest = str(member.get("sha256") or "")
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise CourseImportError(f"{member_label}.sha256 must be 64 lowercase hexadecimal characters")
            target = root.joinpath(*path.parts)
            data = target.read_bytes()
            if member.get("bytes") != len(data):
                raise CourseImportError(f"{member_label}.bytes does not match the current file")
            if hashlib.sha256(data).hexdigest() != digest:
                raise CourseImportError(f"{member_label}.sha256 does not match the current file")
            member_paths.append(raw_path)
            member_lines.append(f"{raw_path}\t{digest}\n")

        if member_paths != sorted(member_paths) or len(member_paths) != len(set(member_paths)):
            raise CourseImportError(f"{label}.members must use unique paths in ordinal sorted order")
        missing_members = sorted(required_members_by_check[check_path] - set(member_paths))
        if missing_members:
            raise CourseImportError(
                f"{label}.members is missing required check inputs: {', '.join(missing_members)}"
            )
        group_digest = hashlib.sha256("".join(member_lines).encode("utf-8")).hexdigest()
        if group.get("group_sha256") != group_digest:
            raise CourseImportError(f"{label}.group_sha256 does not match its members")
        by_check[check_path] = (group_id, group_digest)

    if set(by_check) != VALIDATION_CHECK_PATHS:
        raise CourseImportError(f"{ARTIFACT_HASH_MANIFEST_PATH} must cover all four validation checks")
    for check_path, (group_id, group_digest) in by_check.items():
        receipt = _load_json(root / check_path, check_path)
        if receipt.get("input_artifact_id") != group_id:
            raise CourseImportError(f"{check_path} input_artifact_id must match its hash group")
        if receipt.get("input_artifact_hash") != group_digest:
            raise CourseImportError(f"{check_path} input_artifact_hash must match its hash group")


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


def _validate_practice_questions(
    questions: list[Any],
    chapter_ids: set[str],
    source_ids: set[str],
) -> None:
    seen_questions: set[str] = set()
    per_chapter: dict[str, list[dict[str, Any]]] = {chapter_id: [] for chapter_id in chapter_ids}
    for index_number, raw in enumerate(questions):
        label = f"question-bank.json questions[{index_number}]"
        if not isinstance(raw, dict):
            raise CourseImportError(f"{label} must be an object")
        question_id = str(raw.get("question_id") or "").strip()
        chapter_id = str(raw.get("chapter_id") or "").strip()
        if not question_id or question_id in seen_questions:
            raise CourseImportError(f"{label} has a missing or duplicate question_id")
        if chapter_id not in chapter_ids:
            raise CourseImportError(f"{label} references an unknown chapter_id")
        seen_questions.add(question_id)
        per_chapter[chapter_id].append(raw)
        if raw.get("type") not in {"standalone_mcq", "scenario_mcq"}:
            raise CourseImportError(f"{label}.type must be standalone_mcq or scenario_mcq")
        if not isinstance(raw.get("prompt"), str) or not str(raw["prompt"]).strip():
            raise CourseImportError(f"{label} requires a prompt")
        options = raw.get("options")
        if not isinstance(options, list) or len(options) != 4:
            raise CourseImportError(f"{label} must contain exactly four options")
        option_ids: list[str] = []
        for option_index, option in enumerate(options):
            if not isinstance(option, dict):
                raise CourseImportError(f"{label}.options[{option_index}] must be an object")
            option_id = str(option.get("option_id") or "").strip()
            if not option_id or not isinstance(option.get("text"), str) or not str(option["text"]).strip():
                raise CourseImportError(f"{label}.options[{option_index}] requires option_id and text")
            if not isinstance(option.get("rationale"), str) or not str(option["rationale"]).strip():
                raise CourseImportError(f"{label}.options[{option_index}] requires a rationale")
            option_ids.append(option_id)
        if option_ids != ["A", "B", "C", "D"]:
            raise CourseImportError(f"{label} options must use ordered IDs A, B, C, D")
        if raw.get("correct_option_id") not in option_ids:
            raise CourseImportError(f"{label} has an invalid correct_option_id")
        if not isinstance(raw.get("explanation"), str) or not str(raw["explanation"]).strip():
            raise CourseImportError(f"{label} requires an explanation")
        if raw.get("quality_status") != "draft":
            raise CourseImportError(f"{label}.quality_status must remain draft")
        refs = raw.get("source_refs")
        if not isinstance(refs, list) or not refs:
            raise CourseImportError(f"{label} requires source_refs")
        supported_targets: set[str] = set()
        for ref_index, ref in enumerate(refs):
            if not isinstance(ref, dict) or str(ref.get("source_id") or "") not in source_ids:
                raise CourseImportError(f"{label}.source_refs[{ref_index}] references an unknown source")
            locator = ref.get("locator")
            supports = ref.get("supports")
            if not isinstance(locator, dict) or not isinstance(locator.get("kind"), str) or not isinstance(locator.get("label"), str):
                raise CourseImportError(f"{label}.source_refs[{ref_index}] has an invalid locator")
            if not isinstance(supports, list) or not supports:
                raise CourseImportError(f"{label}.source_refs[{ref_index}] lacks assessment support targets")
            supported_targets.update(str(target) for target in supports)
            if ref.get("support_strength") not in {"direct", "partial", "contextual"}:
                raise CourseImportError(f"{label}.source_refs[{ref_index}] has invalid support_strength")
        if not {"question_prompt", "correct_answer", "explanation"}.issubset(supported_targets):
            raise CourseImportError(f"{label}.source_refs do not support the prompt, answer, and explanation")

    for chapter_id, chapter_questions in per_chapter.items():
        if len(chapter_questions) != 10:
            raise CourseImportError(f"Chapter {chapter_id} must contain exactly ten practice questions")
        type_counts = {
            question_type: sum(question.get("type") == question_type for question in chapter_questions)
            for question_type in ("standalone_mcq", "scenario_mcq")
        }
        if type_counts != {"standalone_mcq": 8, "scenario_mcq": 2}:
            raise CourseImportError(f"Chapter {chapter_id} must contain eight standalone and two scenario questions")
        positions = [str(question["correct_option_id"]) for question in chapter_questions]
        if any(positions.count(option_id) not in {2, 3} for option_id in ("A", "B", "C", "D")):
            raise CourseImportError(f"Chapter {chapter_id} has unbalanced correct-option positions")
        if any(positions[index] == positions[index + 1] == positions[index + 2] for index in range(8)):
            raise CourseImportError(f"Chapter {chapter_id} repeats one correct option three times consecutively")


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


def validate_course_folder(
    root: Path,
    *,
    allow_runtime_state: bool = False,
    require_practice: bool = True,
) -> dict[str, str]:
    """Validate an extracted ChatGPT course folder without modifying it."""
    if not root.is_dir() or root.is_symlink():
        raise CourseImportError("Course folder must be a normal directory")

    present: set[str] = set()
    total_bytes = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise CourseImportError(f"Course folder may not contain symlinks: {path.relative_to(root).as_posix()}")
        if not path.is_file():
            continue
        relative = PurePosixPath(path.relative_to(root).as_posix())
        max_entries = MAX_ENTRIES + (MAX_RUNTIME_STATE_FILES if allow_runtime_state else 0)
        if len(present) >= max_entries:
            raise CourseImportError(f"Course folder exceeds the {max_entries}-file limit")
        if any(not PATH_COMPONENT.fullmatch(part) or part in {".", ".."} for part in relative.parts):
            raise CourseImportError(f"Course folder contains an unsafe path: {relative}")
        is_runtime_attempt = relative.parts[0] == "attempts"
        if is_runtime_attempt:
            if not allow_runtime_state:
                raise CourseImportError("Course bundles may not contain saved attempts")
            if len(relative.parts) != 2 or relative.suffix.casefold() != ".json":
                raise CourseImportError(f"Unsupported saved-attempt path: {relative}")
        elif len(relative.parts) == 1:
            if relative.as_posix() not in ALLOWED_ROOT_FILES:
                raise CourseImportError(f"Unsupported file at the course root: {relative}")
        elif relative.parts[0] not in ALLOWED_ROOT_DIRECTORIES:
            raise CourseImportError(f"Unsupported course directory: {relative.parts[0]}")
        elif relative.parts[0] == "exams" and relative.as_posix() != PRACTICE_EXAM_PATH:
            raise CourseImportError(f"AI self-checked bundles may contain only {PRACTICE_EXAM_PATH}")
        if relative.suffix.casefold() not in ALLOWED_SUFFIXES:
            raise CourseImportError(f"Unsupported course file type: {relative}")
        size = path.stat().st_size
        if size > MAX_ENTRY_BYTES:
            raise CourseImportError(f"Course file exceeds {MAX_ENTRY_BYTES} bytes: {relative}")
        total_bytes += size
        if total_bytes > MAX_UNCOMPRESSED_BYTES:
            raise CourseImportError("Course folder exceeds the uncompressed size limit")
        present.add(relative.as_posix())
    practice_present = PRACTICE_EXAM_PATH in present
    required_files = REQUIRED_FILES if require_practice else BASE_REQUIRED_FILES
    missing = sorted(required_files - present)
    if missing:
        raise CourseImportError("Course is missing required files: " + ", ".join(missing))

    study = _load_yaml(root / "study.yaml", "study.yaml")
    if study.get("schema_version") != "1.0":
        raise CourseImportError("study.yaml schema_version must be \"1.0\"")
    if study.get("layout_schema") != LAYOUT_SCHEMA:
        raise CourseImportError(f"study.yaml layout_schema must be {LAYOUT_SCHEMA}")
    if study.get("bundle_schema") != BUNDLE_SCHEMA:
        raise CourseImportError(f"study.yaml bundle_schema must be {BUNDLE_SCHEMA}")
    if study.get("workflow_state") != "STUDY_PACK_DRAFTED":
        raise CourseImportError("AI self-checked courses must use workflow_state STUDY_PACK_DRAFTED")
    if study.get("publication_status") != "DRAFT_UNVERIFIED":
        raise CourseImportError("AI self-checked courses must retain publication_status DRAFT_UNVERIFIED")
    study_id = str(study.get("study_id") or "").strip()
    title = str(study.get("title") or "").strip()
    if not study_id or not title:
        raise CourseImportError("study.yaml requires study_id and title")
    artifact_paths = study.get("artifact_paths")
    if not isinstance(artifact_paths, dict):
        raise CourseImportError("study.yaml artifact_paths must be an object")
    required_artifact_paths = REQUIRED_ARTIFACT_PATHS.items()
    for key, expected in required_artifact_paths:
        if key == "practice_exam" and not (require_practice or practice_present):
            continue
        if artifact_paths.get(key) != expected:
            raise CourseImportError(f"study.yaml artifact_paths.{key} must be {expected}")
    _validate_artifact_hash_manifest(root, present, artifact_paths, study_id)

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
    if practice_present:
        if progress.get("applied_attempt_ids") not in (None, []):
            raise CourseImportError("AI self-checked courses may not import applied mastery attempts")
        if "progress/review-queue.json" in present:
            raise CourseImportError("AI self-checked courses may not import a review queue")
        for index_number, concept in enumerate(progress["concepts"]):
            if not isinstance(concept, dict):
                raise CourseImportError(f"learner-progress.json concepts[{index_number}] must be an object")
            if concept.get("status") not in {"unseen", "introduced"}:
                raise CourseImportError(f"learner-progress.json concepts[{index_number}] may not seed mastery")
            for key, value in concept.items():
                if (key.endswith("_score") or key.endswith("_count")) and value not in (0, 0.0, None):
                    raise CourseImportError(f"learner-progress.json concepts[{index_number}].{key} must be zero")
            for key in ("evidence", "misconceptions"):
                if concept.get(key) not in (None, []):
                    raise CourseImportError(f"learner-progress.json concepts[{index_number}].{key} must be empty")
            for key in ("last_reviewed_at", "next_review_at"):
                if concept.get(key) is not None:
                    raise CourseImportError(f"learner-progress.json concepts[{index_number}].{key} must be null")

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

    if practice_present:
        _validate_practice_questions(questions, seen_chapters, source_ids)

        practice = _load_json(root / PRACTICE_EXAM_PATH, PRACTICE_EXAM_PATH)
        if practice.get("schema_version") != "exam-v1":
            raise CourseImportError(f"{PRACTICE_EXAM_PATH} schema_version must be exam-v1")
        if practice.get("exam_id") != "PRACTICE-001" or practice.get("course_id") != study_id:
            raise CourseImportError(f"{PRACTICE_EXAM_PATH} must use PRACTICE-001 and the matching course_id")
        if practice.get("status") != "practice_ready":
            raise CourseImportError(f"{PRACTICE_EXAM_PATH} status must be practice_ready")
        if practice.get("verification_status") != "self_checked":
            raise CourseImportError(f"{PRACTICE_EXAM_PATH} verification_status must be self_checked")
        if practice.get("mastery_eligible") is not False:
            raise CourseImportError(f"{PRACTICE_EXAM_PATH} mastery_eligible must be false")
        if practice.get("questions") != questions:
            raise CourseImportError(f"{PRACTICE_EXAM_PATH} questions must exactly match the canonical question bank")
        if practice.get("question_count") != len(questions):
            raise CourseImportError(f"{PRACTICE_EXAM_PATH} question_count must match its embedded questions")
        if not isinstance(practice.get("estimated_minutes"), int) or practice["estimated_minutes"] < 1:
            raise CourseImportError(f"{PRACTICE_EXAM_PATH} requires positive estimated_minutes")

    for relative in (
        "records/evidence/approved-claims.json",
        "records/evidence/contradictions.json",
        "records/evidence/gaps.json",
    ):
        _load_json(root / relative, relative)
    for relative in (
        "records/evidence/validation/assessment-check.json",
        "records/evidence/validation/citation-check.json",
        "records/evidence/validation/contradiction-check.json",
        "records/evidence/validation/lesson-check.json",
    ):
        check = _load_json(root / relative, relative)
        if practice_present and (
            check.get("review_type") != "same-agent-recheck"
            or check.get("outcome") != "pass_self_check"
        ):
            raise CourseImportError(f"{relative} must record a pass_self_check same-agent recheck")
        if check.get("publication_status") != "DRAFT_UNVERIFIED":
            raise CourseImportError(f"{relative} must retain DRAFT_UNVERIFIED")

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
            metadata = validate_course_folder(staging, require_practice=True)
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
