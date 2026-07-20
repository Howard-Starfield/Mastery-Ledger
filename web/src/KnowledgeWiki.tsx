import { useEffect, useMemo, useState } from 'react'

import { applicationApi, type KnowledgeWikiResult, type WikiConcept } from './api'

export type WorkspaceScreen = 'exams' | 'sources' | 'knowledge' | 'activity'

type KnowledgeWikiProps = {
  workspaceName: string
  onNavigate: (screen: WorkspaceScreen) => void
}

function label(value: string) {
  return value.replaceAll('_', ' ').replaceAll('-', ' ')
}

function conceptKey(concept: Pick<WikiConcept, 'course_id' | 'concept_id'>) {
  return `${concept.course_id}::${concept.concept_id}`
}

function formatDate(value: string | null) {
  if (!value) return 'Not scheduled'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(parsed)
}

function MarkdownDocument({ value }: { value: string }) {
  const lines = value.replace(/^---[\s\S]*?---\s*/, '').split(/\r?\n/)
  return <div className="wiki-markdown">{lines.map((line, index) => {
    const clean = line.trim()
    if (!clean) return <span className="wiki-space" key={index} />
    if (clean.startsWith('### ')) return <h4 key={index}>{clean.slice(4)}</h4>
    if (clean.startsWith('## ')) return <h3 key={index}>{clean.slice(3)}</h3>
    if (clean.startsWith('# ')) return <h2 key={index}>{clean.slice(2)}</h2>
    if (/^[-*] /.test(clean)) return <p className="wiki-bullet" key={index}><span>—</span>{clean.slice(2)}</p>
    if (clean.startsWith('> ')) return <blockquote key={index}>{clean.slice(2)}</blockquote>
    return <p key={index}>{clean.replaceAll('**', '').replaceAll('`', '')}</p>
  })}</div>
}

