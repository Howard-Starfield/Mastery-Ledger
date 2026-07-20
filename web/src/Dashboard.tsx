import { useEffect, useMemo, useState } from 'react'

import { applicationApi, type DashboardExam, type DashboardResult } from './api'
import CurveSettings from './CurveSettings'
import EvidenceActivity from './EvidenceActivity'
import ExamRunner from './ExamRunner'
import KnowledgeWiki, { type WorkspaceScreen } from './KnowledgeWiki'
import SourceInbox from './SourceInbox'

type DashboardProps = {
  workspaceName: string
}

const navItems = [
  { label: 'Home', icon: 'grid' },
  { label: 'Due now', icon: 'clock' },
  { label: 'Exams', icon: 'paper', active: true },
  { label: 'Knowledge', icon: 'book' },
  { label: 'Sources', icon: 'folder' },
  { label: 'Activity', icon: 'activity' },
]

function Icon({ name }: { name: string }) {
  const paths: Record<string, React.ReactNode> = {
    grid: <><rect x="3" y="3" width="6" height="6" /><rect x="15" y="3" width="6" height="6" /><rect x="3" y="15" width="6" height="6" /><rect x="15" y="15" width="6" height="6" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    paper: <><path d="M6 3h9l4 4v14H6z" /><path d="M15 3v5h4M9 12h7M9 16h7" /></>,
    book: <><path d="M4 5.5A3.5 3.5 0 0 1 7.5 2H12v18H7.5A3.5 3.5 0 0 0 4 23z" /><path d="M20 5.5A3.5 3.5 0 0 0 16.5 2H12v18h4.5A3.5 3.5 0 0 1 20 23z" /></>,
    folder: <path d="M3 6h7l2 2h9v11H3z" />,
    activity: <><path d="M5 6h14M5 12h14M5 18h14" /><circle cx="8" cy="6" r="1" /><circle cx="16" cy="12" r="1" /><circle cx="10" cy="18" r="1" /></>,
  }
  return <svg viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>
}

function formatDate(value: string | null) {
  if (!value) return 'Date unavailable'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(parsed)
}

function formatInterval(days: number) {
  if (days < 28) return `${days}d`
  if (days < 365) return days % 28 === 0 ? `${days / 28}mo` : `${days}d`
  const years = days / 365
  return years >= 10 ? `${Math.round(years)}y` : `${years.toFixed(1)}y`
}

function EmptyLedger({ filtered }: { filtered: boolean }) {
  return (
    <div className="ledger-empty">
      <span className="ledger-empty__folio" aria-hidden="true">00</span>
      <div>
        <strong>{filtered ? 'No exams match this view.' : 'No ready exams yet.'}</strong>
        <p>{filtered ? 'Clear the search or choose another course.' : 'Validated exam sets created in a course will appear here automatically.'}</p>
      </div>
    </div>
  )
}

