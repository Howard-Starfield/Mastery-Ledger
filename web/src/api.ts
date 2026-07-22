export interface OnboardingDefaults {
  schema_version: 'onboarding-defaults-v1'
  workspace_path: string
  workspace_name: string
  language: string
  reduced_motion: boolean
  review_intervals: number[]
}

export interface WorkspaceValidation {
  schema_version: 'workspace-validation-v1'
  path: string
  valid: boolean
  exists: boolean
  writable: boolean
  will_create: boolean
  message: string
}

export interface FolderPickerResult {
  schema_version: 'folder-picker-v1'
  status: 'selected' | 'cancelled' | 'unavailable'
  path: string | null
  message: string | null
}

export interface OnboardingPayload {
  workspace_path: string
  workspace_name: string
  language: string
  reduced_motion: boolean
  review_intervals: number[]
}

export interface OnboardingResult {
  schema_version: 'onboarding-result-v1'
  status: 'complete'
  workspace: {
    workspace_id: string
    name: string
    path: string
    available: boolean
    writable: boolean
  }
}

export interface ApplicationStatus {
  schema_version: 'doctor-v2'
  status: 'ready' | 'onboarding_required' | 'workspace_unavailable' | 'incompatible' | 'runtime_error'
  app_version: string
  onboarding_required: boolean
  active_workspace: OnboardingResult['workspace'] | null
  action: string | null
}

export interface DashboardExam {
  exam_id: string
  course_id: string
  course_title: string
  title: string
  question_count: number
  estimated_minutes: number
  concepts: string[]
  created_at: string | null
  source_status: 'verified' | 'ready' | 'review_needed'
  resume_available: boolean
}

export interface DashboardCourse {
  course_id: string
  title: string
  question_count: number
  ready_exam_count: number
  due_count: number
  concept_count: number
  proficient_concept_count: number
  updated_at: string | null
}

export interface OwnershipStage {
  stage_index: number
  interval_days: number
  question_count: number
}

export interface DashboardResult {
  schema_version: 'dashboard-v1'
  workspace: OnboardingResult['workspace']
  due_now: number
  ready_exams: DashboardExam[]
  recent_courses: DashboardCourse[]
  ownership_curve: OwnershipStage[]
  warnings: string[]
}

export interface StudyChapter {
  chapter_id: string
  title: string
  chapter_class: string
  lesson_path: string
  word_count: number
}

export interface StudyCourse {
  course_id: string
  title: string
  updated_at: string | null
  publication_status: string
  chapters: StudyChapter[]
}

export interface CourseImportResult {
  schema_version: 'course-import-v1'
  status: 'imported'
  course_id: string
  title: string
  publication_status: 'DRAFT_UNVERIFIED'
  relative_path: string
}

export interface StudyLibraryResult {
  schema_version: 'study-library-v1'
  workspace: OnboardingResult['workspace']
  courses: StudyCourse[]
  warnings: string[]
}

export interface StudyLessonResult {
  schema_version: 'study-lesson-v1'
  course_id: string
  course_title: string
  chapter_id: string
  title: string
  lesson_path: string
  format: 'markdown'
  content: string
  word_count: number
}

export interface StudyGlossaryTerm {
  term_id: string
  term: string
  definition: string
  aliases: string[]
  chapter_ids: string[]
  source_count: number
}

export interface StudyGlossaryResult {
  schema_version: 'study-glossary-v1'
  course_id: string
  course_title: string
  terms: StudyGlossaryTerm[]
  warnings: string[]
}

export interface GlossaryCourseSummary {
  course_id: string
  title: string
  term_count: number
}

export interface GlossaryChapterLink {
  chapter_id: string
  title: string
}

export interface GlossaryIndexTerm extends StudyGlossaryTerm {
  course_id: string
  course_title: string
  chapters: GlossaryChapterLink[]
}

export interface GlossaryIndexResult {
  schema_version: 'glossary-index-v1'
  workspace: OnboardingResult['workspace']
  courses: GlossaryCourseSummary[]
  selected_course_id: string | null
  query: string
  total_terms: number
  offset: number
  limit: number
  has_more: boolean
  terms: GlossaryIndexTerm[]
  warnings: string[]
}

export interface ReviewCurveProfile {
  curve_id: string
  version: number
  name: string
  interval_days: number[]
  created_at: string | null
  supersedes_version: number | null
}

export interface ApplicationSettings {
  schema_version: 'settings-v1'
  language: string
  reduced_motion: boolean
  review_curve: ReviewCurveProfile
  default_review_intervals: number[]
  scheduled_question_count: number
}

export type ThemeMode = 'system' | 'light' | 'dark'

export interface AppearanceSettings {
  schema_version: 'appearance-settings-v1'
  theme_mode: ThemeMode
  navigation_panel_open: boolean
  navigation_panel_width: number
  content_theme: 'infield'
}

export type AppearanceSettingsUpdate = Omit<AppearanceSettings, 'schema_version'>

export type CurveApplicationPolicy = 'new_questions_only' | 'future_advancement' | 'recalculate_all'

export interface ReviewCurveUpdatePayload {
  name: string
  interval_days: number[]
  application_policy: CurveApplicationPolicy
  save_mode: 'new_version' | 'duplicate_profile'
  confirm_recalculate: boolean
}

export interface ReviewCurveUpdateResult {
  schema_version: 'review-curve-update-v1'
  review_curve: ReviewCurveProfile
  application_policy: CurveApplicationPolicy
  affected_question_count: number
  preserved_without_anchor_count: number
}

export interface ExamOption {
  option_id: string
  text: string
}

