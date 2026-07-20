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


class ReviewCurveProfile(BaseModel):
    curve_id: str = Field(min_length=1, max_length=120)
    version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=120)
    interval_days: list[int]
    created_at: str | None = None
    supersedes_version: int | None = Field(default=None, ge=1)

    @field_validator("interval_days")
    @classmethod
    def validate_intervals(cls, value: list[int]) -> list[int]:
        return OnboardingRequest.validate_intervals(value)


class ApplicationSettings(BaseModel):
    schema_version: Literal["settings-v1"] = "settings-v1"
    language: str
    processing_mode: Literal["local_only", "cloud_allowed", "metadata_only"]
    reduced_motion: bool
    review_curve: ReviewCurveProfile
    default_review_intervals: list[int]
    scheduled_question_count: int = Field(ge=0)


class ReviewCurveUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    interval_days: list[int]
    application_policy: Literal[
        "new_questions_only", "future_advancement", "recalculate_all"
    ]
    save_mode: Literal["new_version", "duplicate_profile"] = "new_version"
    confirm_recalculate: bool = False

    @field_validator("interval_days")
    @classmethod
    def validate_intervals(cls, value: list[int]) -> list[int]:
        return OnboardingRequest.validate_intervals(value)


class ReviewCurveUpdateResult(BaseModel):
    schema_version: Literal["review-curve-update-v1"] = "review-curve-update-v1"
    review_curve: ReviewCurveProfile
    application_policy: Literal[
        "new_questions_only", "future_advancement", "recalculate_all"
    ]
    affected_question_count: int = Field(ge=0)
    preserved_without_anchor_count: int = Field(ge=0)


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
    resume_available: bool = False


class DashboardCourse(BaseModel):
    course_id: str
    title: str
    question_count: int = Field(ge=0)
    ready_exam_count: int = Field(ge=0)
    due_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    source_ready_count: int = Field(ge=0)
    concept_count: int = Field(ge=0)
    proficient_concept_count: int = Field(ge=0)
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


class ExamOption(BaseModel):
    option_id: str = Field(min_length=1, max_length=24)
    text: str = Field(min_length=1, max_length=10_000)


class ExamQuestionView(BaseModel):
    question_id: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=50_000)
    options: list[ExamOption] = Field(min_length=2, max_length=12)
    difficulty: str | int | None = None
    concept_ids: list[str] = Field(default_factory=list)
    source_count: int = Field(ge=0)
    source_status: Literal["verified", "unavailable"]


class SourceDisclosure(BaseModel):
    source_id: str
    title: str
    locator_label: str
    support_strength: Literal["direct", "partial", "contextual"]
    href: str | None = None


class QuestionFeedback(BaseModel):
    schema_version: Literal["question-feedback-v1"] = "question-feedback-v1"
    question_id: str
    selected_option_id: str
    status: Literal["correct", "incorrect"]
    correct: bool
    locked: Literal[True] = True
    explanation: str | None = None
    sources: list[SourceDisclosure] = Field(default_factory=list)


class ExamAttemptStart(BaseModel):
    schema_version: Literal["exam-attempt-v1"] = "exam-attempt-v1"
    attempt_id: str
    exam_id: str
    course_id: str
    course_title: str
    title: str
    estimated_minutes: int = Field(ge=0)
    started_at: str
    resumed: bool = False
    questions: list[ExamQuestionView]
    answers: list[QuestionFeedback] = Field(default_factory=list)


class QuestionSubmissionRequest(BaseModel):
    option_id: str = Field(min_length=1, max_length=24)


class QuestionReview(BaseModel):
    question_id: str
    selected_option_id: str | None = None
    correct_option_id: str
    status: Literal["correct", "incorrect", "unanswered"]
    explanation: str
    sources: list[SourceDisclosure] = Field(default_factory=list)


class ExamCompletion(BaseModel):
    schema_version: Literal["exam-completion-v1"] = "exam-completion-v1"
    attempt_id: str
    status: Literal["complete"] = "complete"
    question_count: int = Field(ge=0)
    answered_count: int = Field(ge=0)
    correct_count: int = Field(ge=0)
    incorrect_count: int = Field(ge=0)
    unanswered_count: int = Field(ge=0)
    score_percent: float = Field(ge=0, le=100)
    questions: list[QuestionReview] = Field(default_factory=list)


SourceType = Literal[
    "web_article",
    "remote_video",
    "local_document",
    "local_media",
    "local_subtitle",
]
RightsBasis = Literal[
    "web_reference",
    "user_owned",
    "platform_permitted_download",
    "public_license",
    "explicit_permission",
]
JobState = Literal[
    "queued",
    "running",
    "needs_user_action",
    "partial",
    "complete",
    "failed",
    "cancelled",
]


class SourceIntakeRequest(BaseModel):
    course_id: str | None = Field(default=None, min_length=1, max_length=120)
    new_course_title: str | None = Field(default=None, min_length=1, max_length=160)
    source_type: SourceType
    location: str = Field(min_length=1, max_length=8192)
    title: str | None = Field(default=None, max_length=300)
    rights_basis: RightsBasis = "web_reference"
    language: str = Field(default="en", min_length=2, max_length=24)
    allow_transcription: bool = False


class SourceSummary(BaseModel):
    source_id: str
    course_id: str
    title: str
    source_type: SourceType
    original_location: str
    processing_status: str
    rights_basis: RightsBasis
    language: str
    retrieved_at: str | None = None
    content_hash: str | None = None
    knowledge_path: str | None = None
    artifact_count: int = Field(default=0, ge=0)
    error_code: str | None = None
    recovery_suggestion: str | None = None


class IngestionJobView(BaseModel):
    job_id: str
    kind: str
    state: JobState
    course_id: str
    source_id: str
    progress: float = Field(ge=0, le=1)
    stage: str
    error_code: str | None = None
    recovery_suggestion: str | None = None
    created_at: str
    updated_at: str


class SourceInboxCourse(BaseModel):
    course_id: str
    title: str
    source_count: int = Field(ge=0)
    ready_count: int = Field(ge=0)


class SourceInboxResult(BaseModel):
    schema_version: Literal["source-inbox-v1"] = "source-inbox-v1"
    courses: list[SourceInboxCourse] = Field(default_factory=list)
    sources: list[SourceSummary] = Field(default_factory=list)
    jobs: list[IngestionJobView] = Field(default_factory=list)
    capabilities: CapabilityState = Field(default_factory=CapabilityState)


class SourceIntakeResult(BaseModel):
    schema_version: Literal["source-intake-v1"] = "source-intake-v1"
    course_id: str
    source_id: str
    job: IngestionJobView
