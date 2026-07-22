import { useRef, useState } from 'react'
import { BookOpen, ChevronRight, FileText, Upload } from 'lucide-react'

import { applicationApi } from './api'
import type { StudyNavigationSnapshot } from './StudyReader'

type StudyContextPanelProps = {
  snapshot: StudyNavigationSnapshot
  onSelect: (courseId: string, chapterId: string | null) => void
  onImported: (courseId: string) => void
}

export default function StudyContextPanel({ snapshot, onSelect, onImported }: StudyContextPanelProps) {
  const chapterCount = snapshot.courses.reduce((total, course) => total + course.chapters.length, 0)
  const inputRef = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)
  const [importStatus, setImportStatus] = useState<string | null>(null)

  const importCourse = async (file: File | undefined) => {
    if (!file) return
    setImporting(true)
    setImportStatus(null)
    try {
      const result = await applicationApi.importCourse(file)
      setImportStatus(`${result.title} imported as a draft preview.`)
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
        <span>{chapterCount}</span>
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
      </div>

      {snapshot.loading && !snapshot.courses.length ? (
        <p className="study-context__status">Reading course lessons…</p>
      ) : snapshot.courses.length ? (
        <nav aria-label="Courses and chapters">
          {snapshot.courses.map((course) => {
            const selected = course.course_id === snapshot.selectedCourseId
            const firstChapter = course.chapters[0]?.chapter_id ?? null
            return (
              <section key={course.course_id} className={selected ? 'is-open' : ''}>
                <button
                  type="button"
                  className="study-context__course"
                  aria-expanded={selected}
                  title={course.title}
                  onClick={() => onSelect(course.course_id, firstChapter)}
                >
                  <ChevronRight aria-hidden="true" />
                  <BookOpen aria-hidden="true" />
                  <span>
                    <strong>{course.title}</strong>
                    <small>
                      {course.chapters.length} lesson{course.chapters.length === 1 ? '' : 's'}
                      {course.publication_status === 'DRAFT_UNVERIFIED' ? ' · Draft preview' : ''}
                    </small>
                  </span>
                </button>
                {selected && (
                  <div className="study-context__chapters">
                    {course.chapters.map((chapter) => (
                      <button
                        type="button"
                        key={chapter.chapter_id}
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
                    ))}
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
