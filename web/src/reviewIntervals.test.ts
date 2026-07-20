import { describe, expect, it } from 'vitest'

import { formatReviewInterval, formatReviewIntervals, parseReviewIntervals, reviewCurveWarnings } from './reviewIntervals'

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

  it('renders human horizons and non-blocking curve warnings', () => {
    expect(formatReviewInterval(365)).toBe('1.0 years')
    expect(reviewCurveWarnings([10, 11, 8000])).toEqual([
      'The first retrieval is more than one week away.',
      'This curve extends beyond twenty years.',
      'Some stages are only one day apart.',
    ])
  })
})
