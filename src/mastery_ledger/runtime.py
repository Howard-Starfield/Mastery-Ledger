from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path

from mastery_ledger import __version__
from mastery_ledger.config import database_path
from mastery_ledger.database import DatabaseReadError, active_workspace
from mastery_ledger.models import CapabilityState, DoctorResult, WorkspaceState, WorkspaceValidationResult


def _is_writable_directory(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        descriptor, probe = tempfile.mkstemp(prefix=".mastery-ledger-write-", dir=path)
        os.close(descriptor)
        Path(probe).unlink(missing_ok=True)
        return True
    except OSError:
        return False


def validate_workspace(raw_path: str, *, create: bool = False) -> WorkspaceValidationResult:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        return WorkspaceValidationResult(
            path=str(candidate),
            valid=False,
            exists=candidate.exists(),
            writable=False,
            will_create=False,
            message="Use an absolute workspace path.",
        )

    candidate = candidate.resolve(strict=False)
    exists = candidate.exists()
    if exists and not candidate.is_dir():
        return WorkspaceValidationResult(
            path=str(candidate),
            valid=False,
            exists=True,
            writable=False,
            will_create=False,
            message="The selected path is a file, not a folder.",
        )

    if not exists and create:
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            exists = True
        except OSError as error:
            return WorkspaceValidationResult(
                path=str(candidate),
                valid=False,
                exists=False,
                writable=False,
                will_create=False,
                message=f"The workspace could not be created: {error}",
            )

    if exists:
        writable = _is_writable_directory(candidate)
        return WorkspaceValidationResult(
            path=str(candidate),
            valid=writable,
            exists=True,
            writable=writable,
            will_create=False,
            message="Workspace is ready." if writable else "The workspace is not writable.",
        )

    parent = candidate.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    writable = parent.is_dir() and _is_writable_directory(parent)
    return WorkspaceValidationResult(
        path=str(candidate),
        valid=writable,
        exists=False,
        writable=writable,
        will_create=writable,
        message="The folder will be created when setup is saved." if writable else "The parent folder is not writable.",
    )


def capabilities() -> CapabilityState:
    return CapabilityState(
        web_app="ready",
        yt_dlp="ready" if importlib.util.find_spec("yt_dlp") else "not_installed",
        local_asr="ready" if importlib.util.find_spec("faster_whisper") else "not_configured",
        ffmpeg_export="unavailable",
    )


def build_doctor_result() -> DoctorResult:
    try:
        row = active_workspace(database_path())
    except DatabaseReadError:
        return DoctorResult(
            status="runtime_error",
            app_version=__version__,
            onboarding_required=False,
            capabilities=capabilities(),
            action="inspect_runtime",
        )
    if row is None:
        return DoctorResult(
            status="onboarding_required",
            app_version=__version__,
            onboarding_required=True,
            capabilities=capabilities(),
            action="open_onboarding",
        )

    validation = validate_workspace(row["path"])
    workspace = WorkspaceState(
        workspace_id=row["workspace_id"],
        name=row["name"],
        path=validation.path,
        available=validation.exists,
        writable=validation.writable,
    )
    if not validation.valid:
        return DoctorResult(
            status="workspace_unavailable",
            app_version=__version__,
            onboarding_required=False,
            active_workspace=workspace,
            capabilities=capabilities(),
            action="repair_workspace",
        )

    return DoctorResult(
        status="ready",
        app_version=__version__,
        onboarding_required=False,
        active_workspace=workspace,
        capabilities=capabilities(),
    )
