# Mastery Ledger design decisions

This is the canonical architecture record for the current repository. Superseded designs remain available in Git history; they are intentionally absent here so implementation agents do not treat retired application ingestion or wiki interfaces as active requirements.

## Product boundary

Mastery Ledger has two cooperating but independently useful parts:

| Part | Owns | Must not own |
| --- | --- | --- |
| Codex skill | learning intake, source acquisition, extraction, transcription, research, evidence review, course compilation, wiki files, question banks, and ready-exam generation | exam attempts, learner scheduling, application registry |
| Offline application | workspace registration, read-only playback of published lessons, ready-exam discovery and playback, attempts, progress, due reviews, and review-curve settings | source ingestion, research, course or lesson writing, wiki authoring, question generation, or mutation of generated exams |

The application may be installed after a course is generated. A missing application never downgrades course building to provisional chat.

## First-turn learning intake

For a new topic-only course request:

1. Ask exactly one open prior-knowledge question.
2. End the first turn without browsing, setup, tutoring, or file writes.
3. Use the response as calibration question 1 and as a provisional learner-model signal, never as factual evidence.
4. Continue the durable workflow after the learner responds.

When the first request contains an attachment, local path, URL, pasted source excerpt, or identified existing source, skip the open question and begin operational intake. Do not ask whether the learner has a source that is already present. Allow later sources to join the same approved course.

## Workspace ownership

- Reuse the application's registered writable workspace when available and learner-approved.
- Otherwise ask the learner for one absolute workspace path before the first durable write.
- Never store courses, source media, models, logs, or generated artifacts inside the installed skill.
- The skill writes only within the approved workspace and its course-specific `.work/` boundary.
- The application scans the workspace for generated courses but does not edit their knowledge or exam definitions.

## Course artifact lifecycle

Initialize structural shells early, then publish substantive material only after evidence approval:

`INTAKE -> SCOPED -> SOURCES_READY -> CORPUS_MAPPED -> TASKS_PLANNED -> EVIDENCE_SUBMITTED -> EVIDENCE_VERIFIED -> EVIDENCE_APPROVED -> STUDY_PACK_DRAFTED -> STUDY_PACK_VALIDATED -> LEARNING_ACTIVE`

The deterministic reconciliation script owns state transitions. Agents never edit `workflow_state` by hand.

Durable course artifacts include:

```text
course/
  study.yaml
  source-manifest.yaml
  source/
    SRC-NNN.md
    media/SRC-NNN/
  evidence/
  lessons/
  wiki/
  questions/
  exams/
  attempts/
  progress/
  logs/events.jsonl
  .work/
    ingestion/
    runs/
```

Workers write only under their assigned `.work/runs/<run-id>/tasks/<task-id>/` directory. The main agent alone promotes validated results.

## Source and media processing

- Store extracted knowledge as Markdown directly under `source/`.
- Store binaries, original documents, captions, transcripts, and media under `source/media/<source-id>/`.
- Require an explicit rights basis before remote media acquisition.
- Prefer human captions, then permitted platform captions, then labeled automatic captions, then optional local ASR.
- Invoke packaged skill scripts through absolute paths resolved from `SKILL_ROOT`.
- Use the Python `yt-dlp` package; do not vendor `youtube-dl`, `yt-dlp`, FFmpeg, or model binaries into the skill.
- Detect dependencies before work. Never silently install or update them during a course run.
- Keep retries, manifests, recovery details, and observable events under `.work/ingestion/<job-id>/`; the application has no ingestion service or job queue.

## Research and worker ordering

Publishable researched courses require independent workers:

```text
corpus map
  -> bounded research/source extraction wave
  -> contradiction review
  -> final citation verification
  -> assessment generation
  -> independent assessment validation
  -> main-agent promotion
```

Compile each worker's context from the versioned role profile and required contracts. Validate the run plan before dispatch and start only `ready_task_ids`. Never start contradiction review before its research wave, citation verification before contradiction review, or assessment validation before question generation.

