import { useEffect, useMemo, useState } from 'react'

import { applicationApi, type GlossaryIndexResult, type GlossaryIndexTerm } from './api'

type GlossaryBrowserProps = {
  refreshToken: number
  onOpenChapter: (courseId: string, chapterId: string) => void
}

const PAGE_SIZE = 100

export function glossaryLetter(term: string) {
  const first = term.trim().charAt(0).toLocaleUpperCase()
  return /^[A-Z]$/.test(first) ? first : '#'
}

export function groupGlossaryTerms(terms: GlossaryIndexTerm[]) {
  const groups = new Map<string, GlossaryIndexTerm[]>()
  for (const term of terms) {
    const letter = glossaryLetter(term.term)
    groups.set(letter, [...(groups.get(letter) ?? []), term])
  }
  return [...groups.entries()]
}

export default function GlossaryBrowser({ refreshToken, onOpenChapter }: GlossaryBrowserProps) {
  const [courseId, setCourseId] = useState('all')
  const [query, setQuery] = useState('')
  const [settledQuery, setSettledQuery] = useState('')
  const [result, setResult] = useState<GlossaryIndexResult | null>(null)
  const [terms, setTerms] = useState<GlossaryIndexTerm[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const timer = window.setTimeout(() => setSettledQuery(query.trim()), 220)
    return () => window.clearTimeout(timer)
  }, [query])

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    applicationApi.glossaryIndex({
      courseId: courseId === 'all' ? undefined : courseId,
      query: settledQuery,
      limit: PAGE_SIZE,
    }).then((next) => {
      if (!active) return
      setResult(next)
      setTerms(next.terms)
    }).catch((cause: Error) => {
      if (active) setError(cause.message)
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [courseId, refreshToken, settledQuery])

  const groups = useMemo(() => groupGlossaryTerms(terms), [terms])

  const loadMore = async () => {
    if (!result?.has_more || loadingMore) return
    setLoadingMore(true)
    setError(null)
    try {
      const next = await applicationApi.glossaryIndex({
        courseId: courseId === 'all' ? undefined : courseId,
        query: settledQuery,
        offset: terms.length,
        limit: PAGE_SIZE,
      })
      setResult(next)
      setTerms((current) => [...current, ...next.terms])
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'More terms could not be loaded.')
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <section className="glossary-browser" aria-labelledby="glossary-title">
      <header className="glossary-toolbar">
        <div>
          <p className="kicker">Knowledge index</p>
          <h1 id="glossary-title">Glossary</h1>
        </div>
        <label className="glossary-course-filter">
          <span>Course</span>
          <select value={courseId} onChange={(event) => setCourseId(event.target.value)}>
            <option value="all">All courses</option>
            {result?.courses.map((course) => (
              <option key={course.course_id} value={course.course_id}>{course.title} ({course.term_count})</option>
            ))}
          </select>
        </label>
        <label className="glossary-browser-search">
          <span aria-hidden="true">⌕</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search terms, aliases, definitions" aria-label="Search glossary" />
          {query && <button type="button" onClick={() => setQuery('')} aria-label="Clear glossary search">×</button>}
        </label>
        <div className="glossary-result-count" aria-live="polite">
          <strong>{result?.total_terms ?? 0}</strong>
          <span>{result?.total_terms === 1 ? 'term' : 'terms'}</span>
        </div>
      </header>

      {error && <div className="dashboard-error glossary-error" role="alert"><strong>Glossary could not be opened.</strong><span>{error}</span></div>}

      <div className="glossary-workspace">
        <nav className="alphabet-rail" aria-label="Glossary letters">
          {groups.map(([letter]) => <a key={letter} href={`#glossary-${encodeURIComponent(letter)}`}>{letter}</a>)}
        </nav>
        <div className="glossary-entries" tabIndex={0}>
          {loading ? <div className="glossary-browser-empty" aria-busy="true">Reading published terms…</div> : groups.length ? groups.map(([letter, letterTerms]) => (
            <section className="glossary-letter-group" id={`glossary-${letter}`} key={letter}>
              <h2>{letter}</h2>
              <div>
                {letterTerms.map((item) => (
                  <article key={`${item.course_id}-${item.term_id}`}>
                    <header>
                      <h3>{item.term}</h3>
                      {Boolean(item.aliases.length) && <p>{item.aliases.join(' · ')}</p>}
                    </header>
                    <p className="glossary-definition">{item.definition}</p>
                    <footer>
                      <span className="glossary-course-badge">{item.course_title}</span>
                      <div className="glossary-chapter-links">
                        {item.chapters.map((chapter) => (
                          <button type="button" key={chapter.chapter_id} onClick={() => onOpenChapter(item.course_id, chapter.chapter_id)}>
                            {chapter.title} <span aria-hidden="true">→</span>
                          </button>
                        ))}
                      </div>
                      <span className="glossary-source-count">{item.source_count} source{item.source_count === 1 ? '' : 's'}</span>
                    </footer>
                  </article>
                ))}
              </div>
            </section>
          )) : (
            <div className="glossary-browser-empty">
              <span aria-hidden="true">Aa</span>
              <strong>{settledQuery ? 'No matching terms' : 'No published glossary terms'}</strong>
              <p>{settledQuery ? 'Try a broader word or search another course.' : 'Glossary terms published by the Mastery Ledger skill will appear here.'}</p>
            </div>
          )}
          {result?.has_more && <button className="glossary-load-more" type="button" onClick={loadMore} disabled={loadingMore}>{loadingMore ? 'Loading…' : `Load ${Math.min(PAGE_SIZE, result.total_terms - terms.length)} more terms`}</button>}
          {Boolean(result?.warnings.length) && <details className="scan-warnings glossary-warnings"><summary>{result?.warnings.length} catalog notice{result?.warnings.length === 1 ? '' : 's'}</summary>{result?.warnings.map((warning) => <p key={warning}>{warning}</p>)}</details>}
        </div>
      </div>
    </section>
  )
}
