export type ProcessingMode = 'local_only' | 'cloud_allowed' | 'metadata_only'

export interface OnboardingDefaults {
  schema_version: 'onboarding-defaults-v1'
  workspace_path: string
  workspace_name: string
  language: string
  processing_mode: ProcessingMode
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

export interface OnboardingPayload {
  workspace_path: string
  workspace_name: string
  language: string
  processing_mode: ProcessingMode
  reduced_motion: boolean
  review_intervals: number[]
  initial_source_hint: string | null
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
  schema_version: 'doctor-v1'
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
}

export interface DashboardCourse {
  course_id: string
  title: string
  question_count: number
  ready_exam_count: number
  due_count: number
  source_count: number
  source_ready_count: number
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
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
  return response.json() as Promise<T>
}

export const onboardingApi = {
  defaults: () => request<OnboardingDefaults>('/api/v1/onboarding/defaults'),
  validateWorkspace: (path: string) =>
    request<WorkspaceValidation>('/api/v1/onboarding/validate-workspace', {
      method: 'POST',
      body: JSON.stringify({ path }),
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
}