export default function Dashboard({ workspaceName }: DashboardProps) {
  const [data, setData] = useState<DashboardResult | null>(null)
  const [query, setQuery] = useState('')
  const [course, setCourse] = useState('all')
  const [evidence, setEvidence] = useState('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedExam, setSelectedExam] = useState<DashboardExam | null>(null)
  const [activeExam, setActiveExam] = useState<DashboardExam | null>(null)
  const [activeReview, setActiveReview] = useState(false)
  const [curveSettingsOpen, setCurveSettingsOpen] = useState(false)
  const [workspaceScreen, setWorkspaceScreen] = useState<WorkspaceScreen>('exams')

  const refresh = () => {
    setLoading(true)
    setError(null)
    applicationApi
      .dashboard()
      .then(setData)
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setLoading(false))
  }

  useEffect(refresh, [])

  const filteredExams = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase()
    return (data?.ready_exams ?? []).filter((exam) => {
      const matchesCourse = course === 'all' || exam.course_id === course
      const matchesEvidence = evidence === 'all' || exam.source_status === evidence
      const searchable = `${exam.title} ${exam.course_title} ${exam.concepts.join(' ')}`.toLocaleLowerCase()
      return matchesCourse && matchesEvidence && (!normalized || searchable.includes(normalized))
    })
  }, [course, data, evidence, query])

  const maxStageCount = Math.max(1, ...(data?.ownership_curve.map((stage) => stage.question_count) ?? [1]))

  if (activeExam) {
    return <ExamRunner courseId={activeExam.course_id} examId={activeExam.exam_id} onExit={() => { setActiveExam(null); refresh() }} />
  }
  if (activeReview) {
    return <ExamRunner reviewMode onExit={() => { setActiveReview(false); refresh() }} />
  }
  if (workspaceScreen === 'sources') return <SourceInbox workspaceName={data?.workspace.name ?? workspaceName} onNavigate={setWorkspaceScreen} />
  if (workspaceScreen === 'knowledge') return <KnowledgeWiki workspaceName={data?.workspace.name ?? workspaceName} onNavigate={setWorkspaceScreen} />
  if (workspaceScreen === 'activity') return <EvidenceActivity workspaceName={data?.workspace.name ?? workspaceName} onNavigate={setWorkspaceScreen} />

  return (
    <main className="ledger-app">
      <header className="ledger-topbar">
        <a className="ledger-wordmark" href="/" aria-label="Mastery Ledger home">
          <span>ML</span>
          <strong>Mastery Ledger</strong>
        </a>
        <div className="workspace-crumb"><span>Workspace</span><b>/</b><strong>{data?.workspace.name ?? workspaceName}</strong></div>
        <button className="topbar-action" type="button" onClick={refresh} disabled={loading}>
          <span className={loading ? 'refresh-glyph is-spinning' : 'refresh-glyph'}>↻</span>
          {loading ? 'Scanning' : 'Rescan'}
        </button>
      </header>

      <aside className="ledger-nav">
        <nav aria-label="Primary navigation">
          {navItems.map((item) => (
            <button key={item.label} type="button" className={item.active ? 'is-active' : ''} disabled={!item.active && !['Sources', 'Knowledge', 'Activity'].includes(item.label)} onClick={() => { if (item.label === 'Sources') setWorkspaceScreen('sources'); if (item.label === 'Knowledge') setWorkspaceScreen('knowledge'); if (item.label === 'Activity') setWorkspaceScreen('activity') }}>
              <Icon name={item.icon} />
              <span>{item.label}</span>
              {item.label === 'Due now' && Boolean(data?.due_now) && <em>{data?.due_now}</em>}
            </button>
          ))}
        </nav>
        <div className="nav-workspace">
          <span className="nav-workspace__avatar">ML</span>
          <div><strong>Local workspace</strong><small><i /> Session protected</small></div>
        </div>
      </aside>

      <section className="ledger-main">
        <header className="dashboard-heading">
          <div>
            <p className="kicker">Exam ledger / today</p>
            <h1>Your next proof of knowledge.</h1>
          </div>
          <div className="dashboard-date">{new Intl.DateTimeFormat(undefined, { weekday: 'long', month: 'long', day: 'numeric' }).format(new Date())}</div>
        </header>

        {error && <div className="dashboard-error" role="alert"><strong>Workspace scan failed.</strong><span>{error}</span><button type="button" onClick={refresh}>Try again</button></div>}

        <section className="due-banner" aria-labelledby="due-title">
          <div className="due-number"><strong>{data?.due_now ?? '—'}</strong><span>questions due</span></div>
          <div className="due-copy">
            <p className="kicker">Recall before recognition</p>
            <h2 id="due-title">{data?.due_now ? 'Keep the ownership curve moving.' : 'Nothing is overdue.'}</h2>
            <p>{data?.due_now ? 'Review the same grounded questions at the moment memory needs another successful retrieval.' : 'Your next scheduled questions will surface here automatically.'}</p>
          </div>
          <button type="button" className="review-button" disabled={!data?.due_now} onClick={() => setActiveReview(true)}>{data?.due_now ? 'Start due review' : 'Nothing due'} <span>→</span></button>
        </section>

        <section className="exam-register" aria-labelledby="ready-exams-title">
          <header className="register-heading">
            <div><p className="kicker">Assessment register</p><h2 id="ready-exams-title">Ready exams</h2></div>
            <span className="register-count" aria-live="polite">{filteredExams.length} of {data?.ready_exams.length ?? 0}</span>
          </header>
          <div className="register-tools">
            <label className="search-field"><span aria-hidden="true">⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search exams or concepts" aria-label="Search ready exams" /></label>
            <label className="course-filter"><span>Course</span><select value={course} onChange={(event) => setCourse(event.target.value)}><option value="all">All courses</option>{data?.recent_courses.map((item) => <option key={item.course_id} value={item.course_id}>{item.title}</option>)}</select></label>
            <label className="course-filter"><span>Evidence</span><select value={evidence} onChange={(event) => setEvidence(event.target.value)}><option value="all">Any status</option><option value="verified">Verified</option><option value="ready">Ready</option><option value="review_needed">Review needed</option></select></label>
          </div>
          <div className="register-scroll" tabIndex={0} aria-label="Scrollable ready exam ledger">
            <div className="register-columns" aria-hidden="true"><span>Exam</span><span>Questions</span><span>Duration</span><span>Evidence</span><span>Action</span></div>
            {loading && !data ? <div className="register-loading">Reading course manifests…</div> : filteredExams.length ? filteredExams.map((exam, index) => (
              <article className="exam-row" key={`${exam.course_id}-${exam.exam_id}`}>
                <div className="exam-identity"><span className="exam-folio">{String(index + 1).padStart(2, '0')}</span><div><h3>{exam.title}</h3><p>{exam.course_title} · {formatDate(exam.created_at)}</p>{Boolean(exam.concepts.length) && <small>{exam.concepts.slice(0, 3).join(' · ')}</small>}</div></div>
                <div className="exam-metric"><strong>{exam.question_count}</strong><span>items</span></div>
                <div className="exam-metric"><strong>{exam.estimated_minutes}</strong><span>minutes</span></div>
                <div className={`evidence-state evidence-state--${exam.source_status}`}><i />{exam.source_status === 'review_needed' ? 'Review needed' : exam.source_status === 'verified' ? 'Verified' : 'Ready'}</div>
                <button type="button" className={exam.resume_available ? 'exam-action has-resume' : 'exam-action'} onClick={() => setSelectedExam(exam)}>{exam.resume_available ? 'Continue' : 'Inspect'} <span>↗</span></button>
              </article>
            )) : <EmptyLedger filtered={Boolean(query || course !== 'all' || evidence !== 'all')} />}
          </div>
        </section>

        <section className="course-shelf" aria-labelledby="recent-courses-title">
          <header><div><p className="kicker">Portable course folders</p><h2 id="recent-courses-title">Recent courses</h2></div><span>{data?.recent_courses.length ?? 0} registered</span></header>
          <div className="course-strip">
            {data?.recent_courses.length ? data.recent_courses.slice(0, 6).map((item) => (
              <article key={item.course_id}>
                <span className="course-index">{item.course_id}</span><h3>{item.title}</h3>
                <dl><div><dt>Questions</dt><dd>{item.question_count}</dd></div><div><dt>Ready exams</dt><dd>{item.ready_exam_count}</dd></div><div><dt>Sources</dt><dd>{item.source_ready_count}/{item.source_count}</dd></div></dl>
                <p className="course-concepts"><span>Concept evidence</span><strong>{item.proficient_concept_count}/{item.concept_count} proficient</strong></p>
                <div className="course-rule"><span style={{ width: `${item.source_count ? (item.source_ready_count / item.source_count) * 100 : 0}%` }} /></div>
              </article>
            )) : <div className="course-empty"><strong>No course folders discovered.</strong><span>Create a course through the Mastery Ledger skill, then rescan this workspace.</span></div>}
          </div>
        </section>
      </section>

      <aside className="curve-rail">
        <header><p className="kicker">Long-term record</p><h2>Ownership curve</h2><p>One transparent ladder, from first recall to ten-year maintenance.</p></header>
        <div className="curve-stages">
          {data?.ownership_curve.map((stage) => (
            <div className="curve-stage" key={stage.stage_index}>
              <span className="curve-node" /><strong>{formatInterval(stage.interval_days)}</strong><div className="curve-bar"><span style={{ width: `${(stage.question_count / maxStageCount) * 100}%` }} /></div><em>{stage.question_count}</em>
            </div>
          ))}
        </div>
        <div className="curve-note"><span>∞</span><p><strong>The curve is the goal.</strong> Correct due answers move one rung. A lapse returns the question to day one.</p></div>
        <button type="button" className="curve-edit" onClick={() => setCurveSettingsOpen(true)}>Edit curve in settings</button>
        {Boolean(data?.warnings.length) && <details className="scan-warnings"><summary>{data?.warnings.length} scan warning{data?.warnings.length === 1 ? '' : 's'}</summary>{data?.warnings.map((warning) => <p key={warning}>{warning}</p>)}</details>}
      </aside>

      {selectedExam && (
        <div className="exam-sheet-backdrop" role="presentation" onMouseDown={() => setSelectedExam(null)}>
          <section className="exam-sheet" role="dialog" aria-modal="true" aria-labelledby="exam-sheet-title" onMouseDown={(event) => event.stopPropagation()}>
            <button type="button" className="sheet-close" onClick={() => setSelectedExam(null)} aria-label="Close exam details">×</button>
            <p className="kicker">{selectedExam.exam_id}</p><h2 id="exam-sheet-title">{selectedExam.title}</h2><p className="sheet-course">{selectedExam.course_title}</p>
            <dl><div><dt>Questions</dt><dd>{selectedExam.question_count}</dd></div><div><dt>Expected time</dt><dd>{selectedExam.estimated_minutes} minutes</dd></div><div><dt>Evidence</dt><dd>{selectedExam.source_status.replace('_', ' ')}</dd></div><div><dt>Created</dt><dd>{formatDate(selectedExam.created_at)}</dd></div></dl>
            {Boolean(selectedExam.concepts.length) && <div className="sheet-concepts">{selectedExam.concepts.map((concept) => <span key={concept}>{concept}</span>)}</div>}
            <div className="sheet-notice"><strong>{selectedExam.resume_available ? 'Saved attempt found' : 'Focused Question delivery'}</strong><p>{selectedExam.resume_available ? 'Locked answers will be restored from the portable course record.' : 'Each answer locks once. Incorrect answers reveal nothing; correct answers enable the collapsed source disclosure.'}</p></div>
            <button type="button" className="sheet-start" onClick={() => { setActiveExam(selectedExam); setSelectedExam(null) }}>{selectedExam.resume_available ? 'Continue saved exam' : 'Begin focused exam'} <span>→</span></button>
          </section>
        </div>
      )}
      {curveSettingsOpen && <CurveSettings onClose={() => setCurveSettingsOpen(false)} onSaved={refresh} />}
    </main>
  )
}
