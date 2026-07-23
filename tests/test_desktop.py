from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from mastery_ledger.desktop import (
    DesktopBackend,
    DesktopFolderPicker,
    _bootstrap_url,
    main,
    run_desktop,
)
from mastery_ledger.models import DoctorResult


@pytest.fixture()
def runtime_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "runtime"
    monkeypatch.setenv("MASTERY_LEDGER_HOME", str(home))
    monkeypatch.setenv("MASTERY_LEDGER_DEFAULT_WORKSPACE", str(tmp_path / "courses"))
    return home


def test_desktop_backend_starts_and_stops_with_the_bundled_frontend(runtime_home: Path) -> None:
    picker = lambda _initial=None: SimpleNamespace(status="cancelled")
    backend = DesktopBackend(picker)
    backend.start()
    try:
        assert backend._server is not None
        assert backend._server.config.log_config is None
        with urllib.request.urlopen(
            f"http://127.0.0.1:{backend.port}/api/v1/health", timeout=1.0
        ) as response:
            assert response.status == 200
            assert json.loads(response.read())["application"] == "mastery-ledger"
    finally:
        backend.stop()


@pytest.mark.parametrize(
    ("action", "suffix"),
    [
        ("open_onboarding", ""),
        ("repair_workspace", "/repair"),
        (None, "/open"),
    ],
)
def test_desktop_bootstrap_route_matches_runtime_action(action: str | None, suffix: str) -> None:
    doctor = DoctorResult(
        status="onboarding_required" if action == "open_onboarding" else "ready",
        onboarding_required=action == "open_onboarding",
        app_version="0.1.2",
        action=action,
    )
    assert _bootstrap_url(8765, "token", doctor) == (
        f"http://127.0.0.1:8765/bootstrap/token{suffix}"
    )


def test_native_folder_picker_uses_bound_window(tmp_path: Path) -> None:
    selected = tmp_path / "chosen"
    calls: list[tuple[int, str, bool]] = []

    class Window:
        def create_file_dialog(
            self, dialog_type: int, *, directory: str, allow_multiple: bool
        ) -> list[str]:
            calls.append((dialog_type, directory, allow_multiple))
            return [str(selected)]

    picker = DesktopFolderPicker(20)
    picker.bind(Window())
    result = picker(str(tmp_path))

    assert result.status == "selected"
    assert result.path == str(selected.resolve(strict=False))
    assert calls == [(20, str(tmp_path.resolve()), False)]


def test_desktop_host_runs_webview_on_the_calling_thread(runtime_home: Path) -> None:
    lifecycle: list[str] = []
    window_options: dict[str, object] = {}

    class Events:
        def __init__(self) -> None:
            self.closed = self

        def __iadd__(self, handler):
            lifecycle.append("close-handler")
            self.handler = handler
            return self

    class Window:
        def __init__(self) -> None:
            self.events = Events()

    class FakeBackend:
        port = 8765
        token = "desktop-token"

        def start(self) -> None:
            lifecycle.append("backend-start")

        def stop(self) -> None:
            lifecycle.append("backend-stop")

    class FakeWebview:
        FileDialog = SimpleNamespace(FOLDER=20)

        def create_window(self, title: str, url: str, **options):
            lifecycle.append(f"window:{title}:{url}")
            window_options.update(options)
            return Window()

        def start(self, **options) -> None:
            lifecycle.append("webview-start")

    run_desktop(
        webview_module=FakeWebview(),
        backend_factory=lambda **_kwargs: FakeBackend(),
        doctor_factory=lambda: DoctorResult(
            status="ready", onboarding_required=False, app_version="0.1.2"
        ),
    )

    assert lifecycle[0] == "backend-start"
    assert lifecycle[1] == (
        "window:Mastery Ledger:"
        "http://127.0.0.1:8765/bootstrap/desktop-token/open"
    )
    assert "close-handler" in lifecycle
    assert "webview-start" in lifecycle
    assert window_options["maximized"] is True
    assert window_options["min_size"] == (900, 640)
    assert lifecycle[-1] == "backend-stop"


def test_desktop_smoke_cli_reports_backend_and_frontend_ready(
    runtime_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--smoke-test", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "schema_version": "desktop-smoke-v1",
        "status": "ready",
        "backend": "ready",
        "frontend": "ready",
    }


def test_desktop_smoke_cli_writes_machine_readable_output(
    runtime_home: Path, tmp_path: Path
) -> None:
    output = tmp_path / "smoke.json"
    assert main(["--smoke-test", "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "ready"
