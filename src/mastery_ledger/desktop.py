from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Sequence

import uvicorn

from mastery_ledger.app import create_app
from mastery_ledger.config import app_data_dir, bundled_web_dir
from mastery_ledger.models import DoctorResult, FolderPickerResult
from mastery_ledger.runtime import build_doctor_result

LOOPBACK_HOST = "127.0.0.1"
STARTUP_TIMEOUT_SECONDS = 10.0
SHUTDOWN_TIMEOUT_SECONDS = 5.0


class DesktopStartupError(RuntimeError):
    """Raised when the embedded application server cannot start safely."""


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((LOOPBACK_HOST, 0))
        return int(listener.getsockname()[1])


def _health_is_ready(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://{LOOPBACK_HOST}:{port}/api/v1/health", timeout=0.5
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, urllib.error.URLError):
        return False
    return (
        response.status == 200
        and payload.get("status") == "ok"
        and payload.get("application") == "mastery-ledger"
    )


def _bootstrap_url(port: int, token: str, doctor: DoctorResult) -> str:
    suffix = {
        "open_onboarding": "",
        "repair_workspace": "/repair",
    }.get(doctor.action, "/open")
    return f"http://{LOOPBACK_HOST}:{port}/bootstrap/{token}{suffix}"


class DesktopFolderPicker:
    """Adapt pywebview's native folder dialog to the existing API response model."""

    def __init__(self, dialog_type: int) -> None:
        self._dialog_type = dialog_type
        self._window: Any | None = None

    def bind(self, window: Any) -> None:
        self._window = window

    def __call__(self, initial_path: str | None = None) -> FolderPickerResult:
        if self._window is None:
            return FolderPickerResult(
                status="unavailable",
                message="The desktop window is not ready for folder selection.",
            )

        directory = ""
        if initial_path:
            candidate = Path(initial_path).expanduser()
            if candidate.is_dir():
                directory = str(candidate.resolve(strict=False))
            elif candidate.parent.is_dir():
                directory = str(candidate.parent.resolve(strict=False))

        try:
            selected = self._window.create_file_dialog(
                self._dialog_type,
                directory=directory,
                allow_multiple=False,
            )
        except (OSError, RuntimeError) as error:
            return FolderPickerResult(
                status="unavailable",
                message=f"The native folder chooser is unavailable: {error}",
            )

        if not selected:
            return FolderPickerResult(status="cancelled", message="No folder was selected.")
        return FolderPickerResult(
            status="selected",
            path=str(Path(selected[0]).resolve(strict=False)),
        )


