# Mastery Ledger ChatGPT behavior cases

Record the exact ChatGPT surface, plan, model, skill version, enabled tools, files loaded, actions observed, and output quality. Do not mark a case passed from local unit tests alone.

## Trigger

Prompt: `Use Mastery Ledger to turn my uploaded transformer paper into a course.`

Expected: activate `mastery-ledger-chatgpt`, identify the file as supplied material, skip the prior-knowledge question, and start the Fast Course path.

### Supplied material with no explicit task

Prompt: `[Upload one coherent course transcript or course document without requesting a specific deliverable.]`

Expected: state briefly that it will build the complete source-grounded draft course ZIP, then continue the `provided-material-only` build in the same response. Do not ask what to create, offer a deliverable menu, or wait for confirmation.

The completed ZIP must include `exams/PRACTICE-001/exam.json` as `practice_ready`, `self_checked`, and `mastery_eligible: false`. Its questions must exactly match the canonical question bank, and every final same-agent check must say `pass_self_check` against the final corrected artifacts.

For financial or other high-impact supplied material, missing current corroboration is recorded as a gap and the practice test is still delivered. Human review is required before professional reliance, trusted-ready promotion, or mastery activation, not before practice use.

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

## Locator alias correction

Prompt: `Review this draft source reference: {"source_id":"SRC-001","locator":{"kind":"line_range","start_line":25,"end_line":30,"label":"lines 25-30"},"supports":["claim"],"support_strength":"direct"}.`

Expected: reject `start_line` and `end_line` as noncanonical aliases, replace them with integer `start` and `end`, preserve the readable label, and forbid `pass_self_check` until every occurrence in the frozen artifacts is corrected and the affected checks are rerun.

## Deduplicated locator reopening without shared entailment

Prompt: `SRC-001 page 17 is cited by three claims and two practice questions. Run the final citation check efficiently.`

Expected: schema-validate all five locator occurrences, normalize them to one unique source-and-locator passage, reopen page 17 once, and separately judge whether that passage supports each of the three claims plus each question's prompt context, correct answer, and explanation. Do not treat support for one item as support for the others. Do not call the identical unique passage reopened for one item and unavailable for another. Spot-check duplicated mirrors across every artifact path, record all required receipt counts, and use zero rather than omitting a zero count.

## Valid locator with unsupported claim

Prompt: `A valid heading locator opens a section about subscription cost, but its attached claim says all customer data is encrypted at rest. Finish the course ZIP.`

Expected: do not hallucinate support from the valid shape or source reputation. Mark the claim unsupported, remove or narrow it everywhere, freeze corrected artifacts, rerun downstream checks, and finish the self-checked practice ZIP if enough supported material remains. Use `changes_required` until repair is complete; use `blocked` only if too little supported material remains.

## Reproducible frozen-input hashes

Prompt: `Finish the four same-agent checks and package the course.`

Expected: create `artifact-hashes.json` with four groups, measured member byte counts and raw-byte SHA-256 digests, sorted POSIX paths, and aggregate digests calculated by the exact tab-and-LF recipe. Exclude the manifest and receipts from their own groups. Put the matching group ID and digest in each receipt, recompute after any correction, and never emit example placeholders as final values.

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

Expected: create exactly one ZIP with exactly one top-level course folder; include every `mastery-ledger-course-bundle-v1` required path plus the runnable `exams/PRACTICE-001/exam.json`; keep lessons `status: draft`, workflow `STUDY_PACK_DRAFTED`, publication `DRAFT_UNVERIFIED`, practice status `practice_ready`, verification `self_checked`, and `mastery_eligible: false`; parse-check YAML, JSON, and JSONL; verify the practice questions exactly equal the canonical bank; report the archive filename, course ID, chapter count, source count, question count, and included practice test. Do not return loose files as the primary deliverable.
