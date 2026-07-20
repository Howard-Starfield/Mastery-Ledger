import { describe, expect, it } from 'vitest'

import { formatReviewIntervals, parseReviewIntervals } from './reviewIntervals'

describe('review interval parsing', () => {
  it('accepts commas, whitespace, and arrows', () => {
    expect(parseReviewIntervals('1d → 3 7, 14'.replaceAll('d', ''))).toEqual([1, 3, 7, 14])
  })

  it('rejects duplicates and descending intervals', () => {
    expect(() => parseReviewIntervals('1, 3, 3, 7')).toThrow(/strictly increasing/)
    expect(() => parseReviewIntervals('1, 7, 3')).toThrow(/strictly increasing/)
  })

  it('formats the canonical field value', () => {
    expect(formatReviewIntervals([1, 3, 7])).toBe('1, 3, 7')
  })
})