export default function KnowledgeWiki({ workspaceName, onNavigate }: KnowledgeWikiProps) {
  const [data, setData] = useState<KnowledgeWikiResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [course, setCourse] = useState('all')
  const [selectedKey, setSelectedKey] = useState<string | null>(null)

  const refresh = () => {
    setLoading(true)
    setError(null)
    applicationApi.knowledge().then((result) => {
      setData(result)
      setSelectedKey((current) => current && result.concepts.some((item) => conceptKey(item) === current) ? current : result.concepts[0] ? conceptKey(result.concepts[0]) : null)
    }).catch((cause: Error) => setError(cause.message)).finally(() => setLoading(false))
  }

  useEffect(refresh, [])

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase()
    return (data?.concepts ?? []).filter((concept) => {
      if (course !== 'all' && concept.course_id !== course) return false
      const text = `${concept.title} ${concept.concept_id} ${concept.summary} ${concept.tags.join(' ')}`.toLocaleLowerCase()
      return !normalized || text.includes(normalized)
    })
  }, [course, data, query])
  const selected = filtered.find((item) => conceptKey(item) === selectedKey) ?? filtered[0] ?? null
  const relations = (data?.relationships ?? []).filter((item) => selected && item.course_id === selected.course_id && (item.from_concept_id === selected.concept_id || item.to_concept_id === selected.concept_id))
  const titleFor = (conceptId: string) => data?.concepts.find((item) => item.course_id === selected?.course_id && item.concept_id === conceptId)?.title ?? label(conceptId)
  const selectRelated = (conceptId: string) => selected && setSelectedKey(`${selected.course_id}::${conceptId}`)

  return (
    <main className="wiki-app">
      <header className="source-topbar">
        <button type="button" className="source-wordmark" onClick={() => onNavigate('exams')}><span>ML</span><strong>Mastery Ledger</strong></button>
        <div className="workspace-crumb"><span>Workspace</span><b>/</b><strong>{workspaceName}</strong><b>/</b><span>Knowledge Wiki</span></div>
        <button type="button" className="topbar-action" onClick={refresh} disabled={loading}><span className={loading ? 'refresh-glyph is-spinning' : 'refresh-glyph'}>↻</span>{loading ? 'Reading' : 'Rescan'}</button>
      </header>

      <aside className="source-nav wiki-nav">
        <nav aria-label="Primary navigation">
          <button type="button" onClick={() => onNavigate('exams')}><span>▦</span>Exams</button>
          <button type="button" onClick={() => onNavigate('sources')}><span>▰</span>Sources</button>
          <button type="button" className="is-active"><span>◇</span>Knowledge</button>
          <button type="button" onClick={() => onNavigate('activity')}><span>≡</span>Activity</button>
        </nav>
        <div className="wiki-index-note"><p>Persistent synthesis</p><strong>{data?.concepts.length ?? 0}</strong><span>concept pages across {data?.courses.length ?? 0} courses</span></div>
      </aside>

      <section className="wiki-main">
        <header className="wiki-heading">
          <div><p className="kicker">Knowledge wiki / approved synthesis</p><h1>A map that compounds.</h1><p>Concept pages gather the relationships, learner evidence, contradictions, and precise source locations already resolved in each portable course.</p></div>
          <div className="wiki-stamp"><span>Read layer</span><strong>Portable Markdown</strong><small>No generated answer is filed from this screen.</small></div>
        </header>

        {error && <div className="dashboard-error" role="alert"><strong>Knowledge scan failed.</strong><span>{error}</span><button type="button" onClick={refresh}>Try again</button></div>}

        <div className="wiki-tools">
          <label className="wiki-search"><span>Search the map</span><input aria-label="Search knowledge concepts" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Concept, summary, or tag" /></label>
          <label><span>Course</span><select value={course} onChange={(event) => setCourse(event.target.value)}><option value="all">All courses</option>{data?.courses.map((item) => <option key={item.course_id} value={item.course_id}>{item.title}</option>)}</select></label>
          <div className="wiki-total"><span>Visible</span><strong>{filtered.length}</strong><small>of {data?.concepts.length ?? 0}</small></div>
        </div>

        <div className="wiki-workbench">
          <aside className="wiki-concepts" aria-label="Concept index">
            <header><span>Concept index</span><em>{filtered.length}</em></header>
            <div>{loading && !data ? <p className="wiki-empty">Reading concept records…</p> : filtered.length ? filtered.map((concept) => (
              <button type="button" key={`${concept.course_id}-${concept.concept_id}`} className={selected && conceptKey(selected) === conceptKey(concept) ? 'is-selected' : ''} onClick={() => setSelectedKey(conceptKey(concept))}>
                <span className={`wiki-status wiki-status--${concept.status}`} />
                <span><strong>{concept.title}</strong><small>{concept.course_title}</small></span>
                <em>{Math.round(concept.proficiency_score * 100)}</em>
              </button>
            )) : <p className="wiki-empty">No concepts match this view.</p>}</div>
          </aside>

          <article className="wiki-page">
            {selected ? <>
              <header>
                <div><p className="kicker">{selected.concept_id}</p><h2>{selected.title}</h2><p>{selected.summary}</p></div>
                <span className={`wiki-state wiki-state--${selected.status}`}>{label(selected.status)}</span>
              </header>
              <div className="wiki-evidence-strip">
                <div><span>Recall evidence</span><strong>{selected.attempt_count}</strong><small>attempts</small></div>
                <div><span>Proficiency</span><strong>{Math.round(selected.proficiency_score * 100)}%</strong><small>observed</small></div>
                <div><span>Next review</span><strong>{formatDate(selected.next_review_at)}</strong><small>ownership curve</small></div>
                <div><span>Contradictions</span><strong>{selected.contradiction_count}</strong><small>{selected.contradiction_count ? 'open records' : 'none recorded'}</small></div>
              </div>
              {selected.tags.length > 0 && <div className="wiki-tags">{selected.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>}
              {selected.page_markdown ? <MarkdownDocument value={selected.page_markdown} /> : <div className="wiki-page-empty"><strong>Structured record only.</strong><p>The concept is already mapped to questions or progress, but an approved Markdown synthesis has not been published yet.</p></div>}
              <section className="wiki-sources"><header><span>Grounding ledger</span><em>{selected.sources.length} source{selected.sources.length === 1 ? '' : 's'}</em></header>{selected.sources.length ? selected.sources.map((source) => <article key={`${source.source_id}-${source.locator_label}`}><code>{source.source_id}</code><div><strong>{source.title}</strong><span>{source.locator_label} · {source.support_strength}</span></div>{source.href && <a href={source.href} target="_blank" rel="noreferrer">Open ↗</a>}</article>) : <p>No concept-level source references have been published. Question citations may still exist separately.</p>}</section>
            </> : <div className="wiki-no-selection"><strong>No knowledge pages yet.</strong><p>Approved wiki artifacts and concept evidence will appear here without changing the course’s portable files.</p></div>}
          </article>

          <aside className="wiki-relations">
            <header><p className="kicker">Map context</p><h2>Relationships</h2></header>
            {selected?.prerequisites.length ? <section><span>Prerequisites</span>{selected.prerequisites.map((item) => <button type="button" key={item} onClick={() => selectRelated(item)}>{titleFor(item)} <em>→</em></button>)}</section> : null}
            <section><span>Edges touching this concept</span>{relations.length ? relations.map((edge, index) => { const other = edge.from_concept_id === selected?.concept_id ? edge.to_concept_id : edge.from_concept_id; return <button type="button" key={`${edge.from_concept_id}-${edge.to_concept_id}-${index}`} onClick={() => selectRelated(other)}><strong>{titleFor(other)}</strong><small>{label(edge.kind)} · {edge.status}</small></button> }) : <p>No relationships published.</p>}</section>
            {selected?.related.length ? <section><span>Related pages</span>{selected.related.filter((item) => !relations.some((edge) => edge.from_concept_id === item || edge.to_concept_id === item)).map((item) => <button type="button" key={item} onClick={() => selectRelated(item)}>{titleFor(item)}</button>)}</section> : null}
            {Boolean(data?.warnings.length) && <details><summary>{data?.warnings.length} scan warning{data?.warnings.length === 1 ? '' : 's'}</summary>{data?.warnings.map((warning) => <p key={warning}>{warning}</p>)}</details>}
          </aside>
        </div>
      </section>
    </main>
  )
}
