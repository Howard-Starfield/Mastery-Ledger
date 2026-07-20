from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from mastery_ledger.config import bundled_web_dir, default_workspace_path
from mastery_ledger.dashboard import build_dashboard
from mastery_ledger.database import (
    get_job,
    initialize_database,
    request_job_cancellation,
    retry_job,
    save_onboarding,
)
from mastery_ledger.exam_service import (
    AttemptConflictError,
    AttemptNotFoundError,
    AttemptStorageError,
    ExamNotFoundError,
    ExamSessionStore,
    ExamValidationError,
)
from mastery_ledger.ingestion_worker import IngestionWorker
from mastery_ledger.models import (
    ApplicationSettings,
    DashboardResult,
    DoctorResult,
    ExamAttemptStart,
    ExamCompletion,
    OnboardingRequest,
    OnboardingResult,
    QuestionFeedback,
    QuestionSubmissionRequest,
    ReviewCurveUpdateRequest,
    ReviewCurveUpdateResult,
    SourceInboxResult,
    SourceIntakeRequest,
    SourceIntakeResult,
    WorkspaceState,
    WorkspaceValidationRequest,
    WorkspaceValidationResult,
)
from mastery_ledger.review_service import ReviewNotFoundError, start_due_review
from mastery_ledger.runtime import build_doctor_result, validate_workspace
from mastery_ledger.settings_service import (
    DEFAULT_REVIEW_INTERVALS,
    SettingsUpdateError,
    application_settings,
    update_review_curve,
)
from mastery_ledger.source_service import (
    SourceIntakeError,
    _course_by_id,
    queue_source,
    source_inbox,
    update_source_record,
)

SESSION_COOKIE = "mastery_ledger_session"


