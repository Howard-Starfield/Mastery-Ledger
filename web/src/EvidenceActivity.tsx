import { useEffect, useMemo, useState } from 'react'

import { applicationApi, type EvidenceActivityResult, type EvidenceKind } from './api'
import type { WorkspaceScreen } from './KnowledgeWiki'

type EvidenceActivityProps = {
  workspaceName: string
  onNavigate: (screen: WorkspaceScreen) => void
}

const kindLabels: Record<EvidenceKind, string> = {
  approved_claim: 'Approved',
  contradiction: 'Contradiction',
  gap: 'Open gap',
  rejected_claim: 'Rejected',
}

function readable(value: string) {
  return value.replaceAll('.', ' / ').replaceAll('_', ' ')
}

function formatTimestamp(value: string) {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value || 'Time unavailable'
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(parsed)
}

export default function EvidenceActivity({ workspaceName, onNavigate }: EvidenceActivityProps) {
  const [data, setData] = useState<EvidenceActivityResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<'evidence' | 'activity'>('evidence')
  const [kind, setKind] = useState<'all' | EvidenceKind>('all')
  const [course, setCourse] = useState('all')

  const refresh = () => {
    setLoading(true)
    setError(null)
    applicationApi.evidenceActivity().then(setData).catch((cause: Error) => setError(cause.message)).finally(() => setLoading(false))
  }
  useEffect(refresh, [])

  const courses = useMemo(() => Array.from(new Map([
    ...(data?.evidence ?? []).map((item) => [item.course_id, item.course_title] as const),
    ...(data?.events ?? []).map((item) => [item.course_id, item.course_title] as const),
  ]).entries()), [data])
  const evidence = useMemo(() => (data?.evidence ?? []).filter((item) => (kind === 'all' || item.kind === kind) && (course === 'all' || item.course_id === course)), [course, data, kind])
  const events = useMemo(() => (data?.events ?? []).filter((item) => course === 'all' || item.course_id === course), [course, data])

  return (
    <main className="audit-app">
      <header className="source-topbar">
        <button type="button" className="source-wordmark" onClick={() => onNavigate('exams')}><span>ML</span><strong>Mastery Ledger</strong></button>
        <div className="workspace-crumb"><span>Workspace</span><b>/</b><strong>{workspaceName}</strong><b>/</b><span>Evidence & Activity</span></div>
        <button type="button" className="topbar-action" onClick={refresh} disabled={loading}><span className={loading ? 'refresh-glyph is-spinning' : 'refresh-glyph'}>↻</span>{loading ? 'Reading' : 'Rescan'}</button>
      </header>

      <aside className="source-nav wiki-nav">
        <nav aria-label="Primary navigation">
          <button type="button" onClick={() => onNavigate('exams')}><span>▦</span>Exams</button>
          <button type="button" onClick={() => onNavigate('sources')}><span>▰</span>Sources</button>
          <button type="button" onClick={() => onNavigate('knowledge')}><span>◇</span>Knowledge</button>
          <button type="button" className="is-active"><span>≡</span>Activity</button>
        </nav>
        <div className="audit-principle"><p>Audit boundary</p><strong>Actions, decisions, evidence.</strong><span>Short justifications are visible. Hidden chain-of-thought is neither requested nor stored.</span></div>
      </aside>

      <section className="audit-main">
        <header className="audit-heading"><div><p className="kicker">Evidence & activity / human verification</p><h1>Show the work that matters.</h1><p>Reopen approved claims, contradictions, rejected material, exact artifact paths, and observable worker handoffs without exposing private reasoning.</p></div><div className="audit-view-switch" role="tablist" aria-label="Audit view"><button role="tab" aria-selected={view === 'evidence'} className={view === 'evidence' ? 'is-active' : ''} onClick={() => setView('evidence')}>Evidence ledger</button><button role="tab" aria-selected={view === 'activity'} className={view === 'activity' ? 'is-active' : ''} onClick={() => setView('activity')}>Activity feed</button></div></header>

        {error && <div className="dashboard-error" role="alert"><strong>Audit scan failed.</strong><span>{error}</span><button type="button" onClick={refresh}>Try again</button></div>}

        <section className="audit-stats" aria-label="Evidence decision summary">
          <div className="is-approved"><span>Approved</span><strong>{data?.approved_count ?? '—'}</strong><small>verified claims</small></div>
          <div className="is-contradiction"><span>Contradictions</span><strong>{data?.contradiction_count ?? '—'}</strong><small>visible disagreements</small></div>
          <div className="is-gap"><span>Open gaps</span><strong>{data?.gap_count ?? '—'}</strong><small>uncovered questions</small></div>
          <div className="is-rejected"><span>Rejected</span><strong>{data?.rejected_count ?? '—'}</strong><small>excluded claims</small></div>
        </section>

        <div className="audit-toolbar">
          <label><span>Course</span><select value={course} onChange={(event) => setCourse(event.target.value)}><option value="all">All courses</option>{courses.map(([id, title]) => <option key={id} value={id}>{title}</option>)}</select></label>
          {view === 'evidence' && <label><span>Decision</span><select value={kind} onChange={(event) => setKind(event.target.value as 'all' | EvidenceKind)}><option value="all">Every decision</option>{Object.entries(kindLabels).map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>}
          <p>{view === 'evidence' ? `${evidence.length} inspectable record${evidence.length === 1 ? '' : 's'}` : `${events.length} observable event${events.length === 1 ? '' : 's'}`}</p>
        </div>

        {view === 'evidence' ? <section className="evidence-ledger" aria-label="Evidence decisions">
          <div className="evidence-columns" aria-hidden="true"><span>Decision</span><span>Claim or question</span><span>Grounding</span><span>Artifact</span></div>
          {loading && !data ? <div className="audit-empty">Reading evidence packets…</div> : evidence.length ? evidence.map((item) => <article key={`${item.course_id}-${item.artifact_path}-${item.item_id}`}>
            <div><span className={`evidence-kind evidence-kind--${item.kind}`}>{kindLabels[item.kind]}</span><small>{item.status}</small></div>
            <div className="evidence-copy"><strong>{item.title}</strong><p>{item.summary}</p><span>{item.course_title}{item.concept_ids.length ? ` · ${item.concept_ids.join(' · ')}` : ''}</span></div>
            <div className="evidence-grounding"><strong>{item.source_ids.length ? item.source_ids.join(', ') : 'No source IDs'}</strong>{item.locator_labels.length ? item.locator_labels.map((locator) => <span key={locator}>{locator}</span>) : <span>No precise locators recorded</span>}</div>
            <code>{item.artifact_path}</code>
          </article>) : <div className="audit-empty"><strong>No evidence records match this view.</strong><span>Validated evidence packets, contradictions, and gaps remain portable JSON inside each course.</span></div>}
        </section> : <section className="activity-feed" aria-label="Learner-facing activity feed">
          {loading && !data ? <div className="audit-empty">Reading action ledgers…</div> : events.length ? events.map((event) => <article key={`${event.course_id}-${event.event_id}`}>
            <div className="activity-time"><span>{formatTimestamp(event.timestamp)}</span><i /></div>
            <div className="activity-card"><header><span>{readable(event.action)}</span><em className={`activity-status activity-status--${event.status}`}>{event.status}</em></header><h2>{event.summary}</h2><p>{event.course_title} · {event.actor}</p>{(event.decision || event.justification) && <blockquote><strong>{event.decision ? `Decision: ${event.decision}` : 'Short justification'}</strong>{event.justification && <span>{event.justification}</span>}</blockquote>}{event.artifacts.length > 0 && <div>{event.artifacts.map((artifact) => <code key={artifact}>{artifact}</code>)}</div>}{(event.source_id || event.job_id) && <footer>{event.source_id && <span>{event.source_id}</span>}{event.job_id && <span>{event.job_id}</span>}</footer>}</div>
          </article>) : <div className="audit-empty"><strong>No observable actions recorded yet.</strong><span>Ingestion and verification events append here as short machine-readable records.</span></div>}
        </section>}

        {Boolean(data?.warnings.length) && <details className="audit-warnings"><summary>{data?.warnings.length} audit warning{data?.warnings.length === 1 ? '' : 's'}</summary>{data?.warnings.map((warning) => <p key={warning}>{warning}</p>)}</details>}
      </section>
    </main>
  )
}
