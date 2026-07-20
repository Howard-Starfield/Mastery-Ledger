from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Sequence

import uvicorn

from mastery_ledger.app import create_app
from mastery_ledger.config import app_data_dir, server_state_path
from mastery_ledger.runtime import build_doctor_result


def _json_print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _read_server_state() -> dict[str, Any] | None:
    path = server_state_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    required = {"schema_version", "port", "pid", "session_token"}
    return payload if required.issubset(payload) else None


def _write_server_state(payload: dict[str, Any]) -> None:
    target = server_state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    temporary.replace(target)


def _server_is_healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=0.35) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return (
                response.status == 200
                and payload.get("schema_version") == "health-v1"
                and payload.get("application") == "mastery-ledger"
            )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, urllib.error.URLError):
        return False


def _wait_for_server(port: int, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _server_is_healthy(port):
            return True
        time.sleep(0.1)
    return False


def _spawn_server(port: int, token: str) -> subprocess.Popen[bytes]:
    runtime_dir = app_data_dir()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["MASTERY_LEDGER_SESSION_TOKEN"] = token
    command = [sys.executable, "-m", "mastery_ledger", "serve", "--port", str(port)]
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": environment,
        "cwd": str(runtime_dir),
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
        )
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


def launch_onboarding(*, open_browser: bool) -> dict[str, Any]:
    existing = _read_server_state()
    status_value = "launched"
    if existing and _server_is_healthy(int(existing["port"])):
        state = existing
        status_value = "already_running"
    else:
        port = _free_loopback_port()
        token = secrets.token_urlsafe(32)
        process = _spawn_server(port, token)
        state = {
            "schema_version": "server-state-v1",
            "port": port,
            "pid": process.pid,
            "session_token": token,
        }
        _write_server_state(state)
        if not _wait_for_server(port):
            server_state_path().unlink(missing_ok=True)
            return {
                "schema_version": "onboarding-launch-v1",
                "status": "needs_user_action",
                "opened": False,
                "message": "The local application did not start. Run mastery-ledger onboard --open --json again.",
            }

    bootstrap_url = f"http://127.0.0.1:{state['port']}/bootstrap/{state['session_token']}"
    opened = bool(webbrowser.open(bootstrap_url, new=2)) if open_browser else False
    if open_browser and not opened:
        return {
            "schema_version": "onboarding-launch-v1",
            "status": "needs_user_action",
            "opened": False,
            "pid": state["pid"],
            "url": f"http://127.0.0.1:{state['port']}/onboarding",
            "message": "The application started, but the browser could not be opened. Rerun the onboarding command.",
        }
    return {
        "schema_version": "onboarding-launch-v1",
        "status": status_value,
        "opened": opened,
        "pid": state["pid"],
        "url": f"http://127.0.0.1:{state['port']}/onboarding",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mastery-ledger")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Inspect runtime and onboarding state")
    doctor.add_argument("--json", action="store_true", dest="as_json")

    onboard = subparsers.add_parser("onboard", help="Start the local onboarding application")
    onboard.add_argument("--open", action="store_true", dest="open_browser")
    onboard.add_argument("--json", action="store_true", dest="as_json")

    serve = subparsers.add_parser("serve", help="Run the loopback web application")
    serve.add_argument("--port", type=int, default=8765)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        result = build_doctor_result().model_dump(mode="json")
        if args.as_json:
            _json_print(result)
        else:
            print(f"Mastery Ledger: {result['status']}")
        return 0

    if args.command == "onboard":
        result = launch_onboarding(open_browser=args.open_browser)
        if args.as_json:
            _json_print(result)
        else:
            print(result.get("message") or f"Mastery Ledger onboarding: {result['status']}")
        return 0 if result["status"] in {"launched", "already_running"} else 2

    if args.command == "serve":
        uvicorn.run(
            create_app(),
            host="127.0.0.1",
            port=args.port,
            access_log=False,
            log_level="warning",
        )
        return 0

    return 2
