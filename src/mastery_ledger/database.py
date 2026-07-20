from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from mastery_ledger.config import database_path
from mastery_ledger.models import OnboardingRequest, WorkspaceRepairRequest, WorkspaceState

SCHEMA_VERSION = "1"


class DatabaseReadError(RuntimeError):
    """Raised when durable state exists but cannot be inspected safely."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def connect(path: Path | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(path or database_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(path: Path | None = None) -> None:
    target = path or database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(target)) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workspaces (
                workspace_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL UNIQUE,
                active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
                created_at TEXT NOT NULL,
                last_used_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_workspace
            ON workspaces(active) WHERE active = 1;
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                state TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
        connection.commit()


def active_workspace(path: Path | None = None) -> sqlite3.Row | None:
    target = path or database_path()
    if not target.exists():
        return None
    uri = f"{target.resolve().as_uri()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        with closing(connection):
            return connection.execute(
                "SELECT workspace_id, name, path FROM workspaces WHERE active = 1 LIMIT 1"
            ).fetchone()
    except sqlite3.Error as error:
        raise DatabaseReadError(f"The application database could not be read: {error}") from error


def read_setting(key: str, default: object = None, path: Path | None = None) -> object:
    target = path or database_path()
    if not target.exists():
        return default
    uri = f"{target.resolve().as_uri()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        with closing(connection):
            row = connection.execute(
                "SELECT value_json FROM settings WHERE key = ? LIMIT 1",
                (key,),
            ).fetchone()
    except sqlite3.Error as error:
        raise DatabaseReadError(f"The application database could not be read: {error}") from error
    if row is None:
        return default
    try:
        return json.loads(row["value_json"])
    except (TypeError, json.JSONDecodeError):
        return default


def save_settings(values: dict[str, object], path: Path | None = None) -> None:
    """Persist a group of application settings in one SQLite transaction."""
    initialize_database(path)
    timestamp = utc_now()
    with closing(connect(path)) as connection:
        for key, value in values.items():
            connection.execute(
                """
                INSERT INTO settings(key, value_json, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, json.dumps(value), timestamp),
            )
        connection.commit()


def enqueue_job(kind: str, payload: dict[str, object], path: Path | None = None) -> str:
    initialize_database(path)
    job_id = f"JOB-{uuid.uuid4().hex[:16].upper()}"
    timestamp = utc_now()
    with closing(connect(path)) as connection:
        connection.execute(
            """
            INSERT INTO jobs(job_id, kind, state, payload_json, created_at, updated_at)
            VALUES(?, ?, 'queued', ?, ?, ?)
            """,
            (job_id, kind, json.dumps(payload), timestamp, timestamp),
        )
        connection.commit()
    return job_id


def recover_interrupted_jobs(path: Path | None = None) -> int:
    initialize_database(path)
    timestamp = utc_now()
    with closing(connect(path)) as connection:
        cursor = connection.execute(
            "UPDATE jobs SET state = 'queued', updated_at = ? WHERE state = 'running'",
            (timestamp,),
        )
        connection.commit()
        return int(cursor.rowcount)


