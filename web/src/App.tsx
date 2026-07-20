import { type CSSProperties, type FormEvent, useEffect, useMemo, useState } from 'react'

import {
  applicationApi,
  onboardingApi,
  type ApplicationStatus,
  type OnboardingDefaults,
  type OnboardingResult,
  type ProcessingMode,
  type WorkspaceValidation,
} from './api'
import Dashboard from './Dashboard'
import WorkspaceRepair from './WorkspaceRepair'
import { formatReviewIntervals, parseReviewIntervals } from './reviewIntervals'

const steps = [
  { eyebrow: '01', label: 'Intent', title: 'Begin the ledger' },
  { eyebrow: '02', label: 'Place', title: 'Choose a workspace' },
  { eyebrow: '03', label: 'Method', title: 'Set your study rhythm' },
  { eyebrow: '04', label: 'Review', title: 'Confirm the first entry' },
]

const processingModes: Array<{ value: ProcessingMode; title: string; detail: string }> = [
  {
    value: 'local_only',
    title: 'Local only',
    detail: 'Source contents stay on this computer. Recommended for first setup.',
  },
  {
    value: 'cloud_allowed',
    title: 'Cloud allowed',
    detail: 'Relevant excerpts may be sent to configured remote models.',
  },
  {
    value: 'metadata_only',
    title: 'Metadata only',
    detail: 'Remote services may receive titles and metadata, never source contents.',
  },
]

type FormState = {
  workspacePath: string
  workspaceName: string
  language: string
  processingMode: ProcessingMode
  reducedMotion: boolean
  intervalText: string
  initialSourceHint: string
}

const emptyForm: FormState = {
  workspacePath: '',
  workspaceName: 'Primary learning workspace',
  language: 'en',
  processingMode: 'local_only',
  reducedMotion: false,
  intervalText: '1, 3, 7, 14, 28, 56, 112, 224, 448, 896, 1792, 3584',
  initialSourceHint: '',
}

function LedgerMark() {
  return (
    <svg className="ledger-mark" viewBox="0 0 46 46" role="img" aria-label="Mastery Ledger">
      <rect x="5" y="4" width="34" height="38" rx="2" />
      <path d="M12 13h20M12 20h20M12 27h12M29 27h3M12 34h8" />
      <path className="ledger-mark__accent" d="m25 34 4 4 9-11" />
    </svg>
  )
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="M3 10h13M11 5l5 5-5 5" />
    </svg>
  )
}