def create_app(
    *,
    session_token: str | None = None,
    web_dir: Path | None = None,
    start_ingestion_worker: bool = True,
) -> FastAPI:
    token = session_token or os.environ.get("MASTERY_LEDGER_SESSION_TOKEN") or secrets.token_urlsafe(32)
    frontend = web_dir or bundled_web_dir()
    exam_sessions = ExamSessionStore()
    ingestion_worker = IngestionWorker(
        lambda: (
            doctor.active_workspace
            if (doctor := build_doctor_result()).status == "ready"
            else None
        )
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        initialize_database()
        if start_ingestion_worker:
            ingestion_worker.start()
        try:
            yield
        finally:
            if start_ingestion_worker:
                ingestion_worker.stop()

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

    @app.get("/api/v1/dashboard", response_model=DashboardResult, dependencies=[Depends(require_session)])
    def dashboard() -> DashboardResult:
        doctor = build_doctor_result()
        if doctor.status != "ready" or doctor.active_workspace is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Complete onboarding before opening the workspace dashboard.",
            )
        return build_dashboard(doctor.active_workspace)

    def ready_workspace() -> WorkspaceState:
        doctor = build_doctor_result()
        if doctor.status != "ready" or doctor.active_workspace is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Complete onboarding before starting an exam.",
            )
        return doctor.active_workspace

    @app.get(
        "/api/v1/settings",
        response_model=ApplicationSettings,
        dependencies=[Depends(require_session)],
    )
    def settings() -> ApplicationSettings:
        return application_settings(ready_workspace())

    @app.get(
        "/api/v1/sources",
        response_model=SourceInboxResult,
        dependencies=[Depends(require_session)],
    )
    def sources() -> SourceInboxResult:
        return source_inbox(ready_workspace())

    @app.post(
        "/api/v1/sources",
        response_model=SourceIntakeResult,
        dependencies=[Depends(require_session)],
    )
    def add_source(request: SourceIntakeRequest) -> SourceIntakeResult:
        try:
            return queue_source(ready_workspace(), request)
        except SourceIntakeError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error

    def owned_job(job_id: str) -> dict[str, object]:
        job = get_job(job_id)
        payload = job.get("payload") if job else None
        workspace = ready_workspace()
        if (
            job is None
            or not isinstance(payload, dict)
            or payload.get("workspace_id") != workspace.workspace_id
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion job not found.")
        return job

    @app.post(
        "/api/v1/sources/jobs/{job_id}/cancel",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_session)],
    )
    def cancel_source_job(job_id: str) -> Response:
        job = owned_job(job_id)
        if not request_job_cancellation(job_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This job cannot be cancelled.")
        current = get_job(job_id)
        payload = job.get("payload")
        if current and current.get("state") == "cancelled" and isinstance(payload, dict):
            workspace = ready_workspace()
            found = _course_by_id(Path(workspace.path), str(payload.get("course_id") or ""))
            if found is not None:
                update_source_record(
                    found[0],
                    str(payload.get("source_id") or ""),
                    {
                        "processing_status": "cancelled",
                        "error_code": "cancelled",
                        "recovery_suggestion": "Retry if this source is still needed.",
                    },
                )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/v1/sources/jobs/{job_id}/retry",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_session)],
    )
    def retry_source_job(job_id: str) -> Response:
        job = owned_job(job_id)
        if not retry_job(job_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This job is not ready to retry.")
        payload = job.get("payload")
        if isinstance(payload, dict):
            workspace = ready_workspace()
            found = _course_by_id(Path(workspace.path), str(payload.get("course_id") or ""))
            if found is not None:
                update_source_record(
                    found[0],
                    str(payload.get("source_id") or ""),
                    {
                        "processing_status": "queued",
                        "error_code": None,
                        "recovery_suggestion": None,
                    },
                )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.put(
        "/api/v1/settings/review-curve",
        response_model=ReviewCurveUpdateResult,
        dependencies=[Depends(require_session)],
    )
    def save_review_curve(request: ReviewCurveUpdateRequest) -> ReviewCurveUpdateResult:
        try:
            return update_review_curve(ready_workspace(), request)
        except SettingsUpdateError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error

    @app.post(
        "/api/v1/reviews/attempts",
        response_model=ExamAttemptStart,
        dependencies=[Depends(require_session)],
    )
    def start_review(course_id: str | None = None) -> ExamAttemptStart:
        try:
            return start_due_review(
                exam_sessions,
                ready_workspace(),
                course_id=course_id,
            )
        except ReviewNotFoundError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except ExamValidationError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        except AttemptStorageError as error:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)) from error

    @app.post(
        "/api/v1/exams/{course_id}/{exam_id}/attempts",
        response_model=ExamAttemptStart,
        dependencies=[Depends(require_session)],
    )
    def start_exam(course_id: str, exam_id: str) -> ExamAttemptStart:
        try:
            return exam_sessions.start(ready_workspace(), course_id, exam_id)
        except ExamNotFoundError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except ExamValidationError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        except AttemptStorageError as error:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)) from error

    @app.post(
        "/api/v1/exams/{course_id}/{exam_id}/attempts/{attempt_id}/questions/{question_id}",
        response_model=QuestionFeedback,
        dependencies=[Depends(require_session)],
    )
    def submit_exam_question(
        course_id: str,
        exam_id: str,
        attempt_id: str,
        question_id: str,
        request: QuestionSubmissionRequest,
    ) -> QuestionFeedback:
        try:
            return exam_sessions.submit(
                attempt_id,
                course_id,
                exam_id,
                question_id,
                request.option_id,
            )
        except AttemptNotFoundError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except AttemptConflictError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        except ExamValidationError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        except AttemptStorageError as error:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)) from error

    @app.post(
        "/api/v1/exams/{course_id}/{exam_id}/attempts/{attempt_id}/finish",
        response_model=ExamCompletion,
        dependencies=[Depends(require_session)],
    )
    def finish_exam(course_id: str, exam_id: str, attempt_id: str) -> ExamCompletion:
        try:
            return exam_sessions.finish(attempt_id, course_id, exam_id)
        except AttemptNotFoundError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except AttemptStorageError as error:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)) from error

    @app.get("/api/v1/onboarding/defaults", dependencies=[Depends(require_session)])
    def onboarding_defaults() -> dict[str, object]:
        return {
            "schema_version": "onboarding-defaults-v1",
            "workspace_path": str(default_workspace_path()),
            "workspace_name": "Primary learning workspace",
            "language": "en",
            "processing_mode": "local_only",
            "reduced_motion": False,
            "review_intervals": DEFAULT_REVIEW_INTERVALS,
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
