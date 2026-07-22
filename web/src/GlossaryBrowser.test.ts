import { describe, expect, it } from 'vitest'

import { glossaryLetter, groupGlossaryTerms } from './GlossaryBrowser'
import type { GlossaryIndexTerm } from './api'

const term = (courseId: string, value: string): GlossaryIndexTerm => ({
  term_id: `${courseId}-${value}`,
  term: value,
  definition: `${value} definition`,
  aliases: [],
  chapter_ids: [],
  source_count: 0,
  course_id: courseId,
  course_title: courseId,
  chapters: [],
})

describe('glossary grouping', () => {
  it('keeps identical terms from separate courses', () => {
    const groups = groupGlossaryTerms([term('COURSE-A', 'Feedback'), term('COURSE-B', 'Feedback')])
    expect(groups).toHaveLength(1)
    expect(groups[0][0]).toBe('F')
    expect(groups[0][1].map((item) => item.course_id)).toEqual(['COURSE-A', 'COURSE-B'])
  })

  it('uses a catch-all group for non-letter terms', () => {
    expect(glossaryLetter('  3D model')).toBe('#')
    expect(glossaryLetter('attention')).toBe('A')
  })
})
