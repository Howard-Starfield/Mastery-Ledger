from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class WorkspaceState(BaseModel):
    workspace_id: str
    name: str
    path: str
    available: bool
    writable: bool


class ApplicationCapabilities(BaseModel):
    exam_player: Literal["ready"] = "ready"
    learner_state: Literal["ready"] = "ready"
    review_scheduler: Literal["ready"] = "ready"


class DoctorResult(BaseModel):
    schema_version: Literal["doctor-v2"] = "doctor-v2"
    status: Literal[
        "ready",
        "onboarding_required",
        "workspace_unavailable",
        "incompatible",
        "runtime_error",
    ]
    app_version: str
    skill_version: str | None = None
    compatible_skill_range: str = ">=0.1.0,<0.2.0"
    skill_compatible: bool = True
    onboarding_required: bool
    active_workspace: WorkspaceState | None = None
    capabilities: ApplicationCapabilities = Field(default_factory=ApplicationCapabilities)
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


class FolderPickerRequest(BaseModel):
    initial_path: str | None = Field(default=None, max_length=4096)


class FolderPickerResult(BaseModel):
    schema_version: Literal["folder-picker-v1"] = "folder-picker-v1"
    status: Literal["selected", "cancelled", "unavailable"]
    path: str | None = None
    message: str | None = None


class WorkspaceRepairRequest(BaseModel):
    workspace_path: str = Field(min_length=1, max_length=4096)
    workspace_name: str = Field(min_length=1, max_length=120)


class WorkspaceRepairResult(BaseModel):
    schema_version: Literal["workspace-repair-v1"] = "workspace-repair-v1"
    status: Literal["complete"] = "complete"
    workspace: WorkspaceState


class OnboardingRequest(BaseModel):
    workspace_path: str = Field(min_length=1, max_length=4096)
    workspace_name: str = Field(default="Primary learning workspace", min_length=1, max_length=120)
    language: str = Field(default="en", min_length=2, max_length=24)
    reduced_motion: bool = False
    review_intervals: list[int] = Field(
        default_factory=lambda: [1, 3, 7, 14, 28, 56, 112, 224, 448, 896, 1792, 3584]
    )
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
    reduced_motion: bool
    review_curve: ReviewCurveProfile
    default_review_intervals: list[int]
    scheduled_question_count: int = Field(ge=0)


class AppearanceSettings(BaseModel):
    schema_version: Literal["appearance-settings-v1"] = "appearance-settings-v1"
    theme_mode: Literal["system", "light", "dark"] = "system"
    navigation_panel_open: bool = True
    navigation_panel_width: int = Field(default=224, ge=220, le=432)
    ui_scale: int = Field(default=100, ge=80, le=125)
    content_theme: Literal["infield"] = "infield"


class AppearanceSettingsUpdateRequest(BaseModel):
    theme_mode: Literal["system", "light", "dark"]
    navigation_panel_open: bool
    navigation_panel_width: int = Field(ge=220, le=432)
    ui_scale: int = Field(default=100, ge=80, le=125)
    content_theme: Literal["infield"] = "infield"


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
    source_status: Literal["verified", "self_checked", "ready", "review_needed"] = "ready"
    assessment_kind: Literal["exam", "practice"] = "exam"
    mastery_eligible: bool = True
    resume_available: bool = False


class DashboardCourse(BaseModel):
    course_id: str
    title: str
    question_count: int = Field(ge=0)
    ready_exam_count: int = Field(ge=0)
    due_count: int = Field(ge=0)
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


class StudyChapter(BaseModel):
    chapter_id: str
    title: str
    chapter_class: str
    lesson_path: str
    word_count: int = Field(ge=0)


class StudyCourse(BaseModel):
    course_id: str
    title: str
    updated_at: str | None = None
    publication_status: str = "UNSPECIFIED"
    chapters: list[StudyChapter] = Field(default_factory=list)


class StudyLibraryResult(BaseModel):
    schema_version: Literal["study-library-v1"] = "study-library-v1"
    workspace: WorkspaceState
    courses: list[StudyCourse] = Field(default_factory=list)
    total_courses: int = Field(default=0, ge=0)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=10, ge=1, le=10)
    has_more: bool = False
    warnings: list[str] = Field(default_factory=list)


class StudyLessonResult(BaseModel):
    schema_version: Literal["study-lesson-v1"] = "study-lesson-v1"
    course_id: str
    course_title: str
    chapter_id: str
    title: str
    lesson_path: str
    format: Literal["markdown"] = "markdown"
    content: str
    word_count: int = Field(ge=0)


class StudyGlossaryTerm(BaseModel):
    term_id: str
    term: str
    definition: str
    aliases: list[str] = Field(default_factory=list)
    chapter_ids: list[str] = Field(default_factory=list)
    source_count: int = Field(ge=0)


class StudyGlossaryResult(BaseModel):
    schema_version: Literal["study-glossary-v1"] = "study-glossary-v1"
    course_id: str
    course_title: str
    terms: list[StudyGlossaryTerm] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GlossaryCourseSummary(BaseModel):
    course_id: str
    title: str
    term_count: int = Field(ge=0)


class GlossaryChapterLink(BaseModel):
    chapter_id: str
    title: str


class GlossaryIndexTerm(StudyGlossaryTerm):
    course_id: str
    course_title: str
    chapters: list[GlossaryChapterLink] = Field(default_factory=list)


class GlossaryIndexResult(BaseModel):
    schema_version: Literal["glossary-index-v1"] = "glossary-index-v1"
    workspace: WorkspaceState
    courses: list[GlossaryCourseSummary] = Field(default_factory=list)
    selected_course_id: str | None = None
    query: str = ""
    total_terms: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    has_more: bool = False
    terms: list[GlossaryIndexTerm] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class UpdateStatus(BaseModel):
    schema_version: Literal["update-status-v1"] = "update-status-v1"
    status: Literal["up_to_date", "available", "unavailable"]
    current_version: str
    latest_version: str | None = None
    release_url: str | None = None
    asset_name: str | None = None
    download_size: int | None = Field(default=None, ge=1)
    automatic_install_available: bool = False
    message: str | None = None


class UpdateInstallRequest(BaseModel):
    version: str = Field(min_length=1, max_length=40)


class UpdateInstallResult(BaseModel):
    schema_version: Literal["update-install-v1"] = "update-install-v1"
    status: Literal["restarting"] = "restarting"
    version: str


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
    source_status: Literal["verified", "self_checked", "unavailable"]


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
    assessment_kind: Literal["exam", "practice", "review"] = "exam"
    mastery_eligible: bool = True
    started_at: str
    elapsed_seconds: int = Field(default=0, ge=0)
    resumed: bool = False
    questions: list[ExamQuestionView]
    answers: list[QuestionFeedback] = Field(default_factory=list)


class QuestionSubmissionRequest(BaseModel):
    option_id: str = Field(min_length=1, max_length=24)


class ExamPauseResult(BaseModel):
    schema_version: Literal["exam-pause-v1"] = "exam-pause-v1"
    attempt_id: str
    status: Literal["paused"] = "paused"
    elapsed_seconds: int = Field(ge=0)


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
    assessment_kind: Literal["exam", "practice", "review"] = "exam"
    mastery_updated: bool = True
    question_count: int = Field(ge=0)
    answered_count: int = Field(ge=0)
    correct_count: int = Field(ge=0)
    incorrect_count: int = Field(ge=0)
    unanswered_count: int = Field(ge=0)
    score_percent: float = Field(ge=0, le=100)
    questions: list[QuestionReview] = Field(default_factory=list)
