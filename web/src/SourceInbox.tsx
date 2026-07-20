import { useEffect, useMemo, useState } from 'react'

import {
  applicationApi,
  type IngestionJob,
  type RightsBasis,
  type SourceInboxResult,
  type SourceIntakePayload,
  type SourceType,
} from './api'
import type { WorkspaceScreen } from './KnowledgeWiki'

type SourceInboxProps = {
  workspaceName: string
  onNavigate: (screen: WorkspaceScreen) => void
}

const sourceKinds: Array<{ value: SourceType; label: string; detail: string }> = [
  { value: 'web_article', label: 'Web article', detail: 'Public HTML, plain text, or Markdown' },
  { value: 'remote_video', label: 'Online video', detail: 'Probe first, then captions before media' },
  { value: 'local_document', label: 'Local document', detail: 'PDF, DOCX, Markdown, HTML, or text' },
  { value: 'local_subtitle', label: 'Local subtitles', detail: 'Timestamped SRT or VTT' },
  { value: 'local_media', label: 'Local media', detail: 'Authorized audio or video' },
]

const rightsLabels: Record<RightsBasis, string> = {
  web_reference: 'Public web reference',
  user_owned: 'I own or supplied it',
  platform_permitted_download: 'Platform permits download',
  public_license: 'Publicly licensed',
  explicit_permission: 'Explicit permission',
}

const initialForm: SourceIntakePayload = {
  course_id: null,
  new_course_title: null,
  source_type: 'web_article',
  location: '',
  title: null,
  rights_basis: 'web_reference',
  language: 'en',
  allow_transcription: false,
}

function shortLocation(value: string) {
  if (value.length <= 76) return value
  return `${value.slice(0, 38)}…${value.slice(-32)}`
}

function jobFor(sourceId: string, jobs: IngestionJob[]) {
  return jobs.find((job) => job.source_id === sourceId)
}

