import { useEffect, useState } from 'react'
import { ArrowRight, Download, RefreshCw, X } from 'lucide-react'

import { applicationApi, type UpdateStatus } from './api'

let updateStatusRequest: Promise<UpdateStatus> | null = null

function loadUpdateStatus() {
  updateStatusRequest ??= applicationApi.updateStatus()
  return updateStatusRequest
}

export function formatUpdateSize(bytes: number | null) {
  if (!bytes || bytes < 1) return null
  const megabytes = bytes / (1024 * 1024)
  return `${megabytes >= 10 ? Math.round(megabytes) : megabytes.toFixed(1)} MB`
}

export default function UpdateNotice() {
  const [update, setUpdate] = useState<UpdateStatus | null>(null)
  const [dismissed, setDismissed] = useState(false)
  const [phase, setPhase] = useState<'ready' | 'installing' | 'restarting'>('ready')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void loadUpdateStatus()
      .then((result) => {
        if (active && result.status === 'available') setUpdate(result)
      })
      .catch(() => {
        // Updating is optional. Offline use must remain quiet and fully functional.
      })
    return () => { active = false }
  }, [])

  if (!update || dismissed) return null
  const size = formatUpdateSize(update.download_size)
  const version = update.latest_version

  const install = async () => {
    if (!version || phase !== 'ready') return
    setPhase('installing')
    setError(null)
    try {
      await applicationApi.installUpdate(version)
      setPhase('restarting')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The update could not be installed.')
      setPhase('ready')
    }
  }

  return (
    <section className="update-notice" role="status" aria-live="polite" aria-label="Application update available">
      <div className="update-notice__edge" aria-hidden="true" />
      <header>
        <span className="update-notice__mark"><Download aria-hidden="true" /></span>
        <div>
          <p>Application update</p>
          <h2>Version {version} is ready</h2>
        </div>
        <button
          type="button"
          className="update-notice__close"
          aria-label="Remind me about this update later"
          disabled={phase !== 'ready'}
          onClick={() => setDismissed(true)}
        >
          <X aria-hidden="true" />
        </button>
      </header>

      <p className="update-notice__copy">
        Install the latest Mastery Ledger app. Your courses and progress stay in the separate workspace.
      </p>

      <div className="update-notice__receipt" aria-label={`Update from version ${update.current_version} to ${version}`}>
        <span>Installed <strong>v{update.current_version}</strong></span>
        <ArrowRight aria-hidden="true" />
        <span>Available <strong>v{version}</strong></span>
        {size && <em>{size}</em>}
      </div>

      {error && <p className="update-notice__error" role="alert">{error}</p>}

      <footer>
        <button type="button" className="update-notice__later" disabled={phase !== 'ready'} onClick={() => setDismissed(true)}>Later</button>
        {update.automatic_install_available ? (
          <button type="button" className="update-notice__install" disabled={phase !== 'ready'} onClick={() => void install()}>
            {phase === 'ready' ? <><span>Update and restart</span><ArrowRight aria-hidden="true" /></> : <><RefreshCw className="is-spinning" aria-hidden="true" /><span>{phase === 'installing' ? 'Downloading and verifying…' : 'Restarting…'}</span></>}
          </button>
        ) : (
          <a className="update-notice__install" href={update.release_url ?? '#'} target="_blank" rel="noreferrer">
            <span>View release</span><ArrowRight aria-hidden="true" />
          </a>
        )}
      </footer>
    </section>
  )
}
