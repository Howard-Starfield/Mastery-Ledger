from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from mastery_ledger.config import bundled_web_dir, default_workspace_path
from mastery_ledger.database import initialize_database, save_onboarding
from mastery_ledger.models import (
    DoctorResult,
    OnboardingRequest,
    OnboardingResult,
    WorkspaceValidationRequest,
    WorkspaceValidationResult,
)
from mastery_ledger.runtime import build_doctor_result, validate_workspace

SESSION_COOKIE = "mastery_ledger_session"


def create_app(*, session_token: str | None = None, web_dir: Path | None = None) -> FastAPI:
    token = session_token or os.environ.get("MASTERY_LEDGER_SESSION_TOKEN") or secrets.token_urlsafe(32)
    frontend = web_dir or bundled_web_dir()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        initialize_database()
        yield

    app = FastAPI(
        title="Mastery Ledger",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    def require_session(mastery_ledger_session: str | None = Cookie(default=None)) -> None:
        if not mastery_ledger_session or not secrets.compare_digest(mastery_ledger_session, token):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Local session required")

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "schema_version": "health-v1", "application": "mastery-ledger"}

    @app.get("/api/v1/status", response_model=DoctorResult, dependencies=[Depends(require_session)])
    def application_status() -> DoctorResult:
        return build_doctor_result()

    @app.get("/api/v1/onboarding/defaults", dependencies=[Depends(require_session)])
    def onboarding_defaults() -> dict[str, object]:
        return {
            "schema_version": "onboarding-defaults-v1",
            "workspace_path": str(default_workspace_path()),
            "workspace_name": "Primary learning workspace",
            "language": "en",
            "processing_mode": "local_only",
            "reduced_motion": False,
            "review_intervals": [1, 3, 7, 14, 28, 56, 112, 224, 448, 896, 1792, 3584],
        }

    @app.post(
        "/api/v1/onboarding/validate-workspace",
        response_model=WorkspaceValidationResult,
        dependencies=[Depends(require_session)],
    )
    def validate_workspace_route(request: WorkspaceValidationRequest) -> WorkspaceValidationResult:
        return validate_workspace(request.path)

    @app.post(
        "/api/v1/onboarding/complete",
        response_model=OnboardingResult,
        dependencies=[Depends(require_session)],
    )
    def complete_onboarding(request: OnboardingRequest) -> OnboardingResult:
        validation = validate_workspace(request.workspace_path, create=True)
        if not validation.valid:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=validation.message)
        workspace = save_onboarding(request, Path(validation.path))
        return OnboardingResult(workspace=workspace)

    @app.get("/bootstrap/{bootstrap_token}", include_in_schema=False)
    def bootstrap(bootstrap_token: str) -> Response:
        if not secrets.compare_digest(bootstrap_token, token):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        response = RedirectResponse(url="/onboarding", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            samesite="strict",
            secure=False,
            path="/",
        )
        return response

    assets = frontend / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{requested_path:path}", include_in_schema=False)
    def frontend_route(requested_path: str) -> Response:
        if requested_path.startswith("api/") or requested_path.startswith("bootstrap/"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        index = frontend / "index.html"
        if index.is_file():
            candidate = (frontend / requested_path).resolve()
            try:
                candidate.relative_to(frontend.resolve())
            except ValueError:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from None
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index)
        return HTMLResponse(
            "<main><h1>Mastery Ledger</h1><p>The frontend has not been built yet.</p></main>",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return app


app = create_app()
