from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class WorkspaceState(BaseModel):
    workspace_id: str
    name: str
    path: str
    available: bool
    writable: bool


class CapabilityState(BaseModel):
    web_app: Literal["ready", "unavailable"] = "ready"
    yt_dlp: Literal["ready", "not_installed"] = "not_installed"
    local_asr: Literal["ready", "not_configured"] = "not_configured"
    ffmpeg_export: Literal["ready", "unavailable"] = "unavailable"


class DoctorResult(BaseModel):
    schema_version: Literal["doctor-v1"] = "doctor-v1"
    status: Literal[
        "ready",
        "onboarding_required",
        "workspace_unavailable",
        "incompatible",
        "runtime_error",
    ]
    app_version: str
    skill_compatible: bool = True
    onboarding_required: bool
    active_workspace: WorkspaceState | None = None
    capabilities: CapabilityState = Field(default_factory=CapabilityState)
    action: str | None = None


class WorkspaceValidationRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


class WorkspaceValidationResult(BaseModel):
    schema_version: Literal["workspace-validation-v1"] = "workspace-validation-v1"
    path: str
    valid: bool
    exists: bool
    writable: bool
    will_create: bool
    message: str


class OnboardingRequest(BaseModel):
    workspace_path: str = Field(min_length=1, max_length=4096)
    workspace_name: str = Field(default="Primary learning workspace", min_length=1, max_length=120)
    language: str = Field(default="en", min_length=2, max_length=24)
    processing_mode: Literal["local_only", "cloud_allowed", "metadata_only"] = "local_only"
    reduced_motion: bool = False
    review_intervals: list[int] = Field(
        default_factory=lambda: [1, 3, 7, 14, 28, 56, 112, 224, 448, 896, 1792, 3584]
    )
    initial_source_hint: str | None = Field(default=None, max_length=4096)

    @field_validator("review_intervals")
    @classmethod
    def validate_intervals(cls, value: list[int]) -> list[int]:
        if not value or len(value) > 24:
            raise ValueError("Provide between 1 and 24 review intervals.")
        if any(day < 1 or day > 36500 for day in value):
            raise ValueError("Review intervals must be between 1 and 36500 days.")
        if value != sorted(set(value)):
            raise ValueError("Review intervals must be unique and strictly increasing.")
        return value


class OnboardingResult(BaseModel):
    schema_version: Literal["onboarding-result-v1"] = "onboarding-result-v1"
    status: Literal["complete"] = "complete"
    workspace: WorkspaceState


class DashboardExam(BaseModel):
    exam_id: str
    course_id: str
    course_title: str
    title: str
    question_count: int = Field(ge=0)
    estimated_minutes: int = Field(ge=0)
    concepts: list[str] = Field(default_factory=list)
    created_at: str | None = None
    source_status: Literal["verified", "ready", "review_needed"] = "ready"


class DashboardCourse(BaseModel):
    course_id: str
    title: str
    question_count: int = Field(ge=0)
    ready_exam_count: int = Field(ge=0)
    due_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    source_ready_count: int = Field(ge=0)
    updated_at: str | None = None


class OwnershipStage(BaseModel):
    stage_index: int = Field(ge=0)
    interval_days: int = Field(ge=1)
    question_count: int = Field(ge=0)


class DashboardResult(BaseModel):
    schema_version: Literal["dashboard-v1"] = "dashboard-v1"
    workspace: WorkspaceState
    due_now: int = Field(ge=0)
    ready_exams: list[DashboardExam] = Field(default_factory=list)
    recent_courses: list[DashboardCourse] = Field(default_factory=list)
    ownership_curve: list[OwnershipStage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
