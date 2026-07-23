from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_remote_media_dependencies_are_not_part_of_the_application_core() -> None:
    package = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = package["project"]
    core_dependencies = "\n".join(project["dependencies"]).casefold()
    media_dependencies = "\n".join(
        project["optional-dependencies"]["media"]
    ).casefold()

    assert "yt-dlp" not in core_dependencies
    assert "yt-dlp" in media_dependencies


def test_dependency_locks_preserve_the_runtime_boundaries() -> None:
    core = (ROOT / "requirements" / "core.lock").read_text(encoding="utf-8").casefold()
    desktop = (ROOT / "requirements" / "desktop.lock").read_text(
        encoding="utf-8"
    ).casefold()
    media = (ROOT / "requirements" / "media.lock").read_text(encoding="utf-8").casefold()
    transcription = (ROOT / "requirements" / "transcription.lock").read_text(
        encoding="utf-8"
    ).casefold()

    assert "yt-dlp==" not in core
    assert "faster-whisper==" not in core
    assert "pywebview==" not in core
    assert "pyinstaller==" not in core
    assert "pywebview==" in desktop
    assert "pyinstaller==" in desktop
    assert "yt-dlp==" not in desktop
    assert "yt-dlp==" in media
    assert "faster-whisper==" not in media
    assert "yt-dlp==" in transcription
    assert "faster-whisper==" in transcription


def test_windows_installer_preserves_the_desktop_runtime_contract() -> None:
    installer = (ROOT / "packaging" / "mastery-ledger.iss").read_text(
        encoding="utf-8"
    )
    runtime_config = (ROOT / "packaging" / "MasteryLedger.exe.config").read_text(
        encoding="utf-8"
    )
    release_workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "AppId={{2D03C5AB-2D70-4E54-B9DE-E4B7766FBA85}" in installer
    assert "PrivilegesRequired=lowest" in installer
    assert "MasteryLedger-Setup-v{#AppVersion}" in installer
    assert "recursesubdirs createallsubdirs" in installer
    assert '<loadFromRemoteSources enabled="true"/>' in runtime_config
    assert "MasteryLedger.exe.config" in release_workflow
    assert "--webview-smoke-test" in release_workflow
    assert "mastery-ledger.iss" in release_workflow