def claim_next_job(path: Path | None = None) -> dict[str, object] | None:
    initialize_database(path)
    timestamp = utc_now()
    with closing(connect(path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT job_id, kind, payload_json, created_at, updated_at
            FROM jobs WHERE state = 'queued' ORDER BY created_at, job_id LIMIT 1
            """
        ).fetchone()
        if row is None:
            connection.commit()
            return None
        updated = connection.execute(
            "UPDATE jobs SET state = 'running', updated_at = ? WHERE job_id = ? AND state = 'queued'",
            (timestamp, row["job_id"]),
        )
        connection.commit()
        if updated.rowcount != 1:
            return None
    try:
        payload = json.loads(row["payload_json"])
    except (TypeError, json.JSONDecodeError):
        payload = {}
    return {
        "job_id": row["job_id"],
        "kind": row["kind"],
        "state": "running",
        "payload": payload if isinstance(payload, dict) else {},
        "created_at": row["created_at"],
        "updated_at": timestamp,
    }


def update_job(
    job_id: str,
    *,
    state: str,
    payload: dict[str, object] | None = None,
    path: Path | None = None,
) -> bool:
    timestamp = utc_now()
    with closing(connect(path)) as connection:
        if payload is None:
            cursor = connection.execute(
                "UPDATE jobs SET state = ?, updated_at = ? WHERE job_id = ?",
                (state, timestamp, job_id),
            )
        else:
            cursor = connection.execute(
                "UPDATE jobs SET state = ?, payload_json = ?, updated_at = ? WHERE job_id = ?",
                (state, json.dumps(payload), timestamp, job_id),
            )
        connection.commit()
        return cursor.rowcount == 1


def list_jobs(path: Path | None = None, *, limit: int = 500) -> list[dict[str, object]]:
    target = path or database_path()
    if not target.exists():
        return []
    with closing(connect(target)) as connection:
        rows = connection.execute(
            """
            SELECT job_id, kind, state, payload_json, created_at, updated_at
            FROM jobs ORDER BY created_at DESC, job_id DESC LIMIT ?
            """,
            (max(1, min(limit, 2000)),),
        ).fetchall()
    jobs: list[dict[str, object]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            payload = {}
        jobs.append(
            {
                "job_id": row["job_id"],
                "kind": row["kind"],
                "state": row["state"],
                "payload": payload if isinstance(payload, dict) else {},
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    return jobs


def get_job(job_id: str, path: Path | None = None) -> dict[str, object] | None:
    target = path or database_path()
    if not target.exists():
        return None
    with closing(connect(target)) as connection:
        row = connection.execute(
            """
            SELECT job_id, kind, state, payload_json, created_at, updated_at
            FROM jobs WHERE job_id = ? LIMIT 1
            """,
            (job_id,),
        ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row["payload_json"])
    except (TypeError, json.JSONDecodeError):
        payload = {}
    return {
        "job_id": row["job_id"],
        "kind": row["kind"],
        "state": row["state"],
        "payload": payload if isinstance(payload, dict) else {},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def request_job_cancellation(job_id: str, path: Path | None = None) -> bool:
    timestamp = utc_now()
    with closing(connect(path)) as connection:
        row = connection.execute(
            "SELECT state, payload_json FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None or row["state"] in {"complete", "failed", "cancelled"}:
            return False
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload["cancellation_requested"] = True
        state = "cancelled" if row["state"] == "queued" else row["state"]
        connection.execute(
            "UPDATE jobs SET state = ?, payload_json = ?, updated_at = ? WHERE job_id = ?",
            (state, json.dumps(payload), timestamp, job_id),
        )
        connection.commit()
        return True


def retry_job(job_id: str, path: Path | None = None) -> bool:
    timestamp = utc_now()
    with closing(connect(path)) as connection:
        row = connection.execute(
            "SELECT state, payload_json FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None or row["state"] not in {
            "needs_user_action",
            "partial",
            "failed",
            "cancelled",
        }:
            return False
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload.update(
            {
                "progress": 0.0,
                "stage": "queued",
                "error_code": None,
                "recovery_suggestion": None,
                "cancellation_requested": False,
            }
        )
        cursor = connection.execute(
            "UPDATE jobs SET state = 'queued', payload_json = ?, updated_at = ? WHERE job_id = ?",
            (json.dumps(payload), timestamp, job_id),
        )
        connection.commit()
        return cursor.rowcount == 1


def save_onboarding(request: OnboardingRequest, workspace_path: Path) -> WorkspaceState:
    initialize_database()
    timestamp = utc_now()
    workspace_id = f"WS-{uuid.uuid4().hex[:12].upper()}"
    with closing(connect()) as connection:
        existing = connection.execute(
            "SELECT workspace_id, created_at FROM workspaces WHERE path = ?",
            (str(workspace_path),),
        ).fetchone()
        if existing:
            workspace_id = existing["workspace_id"]
            created_at = existing["created_at"]
        else:
            created_at = timestamp

        connection.execute("UPDATE workspaces SET active = 0")
        connection.execute(
            """
            INSERT INTO workspaces(workspace_id, name, path, active, created_at, last_used_at)
            VALUES(?, ?, ?, 1, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                name = excluded.name,
                active = 1,
                last_used_at = excluded.last_used_at
            """,
            (workspace_id, request.workspace_name.strip(), str(workspace_path), created_at, timestamp),
        )
        settings = {
            "language": request.language,
            "processing_mode": request.processing_mode,
            "reduced_motion": request.reduced_motion,
            "review_intervals": request.review_intervals,
            "active_review_curve": {
                "curve_id": "CURVE-OWNERSHIP",
                "version": 1,
                "name": "My ownership curve",
                "interval_days": request.review_intervals,
                "created_at": timestamp,
                "supersedes_version": None,
            },
            "review_curve_history": [
                {
                    "curve_id": "CURVE-OWNERSHIP",
                    "version": 1,
                    "name": "My ownership curve",
                    "interval_days": request.review_intervals,
                    "created_at": timestamp,
                    "supersedes_version": None,
                }
            ],
            "initial_source_hint": request.initial_source_hint or None,
            "onboarding_complete": True,
        }
        for key, value in settings.items():
            connection.execute(
                """
                INSERT INTO settings(key, value_json, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, json.dumps(value), timestamp),
            )
        connection.commit()

    return WorkspaceState(
        workspace_id=workspace_id,
        name=request.workspace_name.strip(),
        path=str(workspace_path),
        available=True,
        writable=True,
    )


def repair_active_workspace(
    request: WorkspaceRepairRequest, workspace_path: Path
) -> WorkspaceState:
    initialize_database()
    timestamp = utc_now()
    with closing(connect()) as connection:
        active = connection.execute(
            "SELECT workspace_id, name FROM workspaces WHERE active = 1 LIMIT 1"
        ).fetchone()
        if active is None:
            raise DatabaseReadError("No active workspace is available to repair.")
        existing = connection.execute(
            "SELECT workspace_id FROM workspaces WHERE path = ? LIMIT 1",
            (str(workspace_path),),
        ).fetchone()
        name = request.workspace_name.strip()
        if existing and existing["workspace_id"] != active["workspace_id"]:
            workspace_id = existing["workspace_id"]
            connection.execute("UPDATE workspaces SET active = 0")
            connection.execute(
                "UPDATE workspaces SET name = ?, active = 1, last_used_at = ? WHERE workspace_id = ?",
                (name, timestamp, workspace_id),
            )
        else:
            workspace_id = active["workspace_id"]
            connection.execute(
                "UPDATE workspaces SET name = ?, path = ?, last_used_at = ? WHERE workspace_id = ?",
                (name, str(workspace_path), timestamp, workspace_id),
            )
        connection.commit()
    return WorkspaceState(
        workspace_id=str(workspace_id),
        name=name,
        path=str(workspace_path),
        available=True,
        writable=True,
    )
