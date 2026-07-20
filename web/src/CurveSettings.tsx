import { useEffect, useMemo, useState, type CSSProperties } from 'react'

import {
  applicationApi,
  type ApplicationSettings,
  type CurveApplicationPolicy,
  type ReviewCurveUpdateResult,
} from './api'
import { formatReviewInterval, reviewCurveWarnings } from './reviewIntervals'

type CurveSettingsProps = {
  onClose: () => void
  onSaved: () => void
}

const policies: Array<{ value: CurveApplicationPolicy; title: string; detail: string; badge?: string }> = [
  {
    value: 'future_advancement',
    title: 'Future advancement',
    detail: 'Keep every current due date. The new curve takes over after each question’s next completed due review.',
    badge: 'Recommended',
  },
  {
    value: 'new_questions_only',
    title: 'New questions only',
    detail: 'Existing questions remain on their current curve; newly scheduled questions use this profile.',
  },
  {
    value: 'recalculate_all',
    title: 'Recalculate all',
    detail: 'Apply the new interval for each current stage and recompute pending dates from its scheduling anchor.',
  },
]

function validateStages(values: string[]): { intervals: number[]; error: string | null } {
  const intervals = values.map(Number)
  if (!intervals.length || intervals.some((day) => !Number.isInteger(day) || day < 1 || day > 36500)) {
    return { intervals, error: 'Every stage must be a whole number from 1 to 36,500 days.' }
  }
  if (intervals.length > 24) return { intervals, error: 'A curve can contain no more than 24 stages.' }
  if (intervals.some((day, index) => index > 0 && day <= intervals[index - 1])) {
    return { intervals, error: 'Stages must be unique and strictly increasing.' }
  }
  return { intervals, error: null }
}

