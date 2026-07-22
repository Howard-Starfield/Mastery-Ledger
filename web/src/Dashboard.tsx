import { type FormEvent, useEffect, useMemo, useRef, useState } from 'react'

import { applicationApi, onboardingApi, type DashboardExam, type DashboardResult } from './api'
import CurveSettings from './CurveSettings'
import ExamContextPanel from './ExamContextPanel'
import ExamRunner from './ExamRunner'
import GlossaryContextPanel from './GlossaryContextPanel'
import GlossaryBrowser from './GlossaryBrowser'
import type { GlossaryNavigationSnapshot } from './GlossaryBrowser'
import StudyContextPanel from './StudyContextPanel'
import StudyReader from './StudyReader'
import type { StudyNavigationSnapshot } from './StudyReader'
import WorkbenchShell from './WorkbenchShell'

type DashboardProps = {
  workspaceName: string
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
  const [activeScreen, setActiveScreen] = useState<'study' | 'glossary' | 'exams'>('exams')
  const [studyRefreshToken, setStudyRefreshToken] = useState(0)
  const [studyCourseId, setStudyCourseId] = useState<string | null>(null)
  const [studyChapterId, setStudyChapterId] = useState<string | null>(null)
  const [studyNavigation, setStudyNavigation] = useState<StudyNavigationSnapshot>({
    courses: [],
    selectedCourseId: null,
    selectedChapterId: null,
    loading: true,
  })
  const [glossaryCourseId, setGlossaryCourseId] = useState('all')
  const [glossaryQuery, setGlossaryQuery] = useState('')
  const [glossaryNavigation, setGlossaryNavigation] = useState<GlossaryNavigationSnapshot>({
    courses: [],
    totalTerms: 0,
    loading: true,
  })
  const [workspaceMenuOpen, setWorkspaceMenuOpen] = useState(false)
  const [workspacePath, setWorkspacePath] = useState('')
  const [workspaceBusy, setWorkspaceBusy] = useState(false)
  const [workspaceError, setWorkspaceError] = useState<string | null>(null)
  const workspaceMenuRef = useRef<HTMLDivElement>(null)

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

  useEffect(() => {
    if (!workspaceMenuOpen && data?.workspace.path) setWorkspacePath(data.workspace.path)
  }, [data?.workspace.path, workspaceMenuOpen])

  useEffect(() => {
    if (!workspaceMenuOpen) return
    const closeOnOutsidePress = (event: PointerEvent) => {
      if (!workspaceMenuRef.current?.contains(event.target as Node)) setWorkspaceMenuOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setWorkspaceMenuOpen(false)
    }
    document.addEventListener('pointerdown', closeOnOutsidePress)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsidePress)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [workspaceMenuOpen])

  const activateWorkspace = async (nextPath: string) => {
    const trimmedPath = nextPath.trim()
    if (!trimmedPath) {
      setWorkspaceError('Enter a workspace folder or choose one with Browse.')
      return
    }
    setWorkspaceBusy(true)
    setWorkspaceError(null)
    try {
      const result = await applicationApi.repairWorkspace(trimmedPath, data?.workspace.name ?? workspaceName)
      setData((current) => current ? { ...current, workspace: result.workspace } : current)
      setWorkspacePath(result.workspace.path)
      setWorkspaceMenuOpen(false)
      setStudyCourseId(null)
      setStudyChapterId(null)
      setStudyRefreshToken((value) => value + 1)
      refresh()
    } catch (cause) {
      setWorkspaceError(cause instanceof Error ? cause.message : 'The workspace could not be changed.')
    } finally {
      setWorkspaceBusy(false)
    }
  }

  const browseForWorkspace = async () => {
    setWorkspaceBusy(true)
    setWorkspaceError(null)
    try {
      const selection = await onboardingApi.pickFolder(workspacePath || data?.workspace.path || null)
      if (selection.status === 'selected' && selection.path) await activateWorkspace(selection.path)
      if (selection.status === 'unavailable') setWorkspaceError(selection.message ?? 'The folder picker is unavailable. Paste an absolute path instead.')
    } catch (cause) {
      setWorkspaceError(cause instanceof Error ? cause.message : 'The folder picker could not open.')
    } finally {
      setWorkspaceBusy(false)
    }
  }

  const submitWorkspacePath = (event: FormEvent) => {
    event.preventDefault()
    void activateWorkspace(workspacePath)
  }

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
  return (
    <main className="workbench-app">
      <WorkbenchShell
        activeDestination={activeScreen}
        dueCount={data?.due_now ?? 0}
        loading={loading}
        workspaceName={data?.workspace.name ?? workspaceName}
        workspacePath={data?.workspace.path}
        contextContent={activeScreen === 'study' ? (
          <StudyContextPanel
            snapshot={studyNavigation}
            onSelect={(nextCourseId, nextChapterId) => {
              setStudyCourseId(nextCourseId)
              setStudyChapterId(nextChapterId)
            }}
            onImported={(nextCourseId) => {
              setStudyCourseId(nextCourseId)
              setStudyChapterId(null)
              setStudyRefreshToken((value) => value + 1)
              refresh()
            }}
          />
        ) : activeScreen === 'glossary' ? (
          <GlossaryContextPanel
            snapshot={glossaryNavigation}
            courseId={glossaryCourseId}
            query={glossaryQuery}
            onCourseIdChange={setGlossaryCourseId}
            onQueryChange={setGlossaryQuery}
          />
        ) : (
          <ExamContextPanel
            data={data}
            query={query}
            courseId={course}
            evidence={evidence}
            onQueryChange={setQuery}
            onCourseIdChange={setCourse}
            onEvidenceChange={setEvidence}
            onStartReview={() => setActiveReview(true)}
          />
        )}
        onNavigate={setActiveScreen}
        onStartReview={() => setActiveReview(true)}
        onOpenSettings={() => setCurveSettingsOpen(true)}
        onChangeWorkspace={() => void browseForWorkspace()}
        onRescan={() => {
          refresh()
          if (activeScreen !== 'exams') setStudyRefreshToken((value) => value + 1)
        }}
      >
      <div className={`workbench-canvas workbench-canvas--${activeScreen}`}>
      <header className="legacy-ledger-topbar">
        <a className="ledger-wordmark" href="/" aria-label="Mastery Ledger home">
          <span>ML</span>
          <strong>Mastery Ledger</strong>
        </a>
        <div className="workspace-crumb"><span>Workspace</span><b>/</b><strong>{data?.workspace.name ?? workspaceName}</strong>{activeScreen !== 'exams' && <><b>/</b><span>{activeScreen === 'study' ? 'Study' : 'Glossary'}</span></>}</div>
        <button className="topbar-action" type="button" onClick={() => { refresh(); if (activeScreen !== 'exams') setStudyRefreshToken((value) => value + 1) }} disabled={loading}>
          <span className={loading ? 'refresh-glyph is-spinning' : 'refresh-glyph'}>↻</span>
          {loading ? 'Scanning' : 'Rescan'}
        </button>
      </header>

      <aside className="legacy-ledger-nav">
        <nav aria-label="Primary navigation">
          <button type="button" onClick={() => setActiveScreen('study')}>Study</button>
        </nav>
        <div className="nav-workspace-shell" ref={workspaceMenuRef}>
          {workspaceMenuOpen && (
            <section className="workspace-menu" role="dialog" aria-label="Change workspace">
              <header>
                <span>Current workspace</span>
                <strong>{data?.workspace.name ?? workspaceName}</strong>
                <small title={data?.workspace.path}>{data?.workspace.path}</small>
              </header>
              <form onSubmit={submitWorkspacePath}>
                <label htmlFor="workspace-location">Workspace location</label>
                <input
                  id="workspace-location"
                  value={workspacePath}
                  onChange={(event) => { setWorkspacePath(event.target.value); setWorkspaceError(null) }}
                  placeholder="Absolute folder path"
                  spellCheck={false}
                  autoFocus
                />
                {workspaceError && <p role="alert">{workspaceError}</p>}
                <div>
                  <button type="button" onClick={browseForWorkspace} disabled={workspaceBusy}>Browse…</button>
                  <button type="submit" className="is-primary" disabled={workspaceBusy}>{workspaceBusy ? 'Changing…' : 'Use this location'}</button>
                </div>
              </form>
              <footer>Choose an existing ledger or a new folder. Your review settings stay with the app.</footer>
            </section>
          )}
          <button
            type="button"
            className="nav-workspace"
            aria-haspopup="dialog"
            aria-expanded={workspaceMenuOpen}
            onClick={() => { setWorkspaceMenuOpen((open) => !open); setWorkspaceError(null) }}
          >
            <span className="nav-workspace__avatar">ML</span>
            <span className="nav-workspace__copy"><strong>{data?.workspace.name ?? 'Local workspace'}</strong><small><i /> Local workspace</small></span>
            <span className="nav-workspace__chevron" aria-hidden="true">⌃</span>
          </button>
        </div>
      </aside>

      {activeScreen === 'study' ? (
        <StudyReader
          refreshToken={studyRefreshToken}
          initialCourseId={studyCourseId}
          initialChapterId={studyChapterId}
          showCatalog={false}
          onNavigationChange={setStudyNavigation}
        />
      ) : activeScreen === 'glossary' ? (
        <GlossaryBrowser
          refreshToken={studyRefreshToken}
          courseId={glossaryCourseId}
          query={glossaryQuery}
          showToolbar={false}
          onCourseIdChange={setGlossaryCourseId}
          onQueryChange={setGlossaryQuery}
          onNavigationChange={setGlossaryNavigation}
          onOpenChapter={(nextCourseId, nextChapterId) => {
            setStudyCourseId(nextCourseId)
            setStudyChapterId(nextChapterId)
            setActiveScreen('study')
          }}
        />
      ) : <>
        <section className="ledger-main">
        <header className="dashboard-heading">
          <div>
            <h1>Exams</h1>
            <p className="dashboard-heading__summary">Validated assessments available in this workspace.</p>
          </div>
          <dl className="exam-summary">
            <div><dt>Ready</dt><dd>{data?.ready_exams.length ?? 0}</dd></div>
            <div><dt>Due</dt><dd>{data?.due_now ?? 0}</dd></div>
            <div><dt>Courses</dt><dd>{data?.recent_courses.length ?? 0}</dd></div>
          </dl>
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
            <div><h2 id="ready-exams-title">Ready exams</h2><p>Select an exam to inspect its evidence and start or resume an attempt.</p></div>
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
          <header><div><h2 id="recent-courses-title">Courses</h2><p>Portable course folders discovered in this workspace.</p></div><span>{data?.recent_courses.length ?? 0} registered</span></header>
          <div className="course-strip">
            {data?.recent_courses.length ? data.recent_courses.slice(0, 6).map((item) => (
              <article key={item.course_id}>
                <span className="course-index">{item.course_id}</span><h3>{item.title}</h3>
                <dl><div><dt>Questions</dt><dd>{item.question_count}</dd></div><div><dt>Ready exams</dt><dd>{item.ready_exam_count}</dd></div><div><dt>Due</dt><dd>{item.due_count}</dd></div></dl>
                <p className="course-concepts"><span>Concept evidence</span><strong>{item.proficient_concept_count}/{item.concept_count} proficient</strong></p>
                <div className="course-rule"><span style={{ width: `${item.concept_count ? (item.proficient_concept_count / item.concept_count) * 100 : 0}%` }} /></div>
                <div className="course-actions">
                  <span>{item.ready_exam_count ? 'Lessons and exam available' : item.question_count ? `${item.question_count} authored questions · exam validation pending` : 'Course preparation in progress'}</span>
                  <button type="button" onClick={() => { setStudyCourseId(item.course_id); setStudyChapterId(null); setActiveScreen('study') }}>Open course <span aria-hidden="true">→</span></button>
                </div>
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
      </>}

      </div>
      </WorkbenchShell>

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
