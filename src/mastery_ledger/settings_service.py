from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from mastery_ledger.course_discovery import course_roots as _course_roots
from mastery_ledger.database import read_setting, save_settings
from mastery_ledger.models import (
    ApplicationSettings,
    ReviewCurveProfile,
    ReviewCurveUpdateRequest,
    ReviewCurveUpdateResult,
    WorkspaceState,
)

DEFAULT_REVIEW_INTERVALS = [1, 3, 7, 14, 28, 56, 112, 224, 448, 896, 1792, 3584]
DEFAULT_CURVE_ID = "CURVE-OWNERSHIP"


class SettingsUpdateError(RuntimeError):
    """Raised when settings cannot be applied without risking course state."""


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except (OSError, ValueError):
        return False


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def valid_intervals(value: object) -> list[int]:
    if not isinstance(value, list):
        return DEFAULT_REVIEW_INTERVALS.copy()
    intervals = [item for item in value if isinstance(item, int) and not isinstance(item, bool)]
    if (
        not intervals
        or len(intervals) > 24
        or any(day < 1 or day > 36500 for day in intervals)
        or intervals != sorted(set(intervals))
    ):
        return DEFAULT_REVIEW_INTERVALS.copy()
    return intervals


def active_review_curve() -> ReviewCurveProfile:
    fallback_intervals = valid_intervals(read_setting("review_intervals", DEFAULT_REVIEW_INTERVALS))
    payload = read_setting("active_review_curve", None)
    if isinstance(payload, dict):
        try:
            return ReviewCurveProfile.model_validate(payload)
        except ValueError:
            pass
    return ReviewCurveProfile(
        curve_id=DEFAULT_CURVE_ID,
        version=1,
        name="My ownership curve",
        interval_days=fallback_intervals,
        created_at=None,
        supersedes_version=None,
    )


def _review_queue_files(workspace_root: Path) -> list[Path]:
    return [
        path
        for course in _course_roots(workspace_root)
        if (path := course / "progress" / "review-queue.json").is_file()
        and not path.is_symlink()
        and _inside(workspace_root, path)
    ]