function OnboardingApp() {
  const [step, setStep] = useState(0)
  const [form, setForm] = useState<FormState>(emptyForm)
  const [defaults, setDefaults] = useState<OnboardingDefaults | null>(null)
  const [validation, setValidation] = useState<WorkspaceValidation | null>(null)
  const [result, setResult] = useState<OnboardingResult | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    onboardingApi
      .defaults()
      .then((nextDefaults) => {
        setDefaults(nextDefaults)
        setForm({
          workspacePath: nextDefaults.workspace_path,
          workspaceName: nextDefaults.workspace_name,
          language: nextDefaults.language,
          processingMode: nextDefaults.processing_mode,
          reducedMotion: nextDefaults.reduced_motion,
          intervalText: formatReviewIntervals(nextDefaults.review_intervals),
          initialSourceHint: '',
        })
      })
      .catch((cause: Error) => {
        setError(
          cause.message === 'Local session required'
            ? 'This page needs a local Mastery Ledger session. Reopen it with “mastery-ledger onboard --open --json”.'
            : cause.message,
        )
      })
      .finally(() => setBusy(false))
  }, [])

  useEffect(() => {
    document.documentElement.dataset.reduceMotion = form.reducedMotion ? 'true' : 'false'
  }, [form.reducedMotion])

  const intervals = useMemo(() => {
    try {
      return parseReviewIntervals(form.intervalText)
    } catch {
      return []
    }
  }, [form.intervalText])

  const intervalError = useMemo(() => {
    try {
      parseReviewIntervals(form.intervalText)
      return null
    } catch (cause) {
      return cause instanceof Error ? cause.message : 'Review intervals are invalid.'
    }
  }, [form.intervalText])

  const update = <Key extends keyof FormState>(key: Key, value: FormState[Key]) => {
    setForm((current) => ({ ...current, [key]: value }))
    setError(null)
    if (key === 'workspacePath') setValidation(null)
  }

  const validateWorkspace = async () => {
    setBusy(true)
    setError(null)
    try {
      const nextValidation = await onboardingApi.validateWorkspace(form.workspacePath)
      setValidation(nextValidation)
      return nextValidation.valid
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Workspace validation failed.')
      return false
    } finally {
      setBusy(false)
    }
  }

  const chooseWorkspace = async () => {
    setBusy(true)
    setError(null)
    try {
      const selection = await onboardingApi.pickFolder(form.workspacePath || null)
      if (selection.status === 'selected' && selection.path) update('workspacePath', selection.path)
      else if (selection.status === 'unavailable') setError(selection.message ?? 'The native folder chooser is unavailable. Enter an absolute path instead.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The folder chooser could not open.')
    } finally {
      setBusy(false)
    }
  }

  const next = async () => {
    if (step === 1 && !(await validateWorkspace())) return
    if (step === 2 && intervalError) {
      setError(intervalError)
      return
    }
    setStep((current) => Math.min(current + 1, steps.length - 1))
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (intervalError) {
      setError(intervalError)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const completion = await onboardingApi.complete({
        workspace_path: form.workspacePath,
        workspace_name: form.workspaceName,
        language: form.language,
        processing_mode: form.processingMode,
        reduced_motion: form.reducedMotion,
        review_intervals: parseReviewIntervals(form.intervalText),
        initial_source_hint: form.initialSourceHint.trim() || null,
      })
      setResult(completion)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Setup could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  if (busy && !defaults) {
    return (
      <main className="launch-state" aria-busy="true">
        <LedgerMark />
        <p>Opening the ledger…</p>
      </main>
    )
  }

  if (!defaults) {
    return (
      <main className="launch-state launch-state--error">
        <LedgerMark />
        <h1>Local session unavailable</h1>
        <p>{error ?? 'Mastery Ledger could not load first-run settings.'}</p>
        <code>mastery-ledger onboard --open --json</code>
      </main>
    )
  }

  if (result) {
    return (
      <main className="completion-page">
        <div className="completion-page__rule" />
        <section className="completion-card">
          <div className="completion-card__seal" aria-hidden="true">✓</div>
          <p className="kicker">First entry recorded</p>
          <h1>Your ledger has a home.</h1>
          <p className="completion-card__lede">
            Mastery Ledger is ready to build source-grounded courses, exams, and a review history that compounds over time.
          </p>
          <dl className="receipt">
            <div><dt>Workspace</dt><dd>{result.workspace.name}</dd></div>
            <div><dt>Location</dt><dd>{result.workspace.path}</dd></div>
            <div><dt>Review curve</dt><dd>{intervals.join(' → ')} days</dd></div>
          </dl>
          <div className="completion-card__note">
            Return to Codex and continue your original request. The next doctor check will report <code>ready</code>.
          </div>
          <button className="button button--primary completion-card__action" type="button" onClick={() => window.location.assign('/')}>
            Open Exam Ledger <ArrowIcon />
          </button>
        </section>
      </main>
    )
  }

  return (
    <main className="onboarding-shell">
      <aside className="folio-rail">
        <header className="brand-lockup">
          <LedgerMark />
          <div>
            <strong>Mastery Ledger</strong>
            <span>First-run folio</span>
          </div>
        </header>

        <div className="folio-rail__intro">
          <p className="kicker kicker--light">A durable place to learn</p>
          <h2>Set the rules once.<br />Keep the record for years.</h2>
        </div>

        <nav aria-label="Onboarding progress">
          <ol className="step-list">
            {steps.map((item, index) => (
              <li key={item.label} className={index === step ? 'is-active' : index < step ? 'is-complete' : ''}>
                <button type="button" onClick={() => index < step && setStep(index)} disabled={index > step}>
                  <span className="step-list__index">{index < step ? '✓' : item.eyebrow}</span>
                  <span><small>{item.label}</small>{item.title}</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>

        <footer className="folio-rail__footer">
          <span className="status-dot" />
          Local application · Session protected
        </footer>
      </aside>

      <section className="setup-canvas">
        <header className="canvas-header">
          <span>Setup / {String(step + 1).padStart(2, '0')}</span>
          <span className="local-badge">Local by default</span>
        </header>

        <form onSubmit={submit} className="setup-form">
          {step === 0 && (
            <section className="panel-enter" aria-labelledby="step-title">
              <p className="kicker">Begin with intent</p>
              <h1 id="step-title">What should this ledger help you own?</h1>
              <p className="lead">
                Mastery Ledger turns material you trust into a knowledge map, focused exams, and a review trail. Your sources stay connected to every claim and question.
              </p>

              <label className="field field--large">
                <span>Bring a first source <em>optional</em></span>
                <textarea
                  value={form.initialSourceHint}
                  onChange={(event) => update('initialSourceHint', event.target.value)}
                  placeholder="Paste a link, local file path, or a short note about what you want to study…"
                  rows={4}
                />
                <small>You can also begin empty and add documents, websites, video, or audio later.</small>
              </label>

              <div className="principle-strip" aria-label="Mastery Ledger principles">
                <div><strong>01</strong><span>Sources remain traceable</span></div>
                <div><strong>02</strong><span>Questions become durable records</span></div>
                <div><strong>03</strong><span>Reviews stretch from days to years</span></div>
              </div>
            </section>
          )}

          {step === 1 && (
            <section className="panel-enter" aria-labelledby="step-title">
              <p className="kicker">Choose its home</p>
              <h1 id="step-title">Your courses should outlive the app.</h1>
              <p className="lead">
                Pick a folder for portable course files, sources, exams, attempts, and logs. The application itself remains separate.
              </p>

              <div className="field-grid">
                <label className="field">
                  <span>Workspace name</span>
                  <input
                    value={form.workspaceName}
                    onChange={(event) => update('workspaceName', event.target.value)}
                    autoComplete="off"
                    required
                  />
                </label>
                <label className="field field--path">
                  <span>Absolute folder path</span>
                  <div className="path-input">
                    <input
                      value={form.workspacePath}
                      onChange={(event) => update('workspacePath', event.target.value)}
                      autoComplete="off"
                      spellCheck={false}
                      required
                    />
                    <button type="button" onClick={() => defaults && update('workspacePath', defaults.workspace_path)}>
                      Suggested
                    </button>
                    <button type="button" onClick={chooseWorkspace} disabled={busy}>
                      Browse…
                    </button>
                  </div>
                  <small>Nothing will be placed inside the installed skill directory.</small>
                </label>
              </div>

              <button type="button" className="validation-button" onClick={validateWorkspace} disabled={busy}>
                Check this location
              </button>
              {validation && (
                <div className={`validation-note ${validation.valid ? 'is-valid' : 'is-invalid'}`} role="status">
                  <strong>{validation.valid ? 'Location approved' : 'Choose another location'}</strong>
                  <span>{validation.message}</span>
                  <code>{validation.path}</code>
                </div>
              )}

              <div className="boundary-note">
                <span aria-hidden="true">↳</span>
                <p><strong>Application ≠ workspace.</strong> Updates can replace the app without touching this folder.</p>
              </div>
            </section>
          )}

          {step === 2 && (
            <section className="panel-enter" aria-labelledby="step-title">
              <p className="kicker">Define your method</p>
              <h1 id="step-title">Privacy first. Rhythm second.</h1>
              <p className="lead">These defaults apply to new courses. Each course can adopt stricter rules later.</p>

              <fieldset className="mode-fieldset">
                <legend>Source processing</legend>
                <div className="mode-grid">
                  {processingModes.map((mode) => (
                    <label key={mode.value} className={form.processingMode === mode.value ? 'is-selected' : ''}>
                      <input
                        type="radio"
                        name="processing-mode"
                        value={mode.value}
                        checked={form.processingMode === mode.value}
                        onChange={() => update('processingMode', mode.value)}
                      />
                      <span className="radio-mark" />
                      <strong>{mode.title}</strong>
                      <small>{mode.detail}</small>
                    </label>
                  ))}
                </div>
              </fieldset>

              <div className="preference-grid">
                <label className="field">
                  <span>Interface language</span>
                  <select value={form.language} onChange={(event) => update('language', event.target.value)}>
                    <option value="en">English</option>
                    <option value="fr">Français</option>
                    <option value="zh-Hans">简体中文</option>
                    <option value="es">Español</option>
                  </select>
                </label>
                <label className="toggle-field">
                  <span><strong>Reduce motion</strong><small>Minimize interface transitions.</small></span>
                  <input
                    type="checkbox"
                    checked={form.reducedMotion}
                    onChange={(event) => update('reducedMotion', event.target.checked)}
                  />
                  <span className="toggle" aria-hidden="true" />
                </label>
              </div>

              <label className="field curve-field">
                <span>Ownership curve <em>days after a successful review</em></span>
                <input
                  value={form.intervalText}
                  onChange={(event) => update('intervalText', event.target.value)}
                  aria-invalid={Boolean(intervalError)}
                />
                <small className={intervalError ? 'field-error' : ''}>
                  {intervalError ?? 'Comma-separated, unique, and increasing. You can edit this later.'}
                </small>
              </label>
              {!intervalError && (
                <div className="curve-preview" aria-label={`Reviews after ${intervals.join(', ')} days`}>
                  {intervals.map((day, index) => (
                    <div key={day} style={{ '--curve-step': index } as CSSProperties}>
                      <span />
                      <small>{day >= 365 ? `${(day / 365).toFixed(1)}y` : `${day}d`}</small>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {step === 3 && (
            <section className="panel-enter" aria-labelledby="step-title">
              <p className="kicker">Review the entry</p>
              <h1 id="step-title">One local record, ready to grow.</h1>
              <p className="lead">Saving creates the workspace and application registry. It does not download a model or begin processing sources.</p>

              <dl className="review-ledger">
                <div><dt>Workspace</dt><dd>{form.workspaceName}<small>{form.workspacePath}</small></dd></div>
                <div><dt>Processing</dt><dd>{processingModes.find((mode) => mode.value === form.processingMode)?.title}</dd></div>
                <div><dt>Review curve</dt><dd>{intervals.join(' → ')} days</dd></div>
                <div><dt>First source</dt><dd>{form.initialSourceHint.trim() || 'None yet'}</dd></div>
              </dl>

              <div className="download-notice">
                <strong>No surprise downloads.</strong>
                <p><code>yt-dlp</code> belongs to the installed runtime. If you later choose local transcription, Mastery Ledger will show the ASR model and expected size before downloading it.</p>
              </div>
            </section>
          )}

          {error && <div className="error-banner" role="alert">{error}</div>}

          <footer className="form-actions">
            <button type="button" className="button button--quiet" onClick={() => setStep((current) => Math.max(0, current - 1))} disabled={step === 0 || busy}>
              Back
            </button>
            {step < steps.length - 1 ? (
              <button type="button" className="button button--primary" onClick={next} disabled={busy}>
                {busy ? 'Checking…' : 'Continue'} <ArrowIcon />
              </button>
            ) : (
              <button type="submit" className="button button--primary" disabled={busy}>
                {busy ? 'Recording…' : 'Create my ledger'} <ArrowIcon />
              </button>
            )}
          </footer>
        </form>
      </section>
    </main>
  )
}

function App() {
  const [status, setStatus] = useState<ApplicationStatus | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)

  useEffect(() => {
    applicationApi
      .status()
      .then(setStatus)
      .catch((cause: Error) => setStatusError(cause.message))
  }, [])

  if (statusError) {
    return (
      <main className="launch-state launch-state--error">
        <LedgerMark />
        <h1>Local session unavailable</h1>
        <p>{statusError}</p>
        <code>mastery-ledger onboard --open --json</code>
      </main>
    )
  }

  if (!status) {
    return (
      <main className="launch-state" aria-busy="true">
        <LedgerMark />
        <p>Reading the ledger…</p>
      </main>
    )
  }

  if (status.status === 'ready' && status.active_workspace) {
    return <Dashboard workspaceName={status.active_workspace.name} />
  }

  if (status.status === 'workspace_unavailable' && status.active_workspace) {
    return <WorkspaceRepair workspace={status.active_workspace} onComplete={() => applicationApi.status().then(setStatus).catch((cause: Error) => setStatusError(cause.message))} />
  }

  return <OnboardingApp />
}

export default App