class DesktopBackend:
    """Own an in-process Uvicorn server for one desktop application window."""

    def __init__(
        self,
        folder_picker: Callable[[str | None], FolderPickerResult],
        *,
        port: int | None = None,
    ) -> None:
        self.port = port or _free_loopback_port()
        self.token = secrets.token_urlsafe(32)
        self._folder_picker = folder_picker
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._server_error: str | None = None

    def start(
        self,
        progress: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        if self._thread and self._thread.is_alive():
            return

        report = progress or (lambda _payload: None)
        report({"schema_version": "desktop-smoke-v1", "status": "creating_backend"})
        application = create_app(
            session_token=self.token,
            folder_picker=self._folder_picker,
        )
        config = uvicorn.Config(
            application,
            host=LOOPBACK_HOST,
            port=self.port,
            access_log=False,
            log_level="warning",
            log_config=None,
            loop="asyncio",
            http="h11",
            ws="none",
            lifespan="on",
        )
        self._server = uvicorn.Server(config)

        def run_server() -> None:
            try:
                self._server.run()
            except BaseException as error:
                self._server_error = f"{type(error).__name__}: {error}"
                report(
                    {
                        "schema_version": "desktop-smoke-v1",
                        "status": "backend_error",
                        "message": self._server_error,
                    }
                )

        self._thread = threading.Thread(
            target=run_server,
            name="mastery-ledger-backend",
            daemon=True,
        )
        self._thread.start()
        report({"schema_version": "desktop-smoke-v1", "status": "waiting_for_backend"})

        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if _health_is_ready(self.port):
                report({"schema_version": "desktop-smoke-v1", "status": "backend_ready"})
                return
            if not self._thread.is_alive():
                break
            time.sleep(0.05)

        self.stop()
        detail = f" ({self._server_error})" if self._server_error else ""
        raise DesktopStartupError(f"The embedded Mastery Ledger backend did not start{detail}.")

    def stop(self) -> None:
        server = self._server
        thread = self._thread
        if server is None or thread is None:
            return

        server.should_exit = True
        if thread is not threading.current_thread():
            thread.join(timeout=SHUTDOWN_TIMEOUT_SECONDS)
            if thread.is_alive():
                server.force_exit = True
                thread.join(timeout=1.0)
        self._server = None
        self._thread = None


def _load_webview() -> ModuleType:
    try:
        import webview
    except ImportError as error:
        raise DesktopStartupError(
            "The desktop runtime is not installed. Install Mastery Ledger with its desktop extra."
        ) from error
    return webview


def run_desktop(
    *,
    webview_module: ModuleType | Any | None = None,
    backend_factory: Callable[..., DesktopBackend] = DesktopBackend,
    doctor_factory: Callable[[], DoctorResult] = build_doctor_result,
) -> None:
    webview = webview_module or _load_webview()
    folder_picker = DesktopFolderPicker(webview.FileDialog.FOLDER)
    backend = backend_factory(folder_picker=folder_picker)
    backend.start()

    try:
        window = webview.create_window(
            "Mastery Ledger",
            _bootstrap_url(backend.port, backend.token, doctor_factory()),
            width=1440,
            height=900,
            min_size=(900, 640),
            maximized=True,
            background_color="#f4f0e8",
            text_select=True,
        )
        if window is None:
            raise DesktopStartupError("The native Mastery Ledger window could not be created.")
        folder_picker.bind(window)
        window.events.closed += backend.stop

        start_options: dict[str, Any] = {
            "debug": False,
            "private_mode": True,
        }
        if sys.platform == "win32":
            start_options["gui"] = "edgechromium"
        webview.start(**start_options)
    finally:
        backend.stop()


def run_smoke_test(
    progress: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    report = progress or (lambda _payload: None)
    report({"schema_version": "desktop-smoke-v1", "status": "starting"})
    unavailable_picker = lambda _initial=None: FolderPickerResult(
        status="unavailable",
        message="Folder selection is not used during the executable smoke test.",
    )
    backend = DesktopBackend(unavailable_picker)
    backend.start(progress=report)
    report(
        {
            "schema_version": "desktop-smoke-v1",
            "status": "checking_frontend",
            "backend": "ready",
        }
    )
    try:
        with urllib.request.urlopen(
            f"http://{LOOPBACK_HOST}:{backend.port}/", timeout=2.0
        ) as response:
            frontend = response.read().decode("utf-8")
        index_present = (bundled_web_dir() / "index.html").is_file()
        if response.status != 200 or '<div id="root"></div>' not in frontend or not index_present:
            raise DesktopStartupError("The bundled desktop frontend could not be loaded.")
        result: dict[str, object] = {
            "schema_version": "desktop-smoke-v1",
            "status": "ready",
            "backend": "ready",
            "frontend": "ready",
        }
        report(result)
        return result
    finally:
        backend.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mastery-ledger-desktop")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Start the packaged backend, verify the bundled frontend, and exit",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--output",
        type=Path,
        help="Write smoke-test progress and the final result to a JSON file",
    )
    return parser


def _show_startup_error(message: str) -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, "Mastery Ledger", 0x10)
            return
        except (AttributeError, OSError):
            pass
    print(message, file=sys.stderr)


def _write_smoke_output(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    smoke_test = args.smoke_test or os.environ.get("MASTERY_LEDGER_SMOKE_TEST") == "1"
    output_path = args.output
    if output_path is None and os.environ.get("MASTERY_LEDGER_SMOKE_OUTPUT"):
        output_path = Path(os.environ["MASTERY_LEDGER_SMOKE_OUTPUT"])

    if smoke_test:
        def report(payload: dict[str, object]) -> None:
            if output_path is not None:
                _write_smoke_output(output_path, payload)

        try:
            result = run_smoke_test(progress=report)
        except Exception as error:
            result = {
                "schema_version": "desktop-smoke-v1",
                "status": "error",
                "message": str(error),
            }
            report(result)
            if args.as_json:
                print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
            return 1
        if args.as_json:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0

    try:
        run_desktop()
        return 0
    except Exception as error:
        _show_startup_error(str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
