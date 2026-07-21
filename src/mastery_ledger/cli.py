from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
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
from mastery_ledger.config import app_data_dir, runtime_signature, server_state_path
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


def _server_is_healthy(port: int, expected_signature: str | None = None) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=0.35) as response:
            payload = json.loads(response.read().decode("utf-8"))
            healthy = (
                response.status == 200
                and payload.get("schema_version") == "health-v1"
                and payload.get("application") == "mastery-ledger"
            )
            return healthy and (
                expected_signature is None
                or payload.get("runtime_signature") == expected_signature
            )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, urllib.error.URLError):
        return False


def _wait_for_server(port: int, expected_signature: str, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _server_is_healthy(port, expected_signature):
            return True
        time.sleep(0.1)
    return False


def _stop_server(state: dict[str, Any], timeout: float = 4.0) -> None:
    try:
        pid = int(state["pid"])
        port = int(state["port"])
    except (KeyError, TypeError, ValueError):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _server_is_healthy(port):
            return
        time.sleep(0.1)


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


def _launch_application(*, open_browser: bool, purpose: str) -> dict[str, Any]:
    if purpose not in {"application", "onboarding", "workspace-repair"}:
        raise ValueError(f"Unsupported application launch purpose: {purpose}")
    schema_version = f"{purpose}-launch-v1"
    command_name = {
        "application": "open",
        "onboarding": "onboard",
        "workspace-repair": "repair",
    }[purpose]
    retry_command = f"mastery-ledger {command_name}{'' if purpose == 'application' else ' --open'} --json"
    existing = _read_server_state()
    expected_signature = runtime_signature()
    status_value = "launched"
    if existing and _server_is_healthy(int(existing["port"]), expected_signature):
        state = existing
        status_value = "already_running"
    else:
        if existing and _server_is_healthy(int(existing["port"])):
            _stop_server(existing)
        port = _free_loopback_port()
        token = secrets.token_urlsafe(32)
        process = _spawn_server(port, token)
        state = {
            "schema_version": "server-state-v1",
            "port": port,
            "pid": process.pid,
            "session_token": token,
            "runtime_signature": expected_signature,
        }
        _write_server_state(state)
        if not _wait_for_server(port, expected_signature):
            server_state_path().unlink(missing_ok=True)
            return {
                "schema_version": schema_version,
                "status": "needs_user_action",
                "opened": False,
                "message": f"The local application did not start. Run {retry_command} again.",
            }

    bootstrap_suffix = {
        "application": "/open",
        "onboarding": "",
        "workspace-repair": "/repair",
    }[purpose]
    bootstrap_url = (
        f"http://127.0.0.1:{state['port']}/bootstrap/{state['session_token']}"
        f"{bootstrap_suffix}"
    )
    opened = bool(webbrowser.open(bootstrap_url, new=2)) if open_browser else False
    if open_browser and not opened:
        return {
            "schema_version": schema_version,
            "status": "needs_user_action",
            "opened": False,
            "pid": state["pid"],
            "url": f"http://127.0.0.1:{state['port']}/{'onboarding' if purpose == 'onboarding' else ''}",
            "message": f"The application started, but the browser could not be opened. Open the URL shown here or rerun mastery-ledger {command_name}.",
        }
    return {
        "schema_version": schema_version,
        "status": status_value,
        "opened": opened,
        "pid": state["pid"],
        "url": f"http://127.0.0.1:{state['port']}/{'onboarding' if purpose == 'onboarding' else ''}",
    }


def launch_application() -> dict[str, Any]:
    return _launch_application(open_browser=True, purpose="application")


def launch_onboarding(*, open_browser: bool) -> dict[str, Any]:
    return _launch_application(open_browser=open_browser, purpose="onboarding")


def launch_workspace_repair(*, open_browser: bool) -> dict[str, Any]:
    return _launch_application(open_browser=open_browser, purpose="workspace-repair")


def stop_application() -> dict[str, Any]:
    state = _read_server_state()
    if state is None:
        return {"schema_version": "application-stop-v1", "status": "not_running"}
    try:
        port = int(state["port"])
    except (KeyError, TypeError, ValueError):
        server_state_path().unlink(missing_ok=True)
        return {"schema_version": "application-stop-v1", "status": "not_running"}
    if _server_is_healthy(port):
        _stop_server(state)
    if _server_is_healthy(port):
        return {
            "schema_version": "application-stop-v1",
            "status": "needs_user_action",
            "message": "The local application is still running. Close it before updating.",
        }
    server_state_path().unlink(missing_ok=True)
    return {"schema_version": "application-stop-v1", "status": "stopped"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mastery-ledger")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Inspect runtime and onboarding state")
    doctor.add_argument("--json", action="store_true", dest="as_json")
    doctor.add_argument("--skill-version")

    onboard = subparsers.add_parser("onboard", help="Start the local onboarding application")
    onboard.add_argument("--open", action="store_true", dest="open_browser")
    onboard.add_argument("--json", action="store_true", dest="as_json")

    open_command = subparsers.add_parser("open", help="Open the local Mastery Ledger application")
    open_command.add_argument("--json", action="store_true", dest="as_json")

    repair = subparsers.add_parser("repair", help="Open the workspace repair application")
    repair.add_argument("--open", action="store_true", dest="open_browser")
    repair.add_argument("--json", action="store_true", dest="as_json")

    stop = subparsers.add_parser("stop", help="Stop the loopback web application")
    stop.add_argument("--json", action="store_true", dest="as_json")

    serve = subparsers.add_parser("serve", help="Run the loopback web application")
    serve.add_argument("--port", type=int, default=8765)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        result = build_doctor_result(args.skill_version).model_dump(mode="json")
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

    if args.command == "open":
        result = launch_application()
        if args.as_json:
            _json_print(result)
        else:
            print(result.get("message") or f"Mastery Ledger opened: {result.get('url', result['status'])}")
        return 0 if result["status"] in {"launched", "already_running"} else 2

    if args.command == "repair":
        result = launch_workspace_repair(open_browser=args.open_browser)
        if args.as_json:
            _json_print(result)
        else:
            print(result.get("message") or f"Mastery Ledger workspace repair: {result['status']}")
        return 0 if result["status"] in {"launched", "already_running"} else 2

    if args.command == "stop":
        result = stop_application()
        if args.as_json:
            _json_print(result)
        else:
            print(result.get("message") or f"Mastery Ledger application: {result['status']}")
        return 0 if result["status"] in {"stopped", "not_running"} else 2

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
