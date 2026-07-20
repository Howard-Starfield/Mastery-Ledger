from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from mastery_ledger.config import database_path
from mastery_ledger.models import OnboardingRequest, WorkspaceState

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
