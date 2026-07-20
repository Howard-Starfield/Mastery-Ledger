export function parseReviewIntervals(value: string): number[] {
  const parsed = value
    .split(/[,→\s]+/)
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
