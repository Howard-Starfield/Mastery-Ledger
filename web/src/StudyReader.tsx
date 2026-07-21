import { useEffect, useMemo, useState } from 'react'
import { Marked } from 'marked'
import markedFootnote from 'marked-footnote'

import { applicationApi, type StudyLessonResult, type StudyLibraryResult } from './api'

type StudyReaderProps = {
  refreshToken: number
  initialCourseId?: string | null
}

function readingMinutes(wordCount: number) {
  return Math.max(1, Math.ceil(wordCount / 225))
}

const lessonMarkdown = new Marked().use(markedFootnote({
  description: 'Sources used',
  footnoteDivider: false,
  refMarkers: true,
}))

export function lessonDocument(markdown: string) {
  const content = lessonMarkdown.parse(markdown, { async: false, gfm: true }) as string
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data: https: http:; media-src data: https: http:; style-src 'unsafe-inline'; font-src data: https:; script-src 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'">
    <style>
      :root { color: #17283e; background: #fffdf8; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
      * { box-sizing: border-box; }
      body { max-width: 760px; margin: 0 auto; padding: 52px clamp(28px, 7vw, 74px) 90px; font-size: 17px; line-height: 1.72; }
      h1, h2, h3, h4 { color: #10243c; font-family: Georgia, "Times New Roman", serif; font-weight: 500; line-height: 1.12; text-wrap: balance; }
      h1 { margin: 0 0 34px; font-size: clamp(2.35rem, 7vw, 4.1rem); letter-spacing: -.045em; }
      h2 { margin: 52px 0 18px; padding-top: 18px; border-top: 1px solid #d8d0c3; font-size: 1.75rem; }
      h3 { margin: 36px 0 14px; font-size: 1.3rem; }
      p, ul, ol, blockquote, table, pre { margin: 0 0 22px; }
      a { color: #145f9d; text-decoration-thickness: 1px; text-underline-offset: 3px; }
      sup { margin-left: .08em; font-family: Inter, ui-sans-serif, system-ui, sans-serif; font-size: .68em; }
      [data-footnote-ref] { font-weight: 700; text-decoration: none; }
      .footnotes { margin-top: 20px; padding-top: 4px; color: #40536a; font-size: .92rem; }
      .footnotes ol { padding-left: 24px; }
      .footnotes li { margin-bottom: 12px; padding-left: 5px; }
      .footnotes p { margin-bottom: 8px; }
      [data-footnote-backref] { margin-left: .35em; text-decoration: none; }
      .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
      blockquote, aside { margin: 30px 0; padding: 18px 22px; border-left: 4px solid #d45c43; color: #31445a; background: #f4eee4; }
      code { padding: .12rem .3rem; color: #8a3424; background: #eee7dc; font-family: "Cascadia Mono", Consolas, monospace; font-size: .88em; }
      pre { overflow: auto; padding: 20px; color: #e8edf3; background: #10243c; }
      pre code { padding: 0; color: inherit; background: transparent; }
      table { width: 100%; border-collapse: collapse; font-size: .92rem; }
      th, td { padding: 10px 12px; border: 1px solid #d8d0c3; text-align: left; }
      th { color: #52657a; background: #eee9df; }
      img, video, audio { max-width: 100%; }
      hr { margin: 46px 0; border: 0; border-top: 1px solid #d8d0c3; }
    </style>
  </head>
  <body>${content}</body>
</html>`
}

export default function StudyReader({ refreshToken, initialCourseId = null }: StudyReaderProps) {
  const [library, setLibrary] = useState<StudyLibraryResult | null>(null)
  const [lesson, setLesson] = useState<StudyLessonResult | null>(null)
  const [courseId, setCourseId] = useState<string | null>(null)
  const [chapterId, setChapterId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [lessonLoading, setLessonLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    applicationApi.studyLibrary().then((result) => {
      if (!active) return
      setLibrary(result)
      const selectedCourse = result.courses.find((course) => course.course_id === initialCourseId)
        ?? result.courses.find((course) => course.course_id === courseId)
        ?? result.courses[0]
      const selectedChapter = selectedCourse?.chapters.find((chapter) => chapter.chapter_id === chapterId) ?? selectedCourse?.chapters[0]
      setCourseId(selectedCourse?.course_id ?? null)
      setChapterId(selectedChapter?.chapter_id ?? null)
    }).catch((cause: Error) => {
      if (active) setError(cause.message)
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [initialCourseId, refreshToken])

  useEffect(() => {
    if (!courseId || !chapterId) {
      setLesson(null)
      return
    }
    let active = true
    setLessonLoading(true)
    setError(null)
    applicationApi.studyLesson(courseId, chapterId).then((result) => {
      if (active) setLesson(result)
    }).catch((cause: Error) => {
      if (active) {
        setLesson(null)
        setError(cause.message)
      }
    }).finally(() => {
      if (active) setLessonLoading(false)
    })
    return () => { active = false }
  }, [courseId, chapterId, refreshToken])

  const selectedCourse = library?.courses.find((course) => course.course_id === courseId) ?? null
  const selectedChapter = selectedCourse?.chapters.find((chapter) => chapter.chapter_id === chapterId) ?? null
  const renderedDocument = useMemo(() => lessonDocument(lesson?.content ?? ''), [lesson?.content])

  const selectCourse = (nextCourseId: string) => {
    const nextCourse = library?.courses.find((course) => course.course_id === nextCourseId)
    setCourseId(nextCourseId)
    setChapterId(nextCourse?.chapters[0]?.chapter_id ?? null)
  }

  return (
    <>
      <section className="study-main">
        <header className="study-heading">
          <div>
            <p className="kicker">Validated study material</p>
            <h1>Read before you prove it.</h1>
            <p>Each chapter appears as soon as its lesson contract is validated; exams remain separate until their own review is complete.</p>
          </div>
          <span className="study-reader-badge">Reader view</span>
        </header>

        {error && <div className="dashboard-error" role="alert"><strong>Study material could not be opened.</strong><span>{error}</span></div>}

        {loading && !library ? (
          <div className="study-loading" aria-busy="true">Reading the published lesson catalog…</div>
        ) : library?.courses.length ? (
          <div className="study-workbench">
            <aside className="study-catalog" aria-label="Study course and chapter index">
              <label>
                <span>Course</span>
                <select value={courseId ?? ''} onChange={(event) => selectCourse(event.target.value)}>
                  {library.courses.map((course) => <option key={course.course_id} value={course.course_id}>{course.title}</option>)}
                </select>
              </label>
              <header><span>Chapter ledger</span><em>{selectedCourse?.chapters.length ?? 0}</em></header>
              <div>
                {selectedCourse?.chapters.map((chapter, index) => (
                  <button
                    type="button"
                    key={chapter.chapter_id}
                    className={chapter.chapter_id === chapterId ? 'is-selected' : ''}
                    onClick={() => setChapterId(chapter.chapter_id)}
                  >
                    <span>{String(index + 1).padStart(2, '0')}</span>
                    <span><strong>{chapter.title}</strong><small>{chapter.chapter_class} · {readingMinutes(chapter.word_count)} min read</small></span>
                  </button>
                ))}
              </div>
            </aside>

            <article className="study-document">
              {lessonLoading ? <div className="study-loading" aria-busy="true">Opening the lesson…</div> : lesson ? (
                <iframe
                  className="study-preview"
                  title={`${lesson.title} read-only lesson`}
                  sandbox=""
                  srcDoc={renderedDocument}
                />
              ) : <div className="study-loading">Choose a validated chapter to begin.</div>}
            </article>
          </div>
        ) : (
          <div className="study-empty">
            <span aria-hidden="true">Aa</span>
            <div><strong>No validated study material yet.</strong><p>Ask Codex to build a lesson, then rescan this workspace. Unvalidated drafts remain hidden.</p></div>
          </div>
        )}
      </section>

      <aside className="study-detail-rail">
        <header><p className="kicker">Reading folio</p><h2>{selectedChapter?.title ?? 'No lesson selected'}</h2><p>{selectedCourse?.title ?? 'Validated courses will appear here.'}</p></header>
        {selectedChapter && <dl>
          <div><dt>Chapter</dt><dd>{selectedChapter.chapter_id}</dd></div>
          <div><dt>Length</dt><dd>{selectedChapter.word_count} words</dd></div>
          <div><dt>Reading time</dt><dd>{readingMinutes(selectedChapter.word_count)} minutes</dd></div>
          <div><dt>File</dt><dd>{selectedChapter.lesson_path}</dd></div>
        </dl>}
        <div className="study-view-note">
          <strong>Focused reading view</strong>
          <p>Authoring frontmatter and Markdown syntax stay hidden. The formatted lesson opens inside an isolated, read-only document.</p>
        </div>
        {Boolean(library?.warnings.length) && <details className="scan-warnings"><summary>{library?.warnings.length} catalog warning{library?.warnings.length === 1 ? '' : 's'}</summary>{library?.warnings.map((warning) => <p key={warning}>{warning}</p>)}</details>}
      </aside>
    </>
  )
}
