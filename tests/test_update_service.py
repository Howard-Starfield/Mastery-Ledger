from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mastery_ledger.app import create_app
from mastery_ledger.models import UpdateInstallResult, UpdateStatus
from mastery_ledger import update_service
from mastery_ledger.update_service import (
    UpdateServiceError,
    _extract_update,
    check_for_updates,
    install_update,
)


class Response(io.BytesIO):
    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def release_payload(version: str, archive: bytes = b"update") -> dict[str, Any]:
    name = f"MasteryLedger-windows-x64-v{version}.zip"
    return {
        "tag_name": f"v{version}",
        "html_url": f"https://github.com/Howard-Starfield/Mastery-Ledger/releases/tag/v{version}",
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": name,
                "state": "uploaded",
                "size": len(archive),
                "digest": f"sha256:{hashlib.sha256(archive).hexdigest()}",
                "browser_download_url": (
                    "https://github.com/Howard-Starfield/Mastery-Ledger/releases/"
                    f"download/v{version}/{name}"
                ),
            }
        ],
    }


def metadata_opener(payload: dict[str, Any]):
    encoded = json.dumps(payload).encode("utf-8")

    def open_request(_request, *, timeout: float):
        assert timeout == 10.0
        return Response(encoded)

    return open_request


def test_update_check_compares_stable_versions_and_exposes_verified_asset() -> None:
    result = check_for_updates(
        "0.1.1",
        opener=metadata_opener(release_payload("0.1.2")),
        can_install=True,
    )

    assert result.status == "available"
    assert result.latest_version == "0.1.2"
    assert result.asset_name == "MasteryLedger-windows-x64-v0.1.2.zip"
    assert result.automatic_install_available is True

    current = check_for_updates(
        "0.1.2",
        opener=metadata_opener(release_payload("0.1.2")),
        can_install=False,
    )
    assert current.status == "up_to_date"


def test_update_check_rejects_untrusted_or_unverified_assets() -> None:
    payload = release_payload("0.1.2")
    payload["assets"][0]["browser_download_url"] = "https://example.com/update.zip"
    with pytest.raises(UpdateServiceError, match="URL is not trusted"):
        check_for_updates("0.1.1", opener=metadata_opener(payload))

    payload = release_payload("0.1.2")
    payload["assets"][0]["digest"] = None
    with pytest.raises(UpdateServiceError, match="SHA-256"):
        check_for_updates("0.1.1", opener=metadata_opener(payload))


def test_update_archive_rejects_parent_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../outside.txt", "unsafe")

    with pytest.raises(UpdateServiceError, match="unsafe path"):
        _extract_update(archive, tmp_path / "payload")
    assert not (tmp_path / "outside.txt").exists()

    windows_archive = tmp_path / "unsafe-windows.zip"
    with zipfile.ZipFile(windows_archive, "w") as bundle:
        bundle.writestr("..\\outside.txt", "unsafe")
    with pytest.raises(UpdateServiceError, match="unsafe path"):
        _extract_update(windows_archive, tmp_path / "windows-payload")


def test_packaged_update_downloads_verifies_and_launches_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as bundle:
        bundle.writestr("MasteryLedger.exe", b"new executable")
        bundle.writestr("_internal/version.txt", b"9.9.9")
    archive = archive_buffer.getvalue()
    metadata = json.dumps(release_payload("9.9.9", archive)).encode("utf-8")

    def opener(request, *, timeout: float):
        if request.full_url == update_service.LATEST_RELEASE_URL:
            assert timeout == 10.0
            return Response(metadata)
        assert request.full_url.endswith("MasteryLedger-windows-x64-v9.9.9.zip")
        assert timeout == 60.0
        return Response(archive)

    install_root = tmp_path / "installed"
    install_root.mkdir()
    executable = install_root / "MasteryLedger.exe"
    executable.write_bytes(b"old executable")
    launches: list[list[str]] = []

    monkeypatch.setattr(update_service, "automatic_install_available", lambda: True)
    monkeypatch.setattr(update_service.sys, "executable", str(executable))
    monkeypatch.setattr(update_service, "app_data_dir", lambda: tmp_path / "app-data")
    monkeypatch.setattr(
        update_service.subprocess,
        "Popen",
        lambda args, **_kwargs: launches.append(args),
    )

    result = install_update("9.9.9", opener=opener)

    assert result == UpdateInstallResult(version="9.9.9")
    payload_root = tmp_path / "app-data" / "updates" / "v9.9.9" / "payload"
    assert (payload_root / "MasteryLedger.exe").read_bytes() == b"new executable"
    assert (payload_root / "_internal" / "version.txt").read_text() == "9.9.9"
    assert launches and launches[0][0] == "powershell.exe"
    assert (payload_root.parent / "apply-update.ps1").is_file()


def test_update_routes_require_session_and_schedule_restart(tmp_path: Path) -> None:
    installed: list[str] = []
    exits: list[str] = []
    app = create_app(
        session_token="update-session",
        web_dir=tmp_path / "missing-web",
        update_checker=lambda: UpdateStatus(
            status="available",
            current_version="0.1.1",
            latest_version="0.1.2",
            release_url="https://github.com/Howard-Starfield/Mastery-Ledger/releases/tag/v0.1.2",
            asset_name="MasteryLedger-windows-x64-v0.1.2.zip",
            download_size=20_000_000,
            automatic_install_available=True,
        ),
        update_installer=lambda version: (
            installed.append(version) or UpdateInstallResult(version=version)
        ),
        update_exit=lambda: exits.append("exit"),
    )

    with TestClient(app) as client:
        assert client.get("/api/v1/update").status_code == 401
        client.get("/bootstrap/update-session/open", follow_redirects=False)
        status = client.get("/api/v1/update")
        assert status.status_code == 200
        assert status.json()["latest_version"] == "0.1.2"
        install = client.post("/api/v1/update/install", json={"version": "0.1.2"})
        assert install.status_code == 200
        assert install.json()["status"] == "restarting"

    assert installed == ["0.1.2"]
    assert exits == ["exit"]
