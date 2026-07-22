import { useEffect, useMemo, useState } from 'react'
import { Marked } from 'marked'
import markedFootnote from 'marked-footnote'

import { useAppearance } from './AppearanceProvider'
import {
  applicationApi,
  type StudyGlossaryResult,
  type StudyLessonResult,
  type StudyLibraryResult,
  type StudyCourse,
} from './api'

export type StudyNavigationSnapshot = {
  courses: StudyCourse[]
  selectedCourseId: string | null
  selectedChapterId: string | null
  loading: boolean
}

type StudyReaderProps = {
  refreshToken: number
  initialCourseId?: string | null
  initialChapterId?: string | null
  showCatalog?: boolean
  onNavigationChange?: (snapshot: StudyNavigationSnapshot) => void
}

function readingMinutes(wordCount: number) {
  return Math.max(1, Math.ceil(wordCount / 225))
}

const lessonMarkdown = new Marked().use(markedFootnote({
  description: 'Sources used',
  footnoteDivider: false,
  refMarkers: true,
}))

export function lessonDocument(markdown: string, theme: 'light' | 'dark' = 'light') {
  const content = lessonMarkdown.parse(markdown, { async: false, gfm: true }) as string
  const palette = theme === 'dark'
    ? {
        canvas: '#1e1e1e', foreground: '#c9cacb', heading1: '#dedfe0', heading2: '#d3d4d5',
        heading3: '#c5c6c7', muted: '#a0a0a0', surface: '#202020', raised: '#282828',
        accent: '#0169cc', link: '#6aaeff', selection: '#0d263e', border: '#383838',
      }
    : {
        canvas: '#ffffff', foreground: '#1f1f1f', heading1: '#1f1f1f', heading2: '#1f1f1f',
        heading3: '#1f1f1f', muted: '#737373', surface: '#ececed', raised: '#e3e3e4',
        accent: '#5e6ad2', link: '#5e6ad2', selection: '#d6d9f3', border: '#dededf',
      }
  return `<!doctype html>
<html lang="en" data-theme="${theme}">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data: https: http:; media-src data: https: http:; style-src 'unsafe-inline'; font-src data: https:; script-src 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'">
    <style>
      :root {
        color-scheme: ${theme};
        color: ${palette.foreground};
        background: ${palette.canvas};
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", sans-serif;
        font-synthesis: none;
      }
      * { box-sizing: border-box; }
      html, body { min-height: 100%; margin: 0; }
      body {
        color: ${palette.foreground};
        background: ${palette.canvas};
        font-size: 16px;
        font-weight: 450;
        line-height: 1.7;
        letter-spacing: -0.011em;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
        text-rendering: optimizeLegibility;
      }
      ::selection { color: ${palette.foreground}; background: ${palette.selection}; }
      .lesson-note { width: min(720px, 100%); min-height: 100vh; margin: 0 auto; padding: 42px 24px 96px; }
      h1, h2, h3, h4 { margin-left: 0; margin-right: 0; text-wrap: pretty; }
      h1 { margin-top: .15em; margin-bottom: .1em; color: ${palette.heading1}; font-size: 1.35em; font-weight: 700; line-height: 1.3; }
      h2 { margin-top: .75em; margin-bottom: .15em; color: ${palette.heading2}; font-size: 1.2em; font-weight: 700; line-height: 1.35; }
      h3 { margin-top: .65em; margin-bottom: .1em; color: ${palette.heading3}; font-size: 1.1em; font-weight: 600; line-height: 1.4; }
      h4 { margin-top: .6em; margin-bottom: .1em; color: ${palette.heading3}; font-size: 1em; font-weight: 600; line-height: 1.45; }
      p { margin: 0 0 .5em; }
      ul, ol { margin: 0 0 .5em; padding-left: 1.2em; }
      li { padding-left: .3em; }
      li + li { margin-top: .18em; }
      li::marker { color: ${palette.muted}; }
      a { color: ${palette.link}; text-decoration-thickness: 1px; text-underline-offset: 3px; }
      sup { margin-left: .08em; font-size: .68em; }
      [data-footnote-ref] { font-weight: 700; text-decoration: none; }
      .footnotes { margin-top: 1.5em; padding-top: .5em; border-top: 1px solid ${palette.border}; color: ${palette.muted}; font-size: .9em; }
      .footnotes ol { padding-left: 1.2em; }
      .footnotes li { margin-bottom: .6em; padding-left: .3em; }
      .footnotes p { margin-bottom: .4em; }
      [data-footnote-backref] { margin-left: .35em; text-decoration: none; }
      .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
      blockquote, aside { margin: .8em 0; padding: .7em .9em; border-left: 3px solid ${palette.accent}; color: ${palette.foreground}; background: ${palette.surface}; }
      blockquote > :last-child, aside > :last-child { margin-bottom: 0; }
      code { padding: .1em .28em; border-radius: 3px; color: ${palette.foreground}; background: ${palette.surface}; font-family: "Geist Mono", "JetBrains Mono", "Cascadia Code", "SFMono-Regular", ui-monospace, monospace; font-size: .88em; letter-spacing: 0; }
      pre { margin: .75em 0; overflow: auto; padding: 1em; border: 1px solid ${palette.border}; border-radius: 5px; color: ${palette.foreground}; background: ${palette.raised}; }
      pre code { padding: 0; color: inherit; background: transparent; }
      table { width: 100%; margin: .75em 0; border-collapse: collapse; font-size: .92em; }
      th, td { padding: .5em .65em; border: 1px solid ${palette.border}; text-align: left; }
      th { color: ${palette.heading2}; background: ${palette.surface}; }
      img, video, audio { max-width: 100%; }
      hr { margin: 1.5em 0; border: 0; border-top: 1px solid ${palette.border}; }
      @media (max-width: 620px) { .lesson-note { padding: 30px 20px 72px; } }
    </style>
  </head>
  <body><main class="lesson-note">${content}</main></body>
</html>`
}

