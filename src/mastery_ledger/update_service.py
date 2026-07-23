from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from mastery_ledger import __version__
from mastery_ledger.config import app_data_dir
from mastery_ledger.models import UpdateInstallResult, UpdateStatus

GITHUB_OWNER = "Howard-Starfield"
GITHUB_REPOSITORY = "Mastery-Ledger"
LATEST_RELEASE_URL = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPOSITORY}/releases/latest"
)
RELEASE_DOWNLOAD_PREFIX = (
    f"/{GITHUB_OWNER}/{GITHUB_REPOSITORY}/releases/download/"
)
MAX_RELEASE_METADATA_BYTES = 1 * 1024 * 1024
MAX_UPDATE_ARCHIVE_BYTES = 300 * 1024 * 1024
VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
SHA256_PATTERN = re.compile(r"^sha256:([0-9a-fA-F]{64})$")


class UpdateServiceError(RuntimeError):
    """Raised when an application update cannot be verified or prepared safely."""


@dataclass(frozen=True)
class ReleaseAsset:
    version: str
    release_url: str
    name: str
    download_url: str
    size: int
    sha256: str


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(value.strip())
    if match is None:
        raise UpdateServiceError(f"Unsupported release version: {value!r}")
    return tuple(int(part) for part in match.groups())


def _read_limited(response: Any, limit: int) -> bytes:
    payload = response.read(limit + 1)
    if len(payload) > limit:
        raise UpdateServiceError("The update response exceeded the allowed size.")
    return payload


def _request(url: str, *, accept: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": f"Mastery-Ledger/{__version__}",
            "X-GitHub-Api-Version": "2026-03-10",
        },
    )


def _latest_release(
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> ReleaseAsset:
    try:
        with opener(
            _request(LATEST_RELEASE_URL, accept="application/vnd.github+json"),
            timeout=10.0,
        ) as response:
            payload = json.loads(
                _read_limited(response, MAX_RELEASE_METADATA_BYTES).decode("utf-8")
            )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        urllib.error.URLError,
    ) as error:
        raise UpdateServiceError("The latest release could not be checked.") from error

    if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
        raise UpdateServiceError("GitHub did not return a stable release.")
    tag = str(payload.get("tag_name") or "")
    version_tuple = _version_tuple(tag)
    version = ".".join(str(part) for part in version_tuple)
    expected_name = f"MasteryLedger-windows-x64-v{version}.zip"
    assets = payload.get("assets")
    asset = next(
        (
            candidate
            for candidate in assets
            if isinstance(candidate, dict)
            and candidate.get("name") == expected_name
            and candidate.get("state") == "uploaded"
        ),
        None,
    ) if isinstance(assets, list) else None
    if asset is None:
        raise UpdateServiceError("The latest release has no compatible Windows update.")

    download_url = str(asset.get("browser_download_url") or "")
    parsed_url = urllib.parse.urlparse(download_url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "github.com"
        or not parsed_url.path.startswith(RELEASE_DOWNLOAD_PREFIX)
        or not parsed_url.path.endswith(f"/{expected_name}")
    ):
        raise UpdateServiceError("The Windows update URL is not trusted.")
    digest_match = SHA256_PATTERN.fullmatch(str(asset.get("digest") or ""))
    if digest_match is None:
        raise UpdateServiceError("The Windows update has no GitHub SHA-256 digest.")
    try:
        size = int(asset.get("size"))
    except (TypeError, ValueError) as error:
        raise UpdateServiceError("The Windows update size is invalid.") from error
    if size <= 0 or size > MAX_UPDATE_ARCHIVE_BYTES:
        raise UpdateServiceError("The Windows update exceeds the allowed size.")

    release_url = str(payload.get("html_url") or "")
    parsed_release_url = urllib.parse.urlparse(release_url)
    if (
        parsed_release_url.scheme != "https"
        or parsed_release_url.hostname != "github.com"
        or not parsed_release_url.path.startswith(
            f"/{GITHUB_OWNER}/{GITHUB_REPOSITORY}/releases/tag/"
        )
    ):
        raise UpdateServiceError("The release page URL is not trusted.")

    return ReleaseAsset(
        version=version,
        release_url=release_url,
        name=expected_name,
        download_url=download_url,
        size=size,
        sha256=digest_match.group(1).lower(),
    )


