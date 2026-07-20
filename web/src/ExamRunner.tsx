import { useEffect, useMemo, useState } from 'react'

import {
  applicationApi,
  type ExamAttempt,
  type ExamCompletion,
  type QuestionFeedback,
  type QuestionReview,
  type SourceDisclosure,
} from './api'

type ExamRunnerProps = {
  courseId: string
  examId: string
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

function SourcesDisclosure({ sources, count, enabled }: { sources: SourceDisclosure[]; count: number; enabled: boolean }) {
  if (!enabled) {
    return (
      <div className="question-sources is-disabled" aria-disabled="true">
        <div><span className="source-lock" aria-hidden="true">◇</span><strong>Sources used in this question</strong></div>
        <span>Verified · {count} {count === 1 ? 'source' : 'sources'} · available after a correct answer</span>
      </div>
    )
  }

  return (
    <details className="question-sources">
      <summary>
        <div><span className="source-lock" aria-hidden="true">✓</span><strong>Sources used in this question</strong></div>
        <span>Verified · {sources.length} {sources.length === 1 ? 'source' : 'sources'} · open deliberately</span>
      </summary>
      <div className="source-disclosure-list">
        {sources.map((source) => (
          <article key={`${source.source_id}-${source.locator_label}`}>
            <span>{source.source_id}</span>
            <div><strong>{source.title}</strong><p>{source.locator_label} · {source.support_strength} support</p></div>
            {source.href && <a href={source.href} target="_blank" rel="noreferrer">Open source <span aria-hidden="true">↗</span></a>}
          </article>
        ))}
      </div>
    </details>
  )
}

function ResultDialog({ completion, onReview, onExit }: { completion: ExamCompletion; onReview: () => void; onExit: () => void }) {
  return (
    <div className="exam-modal-backdrop">
      <section className="result-card" role="dialog" aria-modal="true" aria-labelledby="result-title">
        <p className="kicker">Attempt complete</p>
        <div className="result-score"><strong>{completion.score_percent}</strong><span>%</span></div>
        <h2 id="result-title">A record, not a verdict.</h2>
        <p>The ledger preserves what was correct, incorrect, and unanswered so the same knowledge can return at the right time.</p>
        <dl><div><dt>Correct</dt><dd>{completion.correct_count}</dd></div><div><dt>Incorrect</dt><dd>{completion.incorrect_count}</dd></div><div><dt>Unanswered</dt><dd>{completion.unanswered_count}</dd></div></dl>
        <div className="result-actions"><button type="button" onClick={onExit}>Return to ledger</button><button type="button" className="is-primary" onClick={onReview}>Review questions →</button></div>
      </section>
    </div>
  )
}

export default function ExamRunner({ courseId, examId, onExit }: ExamRunnerProps) {
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

  useEffect(() => {
    applicationApi
      .startExam(courseId, examId)
      .then((nextAttempt) => {
        setAttempt(nextAttempt)
        setAnswers(Object.fromEntries(nextAttempt.questions.map((question) => [question.question_id, { selectedOptionId: null, feedback: null }])))
      })
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setBusy(false))
  }, [courseId, examId])

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

  const toggleFlag = () => {
    if (!currentQuestion) return
    setFlags((current) => {
      const next = new Set(current)
      if (next.has(currentQuestion.question_id)) next.delete(currentQuestion.question_id)
      else next.add(currentQuestion.question_id)
      return next
    })
  }

  if (busy && !attempt) return <main className="exam-launch"><span className="exam-launch__mark">ML</span><p>Preparing the focused exam…</p></main>
  if (!attempt || !currentQuestion) return <main className="exam-launch exam-launch--error"><span className="exam-launch__mark">!</span><h1>This exam could not open.</h1><p>{error ?? 'No deliverable questions were found.'}</p><button type="button" onClick={onExit}>Return to Exam Ledger</button></main>

  const isReview = Boolean(completion)
  const selectedOptionId = currentReview?.selected_option_id ?? currentAnswer?.selectedOptionId
  const sourceEnabled = Boolean(currentAnswer?.feedback?.correct || currentReview)
  const sources = currentReview?.sources ?? currentAnswer?.feedback?.sources ?? []
  const explanation = currentReview?.explanation ?? currentAnswer?.feedback?.explanation

  return (
    <main className="focused-exam">
      <header className="exam-topbar">
        <button type="button" className="exam-exit" onClick={onExit} aria-label="Return to Exam Ledger">ML</button>
        <div className="exam-title-lockup"><span>{attempt.course_title}</span><strong>{attempt.title}</strong></div>
        <div className="exam-clock"><small>Time elapsed</small><strong>{formatElapsed(elapsedSeconds)}</strong></div>
        <button type="button" className="palette-toggle" onClick={() => setPaletteOpen((value) => !value)} aria-expanded={paletteOpen}>Questions {currentIndex + 1}/{attempt.questions.length}</button>
        <button type="button" className="finish-exam" onClick={() => completion ? setShowResult(true) : setFinishCheckpoint(true)}>{completion ? 'Results' : 'Finish exam'}</button>
      </header>

      <section className="question-workspace">
        <article className="question-paper" aria-labelledby="active-question-title">
          <header className="question-meta">
            <div><p className="kicker">Focused question</p><span>Question {currentIndex + 1} of {attempt.questions.length}</span></div>
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
            {!currentAnswer?.feedback && !completion && <button type="button" className="submit-answer" onClick={submitAnswer} disabled={!currentAnswer?.selectedOptionId || busy}>{busy ? 'Locking answer…' : 'Submit answer'}</button>}

            {currentAnswer?.feedback && !currentReview && (
              <section className={currentAnswer.feedback.correct ? 'answer-feedback is-correct' : 'answer-feedback is-incorrect'} role="status">
                <span className="feedback-mark" aria-hidden="true">{currentAnswer.feedback.correct ? '✓' : '×'}</span>
                <div><strong>{currentAnswer.feedback.correct ? 'Correct.' : 'Incorrect.'}</strong>{currentAnswer.feedback.correct ? <p>{currentAnswer.feedback.explanation}</p> : <p>This answer is locked. No hint, explanation, source, or correct option is shown during the active attempt.</p>}</div>
              </section>
            )}
            {currentReview && <section className={`answer-feedback review-${currentReview.status}`}><span className="feedback-mark">{currentReview.status === 'correct' ? '✓' : currentReview.status === 'incorrect' ? '×' : '—'}</span><div><strong>{currentReview.status === 'unanswered' ? 'Unanswered.' : `${currentReview.status[0].toUpperCase()}${currentReview.status.slice(1)}.`}</strong><p>{explanation}</p></div></section>}
          </section>

          <div key={`${currentQuestion.question_id}-${sourceEnabled ? 'enabled' : 'locked'}`}><SourcesDisclosure sources={sources} count={currentQuestion.source_count} enabled={sourceEnabled} /></div>

          {error && <div className="exam-error" role="alert">{error}</div>}
          <footer className="question-navigation">
            <button type="button" onClick={() => setCurrentIndex((value) => Math.max(0, value - 1))} disabled={currentIndex === 0}>← Previous</button>
            <span>{isReview ? 'Review mode · sources available' : currentAnswer?.feedback ? 'Answer locked' : currentAnswer?.selectedOptionId ? 'Answer selected' : 'Unanswered'}</span>
            <button type="button" onClick={() => setCurrentIndex((value) => Math.min(attempt.questions.length - 1, value + 1))} disabled={currentIndex === attempt.questions.length - 1}>Next →</button>
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

      {finishCheckpoint && !completion && <div className="exam-modal-backdrop"><section className="finish-card" role="dialog" aria-modal="true" aria-labelledby="finish-title"><p className="kicker">Submission checkpoint</p><h2 id="finish-title">Finish this exam?</h2><p>Once submitted, unanswered questions remain unanswered and the complete answer review becomes available.</p><dl><div><dt>Locked</dt><dd>{answeredCount}</dd></div><div><dt>Unanswered</dt><dd>{attempt.questions.length - answeredCount}</dd></div><div><dt>Flagged</dt><dd>{flags.size}</dd></div></dl><div className="result-actions"><button type="button" onClick={() => setFinishCheckpoint(false)}>Keep working</button><button type="button" className="is-primary" onClick={finishExam} disabled={busy}>{busy ? 'Submitting…' : 'Submit final exam'}</button></div></section></div>}
      {showResult && completion && <ResultDialog completion={completion} onExit={onExit} onReview={() => setShowResult(false)} />}
    </main>
  )
}
