import { BookText, Search, X } from 'lucide-react'

import type { GlossaryNavigationSnapshot } from './GlossaryBrowser'

type GlossaryContextPanelProps = {
  snapshot: GlossaryNavigationSnapshot
  courseId: string
  query: string
  onCourseIdChange: (courseId: string) => void
  onQueryChange: (query: string) => void
}

export default function GlossaryContextPanel({
  snapshot,
  courseId,
  query,
  onCourseIdChange,
  onQueryChange,
}: GlossaryContextPanelProps) {
  return (
    <section className="glossary-context" aria-label="Glossary filters">
      <header>
        <div>
          <p>Glossary</p>
          <strong>Knowledge index</strong>
        </div>
        <span aria-live="polite">{snapshot.loading ? '…' : snapshot.totalTerms}</span>
      </header>

      <label className="context-search">
        <Search aria-hidden="true" />
        <input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Find a term"
          aria-label="Search glossary"
        />
        {query && (
          <button type="button" onClick={() => onQueryChange('')} aria-label="Clear glossary search">
            <X />
          </button>
        )}
      </label>

      <div className="glossary-context__courses">
        <p>Courses</p>
        <nav aria-label="Filter glossary by course">
          <button
            type="button"
            className={courseId === 'all' ? 'is-active' : ''}
            aria-pressed={courseId === 'all'}
            title="All courses"
            onClick={() => onCourseIdChange('all')}
          >
            <BookText aria-hidden="true" />
            <span>All courses</span>
            <em>{snapshot.courses.reduce((total, course) => total + course.term_count, 0)}</em>
          </button>
          {snapshot.courses.map((course) => (
            <button
              type="button"
              key={course.course_id}
              className={courseId === course.course_id ? 'is-active' : ''}
              aria-pressed={courseId === course.course_id}
              title={course.title}
              onClick={() => onCourseIdChange(course.course_id)}
            >
              <BookText aria-hidden="true" />
              <span>{course.title}</span>
              <em>{course.term_count}</em>
            </button>
          ))}
        </nav>
      </div>
    </section>
  )
}