If independent workers are unavailable, preserve provisional material under `.work/`, record `DRAFT_UNVERIFIED`, and do not activate mastery or mark a researched exam ready.

## Evidence and logging

- Use canonical `source-ref-v1` objects with precise locators.
- Keep contradictions, gaps, rejected claims, and limitations visible.
- Logs contain observable actions, decisions, evidence paths, statuses, and short justifications—not hidden chain-of-thought.
- Workers emit task-local event shards. The main agent validates and merges them into `logs/events.jsonl`.
- Learner-facing pages may keep citations collapsed, but durable source references remain available for verification.

## Lesson, wiki, and assessment products

- Lessons and wiki pages are evidence-approved learning material, not raw web extracts.
- Raw or faithful extracted knowledge stays under `source/`.
- The planned Markdown wiki catalog uses a global `index.md` and per-course `wiki/index.md`; migration from the current portable wiki format remains a separate implementation slice.
- Each core chapter contains a readable lesson and exactly ten assessment items: eight concise standalone multiple-choice questions and two short passage-based multiple-choice questions.
- The application Study tab lists only `learning_active` courses and reads chapter paths from the validated `question-bank-v2` catalog.
- Study lessons have `Read` and `Raw` views. Read mode renders Markdown and embedded raw HTML inside a sandboxed document; Raw mode shows the exact stored source as inert text. Both views are read-only, and active content cannot run in the application shell.
- Every published question has four options, one answer key, a supported explanation, misconception-based distractor rationales, objective and concept IDs, and canonical source references.
- Only independently validated questions enter a ready exam.

## Offline exam behavior

- The application reads a ready `exam.json`; it never rewrites it.
- A ready exam is replaceable generated input, not a versioned application record. Rebuilding the same `exam_id` atomically replaces its file, and the next dashboard scan and new attempt use the replacement.
- The application does not compare a ready exam with `question-bank.json`, maintain a drift ledger, migrate exam versions, or block a valid replacement. Those are skill-owned build artifacts, and the ready `exam.json` is the application's delivery boundary.
- Completed attempt files remain historical learner records. An in-progress attempt resumes only while its exact exam content is unchanged; otherwise starting that exam creates a fresh attempt from the current file without mutating the older attempt.
- The first response omits answer keys and explanations.
- A wrong answer locks without a hint.
- A correct answer unlocks the explanation.
- `Sources used in this question` stays collapsed after both correct and incorrect answers; detailed sources become available after a correct answer or in final review.
- Attempts, progress, review queues, and curve assignments are separate learner-state files.
- Generated exams and source manifests must remain byte-identical after practice.

The default review intervals are:

`1, 3, 7, 14, 28, 56, 112, 224, 448, 896, 1792, 3584` days.

This is a transparent provisional schedule, not FSRS and not reinforcement learning.

## Application storage

SQLite contains only application-local registration and settings:

- schema metadata;
- registered workspaces;
- language, accessibility, and review-curve settings.

There is no application ingestion job table. Course content and learner records remain portable workspace files.

## Runtime and release contract

- `mastery-ledger doctor --json --skill-version 0.1.0` is read-only.
- `doctor-v2` reports only application readiness and the capabilities `exam_player`, `learner_state`, and `review_scheduler`.
- Course building can proceed when the launcher is absent, incompatible, unconfigured, or unable to access its registered workspace.
- Application playback requires a ready compatible application and workspace.
- `onboard` and `repair` launch only for application learning or an explicit application-setup request.
- Application and skill versions remain coordinated in the repository, compatibility asset, locks, tests, and release artifacts.

## Explicitly retired surfaces

Do not reintroduce these without a new approved decision:

- application Source Inbox;
- application ingestion workers or source job queue;
- application Knowledge Wiki or Evidence Activity screens; the read-only Study lesson reader is not a wiki authoring or evidence interface;
- source-processing or privacy mode in application onboarding;
- application-owned PDF, DOCX, video, subtitle, or ASR extraction;
- the claim that the skill is merely an application adapter;
- a forced choice between an untracked beginner lesson and a structured course.
