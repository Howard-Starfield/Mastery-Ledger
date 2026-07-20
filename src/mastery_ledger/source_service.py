from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from mastery_ledger.dashboard import _course_roots, _manifest, _read_yaml
from mastery_ledger.database import enqueue_job, list_jobs, read_setting, update_job
from mastery_ledger.models import (
    IngestionJobView,
    SourceInboxCourse,
    SourceInboxResult,
    SourceIntakeRequest,
    SourceIntakeResult,
    SourceSummary,
    WorkspaceState,
)
from mastery_ledger.runtime import capabilities

REMOTE_TYPES = {"web_article", "remote_video"}
MEDIA_RIGHTS = {
    "user_owned",
    "platform_permitted_download",
    "public_license",
    "explicit_permission",
}
TERMINAL_STATES = {"complete", "partial", "needs_user_action", "failed", "cancelled"}
_EVENT_LOCK = threading.Lock()


class SourceIntakeError(ValueError):
    """Raised when source intake would violate a workspace or rights boundary."""


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _slug(value: str, *, fallback: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return (normalized or fallback)[:80]


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except (OSError, ValueError):
        return False


def _atomic_text(path: Path, content: str, root: Path) -> None:
    if not _inside(root, path) or path.is_symlink():
        raise SourceIntakeError("Refused to write outside the registered course folder.")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: Path, payload: dict[str, Any], root: Path) -> None:
    _atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n", root)


def atomic_yaml(path: Path, payload: dict[str, Any], root: Path) -> None:
    _atomic_text(path, yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), root)


def append_event(course_root: Path, event: dict[str, Any]) -> None:
    path = course_root / "logs" / "events.jsonl"
    if not _inside(course_root, path) or path.is_symlink():
        raise SourceIntakeError("The course event log is outside the course boundary.")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "event_id": f"EVT-{uuid.uuid4().hex[:16].upper()}",
        "schema_version": "action-event-v1",
        "timestamp": _timestamp(),
        **event,
    }
    with _EVENT_LOCK, path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _manifest_path(course_root: Path) -> Path:
    return course_root / "source-manifest.yaml"


def load_source_manifest(course_root: Path) -> dict[str, Any]:
    path = _manifest_path(course_root)
    if not path.exists():
        legacy = course_root / "source" / "source-manifest.yaml"
        if legacy.is_file() and not legacy.is_symlink():
            path = legacy
    if not path.exists():
        manifest = _manifest(course_root) or {}
        return {
            "schema_version": "source-manifest-v1",
            "course_id": str(manifest.get("course_id") or manifest.get("study_id") or course_root.name),
            "sources": [],
        }
    payload = _read_yaml(path, course_root)
    if payload is None or not isinstance(payload.get("sources", []), list):
        raise SourceIntakeError(f"Source manifest is malformed: {path}")
    return payload


def save_source_manifest(course_root: Path, payload: dict[str, Any]) -> None:
    payload["schema_version"] = "source-manifest-v1"
    payload["updated_at"] = _timestamp()
    atomic_yaml(_manifest_path(course_root), payload, course_root)


def _course_by_id(workspace_root: Path, course_id: str) -> tuple[Path, dict[str, Any]] | None:
    for course_root in _course_roots(workspace_root):
        manifest = _manifest(course_root)
        if manifest is None:
            continue
        candidate = str(manifest.get("course_id") or manifest.get("study_id") or course_root.name)
        if candidate == course_id:
            return course_root, manifest
    return None