export default function CurveSettings({ onClose, onSaved }: CurveSettingsProps) {
  const [settings, setSettings] = useState<ApplicationSettings | null>(null)
  const [name, setName] = useState('')
  const [stages, setStages] = useState<string[]>([])
  const [policy, setPolicy] = useState<CurveApplicationPolicy>('future_advancement')
  const [duplicate, setDuplicate] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ReviewCurveUpdateResult | null>(null)

  useEffect(() => {
    applicationApi.settings().then((payload) => {
      setSettings(payload)
      setName(payload.review_curve.name)
      setStages(payload.review_curve.interval_days.map(String))
    }).catch((cause: Error) => setError(cause.message))
  }, [])

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [busy, onClose])

  const validation = useMemo(() => validateStages(stages), [stages])
  const warnings = validation.error ? [] : reviewCurveWarnings(validation.intervals)
  const maxLog = Math.log10(Math.max(2, validation.intervals.at(-1) ?? 2))

  const updateStage = (index: number, value: string) => {
    setStages((current) => current.map((stage, stageIndex) => stageIndex === index ? value : stage))
    setResult(null)
  }

  const addStage = () => {
    const last = Number(stages.at(-1) ?? 0)
    const next = Math.min(36500, Math.max(1, Number.isFinite(last) ? last * 2 : 1))
    setStages((current) => [...current, String(next)])
  }

  const save = async () => {
    if (!settings || validation.error || !name.trim()) return
    if (policy === 'recalculate_all' && !confirmed) {
      setError('Confirm the due-date recalculation before saving.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const saved = await applicationApi.updateReviewCurve({
        name: name.trim(),
        interval_days: validation.intervals,
        application_policy: policy,
        save_mode: duplicate ? 'duplicate_profile' : 'new_version',
        confirm_recalculate: confirmed,
      })
      setResult(saved)
      setSettings((current) => current ? { ...current, review_curve: saved.review_curve } : current)
      onSaved()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The curve could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="settings-backdrop" role="presentation" onMouseDown={() => !busy && onClose()}>
      <section className="curve-settings" role="dialog" aria-modal="true" aria-labelledby="curve-settings-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="curve-settings__header">
          <div><p className="kicker">Settings / scheduling</p><h2 id="curve-settings-title">Shape the ownership horizon.</h2></div>
          <button type="button" onClick={onClose} disabled={busy} aria-label="Close curve settings">×</button>
        </header>

        {!settings && !error && <div className="settings-loading" aria-busy="true">Reading the current curve…</div>}

        {settings && (
          <div className="curve-settings__body">
            <section className="curve-editor" aria-labelledby="curve-profile-title">
              <div className="settings-section-heading">
                <div><span>01</span><div><h3 id="curve-profile-title">Curve profile</h3><p>Profile {settings.review_curve.curve_id} · version {settings.review_curve.version}</p></div></div>
                <button type="button" onClick={() => setStages(settings.default_review_intervals.map(String))}>Reset to default</button>
              </div>

              <label className="settings-name"><span>Profile name</span><input value={name} maxLength={120} onChange={(event) => setName(event.target.value)} /></label>

              <div className="stage-label"><span>Interval stages</span><small>Directly edit any day value.</small></div>
              <div className="stage-chips">
                {stages.map((stage, index) => (
                  <label key={index} className="stage-chip">
                    <span>{String(index + 1).padStart(2, '0')}</span>
                    <input value={stage} inputMode="numeric" aria-label={`Stage ${index + 1} interval in days`} onChange={(event) => updateStage(index, event.target.value)} />
                    <em>days</em>
                    <button type="button" disabled={stages.length === 1} onClick={() => setStages((current) => current.filter((_, stageIndex) => stageIndex !== index))} aria-label={`Remove stage ${index + 1}`}>×</button>
                  </label>
                ))}
                {stages.length < 24 && <button type="button" className="stage-add" onClick={addStage}><span>+</span>Add stage</button>}
              </div>
              {validation.error && <p className="curve-validation" role="alert">{validation.error}</p>}

              {!validation.error && (
                <div className="horizon-preview" aria-label="Ownership curve timeline preview">
                  <div className="horizon-line" />
                  {validation.intervals.map((day, index) => (
                    <div className="horizon-stop" key={`${day}-${index}`} style={{ '--horizon-position': `${(Math.log10(Math.max(1, day)) / maxLog) * 100}%` } as CSSProperties}>
                      <i /><strong>{day}d</strong><span>{formatReviewInterval(day)}</span>
                    </div>
                  ))}
                </div>
              )}
              {warnings.length > 0 && <div className="curve-warnings">{warnings.map((warning) => <p key={warning}>{warning}</p>)}</div>}
            </section>

            <section className="curve-policy" aria-labelledby="curve-policy-title">
              <div className="settings-section-heading"><div><span>02</span><div><h3 id="curve-policy-title">Application policy</h3><p>{settings.scheduled_question_count} scheduled question{settings.scheduled_question_count === 1 ? '' : 's'} inspected</p></div></div></div>
              <div className="policy-options">
                {policies.map((item) => (
                  <label key={item.value} className={policy === item.value ? 'is-selected' : ''}>
                    <input type="radio" name="curve-policy" value={item.value} checked={policy === item.value} onChange={() => { setPolicy(item.value); setConfirmed(false) }} />
                    <span className="policy-radio" aria-hidden="true" />
                    <span><strong>{item.title}{item.badge && <em>{item.badge}</em>}</strong><small>{item.detail}</small></span>
                  </label>
                ))}
              </div>
              {policy === 'recalculate_all' && (
                <label className="recalculate-confirm"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /><span>I understand this will change pending due dates for up to {settings.scheduled_question_count} questions. Past attempts will remain unchanged.</span></label>
              )}
              <label className="duplicate-profile"><input type="checkbox" checked={duplicate} onChange={(event) => setDuplicate(event.target.checked)} /><span><strong>Duplicate as a new profile</strong><small>Start at version 1 with a new curve ID instead of superseding this profile.</small></span></label>
            </section>
          </div>
        )}

        {error && <div className="settings-error" role="alert">{error}</div>}
        {result && <div className="settings-success" role="status"><strong>Curve saved as {result.review_curve.curve_id} v{result.review_curve.version}.</strong><span>{result.application_policy === 'recalculate_all' ? `${result.affected_question_count} schedules recalculated.` : `${result.affected_question_count} existing schedules preserved until the selected transition.`}</span></div>}

        <footer className="curve-settings__footer">
          <p>Scheduling history and completed attempts are never rewritten.</p>
          <div><button type="button" className="button button--quiet" onClick={onClose} disabled={busy}>{result ? 'Done' : 'Cancel'}</button>{!result && <button type="button" className="button button--primary" onClick={save} disabled={busy || !settings || Boolean(validation.error) || !name.trim()}>{busy ? 'Saving…' : duplicate ? 'Create profile' : 'Save new version'} <span>→</span></button>}</div>
        </footer>
      </section>
    </div>
  )
}
