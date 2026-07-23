import { useEffect, useMemo, useRef, useState } from 'react'

import {
  applicationApi,
  type ExamAttempt,
  type ExamCompletion,
  type ExamQuestion,
  type QuestionFeedback,
  type QuestionReview,
  type SourceDisclosure,
} from './api'

type ExamRunnerProps = {
  courseId?: string
  examId?: string
  reviewMode?: boolean
  onExit: () => void
}

type AnswerState = {
  selectedOptionId: string | null
  feedback: QuestionFeedback | null
}

function formatElapsed(totalSeconds: number) {
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return [hours, minutes, seconds].map((part) => String(part).padStart(2, '0')).join(':')
}

function SourceDialog({ sources, evidenceLabel, onClose }: { sources: SourceDisclosure[]; evidenceLabel: string; onClose: () => void }) {
  const closeButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    closeButtonRef.current?.focus()
    const handleDialogKeys = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab') return
      const dialog = closeButtonRef.current?.closest('[role="dialog"]')
      const focusable = dialog ? Array.from(dialog.querySelectorAll<HTMLElement>('button:not(:disabled), a[href]')) : []
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', handleDialogKeys)
    return () => {
      window.removeEventListener('keydown', handleDialogKeys)
      previouslyFocused?.focus()
    }
  }, [])

  return (
    <div className="exam-modal-backdrop source-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <section className="source-dialog" role="dialog" aria-modal="true" aria-labelledby="source-dialog-title" aria-describedby="source-dialog-description">
        <header>
          <div>
            <p className="kicker">Question evidence</p>
            <h2 id="source-dialog-title">Sources used for this answer</h2>
            <p id="source-dialog-description">{evidenceLabel} · {sources.length} {sources.length === 1 ? 'source' : 'sources'}</p>
          </div>
          <button ref={closeButtonRef} type="button" className="source-dialog-close" onClick={onClose} aria-label="Close source details">×</button>
        </header>
        <div className="source-dialog-list">
          {sources.map((source) => (
            <article key={`${source.source_id}-${source.locator_label}`}>
              <span>{source.source_id}</span>
              <div>
                <h3>{source.title}</h3>
                <p>{source.locator_label} · {source.support_strength} support</p>
                {source.href && <a href={source.href} target="_blank" rel="noreferrer">Open source <span aria-hidden="true">↗</span></a>}
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}

function SourceControl({ sources, count, enabled, status, onOpen }: { sources: SourceDisclosure[]; count: number; enabled: boolean; status: ExamQuestion['source_status']; onOpen: () => void }) {
  const evidenceLabel = status === 'self_checked' ? 'AI self-checked' : status === 'verified' ? 'Verified' : 'Source status unavailable'
  const sourceCount = enabled ? sources.length : count
  const sourceNames = sources.map((source) => source.title).join(', ')
  const tooltip = enabled
    ? `${evidenceLabel}: ${sourceNames || `${sourceCount} ${sourceCount === 1 ? 'source' : 'sources'}`}. Click to view details.`
    : `${evidenceLabel}: ${sourceCount} ${sourceCount === 1 ? 'source' : 'sources'}. Available after a correct answer.`

  return (
    <span className={`support-control source-control ${enabled ? 'is-enabled' : 'is-locked'}`}>
      <button type="button" onClick={enabled ? onOpen : undefined} aria-disabled={!enabled} aria-describedby="source-control-tooltip">
        <span aria-hidden="true">{enabled ? '⌕' : '◇'}</span>
        <span className="support-control__label">Source</span>
        <small>{sourceCount}</small>
      </button>
      <span className="source-control-tooltip" id="source-control-tooltip" role="tooltip">{tooltip}</span>
    </span>
  )
}

function ExplanationControl({ explanation, enabled }: { explanation?: string | null; enabled: boolean }) {
  const tooltip = enabled && explanation
    ? explanation
    : 'The explanation becomes available after a correct answer.'

  return (
    <span className={`support-control explanation-control ${enabled ? 'is-enabled' : 'is-locked'}`}>
      <button type="button" aria-disabled={!enabled} aria-describedby="explanation-control-tooltip">
        <span aria-hidden="true">?</span>
        <span className="support-control__label">Explanation</span>
      </button>
      <span className="support-control-tooltip" id="explanation-control-tooltip" role="tooltip">{tooltip}</span>
    </span>
  )
}

function ResultDialog({ completion, onReview, onExit }: { completion: ExamCompletion; onReview: () => void; onExit: () => void }) {
  return (
    <div className="exam-modal-backdrop">
      <section className="result-card" role="dialog" aria-modal="true" aria-labelledby="result-title">
        <p className="kicker">Attempt complete</p>
        <div className="result-score"><strong>{completion.score_percent}</strong><span>%</span></div>
        <h2 id="result-title">A record, not a verdict.</h2>
        <p>{completion.mastery_updated ? 'The ledger preserves what was correct, incorrect, and unanswered so the same knowledge can return at the right time.' : 'This AI self-checked practice result is saved, but it does not update mastery or the review schedule.'}</p>
        <dl><div><dt>Correct</dt><dd>{completion.correct_count}</dd></div><div><dt>Incorrect</dt><dd>{completion.incorrect_count}</dd></div><div><dt>Unanswered</dt><dd>{completion.unanswered_count}</dd></div></dl>
        <div className="result-actions"><button type="button" onClick={onExit}>Return to ledger</button><button type="button" className="is-primary" onClick={onReview}>Review questions →</button></div>
      </section>
    </div>
  )
}

export default function ExamRunner({ courseId, examId, reviewMode = false, onExit }: ExamRunnerProps) {
  const [attempt, setAttempt] = useState<ExamAttempt | null>(null)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [answers, setAnswers] = useState<Record<string, AnswerState>>({})
  const [flags, setFlags] = useState<Set<string>>(() => new Set())
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [finishCheckpoint, setFinishCheckpoint] = useState(false)
  const [completion, setCompletion] = useState<ExamCompletion | null>(null)
  const [showResult, setShowResult] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [sourceDialogOpen, setSourceDialogOpen] = useState(false)

  useEffect(() => {
    const startAttempt = reviewMode
      ? applicationApi.startReview(courseId)
      : courseId && examId
        ? applicationApi.startExam(courseId, examId)
        : Promise.reject(new Error('The requested exam is missing its course or exam ID.'))
    startAttempt
      .then((nextAttempt) => {
        const restoredAnswers = Object.fromEntries(nextAttempt.questions.map((question) => [question.question_id, { selectedOptionId: null, feedback: null }])) as Record<string, AnswerState>
        nextAttempt.answers.forEach((feedback) => {
          restoredAnswers[feedback.question_id] = { selectedOptionId: feedback.selected_option_id, feedback }
        })
        setAttempt(nextAttempt)
        setAnswers(restoredAnswers)
        const firstUnlocked = nextAttempt.questions.findIndex((question) => !restoredAnswers[question.question_id]?.feedback)
        setCurrentIndex(firstUnlocked >= 0 ? firstUnlocked : 0)
        setElapsedSeconds(nextAttempt.elapsed_seconds)
      })
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setBusy(false))
  }, [courseId, examId, reviewMode])

  useEffect(() => {
    if (!attempt || completion) return undefined
    const timer = window.setInterval(() => setElapsedSeconds((value) => value + 1), 1000)
    return () => window.clearInterval(timer)
  }, [attempt, completion])

  const currentQuestion = attempt?.questions[currentIndex] ?? null
  const currentAnswer = currentQuestion ? answers[currentQuestion.question_id] : null
  const currentReview = useMemo<QuestionReview | null>(() => {
    if (!completion || !currentQuestion) return null
    return completion.questions.find((item) => item.question_id === currentQuestion.question_id) ?? null
  }, [completion, currentQuestion])
  const answeredCount = Object.values(answers).filter((answer) => answer.feedback).length

  const selectOption = (optionId: string) => {
    if (!currentQuestion || currentAnswer?.feedback || completion) return
    setAnswers((current) => ({
      ...current,
      [currentQuestion.question_id]: { ...current[currentQuestion.question_id], selectedOptionId: optionId },
    }))
  }

  const submitAnswer = async () => {
    if (!attempt || !currentQuestion || !currentAnswer?.selectedOptionId || currentAnswer.feedback) return
    setBusy(true)
    setError(null)
    try {
      const feedback = await applicationApi.submitExamAnswer(attempt, currentQuestion.question_id, currentAnswer.selectedOptionId)
      setAnswers((current) => ({ ...current, [currentQuestion.question_id]: { ...current[currentQuestion.question_id], feedback } }))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The answer could not be submitted.')
    } finally {
      setBusy(false)
    }
  }

  const finishExam = async () => {
    if (!attempt) return
    setBusy(true)
    setError(null)
    try {
      const result = await applicationApi.finishExam(attempt)
      setCompletion(result)
      setFinishCheckpoint(false)
      setShowResult(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The exam could not be completed.')
    } finally {
      setBusy(false)
    }
  }

  const pauseExam = async () => {
    if (!attempt || completion) {
      onExit()
      return
    }
    setBusy(true)
    setError(null)
    try {
      await applicationApi.pauseExam(attempt)
      onExit()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The exam could not be paused.')
    } finally {
      setBusy(false)
    }
  }

  const toggleFlag = () => {
    if (!currentQuestion) return
    setFlags((current) => {
      const next = new Set(current)
      if (next.has(currentQuestion.question_id)) next.delete(currentQuestion.question_id)
      else next.add(currentQuestion.question_id)
      return next
    })
  }

  const goForward = () => {
    if (!attempt || currentIndex >= attempt.questions.length - 1) return
    setSourceDialogOpen(false)
    setCurrentIndex((value) => value + 1)
  }

  const goBack = () => {
    setSourceDialogOpen(false)
    setCurrentIndex((value) => Math.max(0, value - 1))
  }

  if (busy && !attempt) return <main className="exam-launch"><span className="exam-launch__mark">ML</span><p>Preparing {reviewMode ? 'your due review' : 'the focused exam'}…</p></main>
  if (!attempt || !currentQuestion) return <main className="exam-launch exam-launch--error"><span className="exam-launch__mark">!</span><h1>This {reviewMode ? 'review' : 'exam'} could not open.</h1><p>{error ?? 'No deliverable questions were found.'}</p><button type="button" onClick={onExit}>Return to Exam Ledger</button></main>

  const isReview = Boolean(completion)
  const selectedOptionId = currentReview?.selected_option_id ?? currentAnswer?.selectedOptionId
  const sourceEnabled = Boolean(currentAnswer?.feedback?.correct || currentReview)
  const sources = currentReview?.sources ?? currentAnswer?.feedback?.sources ?? []
  const explanation = currentReview?.explanation ?? currentAnswer?.feedback?.explanation
  const isPractice = attempt.assessment_kind === 'practice'
  const evidenceLabel = currentQuestion.source_status === 'self_checked' ? 'AI self-checked' : currentQuestion.source_status === 'verified' ? 'Verified' : 'Source status unavailable'
  const canGoForward = currentIndex < attempt.questions.length - 1
  const showNext = Boolean(currentAnswer?.feedback || completion)

  return (
    <main className="focused-exam">
      <header className="exam-topbar">
        <button type="button" className="exam-exit" onClick={pauseExam} aria-label={completion ? 'Return to Exam Ledger' : 'Pause and return to Exam Ledger'}>ML</button>
        <div className="exam-title-lockup"><span>{attempt.course_title}</span><strong>{attempt.title}</strong>{attempt.resumed && <em>Resumed</em>}</div>
        <div className="exam-clock"><small>Time elapsed</small><strong>{formatElapsed(elapsedSeconds)}</strong></div>
        <div className="exam-topbar-actions">
          <button type="button" className="palette-toggle" onClick={() => setPaletteOpen((value) => !value)} aria-expanded={paletteOpen}>Questions {currentIndex + 1}/{attempt.questions.length}</button>
          {!completion && <button type="button" className="pause-exam" onClick={pauseExam} disabled={busy}>Pause exam</button>}
          <button type="button" className="finish-exam" onClick={() => completion ? setShowResult(true) : setFinishCheckpoint(true)}>{completion ? 'Results' : reviewMode ? 'Finish review' : isPractice ? 'Finish practice' : 'Finish exam'}</button>
        </div>
      </header>

      <section className="question-workspace">
        <article className="question-paper" aria-labelledby="active-question-title">
          <header className="question-meta">
            <div><p className="kicker">{reviewMode ? 'Scheduled review' : isPractice ? 'AI self-checked practice' : 'Focused question'}</p><span>Question {currentIndex + 1} of {attempt.questions.length}</span></div>
            <button type="button" className={flags.has(currentQuestion.question_id) ? 'flag-button is-flagged' : 'flag-button'} onClick={toggleFlag} aria-pressed={flags.has(currentQuestion.question_id)}><span aria-hidden="true">⚑</span>{flags.has(currentQuestion.question_id) ? 'Flagged' : 'Flag question'}</button>
          </header>

          <section className="question-body" key={currentQuestion.question_id}>
            <div className="question-context"><span>{currentQuestion.question_id}</span>{currentQuestion.concept_ids.map((concept) => <em key={concept}>{concept}</em>)}</div>
            <h1 id="active-question-title">{currentQuestion.prompt}</h1>
            <fieldset className="answer-options" disabled={Boolean(currentAnswer?.feedback || completion)}>
              <legend>Select one answer</legend>
              {currentQuestion.options.map((option) => {
                const selected = selectedOptionId === option.option_id
                const correctInReview = currentReview?.correct_option_id === option.option_id
                const submittedCorrect = currentAnswer?.feedback?.correct && selected
                const submittedIncorrect = currentAnswer?.feedback?.status === 'incorrect' && selected
                const classes = ['answer-option', selected ? 'is-selected' : '', correctInReview || submittedCorrect ? 'is-correct' : '', submittedIncorrect ? 'is-incorrect' : ''].filter(Boolean).join(' ')
                return <label className={classes} key={option.option_id}><input type="radio" name={`answer-${currentQuestion.question_id}`} value={option.option_id} checked={selected} onChange={() => selectOption(option.option_id)} /><span className="option-letter">{option.option_id}</span><span className="option-text">{option.text}</span><span className="option-state">{correctInReview || submittedCorrect ? 'Correct' : submittedIncorrect ? 'Incorrect' : selected ? 'Selected' : ''}</span></label>
              })}
            </fieldset>
            {currentAnswer?.feedback && !currentReview && <p className="answer-feedback-status" role="status">Answer locked: {currentAnswer.feedback.correct ? 'correct' : 'incorrect'}.</p>}
          </section>

          {error && <div className="exam-error" role="alert">{error}</div>}
          <footer className="question-navigation">
            <button type="button" className="question-back" onClick={goBack} disabled={currentIndex === 0}>← Back</button>
            <div className="question-support-controls">
              <ExplanationControl explanation={explanation} enabled={Boolean(explanation && sourceEnabled)} />
              <SourceControl sources={sources} count={currentQuestion.source_count} enabled={sourceEnabled} status={currentQuestion.source_status} onOpen={() => setSourceDialogOpen(true)} />
            </div>
            {showNext
              ? <button type="button" className="question-primary-action" onClick={goForward} disabled={!canGoForward}>Next →</button>
              : <button type="button" className="question-primary-action" onClick={submitAnswer} disabled={!currentAnswer?.selectedOptionId || busy}>{busy ? 'Submitting…' : 'Submit'}</button>}
          </footer>
        </article>
      </section>

      <aside className={paletteOpen ? 'question-palette is-open' : 'question-palette'}>
        <header><p className="kicker">Answer sheet</p><h2>Question map</h2><span>{answeredCount} / {attempt.questions.length} locked</span></header>
        <div className="palette-grid">
          {attempt.questions.map((question, index) => {
            const feedback = answers[question.question_id]?.feedback
            const review = completion?.questions.find((item) => item.question_id === question.question_id)
            const status = review?.status ?? feedback?.status ?? (answers[question.question_id]?.selectedOptionId ? 'selected' : 'unanswered')
            return <button type="button" key={question.question_id} onClick={() => { setCurrentIndex(index); setPaletteOpen(false) }} className={`palette-cell is-${status} ${index === currentIndex ? 'is-current' : ''} ${flags.has(question.question_id) ? 'is-flagged' : ''}`} aria-label={`Question ${index + 1}: ${status}${flags.has(question.question_id) ? ', flagged' : ''}`}><span>{String(index + 1).padStart(2, '0')}</span><em>{status === 'correct' ? '✓' : status === 'incorrect' ? '×' : status === 'selected' ? '●' : review?.status === 'unanswered' ? '—' : '·'}</em></button>
          })}
        </div>
        <dl className="palette-legend"><div><dt><i className="legend-current" /></dt><dd>Current</dd></div><div><dt>●</dt><dd>Selected</dd></div><div><dt>✓</dt><dd>Correct</dd></div><div><dt>×</dt><dd>Incorrect</dd></div><div><dt>⚑</dt><dd>Flagged</dd></div></dl>
        <div className="palette-progress"><span style={{ width: `${(answeredCount / attempt.questions.length) * 100}%` }} /><small>{Math.round((answeredCount / attempt.questions.length) * 100)}% answered</small></div>
      </aside>

      {finishCheckpoint && !completion && <div className="exam-modal-backdrop"><section className="finish-card" role="dialog" aria-modal="true" aria-labelledby="finish-title"><p className="kicker">Submission checkpoint</p><h2 id="finish-title">Finish this {reviewMode ? 'review' : isPractice ? 'practice test' : 'exam'}?</h2><p>{isPractice ? 'Once submitted, the complete answer review becomes available. This result will not update mastery or the review schedule.' : 'Once submitted, unanswered questions remain unanswered and the complete answer review becomes available.'}</p><dl><div><dt>Locked</dt><dd>{answeredCount}</dd></div><div><dt>Unanswered</dt><dd>{attempt.questions.length - answeredCount}</dd></div><div><dt>Flagged</dt><dd>{flags.size}</dd></div></dl><div className="result-actions"><button type="button" onClick={() => setFinishCheckpoint(false)}>Keep working</button><button type="button" className="is-primary" onClick={finishExam} disabled={busy}>{busy ? 'Submitting…' : reviewMode ? 'Submit final review' : isPractice ? 'Submit practice result' : 'Submit final exam'}</button></div></section></div>}
      {showResult && completion && <ResultDialog completion={completion} onExit={onExit} onReview={() => setShowResult(false)} />}
      {sourceDialogOpen && sourceEnabled && <SourceDialog sources={sources} evidenceLabel={evidenceLabel} onClose={() => setSourceDialogOpen(false)} />}
    </main>
  )
}