export default function StudyReader({
  refreshToken,
  initialCourseId = null,
  initialChapterId = null,
  showCatalog = true,
  onNavigationChange,
}: StudyReaderProps) {
  const { resolvedTheme } = useAppearance()
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
  }, [refreshToken])

  useEffect(() => {
    if (!library || !initialCourseId) return
    const selectedCourse = library.courses.find((candidate) => candidate.course_id === initialCourseId)
    if (!selectedCourse) return
    const selectedChapter = selectedCourse.chapters.find(
      (candidate) => candidate.chapter_id === initialChapterId,
    ) ?? selectedCourse.chapters[0]
    setCourseId(selectedCourse.course_id)
    setChapterId(selectedChapter?.chapter_id ?? null)
  }, [initialChapterId, initialCourseId, library])

  useEffect(() => {
    onNavigationChange?.({
      courses: library?.courses ?? [],
      selectedCourseId: courseId,
      selectedChapterId: chapterId,
      loading,
    })
  }, [chapterId, courseId, library?.courses, loading, onNavigationChange])

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
  const renderedDocument = useMemo(
    () => lessonDocument(lesson?.content ?? '', resolvedTheme),
    [lesson?.content, resolvedTheme],
  )
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
          <div className={showCatalog ? 'study-workbench' : 'study-workbench study-workbench--document-only'}>
            {showCatalog && <aside className="study-catalog" aria-label="Course files">
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
            </aside>}

            <article className="study-document">
              {selectedCourse?.publication_status === 'DRAFT_UNVERIFIED' && (
                <div className="study-draft-notice" role="note">
                  Draft preview · Same-agent checked, not independently verified. Exams and mastery updates remain disabled.
                </div>
              )}
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
            <div><strong>No course lessons</strong><p>Import a compatible course ZIP or rescan this workspace.</p></div>
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
