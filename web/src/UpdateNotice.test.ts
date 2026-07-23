import { describe, expect, it } from 'vitest'

import { formatUpdateSize } from './UpdateNotice'

describe('formatUpdateSize', () => {
  it('keeps small release sizes precise and rounds larger downloads', () => {
    expect(formatUpdateSize(null)).toBeNull()
    expect(formatUpdateSize(5 * 1024 * 1024)).toBe('5.0 MB')
    expect(formatUpdateSize(20_373_361)).toBe('19 MB')
  })
})
