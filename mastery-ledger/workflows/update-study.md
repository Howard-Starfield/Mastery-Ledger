# Update study

## Purpose

Refresh the current course artifacts when a source, goal, or learner request changes. Keep the workflow evidence-grounded, but do not build a question-bank drift or migration system.

## Workflow

1. Record the requested change and identify the sources or concepts it affects.
2. Run the normal research, contradiction, and citation gates for new or changed factual material.
3. Regenerate the affected `index.md` entries, lessons, and canonical `questions/question-bank.json`.
4. Rebuild each affected ready exam with `scripts/build_exam.py`. Reusing an `exam_id` atomically replaces that ready exam; a new exam ID is needed only when the learner wants both sets available.
5. Run `scripts/validate_study_pack.py <course-root> --publication`.
6. Summarize the learner-visible changes.

Do not create a drift ledger, dependency graph, stale-exam state, bank-version migration, or application-side reconciliation job. The offline application reads the latest valid `exam.json` on its next scan.

## Learner history

- Never rewrite completed attempt files.
- Do not recalculate historical scores or review history merely because a generated question changed.
- An in-progress attempt resumes only while its exact ready exam is unchanged. If that exam was replaced, the next start uses the replacement and leaves the older partial attempt untouched.
- Preserve a question ID when its tested meaning is unchanged. Use a new ID when it now tests a different claim or concept; this is ordinary authoring hygiene, not version governance.

## Destructive source changes

Ask before deleting a user-provided source or learner-authored material. Updating generated lessons, questions, and ready exams within the approved course scope does not require a separate migration approval.

## Exit gate

The update is complete when the changed material is evidence-approved, the current question bank and affected exams are rebuilt, publication validation passes, and the learner receives a concise change summary.
