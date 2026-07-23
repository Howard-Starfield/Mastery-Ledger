import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowRight, BookOpen, Clock3, LibraryBig } from 'lucide-react'
import { Marked } from 'marked'
import markedFootnote from 'marked-footnote'

import { useAppearance } from './AppearanceProvider'
import { courseTrustLabel } from './lib/courseStatus'
import {
  applicationApi,
  type StudyGlossaryResult,
  type StudyLessonResult,
  type StudyLibraryResult,
  type StudyCourse,
} from './api'

export type StudyNavigationSnapshot = {
  courses: StudyCourse[]
  totalCourses: number
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

function mergeCourses(current: StudyCourse[], incoming: StudyCourse[]) {
  const courses = new Map(current.map((course) => [course.course_id, course]))
  incoming.forEach((course) => courses.set(course.course_id, course))
  return [...courses.values()].sort((left, right) =>
    (right.updated_at ?? '').localeCompare(left.updated_at ?? ''),
  )
}

function courseUpdatedLabel(value: string | null) {
  if (!value) return 'Update date unavailable'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(parsed)
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
        scrollbar: '#777a80', scrollbarEdge: '#55585e', scrollbarShine: '#a8abb1',
        scrollbarHover: '#aeb1b7', scrollbarHoverEdge: '#777a80',
      }
    : {
        canvas: '#ffffff', foreground: '#1f1f1f', heading1: '#1f1f1f', heading2: '#1f1f1f',
        heading3: '#1f1f1f', muted: '#737373', surface: '#ececed', raised: '#e3e3e4',
        accent: '#5e6ad2', link: '#5e6ad2', selection: '#d6d9f3', border: '#dededf',
        scrollbar: '#9aa3b1', scrollbarEdge: '#7b8492', scrollbarShine: '#d6dbe3',
        scrollbarHover: '#788392', scrollbarHoverEdge: '#5f6977',
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
      * { scrollbar-color: ${palette.scrollbar} transparent; scrollbar-width: thin; }
      *::-webkit-scrollbar { width: 8px; height: 8px; }
      *::-webkit-scrollbar-track, *::-webkit-scrollbar-corner { background: transparent; }
      *::-webkit-scrollbar-thumb {
        border: 2px solid transparent;
        border-radius: 999px;
        background: linear-gradient(90deg, ${palette.scrollbarEdge}, ${palette.scrollbar} 42%, ${palette.scrollbarShine} 58%, ${palette.scrollbar});
        background-clip: padding-box;
      }
      *::-webkit-scrollbar-thumb:hover {
        background: linear-gradient(90deg, ${palette.scrollbarHoverEdge}, ${palette.scrollbarHover} 45%, ${palette.scrollbarShine} 62%, ${palette.scrollbarHover});
        background-clip: padding-box;
      }
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
  const [loadingMore, setLoadingMore] = useState(false)
  const [nextOffset, setNextOffset] = useState(0)
  const [hasMoreCourses, setHasMoreCourses] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const galleryScrollRef = useRef<HTMLDivElement>(null)
  const gallerySentinelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    setLibrary(null)
    setNextOffset(0)
    setHasMoreCourses(false)
    const loadLibrary = async () => {
      const firstPage = await applicationApi.studyLibrary({ limit: 10 })
      let courses = firstPage.courses
      if (initialCourseId && !courses.some((course) => course.course_id === initialCourseId)) {
        const selectedResult = await applicationApi.studyLibrary({ courseId: initialCourseId, limit: 1 })
        courses = mergeCourses(courses, selectedResult.courses)
      }
      if (!active) return
      setLibrary({ ...firstPage, courses })
      setNextOffset(firstPage.offset + firstPage.courses.length)
      setHasMoreCourses(firstPage.has_more)
      const selectedCourse = initialCourseId
        ? courses.find((course) => course.course_id === initialCourseId)
        : null
      const selectedChapter = selectedCourse?.chapters.find((chapter) => chapter.chapter_id === initialChapterId)
        ?? selectedCourse?.chapters[0]
      setCourseId(selectedCourse?.course_id ?? null)
      setChapterId(selectedChapter?.chapter_id ?? null)
    }
    void loadLibrary().catch((cause: Error) => {
      if (active) setError(cause.message)
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [refreshToken])

  useEffect(() => {
    if (!library) return
    if (!initialCourseId) {
      setCourseId(null)
      setChapterId(null)
      return
    }
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
      totalCourses: library?.total_courses ?? 0,
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

  const loadMoreCourses = useCallback(async () => {
    if (!library || !hasMoreCourses || loadingMore) return
    setLoadingMore(true)
    try {
      const page = await applicationApi.studyLibrary({ offset: nextOffset, limit: 10 })
      setLibrary((current) => current ? {
        ...current,
        courses: mergeCourses(current.courses, page.courses),
        total_courses: page.total_courses,
        warnings: [...new Set([...current.warnings, ...page.warnings])],
      } : page)
      setNextOffset(page.offset + page.courses.length)
      setHasMoreCourses(page.has_more)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'More courses could not be loaded.')
    } finally {
      setLoadingMore(false)
    }
  }, [hasMoreCourses, library, loadingMore, nextOffset])

  useEffect(() => {
    const root = galleryScrollRef.current
    const target = gallerySentinelRef.current
    if (!root || !target || selectedCourse || !hasMoreCourses) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) void loadMoreCourses()
      },
      { root, rootMargin: '240px 0px' },
    )
    observer.observe(target)
    return () => observer.disconnect()
  }, [hasMoreCourses, loadMoreCourses, selectedCourse])

  return (
    <>
      <section className="study-main">
        {error && <div className="dashboard-error" role="alert"><strong>Study material could not be opened.</strong><span>{error}</span></div>}

        {loading && !library ? (
          <div className="study-loading" aria-busy="true">Reading the lesson catalog…</div>
        ) : library ? selectedCourse ? (
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
          <div className="study-library" ref={galleryScrollRef}>
            <header className="study-library__header">
              <div>
                <p className="kicker">Course library</p>
                <h1>Choose what to study</h1>
                <p>Open a grounded course, then move through its lessons from the library panel.</p>
              </div>
              <div className="study-library__count" aria-label={`${library.total_courses} available courses`}>
                <LibraryBig aria-hidden="true" />
                <strong>{library.total_courses}</strong>
                <span>available</span>
              </div>
            </header>

            <div className="study-course-gallery" aria-label="Available courses">
              {!library.courses.length && (
                <div className="study-library__empty">
                  <LibraryBig aria-hidden="true" />
                  <strong>No courses are available yet.</strong>
                  <p>Import a compatible course ZIP or place a course folder in this workspace, then rescan.</p>
                </div>
              )}
              {library.courses.map((course, index) => {
                const totalWords = course.chapters.reduce((sum, chapter) => sum + chapter.word_count, 0)
                const trustLabel = courseTrustLabel(course.publication_status)
                return (
                  <article className="study-course-card" key={course.course_id}>
                    <div className="study-course-card__cover" aria-hidden="true">
                      <span>{String(index + 1).padStart(2, '0')}</span>
                      <BookOpen />
                    </div>
                    <div className="study-course-card__body">
                      <div className="study-course-card__meta">
                        <span>{trustLabel || 'Published course'}</span>
                        <time dateTime={course.updated_at ?? undefined}>{courseUpdatedLabel(course.updated_at)}</time>
                      </div>
                      <h2>{course.title}</h2>
                      <p>{course.chapters.slice(0, 3).map((chapter) => chapter.title).join(' · ')}</p>
                      <dl>
                        <div><dt>Lessons</dt><dd>{course.chapters.length}</dd></div>
                        <div><dt><Clock3 aria-hidden="true" /> Reading</dt><dd>{readingMinutes(totalWords)} min</dd></div>
                      </dl>
                      <button type="button" onClick={() => selectCourse(course.course_id)}>
                        Open course <ArrowRight aria-hidden="true" />
                      </button>
                    </div>
                  </article>
                )
              })}
            </div>

            <div className="study-library__sentinel" ref={gallerySentinelRef}>
              <span aria-live="polite">
                {loadingMore
                  ? 'Loading the next 10 courses…'
                  : `${library.courses.length} of ${library.total_courses} courses loaded`}
              </span>
              {hasMoreCourses && (
                <button type="button" onClick={() => void loadMoreCourses()} disabled={loadingMore}>
                  {loadingMore ? 'Loading…' : 'Load 10 more'}
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="study-empty">
            <span aria-hidden="true">Aa</span>
            <div><strong>No course lessons</strong><p>Import a compatible course ZIP or rescan this workspace.</p></div>
          </div>
        )}
      </section>

      {selectedCourse && <aside className="study-detail-rail glossary-rail" aria-label="Course glossary">
        <header>
          <div className="glossary-rail__heading">
            <h2>Glossary</h2>
            <span>{glossary?.terms.length ?? 0} terms</span>
          </div>
          <label className="glossary-search">
            <span aria-hidden="true">⌕</span>
            <input
              value={glossaryQuery}
              onChange={(event) => setGlossaryQuery(event.target.value)}
              placeholder="Search"
              aria-label={`Search glossary for ${selectedCourse?.title ?? 'this course'}`}
            />
          </label>
        </header>
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
      </aside>}
    </>
  )
}
