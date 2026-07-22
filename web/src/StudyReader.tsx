import { useEffect, useMemo, useState } from 'react'
import { Marked } from 'marked'
import markedFootnote from 'marked-footnote'

import {
  applicationApi,
  type StudyGlossaryResult,
  type StudyLessonResult,
  type StudyLibraryResult,
} from './api'

type StudyReaderProps = {
  refreshToken: number
  initialCourseId?: string | null
  initialChapterId?: string | null
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
      :root { color: #2e3338; background: #fbfbfa; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
      * { box-sizing: border-box; }
      html, body { min-height: 100%; margin: 0; }
      body { font-size: 16px; line-height: 1.7; }
      .lesson-note { width: min(900px, 100%); min-height: 100vh; margin: 0 auto; padding: 44px clamp(28px, 7vw, 88px) 100px; }
      h1, h2, h3, h4 { color: #1f2328; font-weight: 650; line-height: 1.25; text-wrap: balance; }
      h1 { margin: 0 0 30px; font-size: clamp(2rem, 5vw, 2.7rem); letter-spacing: -.035em; }
      h2 { margin: 46px 0 16px; padding-bottom: 7px; border-bottom: 1px solid #e3e3e1; font-size: 1.55rem; }
      h3 { margin: 32px 0 12px; font-size: 1.2rem; }
      p, ul, ol, blockquote, table, pre { margin: 0 0 20px; }
      a { color: #5865a7; text-decoration-thickness: 1px; text-underline-offset: 3px; }
      sup { margin-left: .08em; font-size: .68em; }
      [data-footnote-ref] { font-weight: 700; text-decoration: none; }
      .footnotes { margin-top: 24px; padding-top: 8px; color: #5a6068; font-size: .9rem; }
      .footnotes ol { padding-left: 24px; }
      .footnotes li { margin-bottom: 12px; padding-left: 5px; }
      .footnotes p { margin-bottom: 8px; }
      [data-footnote-backref] { margin-left: .35em; text-decoration: none; }
      .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
      blockquote, aside { margin: 26px 0; padding: 14px 18px; border-left: 3px solid #7c6fbb; color: #43484f; background: #f2f1f7; }
      code { padding: .12rem .3rem; border-radius: 3px; color: #9b3f46; background: #f1f1ef; font-family: "Cascadia Mono", Consolas, monospace; font-size: .88em; }
      pre { overflow: auto; padding: 18px; border-radius: 5px; color: #e8edf3; background: #282c34; }
      pre code { padding: 0; color: inherit; background: transparent; }
      table { width: 100%; border-collapse: collapse; font-size: .92rem; }
      th, td { padding: 9px 11px; border: 1px solid #dededb; text-align: left; }
      th { color: #50555c; background: #f2f2f0; }
      img, video, audio { max-width: 100%; }
      hr { margin: 42px 0; border: 0; border-top: 1px solid #e3e3e1; }
      @media (max-width: 620px) { .lesson-note { padding: 30px 20px 72px; } }
    </style>
  </head>
  <body><main class="lesson-note">${content}</main></body>
</html>`
}

export default function StudyReader({ refreshToken, initialCourseId = null, initialChapterId = null }: StudyReaderProps) {
  const [library, setLibrary] = useState<StudyLibraryResult | null>(null)
  const [lesson, setLesson] = useState<StudyLessonResult | null>(null)
  const [glossary, setGlossary] = useState<StudyGlossaryResult | null>(null)
  const [courseId, setCourseId] = useState<string | null>(null)
  const [chapterId, setChapterId] = useState<string | null>(null)
  const [glossaryQuery, setGlossaryQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [lessonLoading, setLessonLoading] = useState(false)
  const [glossaryLoading, setGlossaryLoading] = useState(false)
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
      const selectedChapter = selectedCourse?.chapters.find((chapter) => chapter.chapter_id === initialChapterId)
        ?? selectedCourse?.chapters.find((chapter) => chapter.chapter_id === chapterId)
        ?? selectedCourse?.chapters[0]
      setCourseId(selectedCourse?.course_id ?? null)
      setChapterId(selectedChapter?.chapter_id ?? null)
    }).catch((cause: Error) => {
      if (active) setError(cause.message)
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [initialChapterId, initialCourseId, refreshToken])

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

  useEffect(() => {
    if (!courseId) {
      setGlossary(null)
      return
    }
    let active = true
    setGlossaryLoading(true)
    setGlossaryQuery('')
    applicationApi.studyGlossary(courseId).then((result) => {
      if (active) setGlossary(result)
    }).catch(() => {
      if (active) setGlossary(null)
    }).finally(() => {
      if (active) setGlossaryLoading(false)
    })
    return () => { active = false }
  }, [courseId, refreshToken])

  const selectedCourse = library?.courses.find((course) => course.course_id === courseId) ?? null
  const renderedDocument = useMemo(() => lessonDocument(lesson?.content ?? ''), [lesson?.content])
  const filteredTerms = useMemo(() => {
    const query = glossaryQuery.trim().toLocaleLowerCase()
    if (!query) return glossary?.terms ?? []
    return (glossary?.terms ?? []).filter((item) =>
      `${item.term} ${item.definition} ${item.aliases.join(' ')}`.toLocaleLowerCase().includes(query),
    )
  }, [glossary?.terms, glossaryQuery])

  const selectCourse = (nextCourseId: string) => {
    const nextCourse = library?.courses.find((course) => course.course_id === nextCourseId)
    setCourseId(nextCourseId)
    setChapterId(nextCourse?.chapters[0]?.chapter_id ?? null)
  }

  return (
    <>
      <section className="study-main">
        {error && <div className="dashboard-error" role="alert"><strong>Study material could not be opened.</strong><span>{error}</span></div>}

        {loading && !library ? (
          <div className="study-loading" aria-busy="true">Reading the lesson catalog…</div>
        ) : library?.courses.length ? (
          <div className="study-workbench">
            <aside className="study-catalog" aria-label="Course files">
              <label>
                <span>Course</span>
                <select value={courseId ?? ''} onChange={(event) => selectCourse(event.target.value)}>
                  {library.courses.map((course) => <option key={course.course_id} value={course.course_id}>{course.title}</option>)}
                </select>
              </label>
              <header><span>Lessons</span><em>{selectedCourse?.chapters.length ?? 0}</em></header>
              <div>
                {selectedCourse?.chapters.map((chapter) => (
                  <button
                    type="button"
                    key={chapter.chapter_id}
                    className={chapter.chapter_id === chapterId ? 'is-selected' : ''}
                    onClick={() => setChapterId(chapter.chapter_id)}
                  >
                    <span aria-hidden="true">▤</span>
                    <span><strong>{chapter.title}</strong><small>{readingMinutes(chapter.word_count)} min · {chapter.chapter_class}</small></span>
                  </button>
                ))}
              </div>
            </aside>

            <article className="study-document">
              {lessonLoading ? <div className="study-loading" aria-busy="true">Opening the lesson…</div> : lesson ? (
                <iframe
                  className="study-preview"
                  title={`${lesson.title} lesson`}
                  sandbox=""
                  srcDoc={renderedDocument}
                />
              ) : <div className="study-loading">Choose a lesson.</div>}
            </article>
          </div>
        ) : (
          <div className="study-empty">
            <span aria-hidden="true">Aa</span>
            <div><strong>No published lessons</strong><p>Build a course with the Mastery Ledger skill, then rescan this workspace.</p></div>
          </div>
        )}
      </section>

      <aside className="study-detail-rail glossary-rail" aria-label="Course glossary">
        <header>
          <p className="kicker">Glossary</p>
          <h2>Course terms</h2>
          <p>{glossary?.terms.length ?? 0} definitions in {selectedCourse?.title ?? 'this course'}</p>
        </header>
        <label className="glossary-search">
          <span aria-hidden="true">⌕</span>
          <input
            value={glossaryQuery}
            onChange={(event) => setGlossaryQuery(event.target.value)}
            placeholder="Find a term"
            aria-label="Search course glossary"
          />
        </label>
        <div className="glossary-list">
          {glossaryLoading ? <p className="glossary-status">Loading terms…</p> : filteredTerms.length ? filteredTerms.map((item) => (
            <article key={item.term_id}>
              <header><h3>{item.term}</h3>{Boolean(item.aliases.length) && <small>{item.aliases.join(' · ')}</small>}</header>
              <p>{item.definition}</p>
              <footer>
                <div>{item.chapter_ids.map((linkedChapterId) => {
                  const chapter = selectedCourse?.chapters.find((candidate) => candidate.chapter_id === linkedChapterId)
                  return chapter ? <button type="button" key={linkedChapterId} onClick={() => setChapterId(linkedChapterId)}>{chapter.title}</button> : null
                })}</div>
                <span>{item.source_count} source{item.source_count === 1 ? '' : 's'}</span>
              </footer>
            </article>
          )) : <p className="glossary-status">{glossaryQuery ? 'No matching terms.' : 'No glossary has been published for this course.'}</p>}
        </div>
        {Boolean(glossary?.warnings.length) && <details className="scan-warnings"><summary>Glossary notice</summary>{glossary?.warnings.map((warning) => <p key={warning}>{warning}</p>)}</details>}
        {Boolean(library?.warnings.length) && <details className="scan-warnings"><summary>{library?.warnings.length} catalog warning{library?.warnings.length === 1 ? '' : 's'}</summary>{library?.warnings.map((warning) => <p key={warning}>{warning}</p>)}</details>}
      </aside>
    </>
  )
}
