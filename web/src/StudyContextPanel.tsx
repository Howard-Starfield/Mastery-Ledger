import { useEffect, useRef, useState } from 'react'
import { BookOpen, ChevronRight, FileText, LibraryBig, Upload } from 'lucide-react'

import { applicationApi } from './api'
import { courseTrustNotice } from './lib/courseStatus'
import type { StudyNavigationSnapshot } from './StudyReader'

type StudyContextPanelProps = {
  snapshot: StudyNavigationSnapshot
  onSelect: (courseId: string | null, chapterId: string | null) => void
  onImported: (courseId: string) => void
}

export default function StudyContextPanel({ snapshot, onSelect, onImported }: StudyContextPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)
  const [importStatus, setImportStatus] = useState<string | null>(null)
  const [expandedCourseIds, setExpandedCourseIds] = useState<Set<string>>(() => new Set())

  useEffect(() => {
    if (!snapshot.selectedCourseId) return
    setExpandedCourseIds((current) => {
      if (current.has(snapshot.selectedCourseId!)) return current
      const next = new Set(current)
      next.add(snapshot.selectedCourseId!)
      return next
    })
  }, [snapshot.selectedCourseId])

  const toggleCourse = (courseId: string) => {
    setExpandedCourseIds((current) => {
      const next = new Set(current)
      if (next.has(courseId)) next.delete(courseId)
      else next.add(courseId)
      return next
    })
  }

  const importCourse = async (file: File | undefined) => {
    if (!file) return
    setImporting(true)
    setImportStatus(null)
    try {
      const result = await applicationApi.importCourse(file)
      setImportStatus(`${result.title} imported as AI source-cited, self-checked study material.`)
      onImported(result.course_id)
    } catch (cause) {
      setImportStatus(cause instanceof Error ? cause.message : 'The course ZIP could not be imported.')
    } finally {
      setImporting(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <section className="study-context" aria-label="Study library navigation">
      <header>
        <div>
          <p>Study</p>
          <strong>Course library</strong>
        </div>
        <span>{snapshot.totalCourses}</span>
      </header>

      <div className="study-context__import">
        <input
          ref={inputRef}
          type="file"
          accept=".zip,application/zip,application/x-zip-compressed"
          aria-label="Select a Mastery Ledger course ZIP"
          onChange={(event) => void importCourse(event.target.files?.[0])}
        />
        <button
          type="button"
          disabled={importing}
          onClick={() => inputRef.current?.click()}
        >
          <Upload aria-hidden="true" />
          <span>{importing ? 'Validating ZIP…' : 'Import course ZIP'}</span>
        </button>
        {importStatus && <p role="status">{importStatus}</p>}
        <p>Or place an extracted course folder directly in this workspace and rescan.</p>
      </div>

      {snapshot.loading && !snapshot.courses.length ? (
        <p className="study-context__status">Reading course lessons…</p>
      ) : snapshot.courses.length ? (
        <nav aria-label="Courses and chapters">
          <button
            type="button"
            className={`study-context__library${snapshot.selectedCourseId ? '' : ' is-active'}`}
            aria-current={snapshot.selectedCourseId ? undefined : 'page'}
            onClick={() => onSelect(null, null)}
          >
            <LibraryBig aria-hidden="true" />
            <span><strong>All courses</strong><small>{snapshot.totalCourses} available</small></span>
          </button>
          {snapshot.courses.slice(0, 10).map((course) => {
            const expanded = expandedCourseIds.has(course.course_id)
            const trustNotice = courseTrustNotice(course.publication_status)
            return (
              <section key={course.course_id} className={expanded ? 'is-open' : ''}>
                <button
                  type="button"
                  className="study-context__course"
                  aria-expanded={expanded}
                  title={course.title}
                  onClick={() => toggleCourse(course.course_id)}
                >
                  <ChevronRight aria-hidden="true" />
                  <BookOpen aria-hidden="true" />
                  <span>
                    <strong>{course.title}</strong>
                    <small>
                      {course.chapters.length} lesson{course.chapters.length === 1 ? '' : 's'}
                    </small>
                  </span>
                </button>
                {expanded && (
                  <div className="study-context__chapters">
                    {course.chapters.map((chapter) => {
                      const tooltipId = `course-trust-${course.course_id}-${chapter.chapter_id}`
                      return (
                        <div className="study-context__chapter-row" key={chapter.chapter_id}>
                          <button
                            type="button"
                            className={chapter.chapter_id === snapshot.selectedChapterId ? 'is-active' : ''}
                            aria-current={chapter.chapter_id === snapshot.selectedChapterId ? 'page' : undefined}
                            title={chapter.title}
                            onClick={() => onSelect(course.course_id, chapter.chapter_id)}
                          >
                            <FileText aria-hidden="true" />
                            <span>
                              <strong>{chapter.title}</strong>
                              <small>{Math.max(1, Math.ceil(chapter.word_count / 225))} min</small>
                            </span>
                          </button>
                          {trustNotice && (
                            <span className="study-context__trust-wrap">
                              <button type="button" className="study-context__trust" aria-label="Course verification status" aria-describedby={tooltipId}>!</button>
                              <span className="study-context__trust-tooltip" id={tooltipId} role="tooltip">{trustNotice}</span>
                            </span>
                          )}
                        </div>
                      )
                    })}
                    {!course.chapters.length && <p>No course lessons.</p>}
                  </div>
                )}
              </section>
            )
          })}
        </nav>
      ) : (
        <p className="study-context__status">No courses are available in this workspace.</p>
      )}
    </section>
  )
}
