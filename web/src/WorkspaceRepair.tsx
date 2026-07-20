import { useState } from 'react'

import { applicationApi, onboardingApi, type ApplicationStatus, type WorkspaceValidation } from './api'

type WorkspaceRepairProps = {
  workspace: NonNullable<ApplicationStatus['active_workspace']>
  onComplete: () => void
}

export default function WorkspaceRepair({ workspace, onComplete }: WorkspaceRepairProps) {
  const [path, setPath] = useState(workspace.path)
  const [name, setName] = useState(workspace.name)
  const [validation, setValidation] = useState<WorkspaceValidation | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const validate = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await onboardingApi.validateWorkspace(path)
      setValidation(result)
      return result.valid
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Workspace validation failed.')
      return false
    } finally {
      setBusy(false)
    }
  }

  const browse = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await onboardingApi.pickFolder(path)
      if (result.status === 'selected' && result.path) {
        setPath(result.path)
        setValidation(null)
      } else if (result.status === 'unavailable') setError(result.message ?? 'Enter an absolute path instead.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The folder chooser could not open.')
    } finally {
      setBusy(false)
    }
  }

  const save = async () => {
    if (!(await validate())) return
    setBusy(true)
    try {
      await applicationApi.repairWorkspace(path, name)
      onComplete()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The workspace could not be repaired.')
    } finally {
      setBusy(false)
    }
  }

  return <main className="repair-page">
    <aside className="repair-rail"><div className="repair-mark">ML</div><div><p>Workspace repair</p><h1>Reconnect the ledger. Preserve the record.</h1></div><footer>Nothing is copied, deleted, or silently relocated.</footer></aside>
    <section className="repair-canvas">
      <header><span>Mastery Ledger</span><strong>Local · session protected</strong></header>
      <div className="repair-card">
        <p className="kicker">Registered workspace unavailable</p>
        <h2>Point back to your courses.</h2>
        <p className="repair-lede">The registered folder is missing or no longer writable. Restore it at the original location, or select the folder that now owns these portable course records.</p>
        <dl><div><dt>Last registered name</dt><dd>{workspace.name}</dd></div><div><dt>Last registered path</dt><dd>{workspace.path}</dd></div></dl>
        <label className="field"><span>Workspace name</span><input value={name} onChange={(event) => setName(event.target.value)} required /></label>
        <label className="field"><span>Absolute folder path</span><div className="repair-path"><input value={path} onChange={(event) => { setPath(event.target.value); setValidation(null) }} spellCheck={false} required /><button type="button" onClick={browse} disabled={busy}>Browse…</button></div><small>Selecting a new empty folder starts an empty workspace. It does not migrate the missing one.</small></label>
        {validation && <div className={`validation-note ${validation.valid ? 'is-valid' : 'is-invalid'}`} role="status"><strong>{validation.valid ? 'Location approved' : 'Choose another location'}</strong><span>{validation.message}</span><code>{validation.path}</code></div>}
        {error && <div className="error-banner" role="alert">{error}</div>}
        <div className="repair-actions"><button type="button" className="button button--quiet" onClick={validate} disabled={busy}>Check location</button><button type="button" className="button button--primary" onClick={save} disabled={busy || !path.trim() || !name.trim()}>{busy ? 'Checking…' : 'Use this workspace'} <span>→</span></button></div>
      </div>
    </section>
  </main>
}
