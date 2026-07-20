from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "MasteryLedger"


def app_data_dir() -> Path:
    override = os.environ.get("MASTERY_LEDGER_HOME")
    if override:
        return Path(override).expanduser().resolve()

    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return (base / APP_NAME).resolve()
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / APP_NAME).resolve()

    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return (base / "mastery-ledger").resolve()


def database_path() -> Path:
    return app_data_dir() / "mastery-ledger.sqlite3"


def server_state_path() -> Path:
    return app_data_dir() / "server.json"


def default_workspace_path() -> Path:
    override = os.environ.get("MASTERY_LEDGER_DEFAULT_WORKSPACE")
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / "MasteryLedger" / "courses").resolve()


def bundled_web_dir() -> Path:
    return Path(__file__).resolve().parent / "web"