export default function SourceInbox({ workspaceName, onNavigate }: SourceInboxProps) {
  const [data, setData] = useState<SourceInboxResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [courseFilter, setCourseFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [addOpen, setAddOpen] = useState(false)
  const [form, setForm] = useState<SourceIntakePayload>(initialForm)
  const [courseChoice, setCourseChoice] = useState('new')
  const [busy, setBusy] = useState(false)

  const refresh = (quiet = false) => {
    if (!quiet) setLoading(true)
    applicationApi.sources().then(setData).catch((cause: Error) => setError(cause.message)).finally(() => !quiet && setLoading(false))
  }

  useEffect(() => { refresh() }, [])

  useEffect(() => {
    const active = data?.jobs.some((job) => job.state === 'queued' || job.state === 'running')
    if (!active) return
    const timer = window.setTimeout(() => refresh(true), 900)
    return () => window.clearTimeout(timer)
  }, [data])

  const filtered = useMemo(() => (data?.sources ?? []).filter((source) => {
    const courseMatches = courseFilter === 'all' || source.course_id === courseFilter
    const statusMatches = statusFilter === 'all' || source.processing_status === statusFilter
    return courseMatches && statusMatches
  }), [courseFilter, data, statusFilter])

  const openAdd = () => {
    const firstCourse = data?.courses[0]?.course_id
    setCourseChoice(firstCourse ?? 'new')
    setForm({ ...initialForm, course_id: firstCourse ?? null })
    setError(null)
    setAddOpen(true)
  }

  const updateKind = (sourceType: SourceType) => {
    const remoteArticle = sourceType === 'web_article'
    setForm((current) => ({
      ...current,
      source_type: sourceType,
      rights_basis: remoteArticle ? 'web_reference' : 'user_owned',
      allow_transcription: false,
    }))
  }

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await applicationApi.addSource({
        ...form,
        course_id: courseChoice === 'new' ? null : courseChoice,
        new_course_title: courseChoice === 'new' ? form.new_course_title : null,
        title: form.title?.trim() || null,
        location: form.location.trim(),
      })
      setAddOpen(false)
      setForm(initialForm)
      refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The source could not be queued.')
    } finally {
      setBusy(false)
    }
  }

  const actOnJob = async (job: IngestionJob, action: 'cancel' | 'retry') => {
    setError(null)
    try {
      if (action === 'cancel') await applicationApi.cancelSourceJob(job.job_id)
      else await applicationApi.retrySourceJob(job.job_id)
      refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : `The job could not ${action}.`)
    }
  }

  return (
    <main className="source-app">
      <header className="source-topbar">
        <button type="button" className="source-wordmark" onClick={() => onNavigate('exams')}><span>ML</span><strong>Mastery Ledger</strong></button>
        <div className="workspace-crumb"><span>Workspace</span><b>/</b><strong>{workspaceName}</strong><b>/</b><span>Source Inbox</span></div>
        <button type="button" className="topbar-action" onClick={() => refresh()} disabled={loading}><span className={loading ? 'refresh-glyph is-spinning' : 'refresh-glyph'}>↻</span>{loading ? 'Scanning' : 'Rescan'}</button>
      </header>

      <aside className="source-nav">
        <nav aria-label="Primary navigation">
          <button type="button" onClick={() => onNavigate('exams')}><span>▦</span>Exams</button>
          <button type="button" className="is-active"><span>▰</span>Sources</button>
          <button type="button" onClick={() => onNavigate('knowledge')}><span>◇</span>Knowledge</button>
          <button type="button" onClick={() => onNavigate('activity')}><span>≡</span>Activity</button>
        </nav>
        <div className="source-capabilities">
          <p>Runtime capabilities</p>
          <span className={data?.capabilities.yt_dlp === 'ready' ? 'is-ready' : ''}><i />Video probe {data?.capabilities.yt_dlp === 'ready' ? 'ready' : 'unavailable'}</span>
          <span className={data?.capabilities.local_asr === 'ready' ? 'is-ready' : ''}><i />Local ASR {data?.capabilities.local_asr === 'ready' ? 'installed' : 'not configured'}</span>
        </div>
      </aside>

      <section className="source-main">
        <header className="source-heading">
          <div><p className="kicker">Source inbox / provenance first</p><h1>Bring the material. Keep the receipt.</h1><p>Every source is registered before extraction, processed through a durable job, and promoted from isolated working space only when its artifacts are inspectable.</p></div>
          <button type="button" onClick={openAdd}><span>+</span>Add source</button>
        </header>

        {error && <div className="dashboard-error" role="alert"><strong>Source action needs attention.</strong><span>{error}</span><button type="button" onClick={() => setError(null)}>Dismiss</button></div>}

        <section className="source-stats" aria-label="Source inbox summary">
          <div><span>Registered</span><strong>{data?.sources.length ?? '—'}</strong><small>sources</small></div>
          <div><span>Ready</span><strong>{data?.sources.filter((source) => source.processing_status === 'ready').length ?? '—'}</strong><small>knowledge records</small></div>
          <div><span>In flight</span><strong>{data?.jobs.filter((job) => job.state === 'queued' || job.state === 'running').length ?? '—'}</strong><small>durable jobs</small></div>
          <div><span>Needs action</span><strong>{data?.sources.filter((source) => ['failed', 'partial', 'needs_user_action'].includes(source.processing_status)).length ?? '—'}</strong><small>with recovery steps</small></div>
        </section>

        <section className="source-ledger" aria-labelledby="source-ledger-title">
          <header>
            <div><p className="kicker">Registered evidence</p><h2 id="source-ledger-title">Sources</h2></div>
            <div className="source-filters">
              <label><span>Course</span><select value={courseFilter} onChange={(event) => setCourseFilter(event.target.value)}><option value="all">All courses</option>{data?.courses.map((course) => <option key={course.course_id} value={course.course_id}>{course.title}</option>)}</select></label>
              <label><span>Status</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">Any status</option><option value="ready">Ready</option><option value="processing">Processing</option><option value="queued">Queued</option><option value="needs_user_action">Needs action</option><option value="partial">Partial</option><option value="failed">Failed</option></select></label>
            </div>
          </header>

          <div className="source-table">
            <div className="source-columns" aria-hidden="true"><span>Source</span><span>Course</span><span>State</span><span>Artifacts</span><span>Job</span></div>
            {loading && !data ? <div className="source-empty">Reading source manifests…</div> : filtered.length ? filtered.map((source) => {
              const job = jobFor(source.source_id, data?.jobs ?? [])
              const course = data?.courses.find((item) => item.course_id === source.course_id)
              const canRetry = job && ['needs_user_action', 'partial', 'failed', 'cancelled'].includes(job.state)
              const canCancel = job && ['queued', 'running'].includes(job.state)
              return (
                <article key={source.source_id}>
                  <div className="source-identity"><span>{source.source_type.replaceAll('_', ' ')}</span><h3>{source.title}</h3><p title={source.original_location}>{shortLocation(source.original_location)}</p><code>{source.source_id}</code></div>
                  <div className="source-course"><strong>{course?.title ?? source.course_id}</strong><span>{source.rights_basis.replaceAll('_', ' ')}</span></div>
                  <div className={`source-state source-state--${source.processing_status}`}><i /><span>{source.processing_status.replaceAll('_', ' ')}</span>{job && (job.state === 'queued' || job.state === 'running') && <progress max={1} value={job.progress} />}</div>
                  <div className="source-artifacts"><strong>{source.artifact_count}</strong><span>{source.knowledge_path ?? 'No knowledge record yet'}</span></div>
                  <div className="source-job">{job ? <><code>{job.job_id}</code><span>{job.stage.replaceAll('_', ' ')}</span>{canCancel && <button type="button" onClick={() => actOnJob(job, 'cancel')}>Cancel</button>}{canRetry && <button type="button" onClick={() => actOnJob(job, 'retry')}>Retry</button>}</> : <span>No job record</span>}</div>
                  {(source.recovery_suggestion || job?.recovery_suggestion) && <p className="source-recovery"><strong>{source.error_code || job?.error_code}</strong>{source.recovery_suggestion || job?.recovery_suggestion}</p>}
                </article>
              )
            }) : <div className="source-empty"><strong>{data?.sources.length ? 'No sources match this view.' : 'No sources registered yet.'}</strong><span>{data?.sources.length ? 'Change the filters to inspect another state.' : 'Add a document, article, video, audio file, or subtitle to begin a traceable course.'}</span></div>}
          </div>
        </section>
      </section>

      <aside className="source-receipt-rail">
        <p className="kicker">Promotion contract</p><h2>Clean course, visible process.</h2>
        <ol><li><span>01</span><div><strong>Register</strong><p>Write the source and rights basis before extraction.</p></div></li><li><span>02</span><div><strong>Isolate</strong><p>Run work under the course’s <code>.work/ingestion</code> boundary.</p></div></li><li><span>03</span><div><strong>Promote</strong><p>Keep source Markdown at the root and originals under <code>source/media</code>.</p></div></li><li><span>04</span><div><strong>Record</strong><p>Append observable actions and recovery steps without private reasoning.</p></div></li></ol>
        <div className="source-path-rule"><span>Portable layout</span><code>source/SRC-*.md</code><code>source/media/SRC-*/</code><code>source-manifest.yaml</code><code>logs/events.jsonl</code></div>
      </aside>

      {addOpen && (
        <div className="source-add-backdrop" role="presentation" onMouseDown={() => !busy && setAddOpen(false)}>
          <section className="source-add" role="dialog" aria-modal="true" aria-labelledby="add-source-title" onMouseDown={(event) => event.stopPropagation()}>
            <header><div><p className="kicker">New source receipt</p><h2 id="add-source-title">Register before processing.</h2></div><button type="button" onClick={() => setAddOpen(false)} disabled={busy} aria-label="Close source intake">×</button></header>
            <div className="source-add-body">
              <label className="source-field"><span>Course</span><select value={courseChoice} onChange={(event) => { setCourseChoice(event.target.value); setForm((current) => ({ ...current, course_id: event.target.value === 'new' ? null : event.target.value })) }}>{data?.courses.map((course) => <option key={course.course_id} value={course.course_id}>{course.title}</option>)}<option value="new">+ Create a new course</option></select></label>
              {courseChoice === 'new' && <label className="source-field"><span>New course title</span><input value={form.new_course_title ?? ''} onChange={(event) => setForm((current) => ({ ...current, new_course_title: event.target.value }))} placeholder="e.g. Cellular Biology" /></label>}
              <fieldset className="source-kind"><legend>Source type</legend><div>{sourceKinds.map((kind) => <label key={kind.value} className={form.source_type === kind.value ? 'is-selected' : ''}><input type="radio" name="source-kind" checked={form.source_type === kind.value} onChange={() => updateKind(kind.value)} /><strong>{kind.label}</strong><small>{kind.detail}</small></label>)}</div></fieldset>
              <label className="source-field source-field--wide"><span>{form.source_type.startsWith('local_') ? 'Absolute file path' : 'Public URL'}</span><input value={form.location} onChange={(event) => setForm((current) => ({ ...current, location: event.target.value }))} placeholder={form.source_type.startsWith('local_') ? 'C:\Learning\source.pdf' : 'https://…'} /></label>
              <label className="source-field"><span>Display title <em>optional</em></span><input value={form.title ?? ''} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} /></label>
              <label className="source-field"><span>Language</span><input value={form.language} onChange={(event) => setForm((current) => ({ ...current, language: event.target.value }))} /></label>
              <label className="source-field source-field--wide"><span>Rights basis</span><select value={form.rights_basis} disabled={form.source_type === 'web_article'} onChange={(event) => setForm((current) => ({ ...current, rights_basis: event.target.value as RightsBasis }))}>{(Object.keys(rightsLabels) as RightsBasis[]).filter((rights) => form.source_type === 'web_article' ? rights === 'web_reference' : rights !== 'web_reference').map((rights) => <option key={rights} value={rights}>{rightsLabels[rights]}</option>)}</select><small>Remote media with unknown rights is refused. Credentials, cookies, DRM bypass, and private-network URLs are never accepted.</small></label>
              {(form.source_type === 'remote_video' || form.source_type === 'local_media') && <label className="source-transcription"><input type="checkbox" checked={form.allow_transcription} onChange={(event) => setForm((current) => ({ ...current, allow_transcription: event.target.checked }))} /><span><strong>Permit local transcription if captions are unavailable</strong><small>This runs only when an approved local ASR model is already configured. No model is downloaded here.</small></span></label>}
            </div>
            <footer><p>Submitting writes a pending manifest record and durable job. It does not wait for extraction.</p><div><button type="button" className="button button--quiet" onClick={() => setAddOpen(false)} disabled={busy}>Cancel</button><button type="button" className="button button--primary" onClick={submit} disabled={busy || !form.location.trim() || (courseChoice === 'new' && !form.new_course_title?.trim())}>{busy ? 'Registering…' : 'Register & queue'} <span>→</span></button></div></footer>
          </section>
        </div>
      )}
    </main>
  )
}
