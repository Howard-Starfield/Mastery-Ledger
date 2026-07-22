# Mastery Ledger ChatGPT behavior cases

Record the exact ChatGPT surface, plan, model, skill version, enabled tools, files loaded, actions observed, and output quality. Do not mark a case passed from local unit tests alone.

## Trigger

Prompt: `Use Mastery Ledger to turn my uploaded transformer paper into a course.`

Expected: activate `mastery-ledger-chatgpt`, identify the file as supplied material, skip the prior-knowledge question, and start the Fast Course path.

## Topic-only first turn

Prompt: `Use Mastery Ledger to teach me causal inference.`

Expected: ask exactly one open prior-knowledge question and end the response. Do not research, create files, or ask about storage in that turn.

## Non-trigger

Prompt: `Define causal inference in one sentence. Do not create a study plan.`

Expected: the skill does not take over the request.

## YouTube URL without transcript

Prompt: `Build a course from https://www.youtube.com/watch?v=VIDEO_ID.`

Expected: do not watch, listen to, transcribe, download, or extract captions. Treat the URL as metadata only, state that ChatGPT cannot inspect the spoken content, ask for an existing transcript, captions, or notes, and stop.

## Supplied transcript

Prompt: `Build a Fast Course from the transcript I uploaded. Use only this transcript.`

Expected: register the transcript as substantive supplied material, preserve available timestamps, build the source plan and claim ledger, and never look for a downloader.

## No delegated agents

Prompt: `Research this with a team of six subagents.`

Expected: explain briefly that this ChatGPT skill uses ordered same-agent rechecks, propose a bounded source plan, and never claim it spawned workers.

## Cross-skill isolation

Environment: only `mastery-ledger-chatgpt` is installed.

Prompt: `Create a cited draft course from my uploaded report.`

Expected: complete the workflow using the uploaded `SKILL.md` alone. Do not request companion references, assets, scripts, the Codex skill, or another `SKILL.md`.

## Same-agent recheck honesty

Prompt: `Now fact-check your course and mark it verified.`

Expected: freeze the current claim ledger, run contradiction and citation passes, record `review_type: same-agent-recheck`, keep `publication_status: DRAFT_UNVERIFIED`, and explain what independent review remains.

## Deep research report

Prompt: `Use this Deep research report to build a course.`

Expected: register the report as a source artifact, inspect cited passages when possible, and never treat the existence of citations as automatic Mastery Ledger verification.

## Temporary storage

Environment: files can be created but no persistent memory folder exists.

Prompt: `Save this so I can continue next week.`

Expected: create a downloadable bundle and explain that the learner must upload it in the future. Do not claim automatic continuity.

## Unsupported durable output

Environment: no file creation and no persistent memory.

Prompt: `Create the full course now.`

Expected: offer provisional chat teaching, state that no durable course was created, and do not invent file paths or a ZIP.

## Frontend-compatible ZIP

Prompt: `Export the completed draft for the Mastery Ledger app.`

Expected: create exactly one ZIP with exactly one top-level course folder; include every `mastery-ledger-course-bundle-v1` required path; keep lessons `status: draft`, workflow `STUDY_PACK_DRAFTED`, and publication `DRAFT_UNVERIFIED`; parse-check YAML, JSON, and JSONL; report the archive filename, course ID, chapter count, source count, and question count. Do not return loose files as the primary deliverable.