def automatic_install_available() -> bool:
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def check_for_updates(
    current_version: str = __version__,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
    can_install: bool | None = None,
) -> UpdateStatus:
    current = _version_tuple(current_version)
    release = _latest_release(opener)
    available = _version_tuple(release.version) > current
    return UpdateStatus(
        status="available" if available else "up_to_date",
        current_version=current_version.lstrip("v"),
        latest_version=release.version,
        release_url=release.release_url,
        asset_name=release.name,
        download_size=release.size,
        automatic_install_available=(
            automatic_install_available() if can_install is None else can_install
        ),
    )


def _download_update(
    release: ReleaseAsset,
    destination: Path,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".download")
    digest = hashlib.sha256()
    downloaded = 0
    try:
        with opener(
            _request(release.download_url, accept="application/octet-stream"),
            timeout=60.0,
        ) as response, temporary.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > MAX_UPDATE_ARCHIVE_BYTES or downloaded > release.size:
                    raise UpdateServiceError("The downloaded update exceeded its declared size.")
                output.write(chunk)
                digest.update(chunk)
        if downloaded != release.size:
            raise UpdateServiceError("The downloaded update was incomplete.")
        if digest.hexdigest().lower() != release.sha256:
            raise UpdateServiceError("The downloaded update failed its SHA-256 check.")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _extract_update(archive: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                relative = PurePosixPath(member.filename.replace("\\", "/"))
                mode = member.external_attr >> 16
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or (relative.parts and ":" in relative.parts[0])
                    or stat.S_ISLNK(mode)
                    or not relative.parts
                ):
                    raise UpdateServiceError("The Windows update contains an unsafe path.")
                target = (destination / Path(*relative.parts)).resolve(strict=False)
                try:
                    target.relative_to(destination.resolve(strict=False))
                except ValueError as error:
                    raise UpdateServiceError(
                        "The Windows update contains an unsafe path."
                    ) from error
            bundle.extractall(destination)
    except (OSError, zipfile.BadZipFile) as error:
        raise UpdateServiceError("The Windows update archive could not be opened.") from error


def _write_update_script(path: Path) -> None:
    script = r'''param(
  [Parameter(Mandatory=$true)][int]$ProcessId,
  [Parameter(Mandatory=$true)][string]$Source,
  [Parameter(Mandatory=$true)][string]$Target,
  [Parameter(Mandatory=$true)][string]$Executable
)
$ErrorActionPreference = "Stop"
$deadline = (Get-Date).AddSeconds(90)
while ((Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
  Start-Sleep -Milliseconds 250
}
if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) { exit 2 }
New-Item -ItemType Directory -Force -Path $Target | Out-Null
Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {
  Copy-Item -LiteralPath $_.FullName -Destination $Target -Recurse -Force
}
Start-Process -FilePath $Executable -WorkingDirectory $Target
Remove-Item -LiteralPath $Source -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
'''
    path.write_text(script, encoding="utf-8-sig")


def _launch_update_script(staging: Path, install_root: Path, executable: Path) -> None:
    script = staging.parent / "apply-update.ps1"
    _write_update_script(script)
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
        subprocess, "DETACHED_PROCESS", 0
    )
    try:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-ProcessId",
                str(os.getpid()),
                "-Source",
                str(staging),
                "-Target",
                str(install_root),
                "-Executable",
                str(executable),
            ],
            close_fds=True,
            creationflags=creation_flags,
        )
    except OSError as error:
        raise UpdateServiceError("The Windows update helper could not start.") from error


def install_update(
    requested_version: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> UpdateInstallResult:
    requested = ".".join(str(part) for part in _version_tuple(requested_version))
    if not automatic_install_available():
        raise UpdateServiceError(
            "One-click installation is available only in the packaged Windows application."
        )
    release = _latest_release(opener)
    if release.version != requested or _version_tuple(release.version) <= _version_tuple(__version__):
        raise UpdateServiceError("The selected update is no longer the latest version.")

    install_root = Path(sys.executable).resolve().parent
    executable = install_root / "MasteryLedger.exe"
    if not executable.is_file():
        raise UpdateServiceError("The installed Mastery Ledger executable was not found.")

    update_root = app_data_dir() / "updates" / f"v{release.version}"
    archive = update_root / release.name
    staging = update_root / "payload"
    _download_update(release, archive, opener=opener)
    _extract_update(archive, staging)
    if not (staging / "MasteryLedger.exe").is_file():
        raise UpdateServiceError("The Windows update does not contain MasteryLedger.exe.")
    _launch_update_script(staging, install_root, executable)
    return UpdateInstallResult(version=release.version)


def exit_for_update() -> None:
    os._exit(0)