def _load_queue(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SettingsUpdateError(f"Could not safely read {path}: {error}") from error
    if not isinstance(payload, dict):
        raise SettingsUpdateError(f"Review queue {path} must contain a JSON object.")
    records = payload.get("questions", [])
    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
        raise SettingsUpdateError(f"Review queue {path} has malformed question records.")
    return payload, records


def scheduled_question_count(workspace_root: Path) -> int:
    total = 0
    for path in _review_queue_files(workspace_root):
        try:
            _, records = _load_queue(path)
        except SettingsUpdateError:
            continue
        total += sum(1 for record in records if record.get("status") != "archived")
    return total


def application_settings(workspace: WorkspaceState) -> ApplicationSettings:
    return ApplicationSettings(
        language=str(read_setting("language", "en")),
        reduced_motion=bool(read_setting("reduced_motion", False)),
        review_curve=active_review_curve(),
        default_review_intervals=DEFAULT_REVIEW_INTERVALS,
        scheduled_question_count=scheduled_question_count(Path(workspace.path)),
    )


def _curve_fields(profile: ReviewCurveProfile) -> dict[str, object]:
    return {
        "curve_id": profile.curve_id,
        "curve_version": profile.version,
        "curve_intervals": profile.interval_days,
    }


def _learner_progress_change(
    course_root: Path,
    records: list[dict[str, Any]],
    timestamp: str,
) -> tuple[Path, dict[str, Any], bytes] | None:
    canonical = course_root / "progress" / "learner-progress.json"
    legacy = course_root / "learner-progress.json"
    path = canonical if canonical.is_file() and not canonical.is_symlink() else legacy
    if not path.is_file() or path.is_symlink() or not _inside(course_root, path):
        return None
    try:
        original = path.read_bytes()
        payload = json.loads(original.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SettingsUpdateError(f"Could not safely read {path}: {error}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("concepts", []), list):
        raise SettingsUpdateError(f"Learner progress {path} has malformed concept records.")
    next_due_by_concept: dict[str, str] = {}
    for record in records:
        next_due = record.get("next_due_at")
        concept_ids = record.get("concept_ids", [])
        if not isinstance(next_due, str) or not isinstance(concept_ids, list):
            continue
        for raw_concept_id in concept_ids:
            concept_id = str(raw_concept_id)
            if concept_id not in next_due_by_concept or next_due < next_due_by_concept[concept_id]:
                next_due_by_concept[concept_id] = next_due
    for concept in payload.get("concepts", []):
        if not isinstance(concept, dict) or "concept_id" not in concept:
            continue
        concept["next_review_at"] = next_due_by_concept.get(str(concept["concept_id"]))
    payload["updated_at"] = timestamp
    return path, payload, original


def _migration_payloads(
    workspace_root: Path,
    previous: ReviewCurveProfile,
    current: ReviewCurveProfile,
    policy: str,
    timestamp: str,
) -> tuple[list[tuple[Path, dict[str, Any], bytes]], int, int]:
    changes: list[tuple[Path, dict[str, Any], bytes]] = []
    affected = 0
    preserved_without_anchor = 0
    for path in _review_queue_files(workspace_root):
        payload, records = _load_queue(path)
        original = path.read_bytes()
        for record in records:
            if record.get("status") == "archived":
                continue
            affected += 1
            existing_intervals = valid_intervals(
                record.get("curve_intervals", payload.get("curve_intervals", previous.interval_days))
            )
            record.setdefault("curve_id", previous.curve_id)
            record.setdefault("curve_version", previous.version)
            record.setdefault("curve_intervals", existing_intervals)

            if policy == "future_advancement":
                record["pending_curve_id"] = current.curve_id
                record["pending_curve_version"] = current.version
                record["pending_curve_intervals"] = current.interval_days
                record["curve_application_policy"] = policy
            elif policy == "recalculate_all":
                old_interval = record.get("interval_days")
                stage = record.get("stage_index", 0)
                if not isinstance(stage, int):
                    stage = 0
                stage = min(max(stage, 0), len(current.interval_days) - 1)
                anchor = _parse_timestamp(record.get("last_successful_due_review_at"))
                if anchor is None:
                    anchor = _parse_timestamp(record.get("scheduled_from_at"))
                if anchor is None:
                    next_due = _parse_timestamp(record.get("next_due_at"))
                    if next_due is not None and isinstance(old_interval, int) and old_interval > 0:
                        anchor = next_due - timedelta(days=old_interval)
                record.update(_curve_fields(current))
                record["stage_index"] = stage
                record["interval_days"] = current.interval_days[stage]
                record["curve_application_policy"] = policy
                for key in ("pending_curve_id", "pending_curve_version", "pending_curve_intervals"):
                    record.pop(key, None)
                if anchor is None:
                    preserved_without_anchor += 1
                else:
                    record["scheduled_from_at"] = _timestamp(anchor)
                    record["next_due_at"] = _timestamp(
                        anchor + timedelta(days=current.interval_days[stage])
                    )
            else:
                record["curve_application_policy"] = policy
                for key in ("pending_curve_id", "pending_curve_version", "pending_curve_intervals"):
                    record.pop(key, None)

        payload["schema_version"] = "review-queue-v1"
        payload["active_curve_id"] = current.curve_id
        payload["active_curve_version"] = current.version
        payload["active_curve_intervals"] = current.interval_days
        payload["curve_migration_policy"] = policy
        payload["updated_at"] = timestamp
        changes.append((path, payload, original))
        if policy == "recalculate_all":
            progress_change = _learner_progress_change(path.parents[1], records, timestamp)
            if progress_change is not None:
                changes.append(progress_change)
    return changes, affected, preserved_without_anchor


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def update_review_curve(
    workspace: WorkspaceState,
    request: ReviewCurveUpdateRequest,
    *,
    now: datetime | None = None,
) -> ReviewCurveUpdateResult:
    if request.application_policy == "recalculate_all" and not request.confirm_recalculate:
        raise SettingsUpdateError("Confirm recalculation before changing existing due dates.")

    previous = active_review_curve()
    timestamp = _timestamp(now or datetime.now(UTC))
    if request.save_mode == "duplicate_profile":
        curve_id = f"CURVE-{uuid.uuid4().hex[:12].upper()}"
        version = 1
        supersedes = None
    else:
        curve_id = previous.curve_id
        version = previous.version + 1
        supersedes = previous.version
    current = ReviewCurveProfile(
        curve_id=curve_id,
        version=version,
        name=request.name.strip(),
        interval_days=request.interval_days,
        created_at=timestamp,
        supersedes_version=supersedes,
    )

    changes, affected, preserved = _migration_payloads(
        Path(workspace.path), previous, current, request.application_policy, timestamp
    )
    written: list[tuple[Path, bytes]] = []
    try:
        for path, payload, original in changes:
            _atomic_write(path, payload)
            written.append((path, original))
        history = read_setting("review_curve_history", [])
        profiles = [item for item in history if isinstance(item, dict)] if isinstance(history, list) else []
        profiles.append(current.model_dump())
        save_settings(
            {
                "active_review_curve": current.model_dump(),
                "review_curve_history": profiles[-100:],
                "review_intervals": current.interval_days,
            }
        )
    except Exception as error:
        for path, original in reversed(written):
            try:
                path.write_bytes(original)
            except OSError:
                pass
        if isinstance(error, SettingsUpdateError):
            raise
        raise SettingsUpdateError(f"The curve update could not be saved: {error}") from error

    return ReviewCurveUpdateResult(
        review_curve=current,
        application_policy=request.application_policy,
        affected_question_count=affected,
        preserved_without_anchor_count=preserved,
    )
