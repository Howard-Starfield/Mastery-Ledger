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
