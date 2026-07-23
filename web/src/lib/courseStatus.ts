export const AI_SELF_CHECKED_LABEL = 'AI source-cited · Self-checked'

export function courseTrustLabel(publicationStatus: string): string | null {
  return publicationStatus === 'DRAFT_UNVERIFIED' ? AI_SELF_CHECKED_LABEL : null
}

export function courseTrustNotice(publicationStatus: string): string | null {
  if (publicationStatus !== 'DRAFT_UNVERIFIED') return null
  return `${AI_SELF_CHECKED_LABEL}. Ready for study; independent verification is still required before exams and mastery updates.`
}