export interface ExamQuestion {
  question_id: string
  prompt: string
  options: ExamOption[]
  difficulty: string | number | null
  concept_ids: string[]
  source_count: number
  source_status: 'verified' | 'unavailable'
}

export interface ExamAttempt {
  schema_version: 'exam-attempt-v1'
  attempt_id: string
  exam_id: string
  course_id: string
  course_title: string
  title: string
  estimated_minutes: number
  started_at: string
  resumed: boolean
  questions: ExamQuestion[]
  answers: QuestionFeedback[]
}

export interface SourceDisclosure {
  source_id: string
  title: string
  locator_label: string
  support_strength: 'direct' | 'partial' | 'contextual'
  href: string | null
}

export interface QuestionFeedback {
  schema_version: 'question-feedback-v1'
  question_id: string
  selected_option_id: string
  status: 'correct' | 'incorrect'
  correct: boolean
  locked: true
  explanation: string | null
  sources: SourceDisclosure[]
}

export interface QuestionReview {
  question_id: string
  selected_option_id: string | null
  correct_option_id: string
  status: 'correct' | 'incorrect' | 'unanswered'
  explanation: string
  sources: SourceDisclosure[]
}

export interface ExamCompletion {
  schema_version: 'exam-completion-v1'
  attempt_id: string
  status: 'complete'
  question_count: number
  answered_count: number
  correct_count: number
  incorrect_count: number
  unanswered_count: number
  score_percent: number
  questions: QuestionReview[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: 'Unexpected application error.' }))
    const message =
      typeof body.detail === 'string'
        ? body.detail
        : Array.isArray(body.detail) && typeof body.detail[0]?.msg === 'string'
          ? body.detail[0].msg
          : 'Unexpected application error.'
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const onboardingApi = {
  defaults: () => request<OnboardingDefaults>('/api/v1/onboarding/defaults'),
  validateWorkspace: (path: string) =>
    request<WorkspaceValidation>('/api/v1/onboarding/validate-workspace', {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),
  pickFolder: (initialPath: string | null) =>
    request<FolderPickerResult>('/api/v1/system/pick-folder', {
      method: 'POST',
      body: JSON.stringify({ initial_path: initialPath }),
    }),
  complete: (payload: OnboardingPayload) =>
    request<OnboardingResult>('/api/v1/onboarding/complete', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}

export const applicationApi = {
  status: () => request<ApplicationStatus>('/api/v1/status'),
  dashboard: () => request<DashboardResult>('/api/v1/dashboard'),
  studyLibrary: () => request<StudyLibraryResult>('/api/v1/study'),
  importCourse: (file: File) =>
    request<CourseImportResult>(`/api/v1/courses/import?filename=${encodeURIComponent(file.name)}`, {
      method: 'POST',
      headers: { 'Content-Type': file.type || 'application/zip' },
      body: file,
    }),
  studyLesson: (courseId: string, chapterId: string) =>
    request<StudyLessonResult>(
      `/api/v1/study/${encodeURIComponent(courseId)}/chapters/${encodeURIComponent(chapterId)}`,
    ),
  studyGlossary: (courseId: string) =>
    request<StudyGlossaryResult>(`/api/v1/study/${encodeURIComponent(courseId)}/glossary`),
  glossaryIndex: (options: { courseId?: string; query?: string; offset?: number; limit?: number } = {}) => {
    const params = new URLSearchParams()
    if (options.courseId) params.set('course_id', options.courseId)
    if (options.query) params.set('q', options.query)
    if (options.offset) params.set('offset', String(options.offset))
    params.set('limit', String(options.limit ?? 100))
    return request<GlossaryIndexResult>(`/api/v1/glossary?${params.toString()}`)
  },
  settings: () => request<ApplicationSettings>('/api/v1/settings'),
  appearanceSettings: () => request<AppearanceSettings>('/api/v1/settings/appearance'),
  updateAppearanceSettings: (payload: AppearanceSettingsUpdate) =>
    request<AppearanceSettings>('/api/v1/settings/appearance', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  updateReviewCurve: (payload: ReviewCurveUpdatePayload) =>
    request<ReviewCurveUpdateResult>('/api/v1/settings/review-curve', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  repairWorkspace: (workspacePath: string, workspaceName: string) =>
    request<{ schema_version: 'workspace-repair-v1'; status: 'complete'; workspace: OnboardingResult['workspace'] }>('/api/v1/workspaces/repair', {
      method: 'POST',
      body: JSON.stringify({ workspace_path: workspacePath, workspace_name: workspaceName }),
    }),
  startReview: (courseId?: string) =>
    request<ExamAttempt>(`/api/v1/reviews/attempts${courseId ? `?course_id=${encodeURIComponent(courseId)}` : ''}`, {
      method: 'POST',
    }),
  startExam: (courseId: string, examId: string) =>
    request<ExamAttempt>(`/api/v1/exams/${encodeURIComponent(courseId)}/${encodeURIComponent(examId)}/attempts`, {
      method: 'POST',
    }),
  submitExamAnswer: (attempt: ExamAttempt, questionId: string, optionId: string) =>
    request<QuestionFeedback>(
      `/api/v1/exams/${encodeURIComponent(attempt.course_id)}/${encodeURIComponent(attempt.exam_id)}/attempts/${encodeURIComponent(attempt.attempt_id)}/questions/${encodeURIComponent(questionId)}`,
      { method: 'POST', body: JSON.stringify({ option_id: optionId }) },
    ),
  finishExam: (attempt: ExamAttempt) =>
    request<ExamCompletion>(
      `/api/v1/exams/${encodeURIComponent(attempt.course_id)}/${encodeURIComponent(attempt.exam_id)}/attempts/${encodeURIComponent(attempt.attempt_id)}/finish`,
      { method: 'POST' },
    ),
}