def _create_course(workspace_root: Path, title: str) -> tuple[Path, dict[str, Any]]:
    courses_root = workspace_root / "courses"
    courses_root.mkdir(parents=True, exist_ok=True)
    base_slug = _slug(title, fallback="course")
    course_root = courses_root / base_slug
    suffix = 2
    while course_root.exists():
        course_root = courses_root / f"{base_slug}-{suffix}"
        suffix += 1
    course_root.mkdir(parents=False)
    course_id = f"COURSE-{uuid.uuid4().hex[:10].upper()}"
    timestamp = _timestamp()
    manifest = {
        "schema_version": "course-v1",
        "course_id": course_id,
        "title": title.strip(),
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    atomic_yaml(course_root / "course.yaml", manifest, course_root)
    (course_root / "source" / "media").mkdir(parents=True)
    (course_root / ".work" / "ingestion").mkdir(parents=True)
    (course_root / "logs").mkdir(parents=True)
    return course_root, manifest


def _validate_location(request: SourceIntakeRequest) -> str:
    location = request.location.strip()
    if request.source_type in REMOTE_TYPES:
        parsed = urlparse(location)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise SourceIntakeError("Remote sources require a public HTTP or HTTPS URL without credentials.")
        if request.source_type == "remote_video" and request.rights_basis not in MEDIA_RIGHTS:
            raise SourceIntakeError("Remote video requires an explicit permitted rights basis.")
        return location

    path = Path(location).expanduser()
    if not path.is_absolute():
        raise SourceIntakeError("Local sources require an absolute file path.")
    try:
        path = path.resolve(strict=True)
    except OSError as error:
        raise SourceIntakeError(f"The local source could not be resolved: {error}") from error
    if not path.is_file() or path.is_symlink():
        raise SourceIntakeError("The local source must be a regular file, not a folder or symbolic link.")
    if request.rights_basis not in MEDIA_RIGHTS:
        raise SourceIntakeError("Local files require user-owned or explicitly permitted rights.")
    return str(path)


def _source_title(request: SourceIntakeRequest, location: str) -> str:
    if request.title and request.title.strip():
        return request.title.strip()
    if request.source_type in REMOTE_TYPES:
        parsed = urlparse(location)
        return Path(parsed.path).stem.replace("-", " ").strip().title() or parsed.hostname or "Web source"
    return Path(location).stem.replace("-", " ").replace("_", " ").strip().title()


def _job_view(job: dict[str, object]) -> IngestionJobView | None:
    payload = job.get("payload")
    if not isinstance(payload, dict):
        return None
    try:
        return IngestionJobView(
            job_id=str(job["job_id"]),
            kind=str(job["kind"]),
            state=str(job["state"]),
            course_id=str(payload["course_id"]),
            source_id=str(payload["source_id"]),
            progress=float(payload.get("progress", 0.0)),
            stage=str(payload.get("stage", "queued")),
            error_code=str(payload["error_code"]) if payload.get("error_code") else None,
            recovery_suggestion=(
                str(payload["recovery_suggestion"])
                if payload.get("recovery_suggestion")
                else None
            ),
            created_at=str(job["created_at"]),
            updated_at=str(job["updated_at"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def queue_source(workspace: WorkspaceState, request: SourceIntakeRequest) -> SourceIntakeResult:
    workspace_root = Path(workspace.path)
    location = _validate_location(request)
    if request.course_id:
        found = _course_by_id(workspace_root, request.course_id)
        if found is None:
            raise SourceIntakeError("The selected course does not exist in the active workspace.")
        course_root, course_manifest = found
    elif request.new_course_title and request.new_course_title.strip():
        course_root, course_manifest = _create_course(workspace_root, request.new_course_title.strip())
    else:
        raise SourceIntakeError("Select an existing course or provide a title for a new course.")

    course_id = str(course_manifest.get("course_id") or course_manifest.get("study_id"))
    source_id = f"SRC-{uuid.uuid4().hex[:12].upper()}"
    title = _source_title(request, location)
    processing_mode = str(read_setting("processing_mode", "local_only"))
    timestamp = _timestamp()
    source_record = {
        "source_id": source_id,
        "title": title,
        "provider": "remote" if request.source_type in REMOTE_TYPES else "local",
        "source_type": request.source_type,
        "original_location": location,
        "local_path": None,
        "retrieved_at": None,
        "content_hash": None,
        "language": request.language,
        "rights_basis": request.rights_basis,
        "permitted_uses": ["personal_study", "derived_notes"]
        + (["transcription"] if request.allow_transcription else []),
        "processing_mode": processing_mode,
        "processing_status": "queued",
        "knowledge_path": None,
        "artifacts": [],
        "created_at": timestamp,
        "updated_at": timestamp,
        "error_code": None,
        "recovery_suggestion": None,
    }
    manifest = load_source_manifest(course_root)
    sources = manifest.setdefault("sources", [])
    if not isinstance(sources, list):
        raise SourceIntakeError("The source manifest has an invalid sources list.")
    sources.append(source_record)
    save_source_manifest(course_root, manifest)

    job_payload: dict[str, object] = {
        "schema_version": "ingestion-job-v1",
        "workspace_id": workspace.workspace_id,
        "workspace_path": workspace.path,
        "course_id": course_id,
        "source_id": source_id,
        "source_type": request.source_type,
        "location": location,
        "title": title,
        "rights_basis": request.rights_basis,
        "language": request.language,
        "allow_transcription": request.allow_transcription,
        "processing_mode": processing_mode,
        "progress": 0.0,
        "stage": "queued",
        "error_code": None,
        "recovery_suggestion": None,
        "attempt_count": 0,
        "cancellation_requested": False,
    }
    try:
        job_id = enqueue_job("source_ingestion", job_payload)
    except Exception as error:
        source_record["processing_status"] = "failed"
        source_record["error_code"] = "job_enqueue_failed"
        source_record["recovery_suggestion"] = "Retry after repairing the application database."
        save_source_manifest(course_root, manifest)
        raise SourceIntakeError(f"The ingestion job could not be created: {error}") from error
    append_event(
        course_root,
        {
            "action": "source.ingest.queued",
            "actor": "application",
            "status": "queued",
            "summary": f"Queued {request.source_type} source for processing.",
            "artifacts": ["source-manifest.yaml"],
            "source_id": source_id,
            "job_id": job_id,
        },
    )
    job = IngestionJobView(
        job_id=job_id,
        kind="source_ingestion",
        state="queued",
        course_id=course_id,
        source_id=source_id,
        progress=0.0,
        stage="queued",
        created_at=timestamp,
        updated_at=timestamp,
    )
    return SourceIntakeResult(course_id=course_id, source_id=source_id, job=job)


def update_source_record(
    course_root: Path,
    source_id: str,
    updates: dict[str, object],
) -> dict[str, Any]:
    manifest = load_source_manifest(course_root)
    sources = manifest.get("sources", [])
    record = next(
        (item for item in sources if isinstance(item, dict) and str(item.get("source_id")) == source_id),
        None,
    )
    if record is None:
        raise SourceIntakeError(f"Source {source_id} is missing from its manifest.")
    record.update(updates)
    record["updated_at"] = _timestamp()
    save_source_manifest(course_root, manifest)
    return record


def source_inbox(workspace: WorkspaceState) -> SourceInboxResult:
    workspace_root = Path(workspace.path)
    courses: list[SourceInboxCourse] = []
    sources: list[SourceSummary] = []
    for course_root in _course_roots(workspace_root):
        course_manifest = _manifest(course_root)
        if course_manifest is None:
            continue
        course_id = str(
            course_manifest.get("course_id") or course_manifest.get("study_id") or course_root.name
        )
        course_title = str(course_manifest.get("title") or course_root.name.replace("-", " ").title())
        try:
            source_manifest = load_source_manifest(course_root)
        except SourceIntakeError:
            source_manifest = {"sources": []}
        records = [item for item in source_manifest.get("sources", []) if isinstance(item, dict)]
        courses.append(
            SourceInboxCourse(
                course_id=course_id,
                title=course_title,
                source_count=len(records),
                ready_count=sum(1 for item in records if item.get("processing_status") == "ready"),
            )
        )
        for record in records:
            raw_type = str(record.get("source_type") or "local_document")
            if raw_type not in {
                "web_article", "remote_video", "local_document", "local_media", "local_subtitle"
            }:
                raw_type = "local_document"
            raw_rights = str(record.get("rights_basis") or "web_reference")
            if raw_rights not in MEDIA_RIGHTS | {"web_reference"}:
                raw_rights = "web_reference"
            artifacts = record.get("artifacts", [])
            sources.append(
                SourceSummary(
                    source_id=str(record.get("source_id") or "unknown"),
                    course_id=course_id,
                    title=str(record.get("title") or record.get("source_id") or "Untitled source"),
                    source_type=raw_type,
                    original_location=str(record.get("original_location") or ""),
                    processing_status=str(record.get("processing_status") or "unknown"),
                    rights_basis=raw_rights,
                    language=str(record.get("language") or "und"),
                    retrieved_at=str(record["retrieved_at"]) if record.get("retrieved_at") else None,
                    content_hash=str(record["content_hash"]) if record.get("content_hash") else None,
                    knowledge_path=str(record["knowledge_path"]) if record.get("knowledge_path") else None,
                    artifact_count=len(artifacts) if isinstance(artifacts, list) else 0,
                    error_code=str(record["error_code"]) if record.get("error_code") else None,
                    recovery_suggestion=(
                        str(record["recovery_suggestion"])
                        if record.get("recovery_suggestion")
                        else None
                    ),
                )
            )
    views = [view for job in list_jobs(limit=1000) if (view := _job_view(job)) is not None]
    views = [view for view in views if any(course.course_id == view.course_id for course in courses)]
    courses.sort(key=lambda item: item.title.casefold())
    sources.sort(key=lambda item: (item.course_id, item.title.casefold()))
    return SourceInboxResult(courses=courses, sources=sources, jobs=views, capabilities=capabilities())


def fail_job(job: dict[str, object], *, code: str, suggestion: str) -> None:
    payload = job.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    payload.update(
        {
            "progress": 1.0,
            "stage": "failed",
            "error_code": code,
            "recovery_suggestion": suggestion,
        }
    )
    update_job(str(job["job_id"]), state="failed", payload=payload)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"
