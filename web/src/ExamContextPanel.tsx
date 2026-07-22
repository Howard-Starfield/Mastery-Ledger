import { FileCheck2, RotateCcw, Search } from 'lucide-react'

import type { DashboardResult } from './api'

type ExamContextPanelProps = {
  data: DashboardResult | null
  query: string
  courseId: string
  evidence: string
  onQueryChange: (query: string) => void
  onCourseIdChange: (courseId: string) => void
  onEvidenceChange: (evidence: string) => void
  onStartReview: () => void
}

export default function ExamContextPanel({
  data,
  query,
  courseId,
  evidence,
  onQueryChange,
  onCourseIdChange,
  onEvidenceChange,
  onStartReview,
}: ExamContextPanelProps) {
  return (
    <section className="exam-context" aria-label="Exam filters">
      <header>
        <div>
          <p>Exams</p>
          <strong>Assessment register</strong>
        </div>
        <span>{data?.ready_exams.length ?? 0}</span>
      </header>

      <label className="context-search">
        <Search aria-hidden="true" />
        <input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Find an exam"
          aria-label="Search ready exams"
        />
        <span />
      </label>

      <label className="exam-context__field">
        <span>Course</span>
        <select value={courseId} onChange={(event) => onCourseIdChange(event.target.value)}>
          <option value="all">All courses</option>
          {data?.recent_courses.map((item) => (
            <option key={item.course_id} value={item.course_id}>{item.title}</option>
          ))}
        </select>
      </label>

      <fieldset className="exam-context__evidence">
        <legend>Evidence</legend>
        {[
          ['all', 'Any'],
          ['verified', 'Verified'],
          ['ready', 'Ready'],
          ['review_needed', 'Needs review'],
        ].map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={evidence === value ? 'is-active' : ''}
            aria-pressed={evidence === value}
            onClick={() => onEvidenceChange(value)}
          >
            {label}
          </button>
        ))}
      </fieldset>

      <div className="exam-context__review">
        <div>
          <RotateCcw aria-hidden="true" />
          <span><strong>{data?.due_now ?? 0}</strong> due now</span>
        </div>
        <button type="button" onClick={onStartReview} disabled={!data?.due_now}>
          Start review
        </button>
      </div>

      <div className="exam-context__note">
        <FileCheck2 aria-hidden="true" />
        <p>Only validated exam sets appear here. Course authoring remains outside the application.</p>
      </div>
    </section>
  )
}
