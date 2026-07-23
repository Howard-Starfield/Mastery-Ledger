import { describe, expect, it } from 'vitest'

import { courseTrustLabel, courseTrustNotice } from './courseStatus'

describe('course trust presentation', () => {
  it('presents ChatGPT drafts as usable self-checked study material', () => {
    expect(courseTrustLabel('DRAFT_UNVERIFIED')).toBe('AI source-cited · Self-checked')
    expect(courseTrustNotice('DRAFT_UNVERIFIED')).toContain('Ready for study')
    expect(courseTrustNotice('DRAFT_UNVERIFIED')).toContain('independent verification')
    expect(courseTrustNotice('DRAFT_UNVERIFIED')).not.toContain('Draft preview')
  })

  it('does not add an AI trust label to other publication states', () => {
    expect(courseTrustLabel('PUBLISHED')).toBeNull()
    expect(courseTrustNotice('PUBLISHED')).toBeNull()
  })
})
