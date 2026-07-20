export function parseReviewIntervals(value: string): number[] {
  const parsed = value
    .split(/[,\s\u2192]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map(Number)

  if (!parsed.length || parsed.some((day) => !Number.isInteger(day) || day < 1 || day > 36500)) {
    throw new Error('Use whole-day intervals between 1 and 36500.')
  }
  if (new Set(parsed).size !== parsed.length || parsed.some((day, index) => index > 0 && day <= parsed[index - 1])) {
    throw new Error('Intervals must be unique and strictly increasing.')
  }
  if (parsed.length > 24) {
    throw new Error('Use no more than 24 intervals.')
  }
  return parsed
}

export function formatReviewIntervals(intervals: number[]): string {
  return intervals.join(', ')
}

export function formatReviewInterval(days: number): string {
  if (days < 28) return `${days} day${days === 1 ? '' : 's'}`
  if (days < 365) {
    const months = days / 30.4375
    return months < 10 ? `${months.toFixed(1)} months` : `${Math.round(months)} months`
  }
  const years = days / 365.25
  return years < 10 ? `${years.toFixed(1)} years` : `${Math.round(years)} years`
}

export function reviewCurveWarnings(intervals: number[]): string[] {
  const warnings: string[] = []
  if (intervals.length >= 18) warnings.push('This is a dense curve; frequent stages may create a heavy review load.')
  if (intervals[0] > 7) warnings.push('The first retrieval is more than one week away.')
  if (intervals.at(-1)! > 7300) warnings.push('This curve extends beyond twenty years.')
  if (intervals.some((day, index) => index > 0 && day - intervals[index - 1] === 1)) {
    warnings.push('Some stages are only one day apart.')
  }
  return warnings
}
