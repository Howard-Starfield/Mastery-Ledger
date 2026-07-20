# Mastery Ledger design decisions

This document records product and architecture decisions for the `mastery-ledger` skill and application. It stays outside the packaged skill so that the skill contains only runtime instructions, reusable references, scripts, and output assets.

## Decision status

| ID | Topic | Status |
| --- | --- | --- |
| 1 | CPA-inspired HTML mock exam | Core behavior and screenshot direction approved; local-app details proposed |
| 2 | Durable Markdown question bank and spaced repetition | Examined; proposed design below |
| 3 | Human-verifiable activity and source history | Accepted; design recorded below |
| 4 | Machine-readable action log and JSON-versus-Markdown choice | Accepted; implementation guardrails refined below |
| 5 | Source-candidate ledger and recurring source intake | Queued |
| 6 | Sub-agent topology and role instructions | Accepted; reception-desk and dependency-gated design recorded below |
| 7 | Course source layout, media, subtitles, and transcription | Revised; Python-package runtime and optional media-export design proposed below |
| 8 | Runtime logs versus packaged assets | Accepted with Item 4 |
| 9 | Codex-compatible `SKILL.md` frontmatter | Accepted and implemented |
| 10 | Standalone product boundary and installation | Accepted; standalone app plus optional skill adapter |
| 11 | Product, skill, package, and command naming | Accepted: Mastery Ledger |
| 12 | Application stack and onboarding ownership | Accepted; FastAPI, SQLite, React, TypeScript, Vite, and application-owned onboarding |
| 13 | Codex skill distribution | Accepted; direct GitHub install through the open skills CLI plus Codex-native fallback |

## Proposed course layout

This is provisional until decisions 2, 4, 5, 7, and 8 are examined.

```text
<workspace>/mastery-ledger-courses/<course-id>/
  course.yaml
  source/
    *.md
    media/
      <source-id>/
  questions/
    question-bank.json
    question-bank.md
  exams/
  attempts/
  progress/
  logs/
    events.jsonl
    runs/
  orchestration/
```

The packaged skill contains reusable templates, schemas, scripts, and workflow instructions. Generated courses contain sources, exams, attempts, progress, and logs. Never place generated course content inside the installed skill.

## First-run workspace and registry

On the first operational learning request, run the application doctor. When no valid workspace has been configured, launch application-owned onboarding. The application asks where to create the Mastery Ledger workspace and includes the mandatory source invitation without duplicating those questions in chat:

> Where should I create your Mastery Ledger workspace? Suggested: `<current-workspace>/mastery-ledger-courses`. You can provide another absolute folder path.
>
> Do you have any documents, links, websites, videos, audio, subtitles, or existing course material you want included or excluded?

If the first user message already supplies a workspace path or source, pass it to onboarding as a proposed hint; the application must still display and validate a path before persistence. If a prior workspace registry exists and the directory is accessible, reuse it and state the selected workspace in the scope card. Launch workspace repair only when the configured path is unavailable, unwritable, or the user asks to change it.

Persist the preference in a small per-user runtime registry, not in the installed skill:

```json
{
  "schema_version": "1.0",
  "active_workspace_id": "WS-001",
  "workspaces": [
    {
      "workspace_id": "WS-001",
      "name": "Primary learning workspace",
      "root": "D:/Learning/mastery-ledger-courses",
      "created_at": "2026-07-19T18:00:00Z",
      "last_used_at": "2026-07-19T18:00:00Z"
    }
  ]
}
```

Use the platform's per-user application configuration directory. The resolver script owns its exact OS-specific location and prints it when asked. Store no source contents, questions, credentials, or learner answers in this registry.

Support multiple registered workspaces. The web app should show the active workspace name and path, allow switching or registering another folder, and never silently migrate courses between workspaces.

## 1. CPA-inspired HTML mock exam

### Product intent

Create a focused, professional exam interface inspired by computer-based CPA testing conventions without claiming to reproduce or affiliate with the official CPA exam. The LLM creates a structured exam from approved evidence; deterministic code renders that exam into a prebuilt HTML template.

### Recommended architecture

Keep presentation code fixed and keep LLM-generated content structured:

```text
mastery-ledger/
  assets/
    exam-template/
      index.html
      exam.css
      exam.js
  scripts/
    build_exam.py
    validate_exam.py
```

The primary interface should be a bundled local web app served by `serve_exam.py`. It loads a validated exam JSON file from an explicit course root. An optional `build_exam.py` export should produce a self-contained HTML file for portable offline use. It should embed validated exam data in a non-executable JSON script element rather than letting the LLM write JavaScript or interpolate arbitrary HTML.

```html
<script id="exam-data" type="application/json">
  {"exam_id":"EXAM-001","questions":[]}
</script>
```

The fixed JavaScript reads the data and controls navigation, scoring, feedback, timing, accessibility, and result export. The LLM never edits the application logic.

### Local web-app boundary

Package the reusable interface with the skill:

```text
mastery-ledger/
  assets/
    exam-app/
      index.html
      exam.css
      exam.js
  scripts/
    serve_exam.py
    build_exam.py
    validate_exam.py
```

Launch the managed experience with an explicit course and exam path:

```text
python scripts/serve_exam.py \
  --course-root <absolute-course-path> \
  --exam exams/EXAM-001/exam.json
```

Bind only to `127.0.0.1` on an available port, generate a per-launch session token, and open the default browser. The server may read and write only within the resolved course root.

The web app should also offer `Load exam file` for a validated external `exam.json`. A browser-selected external file can be taken in portable mode, but its attempt must be exported unless the server has an explicitly registered writable course root. Do not pretend a normal browser file picker grants ongoing permission to write beside the selected file.

The normal skill workflow should launch the exact exam automatically; the learner should not need to browse for a file the skill just created. The manual loader is a recovery and portability feature.

### Landing-page contract

The local web app opens on a workspace dashboard when no specific exam is passed. It reads only registered course manifests and shows:

**Implementation status:** the `dashboard-v1` API and React Exam Ledger landing page now discover registered `course.yaml` or `study.yaml` manifests, ready exam definitions, question banks, source manifests, and review queues. Search, course filtering, the fixed-height exam register, recent-course summaries, the complete curve rail, responsive expansion, and the exam detail sheet are implemented. Ready exams launch into Focused Question delivery with server-side answer checking, one locked submission per question, gated explanations and citations, final scoring, and review mode. Attempts are currently held in application memory; durable attempt artifacts, starting scheduled reviews, and editing the curve from settings remain later slices.

- **Due now:** questions whose `next_due_at` is due or overdue, grouped by course.
- **Ready exams:** every LLM-generated exam set with `status: ready`, question count, estimated duration, concepts, and creation time. Render this as a fixed-height, internally scrollable ledger with a sticky header, visible scrollbar, total count, search, course/status filters, and newest-first default sorting. Do not hide older ready exams behind a small card limit or a required `View all` action. Use windowing/virtualization when the collection is large. Preserve keyboard focus and announce the result count after filtering. On narrow screens, expand the ledger into its own page or sheet instead of creating a cramped nested scroll area.
- **Continue:** resumable in-progress attempts.
- **Recent courses:** course cards with source readiness, question count, last score, and next review.
- **Ownership Curve:** the learner's current distribution across interval stages and the next milestone.
- **Workspace control:** active workspace path, change/switch action, rescan action, and clear error state when a folder is unavailable.

When the LLM creates or validates an exam, write its manifest atomically under the course. The dashboard discovers it by manifest status; the LLM never edits dashboard HTML to add a card.

```json
{
  "exam_id": "EXAM-001",
  "course_id": "COURSE-001",
  "title": "Revenue Recognition Review",
  "status": "ready",
  "question_count": 40,
  "estimated_minutes": 60,
  "created_at": "2026-07-19T18:00:00Z",
  "question_bank_hash": "sha256:..."
}
```

### Landing-page mockup candidates

Three high-fidelity directions were generated from the supplied exam screenshot as a visual-density reference:

**Selected direction: Concept A — Exam Ledger.** It is the default landing-page contract. Its Ready Exams region follows the complete, scrollable-ledger behavior above.

1. **Concept A — Exam Ledger:** balanced workspace dashboard with due review, ready exams, source processing, recent courses, and the complete Ownership Curve in a right rail. This is the strongest general-purpose home screen.
2. **Concept B — Answer Sheet Command Center:** closest to the supplied exam interface, with a dense exam table and answer-sheet-style review queue. This is the strongest operational and high-density direction.
3. **Concept C — Ownership Horizon:** makes the full long-term curve the dominant top-level feature, with due work, ready exams, next milestone, and calendar below. This is the strongest expression of the product's long-term learning identity.

Artifacts:

- `design-mockups/mastery-ledger-dashboard.png`
- `design-mockups/concept-b-answer-sheet-command-center.png`
- `design-mockups/concept-c-ownership-horizon.png`

Treat generated text and example data as illustrative. Rebuild the selected direction in deterministic HTML and CSS with the real schemas and accessibility contract.

### Exam-interface mockup candidates

All three candidates inherit the selected Exam Ledger palette, typography hierarchy, and compact professional tone. They represent different exam modes rather than separate visual brands:

1. **Continuous Paper:** an optional dense mode for ordinary multiple-choice exams. Multiple questions share one scrollable paper, while an independently scrollable answer-sheet rail keeps the full exam map available.
2. **Focused Question:** the selected default exam view. Show one question at a time with a persistent question palette, generous reading measure, notes, keyboard shortcuts, explicit previous/next navigation, and the question's source disclosure at the bottom of the question canvas.
3. **Evidence Testlet:** a document-based mode for case studies. Resizable evidence, question, and answer-sheet panes keep source material, the active question, and testlet progress visible together.

Artifacts:

- `design-mockups/exam-concept-1-continuous-paper.png`
- `design-mockups/exam-concept-2-focused-question.png`
- `design-mockups/exam-concept-2-focused-question-v2.png` — selected default with bottom source disclosure
- `design-mockups/exam-concept-3-evidence-testlet.png`

The modes may coexist in one application. Default ordinary multiple-choice exams to Focused Question and allow the learner to switch to Continuous Paper. Select Evidence Testlet when questions depend on shared exhibits. Record the chosen presentation mode in the attempt rather than duplicating question data.

### Question contract

Every multiple-choice question should contain:

```json
{
  "question_id": "Q-001",
  "concept_ids": ["concept-a"],
  "prompt": "Question text",
  "options": [
    {"option_id": "A", "text": "First answer"},
    {"option_id": "B", "text": "Second answer"}
  ],
  "correct_option_id": "B",
  "correct_explanation": "Why B is correct.",
  "source_refs": [
    {
      "source_id": "SRC-001",
      "locator": {
        "kind": "paragraph",
        "value": "Section 2, paragraph 4",
        "label": "Section 2, paragraph 4"
      },
      "supports": ["correct_answer", "explanation"],
      "support_strength": "direct",
      "href": "https://example.invalid/source#section-2"
    }
  ],
  "difficulty": "medium"
}
```

Generation must use only approved evidence and the skill's canonical `source-ref-v1` citation contract. `validate_exam.py` should reject missing answer keys, duplicate option IDs, invalid source IDs, free-form or unresolved locators, empty support targets, unsupported explanations, malformed hyperlinks, and executable markup in question content.

### Answer behavior

The requested behavior is:

- When the learner submits an incorrect answer, mark it incorrect without giving a hint, explanation, source, or indication of the correct option.
- When the learner submits the correct answer, show the correct explanation and enable the supporting-source disclosure, but do not open it automatically.
- Lock the submitted answer for that attempt so the learner cannot discover the answer by repeatedly clicking options.
- Allow flagging, navigation, progress display, and final submission.
- Keep the answer key out of visually rendered HTML, while recognizing that a self-contained offline file cannot make the embedded key secret from a technically sophisticated user.

This is an immediate-feedback practice exam, not a perfect simulation of a secure CPA testing system. If strict exam behavior is later desired, add a separate mode that withholds all correctness feedback until final submission.

### Source presentation

Place a persistent disclosure row labeled **Sources used in this question** at the bottom of the Focused Question canvas, below the answer and feedback region and above Previous/Next navigation. Always show its source count and verification status. Keep the row collapsed by default before and after every answer outcome; never auto-expand it. Before the question is locked, disable detailed disclosure and do not reveal titles, locators, snippets, or links that could disclose the answer.

On a correct locked answer, show the concise explanation and enable the collapsed row so the learner may deliberately open one or more precise citations. On an incorrect locked answer, leave the row collapsed and disabled, with no source details. After final exam submission, enable the still-collapsed disclosure in review mode for human verification regardless of correctness. A citation may link to a webpage, a PDF location when supported, or a video timestamp. The durable record remains the source ID plus locator; the hyperlink is a convenience and may later break.

Example:

```text
Correct.

The liability is recognized when both stated conditions are met...

Source: SRC-004, ASC section 410-20-25, paragraph 3
Open supporting source
```

### Exam artifacts

Generate each exam under the course rather than inside the skill:

```text
courses/<course-id>/exams/EXAM-001/
  exam.html
  exam.json
  generation-manifest.json
```

- `exam.html` is the learner-facing interface.
- `exam.json` is the validated canonical exam definition.
- `generation-manifest.json` records approved evidence inputs, generator version, prompt version, timestamps, and validation result.

Attempt history should be stored separately from the immutable exam definition. The exact browser-to-course persistence mechanism will be decided with item 2 because a static browser file cannot silently write arbitrary workspace files.

### Security and integrity requirements

- Treat source text and generated question content as untrusted data.
- Escape all rendered text and sanitize allowed hyperlinks.
- Do not permit generated scripts, event handlers, remote embeds, or arbitrary HTML.
- Prefer no third-party CDN dependencies so the exam works offline.
- Record a content hash for `exam.json` in the generation manifest.
- Do not claim that client-side answer keys are tamper-proof or secret.
- Meet keyboard-navigation, focus, contrast, and screen-reader requirements.

### Item 1 approved decisions

1. Use immediate correctness feedback as specified, with one locked submission per question.
2. Call the visual design "CPA-inspired" rather than an official CPA exam replica.
3. Use a fixed local web app and validated JSON as the primary experience; retain self-contained `exam.html` as an offline export.
4. Provide an optional future strict mode that delays feedback until final submission.
5. Decide open-response grading and attempt persistence while examining item 2.

### Item 1 visual-polish research addendum

The first proposal defined a safe rendering architecture but did not define a sufficiently polished exam experience. Current open-source projects show several patterns worth adopting without importing an entire assessment platform.

| Project | Useful patterns | Fit and limitation |
| --- | --- | --- |
| [Exam Simulator - NB](https://github.com/n4srellah24/exam-simulator-nb) | Exam setup, exam-paper layout, side answer grid, timer, zoom, quick navigation, filtered results, flags, local history, and balanced sampling | Closest workflow reference and MIT licensed, but implemented as a small Python Anki add-on rather than a web runtime |
| [Numbas](https://github.com/numbas/Numbas) | Mature browser-only assessment runtime, exam packaging, structured questions, and offline-capable delivery | Strong architectural benchmark and Apache-2.0 licensed, but much larger and more mathematics-oriented than this skill needs |
| [H5P Question Set](https://github.com/h5p/h5p-question-set) | Modular question types, progress display, option feedback, and accessible reusable learning components | MIT licensed and useful for interaction study, but adopting H5P itself would add a substantial content-runtime ecosystem |
| [PrairieLearn](https://github.com/PrairieLearn/PrairieLearn) | Randomized questions, autograding, assessment composition, and rich problem types | Mature and powerful, but server-heavy; its arbitrary HTML, JavaScript, and Python question model conflicts with this skill's fixed safe template |
| [Open Exam Suite](https://github.com/bolorundurowb/Open-Exam-Suite) | Timed sections, real-time checking, explanations, printing, progress tracking, and versioned exam formats | Useful product reference, but it is a GPL-3.0 Windows/.NET desktop application and should not be copied into the portable HTML asset |
| [Seda145/Exam](https://github.com/Seda145/Exam) | Self-contained browser exam driven by JSON, color-coded review, optional notes, and offline packaging | Validates the proposed single-file delivery model, but it is AGPL-3.0, lightly adopted, and not polished enough to become the primary visual reference |

The recommended result is a custom, dependency-free HTML template that borrows interaction patterns rather than source code. This avoids pulling a large assessment platform or a copyleft runtime into the skill.

#### Polished learner flow

1. **Exam setup:** show title, objectives, question count, estimated duration, testlets or sections, timing mode, and concise instructions.
2. **Exam workspace:** use a restrained professional shell with a persistent header, question canvas, answer controls, and an answer-sheet rail.
3. **Submission checkpoint:** summarize answered, unanswered, and flagged questions before confirmation.
4. **Results dashboard:** show score, status breakdown, domain performance, time used, and questions due for later review.
5. **Question review:** filter by correct, incorrect, unanswered, flagged, concept, and source-verification status.
6. **Revisit flow:** create a new practice set from incorrect, uncertain, or due questions without modifying the original attempt.

#### Exam workspace composition

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ Course / Exam title      Testlet 1 of 3        00:42:18      Finish exam │
├───────────────────────────────────────────────────┬──────────────────────┤
│ Question 12 of 40                    Flag question │ Answer sheet         │
│                                                   │ 01 ✓  02 ✓  03 ⚑    │
│ Question stem                                     │ 04 ·  05 ✓  06 ·    │
│                                                   │ 07 ✓  08 !  09 ·    │
│ ○ A. Answer                                       │                      │
│ ○ B. Answer                                       │ Legend               │
│ ○ C. Answer                                       │ ✓ Answered           │
│ ○ D. Answer                                       │ ⚑ Flagged            │
│                                                   │ · Unanswered         │
│ [Submit answer]                                   │                      │
├───────────────────────────────────────────────────┴──────────────────────┤
│ Zoom 100%                    Previous                         Next        │
└──────────────────────────────────────────────────────────────────────────┘
```

Use status text and icons in addition to color. On smaller screens, collapse the answer sheet into a drawer; do not squeeze the question into an unreadable two-column layout.

#### Visual system

- Use a calm navy, slate, white, and restrained status palette rather than gamified gradients.
- Use one modern system-font stack and a comfortable reading measure for long scenarios.
- Give the question stem stronger hierarchy than navigation chrome.
- Keep controls stable between questions to prevent layout movement.
- Use a feedback panel below the locked answer, not a transient toast.
- Reserve red and green for submitted outcomes; unanswered and flagged states need neutral and amber treatments.
- Support keyboard shortcuts only when visible in the interface and disable them while typing an open response.
- Meet accessible focus, contrast, reduced-motion, screen-reader, and non-color status requirements.

#### Revised implementation direction

Build the first template from the approved Mastery Ledger contracts. Use the projects above as interaction references, not runtime dependencies. Create screenshots of setup, active exam, correct feedback, incorrect feedback, submission confirmation, results, and review states as explicit visual acceptance artifacts before calling the template polished.

#### Selected Focused Question interaction contract

- Make Focused Question the default exam route and render one question at a time.
- Keep a persistent, filterable question palette with answered, current, unanswered, and flagged states expressed through text or icons as well as color.
- Keep the question stem and selectable answer rows in the central reading column; do not place sources or explanations in a competing side rail.
- Place `Sources used in this question: <count>` at the bottom of the central question canvas. Keep it collapsed at all times unless the learner explicitly expands it. Enable expansion after a correct answer and for every question in final review mode; never auto-expand it.
- Keep Previous, Flag, Submit answer or Save & Next controls in stable positions between questions.
- Collapse the question palette and notes into drawers on narrow screens while retaining the bottom source row in the normal document flow.

#### Optional Continuous Paper interaction contract

Use the supplied screenshot as the primary visual reference:

- Keep the dark fixed header with exam metadata on the left, a prominent centered timer, and the final submission action on the right.
- Show a vertically scrollable paper-like question area and an independently scrollable answer-sheet rail.
- Render answer letters as real selectable radio controls for single-answer questions, not decorative squares.
- Selecting an option in the question body must update the matching answer-sheet cell, and selecting a cell must update the question body.
- Allow the learner to change a selection until `Submit answer` locks that question.
- Show multiple questions in the main scroll while retaining direct question navigation from the answer sheet.
- Preserve zoom controls for dense or long material.
- Keep the answer-sheet status visible through icons, labels, and color: unanswered, selected, locked-correct, locked-incorrect, and flagged.
- On a correct locked answer, insert the explanation and enable the collapsed source disclosure directly beneath that question without opening it.
- On an incorrect locked answer, show only the incorrect state and no hint, explanation, source, or correct option.

### Open-source scoring and persistence findings

Record these implementation lessons in the future `references/assessment-scoring.md` rather than copying project code:

- **Exam Simulator - NB:** supports all-or-nothing, partial-positive, and partial-negative scoring. Its partial modes award a fraction for each correct selection and subtract the same fraction for each wrong selection. Partial-positive floors each question at zero; partial-negative allows a negative question score but floors the overall exam at zero. It records correct, partial, wrong, and skipped counts. Its history writer uses schema-versioned JSON and an atomic temporary-file replacement.
- **H5P Multiple Choice:** uses binary `1` or `0` for a single-answer question. Multi-answer questions can be single-point or weighted by correct answers. Retry, solution reveal, immediate checking, keyboard interaction, and answered events are configurable rather than hard-coded together.
- **Numbas:** treats each question part as a credit proportion multiplied by available marks, rejects invalid answers before scoring, can delay feedback, supports penalties for revealed steps, and encourages unit tests for marking algorithms.
- **PrairieLearn:** lets an autograder return a score from `0` through `1`, which is multiplied by the points assigned to that test or question.

For the initial Mastery Ledger exam:

1. Score single-answer multiple choice as exactly `1` for the correct option and `0` otherwise.
2. Score unanswered questions as `0` and report them separately from incorrect answers.
3. Default multiple-response questions to all-or-nothing; add partial scoring only as an explicit future exam setting.
4. Keep exam score separate from review scheduling. Only a fully correct due review advances the long-term curve.
5. Persist attempts as schema-versioned JSON using atomic writes.

## 2. Durable question bank and spaced repetition

### Product intent

Keep every generated multiple-choice and open-response question available in the course folder after the HTML exam is finished. Make the bank readable by a person or future LLM, while retaining enough structure to rebuild exams, revisit weak areas, and schedule spaced reviews safely.

### Separate content, attempts, and learner state

Use three distinct records:

```text
courses/<course-id>/
  questions/
    question-bank.json
    question-bank.md
  attempts/
    ATTEMPT-001.json
  progress/
    learner-progress.json
    review-queue.json
```

- `question-bank.json` is the canonical, validated machine representation used to generate HTML exams.
- `question-bank.md` is the complete human- and LLM-readable rendering of the same questions.
- `attempts/*.json` is append-only history of what the learner submitted and what evaluation was returned.
- `learner-progress.json` holds aggregate proficiency and misconception evidence by concept.
- `review-queue.json` holds mutable scheduling state by question and concept.

Do not mix review dates or learner answers into the question definition. A question can be corrected or superseded without erasing what happened in earlier attempts.

### Why both JSON and Markdown

Markdown alone is pleasant to inspect but fragile for deterministic HTML generation, answer validation, schema migration, and atomic scheduling updates. JSON alone is reliable for scripts but poor for long-term human review and direct LLM reading. Therefore:

1. Treat JSON as canonical for computation.
2. Generate Markdown deterministically from JSON.
3. Record the JSON content hash in the Markdown header.
4. Never hand-edit both files independently.
5. If a user edits Markdown, require an explicit import-and-validate step that updates JSON and regenerates Markdown.

### Markdown question format

Render every question under a stable ID. Include enough information for future tutoring and verification, not just the prompt.

```markdown
# Question bank: Example course

Generated from: question-bank.json
Content hash: sha256:...

## Q-001 — Multiple choice

**Concepts:** revenue-recognition
**Difficulty:** 3/5
**Status:** approved

### Prompt

Which condition must be satisfied before revenue is recognized?

### Options

- A. ...
- B. ...
- C. ...
- D. ...

### Answer and explanation

**Correct answer:** B

Explanation supported by the approved evidence.

### Sources

- SRC-004 — ASC section 410-20-25, paragraph 3

### Review notes

- Common error: ...
- Prerequisites: ...
```

For open-response questions, replace options and the single answer key with:

- acceptable answer elements;
- a reference answer;
- scoring rubric;
- common misconceptions;
- source references.

The Markdown bank is an internal course artifact and may reveal answers. The learner-facing exam must not link to it during an active attempt.

### Stable identity and versioning

- Give every question a stable `question_id` that never gets reused.
- Store `version`, `created_at`, `updated_at`, and `supersedes` fields.
- Preserve a question used by an existing attempt; create a new version rather than rewriting attempt history.
- Let exams reference a question ID plus version.
- Mark weak or unsupported questions `draft`, `changes_required`, `rejected`, or `superseded`; only `approved` questions may enter an exam.

### Attempt persistence from HTML

A browser cannot safely and silently write arbitrary files into the course folder. Support two explicit execution paths:

1. **Managed local mode — recommended:** launch the exam with a bundled Python local server. The server serves the fixed HTML and accepts same-origin attempt events, validates them, and writes `attempts/ATTEMPT-*.json` atomically.
2. **Portable offline mode:** open the self-contained HTML directly. Store in-progress state in browser storage and provide an `Export attempt` button that downloads a JSON result. A bundled import script validates and adds it to the course later.

Do not require an internet service or remote account for either mode. Bind the local server to loopback only, use a random session token, and never expose course files through unrestricted paths.

### Open-response evaluation

Multiple-choice grading is deterministic. Open responses need a different contract:

- Save the learner's exact response before evaluation.
- Evaluate against approved answer elements and a cited rubric.
- Return `correct`, `partial`, `incorrect`, or `uncertain` plus present and missing elements.
- Record the evaluating model and prompt version when an LLM is used.
- Do not treat an LLM grade as unquestionable; retain the response, rubric, citations, and short justification for human review.
- In offline mode without an LLM runtime, save the answer as `pending_evaluation` rather than exposing the answer key automatically.

### Fixed long-term review curve

The product goal is one transparent review ladder applied to the same stable multiple-choice question:

```text
1d -> 3d -> 7d -> 14d -> 28d -> 56d -> 112d -> 224d
   -> 448d -> 896d -> 1792d -> 3584d
```

Approximate later milestones are one month, two months, four months, seven months, 1.2 years, 2.5 years, 5 years, and 10 years. Store the exact day values rather than recalculating approximate calendar labels.

Use these deterministic rules:

1. A newly learned question starts at stage `0` and is due in `1` day.
2. A fully correct answer submitted when the question is due advances exactly one stage. Calculate the next due date from the successful review timestamp.
3. An incorrect or uncertain due answer resets the question to stage `0`, due again in `1` day.
4. An unanswered due question remains overdue and does not advance.
5. An early practice answer is recorded but does not advance the scheduled stage.
6. A late correct answer advances one stage only; it never skips rungs.
7. After a correct review at the final `3584`-day stage, keep the question on a `3584`-day maintenance interval unless the user archives it.
8. Keep the same question ID, stem, choices, correct answer, and source grounding throughout the curve. If the factual content changes materially, supersede the question and start a new review record.

Persist at least:

```json
{
  "question_id": "Q-001",
  "question_version": 1,
  "stage_index": 0,
  "interval_days": 1,
  "last_due_at": null,
  "last_reviewed_at": null,
  "next_due_at": "2026-07-20T17:00:00Z",
  "due_success_count": 0,
  "lapse_count": 0,
  "early_practice_count": 0,
  "status": "learning"
}
```

This is an expanding-interval spaced-repetition ladder, not reinforcement learning. The curve itself is the product contract. Do not use FSRS as the default because FSRS intentionally calculates variable intervals. Keep Py-FSRS only as a possible future alternative mode for users who explicitly prefer adaptive scheduling.

### Learner-editable Ownership Curve

Let the learner edit interval days from the web app. Treat each saved curve as a versioned profile:

```json
{
  "curve_id": "CURVE-OWNERSHIP",
  "version": 2,
  "name": "My ownership curve",
  "interval_days": [1, 3, 7, 14, 30, 60, 120, 240, 480],
  "created_at": "2026-07-19T18:00:00Z",
  "supersedes_version": 1
}
```

The editor should provide draggable or directly editable interval chips, human calendar labels, a horizontal timeline preview, reset-to-default, duplicate-as-new-profile, and validation. Require positive whole-day intervals in strictly increasing order. Warn about unusually short, dense, or multi-decade curves without preventing an intentional choice.

When saving a changed curve, require one explicit application policy:

1. **New questions only:** existing review schedules keep their prior curve version.
2. **Future advancement — recommended:** preserve every existing `next_due_at`; after the next completed due review, use the new curve version and corresponding stage.
3. **Recalculate all:** recompute pending dates from each question's last successful due review. Show the number of affected questions and require confirmation.

Never silently rewrite past attempts or review events. Every question progress record stores the curve ID and version used for each scheduling decision.

### Required reusable additions

```text
mastery-ledger/
  scripts/
    render_question_bank.py
    validate_question_bank.py
    serve_exam.py
    import_exam_attempt.py
    update_review_queue.py
  references/
    question-and-attempt-contract.md
  assets/
    exam-template/
    question-bank.json
    learner-progress.json
    review-queue.json
```

### Item 2 decisions to confirm

1. Keep canonical questions in validated JSON and generate a complete Markdown mirror for people and future LLM sessions.
2. Keep immutable attempts, aggregate learner progress, and mutable review scheduling in separate files.
3. Use a loopback-only Python server as the recommended persistence mode, with browser export/import as the offline fallback.
4. Store open responses before grading and allow `pending_evaluation` when no LLM evaluator is available.
5. Use the exact fixed review curve as the default and advance only on fully correct due answers; reserve Py-FSRS for a future optional adaptive mode.

## 3. Human-verifiable activity and source history

Do not require a learner-facing activity feed or place an implementation timeline on the main dashboard. Preserve a human-readable verification report that can be generated or opened on request. Treat it as a derived view of canonical manifests, citation records, validation results, and machine-readable events rather than a second source of truth.

### Human report location

Store generated runtime reports inside the course, never inside the installed skill:

```text
courses/<course-id>/logs/
  reports/
    verification-index.md
    RUN-001-verification.md
```

The skill may package a blank report template under `assets/`, but every populated report belongs under the course's `logs/reports/`. Generate one immutable report per completed run and rebuild `verification-index.md` from those reports. Do not maintain a hand-edited `latest.md` that can drift from the underlying events.

### Verification report contents

Each run report should include:

1. run ID, course ID, timestamps, workflow state, and completion status;
2. requested scope and any approved expansion;
3. source inventory with source ID, title, type, author or publisher, dates, rights basis, processing mode, content hash, and processing status;
4. source outcomes: accepted, rejected, superseded, failed, or still pending, with short reasons;
5. material actions such as search, retrieval, extraction, transcription, validation, question generation, and exam generation;
6. decisions and short outcome-based justifications, without private reasoning or hidden chain-of-thought;
7. artifact inventory with paths, schema versions, hashes when available, and validator results;
8. question-to-source provenance using canonical `source-ref-v1` objects and human-readable locator labels;
9. contradictions, unresolved gaps, limitations, and items not independently verified;
10. any errors, retries, fallbacks, or user approvals that materially affected the result.

### Rendering and privacy rules

- Render source titles and locator labels for people, but preserve source IDs and structured locators beside them.
- Link to a source only when the saved `href` or local application route has been validated.
- Exclude prompts, hidden reasoning, cookies, tokens, credentials, raw model context, and unrelated filesystem details.
- Redact sensitive local paths when the report is exported outside the workspace; retain course-relative paths when possible.
- Quote only short excerpts already stored for verification. Do not copy full articles or transcripts into the report.
- Make report generation deterministic and idempotent: the same frozen run data should produce the same substantive report.
- Label the report as generated and record the generator/schema version so a reviewer does not mistake it for the canonical event store.

### Web-app access

Provide a quiet `Verification` action from the course or exam overflow menu rather than a mandatory feed. It should open the report index, filter by run or source, and allow the learner to inspect question provenance. Keep the normal learning flow focused on studying and exams.

## 4. Machine-readable action log

Record actions, decisions, evidence references, and short justifications without hidden chain-of-thought. Use append-only JSONL as the canonical event stream and generated Markdown as the optional human view.

### Clean runtime boundary

Keep the course root clean by reserving two controlled runtime areas:

```text
courses/<course-id>/
  source/                 # approved knowledge Markdown and media
  exams/                  # published exam artifacts
  evidence/               # approved evidence and known gaps
  logs/                   # durable audit records
    events/
      RUN-001.jsonl
    runs/
      RUN-001-summary.json
    reports/
      verification-index.md
      RUN-001-verification.md
  .work/                  # isolated, disposable run state
    RUN-001/
      main/
      tasks/
        TASK-001/
          task-brief.yaml
          events.jsonl
          submission.json
          tmp/
      staging/
```

Do not use the course root, `source/`, or final artifact directories as scratch space. A dot-prefixed `.work/` keeps intermediate material visually quiet while remaining inspectable. Do not store hidden reasoning or chain-of-thought anywhere; "scratch" means temporary files, candidate lists, query records, extraction intermediates, draft artifacts, and concise working conclusions.

### Agent write isolation

Hard-code the boundary in both instructions and deterministic tooling:

1. Give every run a resolved `run_work_dir` under `.work/<run-id>/`.
2. Give every delegated task a unique `task_work_dir`, `event_path`, and `submission_path` under `.work/<run-id>/tasks/<task-id>/`.
3. Require workers to write only inside their assigned task directory and never edit final learner-facing artifacts.
4. Prevent parallel workers from appending directly to the same canonical log. Each worker writes its own event shard; the main agent or a merge script validates and sequences accepted events into `logs/events/<run-id>.jsonl`.
5. Validate all resolved output paths against the course root and assigned work directory before writing. Reject traversal, absolute paths outside the course, symlink escapes, and overlapping worker outputs.
6. Promote only validated, main-agent-approved artifacts from `.work/` to final course folders, using atomic replacement where possible.
7. After hash-verified promotion, remove only known disposable duplicates and `tmp/` files. Preserve failed-run material until the learner requests cleanup or a configured retention policy applies.
8. Report unexpected files at the course root; never move or delete them automatically because they may belong to the learner.

Skill instructions alone are insufficient enforcement. Add a path resolver/validator, initialize the directories deterministically, include the assigned paths in every task brief, and run a post-run layout audit.

The web app, source indexer, and question generator must ignore `.work/` and must never treat `logs/` as curriculum evidence. Exclude `.work/` from normal course export and backup; include `logs/` only when the learner selects an auditable export.

### Canonical event format

Use one JSON object per line with schema `action-event-v1`:

```json
{
  "schema_version": "action-event-v1",
  "event_id": "EVT-000042",
  "occurred_at": "2026-07-19T20:15:00Z",
  "run_id": "RUN-001",
  "task_id": "TASK-003",
  "actor": {
    "type": "worker",
    "role": "citation-verifier",
    "actor_id": "WORKER-02"
  },
  "event_type": "evidence.validation.completed",
  "status": "complete",
  "summary": "Validated 12 source references; rejected 1 unresolved locator.",
  "justification": "Only locator-resolvable claims may enter the question bank.",
  "inputs": [
    {"kind": "artifact", "path": ".work/RUN-001/tasks/TASK-003/submission.json"}
  ],
  "outputs": [
    {"kind": "review", "id": "REVIEW-003", "path": "evidence/reviews/REVIEW-003.json"}
  ],
  "source_refs": [],
  "error": null
}
```

Required event fields are schema version, event ID, timestamp, run ID, actor, event type, status, and concise summary. Add task ID, justification, inputs, outputs, source references, decision ID, error code, duration, and tool name only when relevant.

Do not log full prompts, model context, chain-of-thought, credentials, cookies, raw headers, unredacted personal data, or complete copyrighted source contents. Tool activity should be summarized as an observable action such as `web.search.completed`, `source.download.failed`, `transcript.normalized`, `exam.generated`, or `artifact.validated`.

### Run summary

Generate `logs/runs/<run-id>-summary.json` after the event stream is closed. It should contain counts, final state, approved outputs, source changes, validation results, failures, fallbacks, user approvals, and the event-stream hash. It is a derived machine summary, not a replacement for the append-only events.

### Item 4 and 8 decisions to confirm

1. Use JSONL for canonical events, JSON for each closed run summary, and Markdown only for generated human verification reports.
2. Put all populated runtime logs under the course `logs/` directory; package only blank schemas and templates under skill `assets/`.
3. Put per-agent WIP under `.work/<run-id>/tasks/<task-id>/` with unique assigned paths and no direct writes to final artifacts.
4. Never persist private reasoning. Persist only observable actions, evidence, decisions, short justifications, and explicit uncertainties.
5. Make the main agent or a deterministic merger the single writer that promotes worker events into the canonical log.

## 5. Source-candidate ledger and source intake

Ask for preferred sources in the first assistant message whenever the learner's first request contains no detected attachment, path, URL, or named source. Allow sources to be added later to the active course, version affected artifacts, and avoid forcing the question again after the preference has been recorded.

Current recommendation: keep canonical candidate records as JSONL and render Markdown only for review.

## 6. Sub-agent topology

Keep concise routing rules in `SKILL.md`. Put detailed role procedures and report contracts in directly linked reference files. Do not create nested "sub-skills" unless a role must independently trigger outside the parent workflow; ordinary research workers should receive bounded task briefs instead.

### Required `.work/` guardrails

Before the main agent delegates or begins a multi-step run, require a deterministic run-preparation script to:

1. resolve and validate `course_root`;
2. create `.work/<run-id>/main/`, `.work/<run-id>/tasks/`, `.work/<run-id>/staging/`, and the durable `logs/` destinations;
3. write `.work/<run-id>/workspace-boundary.json` with canonical resolved paths and allowed roots;
4. record a pre-run course-layout manifest;
5. return the exact paths that must be copied into task briefs.

Every delegated task brief must contain:

```yaml
course_root: /resolved/course/root
run_work_dir: .work/RUN-001
task_work_dir: .work/RUN-001/tasks/TASK-001
allowed_read_paths: [source/, evidence/approved-claims.json]
allowed_write_paths: [.work/RUN-001/tasks/TASK-001/]
event_path: .work/RUN-001/tasks/TASK-001/events.jsonl
submission_path: .work/RUN-001/tasks/TASK-001/submission.json
proposed_final_targets: [evidence/reviews/REVIEW-001.json]
```

Repeat the write boundary in the worker prompt: write only inside `task_work_dir`; do not create or edit files elsewhere; return `blocked` if the assigned directory is missing or unwritable. When the runtime supports a real filesystem sandbox or working-directory restriction, configure it in addition to the prompt.

After every task, validate its paths and schema, compare the post-run layout with the pre-run manifest, and reject promotion when unexpected writes occurred. Do not move or delete unexpected files automatically. Only the main agent or a deterministic promotion script may write final artifacts, canonical logs, or approved evidence.

### Evidence and review locations

Keep raw worker submissions inside `.work/` until reviewed. Store accepted durable evidence separately:

```text
evidence/
  approved-claims.json
  reviews/
    REVIEW-001.json
  fact-checks/
    FACTCHECK-001.json
  contradictions/
    index.json
    CONTRADICTION-001.json
  gaps/
    GAP-001.json
```

- `reviews/` records structural and citation-support decisions about a versioned worker submission.
- `fact-checks/` records claim-level factual checks against reopened sources.
- `contradictions/` is the canonical home for conflicts between claims or sources.
- `gaps/` records missing evidence, unresolved questions, and verification blockers.
- Human verification reports under `logs/reports/` summarize these records but do not replace them.

Tie every review and fact check to the reviewed artifact path, content hash, claim IDs, source references, reviewer role, checks performed, decision, issues, required actions, and timestamp. If the artifact hash changes, mark its prior reviews stale and require re-verification.

A contradiction record should contain:

```json
{
  "contradiction_id": "CONTRADICTION-001",
  "concept_ids": ["concept-a"],
  "claim_ids": ["CLM-014", "CLM-027"],
  "source_refs": [],
  "conflict_type": "direct",
  "severity": "material",
  "status": "open",
  "summary": "The sources specify incompatible thresholds for the same scope and date.",
  "scope_or_date_explanation": null,
  "resolution": null,
  "resolved_by": null
}
```

Supported conflict types should include `direct`, `scope`, `temporal`, `terminology`, `methodology`, and `source-version`. Status should include `open`, `resolved`, `accepted_disagreement`, `superseded`, and `insufficient_evidence`. Preserve disagreement instead of averaging claims.

### Source assignment by role

Do not use one universal source-count rule:

| Role | Default source access | Responsibility |
|---|---|---|
| Source extractor | Exactly one source or one hierarchical source item | Extract claims and locators without cross-source synthesis |
| Research worker | One source by default; up to three closely related sources when the task itself requires comparison | Produce a bounded evidence packet and flag possible conflicts |
| Citation verifier | Every source referenced by the assigned report | Reopen locators and verify exact claim support |
| Contradiction auditor | Two to five normalized claim packets plus their source references | Detect and classify cross-source conflicts |
| Assessment generator | Approved claims only | Generate grounded questions without reopening the whole corpus |
| Assessment validator | The question, approved claims, and cited sources | Check ambiguity, answer support, and leakage |

Every extractor or research worker must perform a self-check for internal inconsistency, missing locators, limitations, and obvious counterevidence within its assigned material. Treat that as quality control, not independent verification. Never let the same worker both generate a report and issue its final fact-check or contradiction-clearance decision.

### Verification pipeline

Use two contradiction stages so expensive citation verification is not wasted on drafts that will never survive:

```text
source extraction
  → structural validation
  → claim normalization and deduplication
  → cheap cross-source contradiction triage
  → main-agent candidate selection
  → targeted independent citation verification
  → final contradiction adjudication
  → main-agent approval or rejection
  → promotion into evidence/
  → question and exam generation
```

Contradiction triage compares normalized claim text, scope, dates, source versions, and provisional references. It may cluster duplicates, flag potential conflicts, and recommend claims for rejection because they are out of scope or structurally unusable. It must not decide which conflicting factual claim is true without reopened source evidence.

After triage, run semantic citation verification only for:

- claims selected for the final guide, question bank, or exam;
- every claim in a material contradiction group;
- numerical, current, high-stakes, safety-relevant, or low-confidence claims that could affect the learner;
- a recorded risk sample of routine claims when the corpus is too large for full verification.

Do not spend semantic-verifier tokens on exact duplicates, out-of-scope claims, structurally invalid claims, or drafts the main agent has already rejected for a non-factual reason. A claim must not be rejected merely because it conflicts with another unverified claim; verify the material conflict group, then run final contradiction adjudication.

Citation verification is therefore a late gate, but not the final authority. It may run as several parallel verifier tasks over independent surviving claim batches. Final contradiction adjudication consumes those verification results, and the main agent remains the only approval authority.

For a single-source course, skip cross-source triage and adjudication but still check internal contradictions and source self-corrections. When subagents are unavailable, the main agent performs separated passes with fresh inputs and records `self-review-fallback`; do not describe that result as independent verification.

### Dependency-gated dispatch

Store the workflow as a directed acyclic graph in `run-plan.json`. Every task record must include:

```json
{
  "task_id": "VERIFY-001",
  "task_type": "citation_verify",
  "depends_on": ["SELECT-001"],
  "required_input_artifacts": [
    {"path": ".work/RUN-001/main/candidate-selection.json", "sha256": "sha256:..."}
  ],
  "produces": ["evidence/reviews/REVIEW-001.json"],
  "status": "planned"
}
```

Use these dependency gates:

| Task type | May become ready only after |
|---|---|
| `source_extract` | its source is registered and processing-ready |
| `research_analyze` | every required source extraction task is structurally valid |
| `claim_normalize` | all extraction and research tasks in its declared scope are structurally valid or explicitly waived |
| `contradiction_triage` | normalization is complete for every source in the comparison group |
| `candidate_select` | contradiction triage and deterministic rejection reasons are recorded |
| `citation_verify` | candidate selection is frozen and the selected claim hashes match |
| `contradiction_adjudicate` | every material claim in its conflict group has a citation-verification decision |
| `main_approve` | required verification and adjudication tasks are complete |
| `assessment_generate` | referenced claims are main-agent approved and promoted |

The runtime scheduler—not the LLM—computes readiness. Add a `next-tasks` runtime subcommand that reads `run-plan.json` and returns only tasks whose dependencies, gates, and input hashes pass. The main agent may dispatch only task IDs returned by that command. `prepare-task` must independently recheck the same gates and return exit code `2` if a task is premature.

Do not create citation-verifier tasks during initial fan-out. Create them after `candidate_select` from the frozen surviving-claim list and material contradiction groups. This both enforces ordering and avoids paying to verify claims already removed for valid non-factual reasons.

### Paperclip-inspired reception desk

Paperclip's useful pattern is not the corporate job titles themselves. It is the control plane behind them: explicit reporting lines, atomic task ownership, dependency-aware work queues, inbox state, approvals, budgets, and an audit trail. Mastery Ledger should adopt those mechanics without keeping a large hierarchy of always-running manager agents. See the [Paperclip repository](https://github.com/paperclipai/paperclip) and [Paperclip documentation](https://docs.paperclip.ing/).

Use this topology:

```text
Human learner / operator
          |
          v
Main orchestrator / tutor (final authority)
          ^
          | compact prioritized inbox and escalations
          |
Reception Desk
  |- deterministic Inbox Controller (mandatory Python runtime)
  `- Receptionist Agent (optional exception classifier)
          ^
          | validated completion envelopes
          |
  +-------+----------------------+----------------------+
  |                              |                      |
Source Operations          Evidence Quality      Learning Product
  |- discovery scouts        |- claim normalizer    |- module drafter
  `- source extractors       |- contradiction       |- assessment generator
                             |  triage/verifier      `- assessment validator
                             `- adjudicator
```

`Source Operations`, `Evidence Quality`, and `Learning Product` are routing groups, not automatically spawned LLM managers. A lead/manager task may be created only when it owns a concrete decomposition or aggregation artifact over two or more child tasks. Small runs route workers directly to the main agent through the Reception Desk.

The Reception Desk is a mailbox and gate, not an evidence authority:

1. Every worker writes its work product, `events.jsonl`, and `completion.json` only inside its assigned task directory.
2. The deterministic Inbox Controller validates the completion envelope, task ownership, allowed paths, schemas, artifact hashes, dependency state, and duplicate receipt status.
3. It classifies the receipt into a machine queue and derives a compact main-agent inbox.
4. If deterministic rules cannot classify an ambiguous narrative, scope drift, or blocker, the main agent may create one `reception_classify` task for the optional Receptionist Agent.
5. The Receptionist Agent writes a recommendation only. The controller validates and applies an allowed route; the main agent decides any escalation, plan change, approval, rejection, or learner-facing question.

The Receptionist Agent must not edit a worker submission, approve or reject a factual claim, resolve a contradiction, change `run-plan.json`, create new work, promote an artifact, or communicate directly with the learner. It must not be invoked merely to summarize a structurally valid completion; the deterministic controller already does that from declared fields.

Store reception state under the run boundary:

```text
.work/<run-id>/inbox/
  envelopes/
    <task-id>.completion.json
  reception-notes/
    <task-id>.reception-note.json
  inbox-events.jsonl
  main-agent-inbox.json
```

`inbox-events.jsonl` is the append-only receipt and routing history. `main-agent-inbox.json` is a derived, replaceable view; it is not canonical task state. Canonical dependency and status state remains in `run-plan.json`. Workers cannot write anything under `inbox/` directly.

Use this worker completion contract:

```json
{
  "schema_version": "task-completion-v1",
  "run_id": "RUN-001",
  "task_id": "EXTRACT-001",
  "worker_role": "source_extractor",
  "status": "submitted",
  "submission_path": ".work/RUN-001/tasks/EXTRACT-001/submission.json",
  "submission_sha256": "sha256:...",
  "event_path": ".work/RUN-001/tasks/EXTRACT-001/events.jsonl",
  "event_sha256": "sha256:...",
  "produced_artifacts": [
    {
      "kind": "evidence_packet",
      "path": ".work/RUN-001/tasks/EXTRACT-001/evidence-packet.json",
      "sha256": "sha256:...",
      "schema": "evidence-packet-v1"
    }
  ],
  "summary": "Extracted one registered source; two claims need review.",
  "blockers": [],
  "scope_drift": [],
  "policy_flags": []
}
```

`status` is one of `submitted`, `blocked`, or `failed`. `summary` is a short handoff, not hidden reasoning. A completion is quarantined if its task identity, path, hash, schema, or ownership check fails.

The Inbox Controller may assign only these classifications:

| Classification | Route |
|---|---|
| `ready_for_validation` | Run the task-type structural validator |
| `ready_for_review` | Put a validated decision item in the main-agent inbox |
| `changes_required` | Return the recorded validation errors to the same task owner |
| `blocked` | Stop dependents and surface the declared blocker |
| `scope_drift` | Require main-agent disposition before any dependent work |
| `policy_violation` | Quarantine the completion and escalate |
| `human_input_required` | Ask the learner only after the main agent confirms the question is necessary |
| `reception_review_required` | Permit an optional Receptionist Agent classification task |

An optional reception note uses `reception-note-v1` and contains only `task_id`, `classification`, `priority`, `compact_summary`, `artifact_inventory`, `validation_needed`, `suggested_next_task_type`, `escalation_reason`, and `questions_for_main`. It records an operational recommendation, not chain-of-thought.

The main agent reads the prioritized inbox instead of receiving every raw worker report in its prompt. It opens the referenced raw artifacts when making a factual, contradiction, approval, or scope decision. This reduces context use without allowing summaries to replace source evidence.

### Item 6 accepted decisions

1. Default extraction tasks to one source, while allowing narrowly justified multi-source comparison tasks.
2. Require an independent citation verifier for worker-generated factual material before approval.
3. Use a separate contradiction auditor across two to five normalized source packets rather than asking each extractor to settle cross-source conflicts.
4. Keep raw reports under `.work/`; promote durable reviews, fact checks, contradictions, and gaps into `evidence/` only after validation.
5. Enforce `.work/` boundaries with run preparation, task fields, path validation, post-run layout audit, and main-agent-only promotion.
6. Gate dispatch through a deterministic `run-plan.json` DAG and `next-tasks`; never let the LLM decide that an unmet dependency is "close enough."
7. Create citation-verifier tasks only after contradiction triage and candidate selection, while still verifying every claim in a material conflict group before final adjudication.
8. Put a hybrid Reception Desk between worker completions and the main agent: deterministic receipt and routing by default, with an optional Receptionist Agent only for ambiguous exceptions.
9. Treat functional leads as task routing groups, not persistent agents; create a manager task only when it owns an explicit decomposition or aggregation deliverable.

### Exact runtime implementation contract

#### Language and dependencies

Implement all workspace creation, boundary checks, event merging, promotion, and finalization in **CPython 3.11 or newer**. Use the Python standard library only for these guardrails so the same commands work on Windows, macOS, and Linux. Do not make Bash, PowerShell, Node.js, or an LLM-generated script part of the canonical workflow.

Detect Python before starting a guarded run. If Python 3.11+ is unavailable, return `blocked` and ask the learner to install or select a supported runtime. Do not simulate the guardrails with ad hoc shell commands.

Use formats by responsibility:

| Responsibility | Canonical format |
|---|---|
| Human-editable course configuration | YAML (`study.yaml`) |
| Run boundary, task brief, worker submission, review, fact check, contradiction, run summary | JSON |
| Append-only action events | JSONL |
| Extracted source knowledge and generated verification reports | Markdown |
| Media, subtitles, and transcript artifacts | Original binary/text plus JSON metadata |

Replace the current runtime `run-plan.yaml` and `task-brief.yaml` templates with versioned JSON contracts during implementation. Do not maintain both YAML and JSON as competing canonical task formats.

#### Fixed script surface

Package these exact Python entry points under `scripts/`:

| Script | Ownership |
|---|---|
| `init_study.py` | Create the course layout and initial manifests; extend the existing script rather than inventing a second initializer |
| `workspace_runtime.py` | Own run preparation, task preparation, completion receipt, inbox derivation, path audits, event merging, artifact promotion, and run finalization through fixed subcommands |
| `validate_evidence.py` | Validate evidence packets and canonical source references structurally |
| `validate_review.py` | Validate review, fact-check, contradiction, and approval records structurally |
| `aggregate_approved_evidence.py` | Aggregate only main-agent-approved claims |
| `render_verification_report.py` | Render deterministic Markdown verification reports from closed events and durable evidence |

The main agent must never invent another script name, flag, schema, or fallback implementation. If a required script or documented subcommand is absent, stop with `blocked` and report the missing packaged capability.

#### `workspace_runtime.py` subcommands

Use only these subcommands:

```text
prepare-run     Create and validate the run boundary and pre-run layout manifest
next-tasks      Return only dependency-satisfied task IDs from run-plan.json
prepare-task    Create one isolated task directory and versioned task-brief.json
receive-task    Validate and register one worker completion envelope, then route it
show-inbox      Derive and return the current prioritized main-agent inbox
audit-task      Validate submission paths, schemas, and unexpected writes
merge-events    Validate worker event shards and create the canonical run JSONL
promote         Atomically promote an approved artifact to an allowlisted final destination
finalize-run    Close the event stream and write the hashed run summary
audit-course    Report unexpected, missing, or misplaced course files without modifying them
clean-run       Remove only hash-verified disposable files after explicit learner approval
```

Do not expose `promote`, `finalize-run`, or `clean-run` to worker agents. Only the main agent invokes them.

#### Command contracts

The documented calls are:

```text
python <skill-root>/scripts/workspace_runtime.py prepare-run \
  --course-root <course-root> --run-id <RUN-ID> --mode <mode>

python <skill-root>/scripts/workspace_runtime.py next-tasks \
  --boundary <workspace-boundary.json> --run-plan <run-plan.json>

python <skill-root>/scripts/workspace_runtime.py prepare-task \
  --course-root <course-root> --run-id <RUN-ID> --task-spec <task-spec.json>

python <skill-root>/scripts/workspace_runtime.py receive-task \
  --boundary <workspace-boundary.json> --completion <completion.json>

python <skill-root>/scripts/workspace_runtime.py show-inbox \
  --boundary <workspace-boundary.json> --run-plan <run-plan.json>

python <skill-root>/scripts/workspace_runtime.py audit-task \
  --boundary <workspace-boundary.json> --task-brief <task-brief.json> \
  --submission <submission.json>

python <skill-root>/scripts/validate_evidence.py \
  --source-manifest <source-manifest.yaml> <submission.json>

python <skill-root>/scripts/validate_review.py \
  --course-root <course-root> --record <review-or-contradiction.json>

python <skill-root>/scripts/workspace_runtime.py promote \
  --boundary <workspace-boundary.json> --submission <submission.json> \
  --approval <main-agent-approval.json>

python <skill-root>/scripts/workspace_runtime.py merge-events \
  --boundary <workspace-boundary.json>

python <skill-root>/scripts/workspace_runtime.py finalize-run \
  --boundary <workspace-boundary.json> --final-state <complete-or-blocked>

python <skill-root>/scripts/render_verification_report.py \
  --course-root <course-root> --run-id <RUN-ID>
```

Use the current Python interpreter when the runtime exposes it; `python` above is documentation shorthand, not a promise about the executable name on every operating system.

#### Script result protocol

Every runtime script must write exactly one JSON result object to standard output and diagnostics to standard error:

```json
{
  "schema_version": "runtime-result-v1",
  "command": "receive-task",
  "status": "complete",
  "run_id": "RUN-001",
  "task_id": "TASK-001",
  "paths": {
    "completion_envelope": ".work/RUN-001/inbox/envelopes/TASK-001.completion.json",
    "main_agent_inbox": ".work/RUN-001/inbox/main-agent-inbox.json"
  },
  "errors": [],
  "next_action": "run-structural-validation"
}
```

Use exit code `0` for success, `2` for validation failure or required user action, `3` for a path-boundary violation, `4` for a missing dependency, and `1` for an unexpected runtime failure. The main agent must inspect both the exit code and JSON `status`; never infer success from a file merely existing.

#### Non-hallucination workflow

Require the main agent to execute this state machine exactly:

```text
1. Detect Python 3.11+ and resolve the packaged skill root.
2. Run init_study.py only when the course does not yet exist.
3. Run workspace_runtime.py prepare-run and use only its returned paths.
4. Call next-tasks and dispatch only returned task IDs; prepare each with prepare-task.
5. Require the worker to write submission.json, events.jsonl, and completion.json only in task_work_dir.
6. Call receive-task for every completion. Quarantine invalid receipts; use a receptionist-classification task only when the result is reception_review_required.
7. Call show-inbox. Follow its validated route, run audit-task, then run structural validators appropriate to the task type.
8. Normalize and deduplicate claims, then run contradiction triage after all declared source work is complete.
9. Freeze candidate-selection.json and create citation-verifier tasks only for surviving, disputed, high-risk, or sampled claims.
10. Call next-tasks again; dispatch independent citation-verifier batches only when their gates pass.
11. Receive every verifier completion through the same Reception Desk, then run final contradiction adjudication after all material conflict claims are citation-verified.
12. Record explicit main-agent approval or rejection.
13. Run promote only for approved artifacts.
14. Run merge-events, finalize-run, and render_verification_report.py.
15. Run audit-course and report remaining WIP, failures, or unexpected files.
```

At any non-zero exit or `blocked` result, stop the dependent steps, record the observable failure when possible, and report the exact recovery action. Do not skip, rename, approximate, or reimplement a failed step inside the conversation.

## 7. Source and media processing

Store course evidence under `source/`, with binary media under `source/media/`. Root-level Markdown should contain extracted, cited knowledge rather than raw binaries.

Use `yt-dlp`, not the older `youtube-dl`. The maintained project exposes thousands of extractors, but an extractor listing is not a guarantee that every site or item currently works. Discover capabilities from the installed Python package instead of hard-coding a claim such as "100+ supported sites."

Prefer subtitles first with `--skip-download`; download authorized media only when usable captions are unavailable and transcription is required. Install the application runtime and locked Python packages through the standalone application installer, not dynamically inside an agent run. First-run onboarding initializes the workspace and asks before downloading an ASR model; it does not silently install or update application code. Local ASR can use `faster-whisper`, subject to the course processing policy.

### Skill package versus course data

Treat the installed skill as immutable application code. Store only these things in it:

- workflow instructions;
- reusable HTML, CSS, and JavaScript;
- Python scripts;
- schemas and blank asset templates;
- small test fixtures.

Never store downloaded articles, videos, subtitles, transcripts, generated exams, learner attempts, models, or logs inside the installed skill. Skill upgrades, reinstalls, read-only package locations, and multiple simultaneous courses make that location unsafe for runtime data.

The default writable course root should be:

```text
<active-workspace>/mastery-ledger-courses/<course-id>/
```

When no writable workspace exists, use a user data location such as `~/MasteryLedger/courses/<course-id>/`. Record the resolved absolute course root for the current run, but keep paths inside `course.yaml` relative so the course folder remains movable.

### Prevent path confusion

Add one deterministic resolver used by every script:

```text
python scripts/resolve_course.py --course-root <path>
```

Resolution priority:

1. explicit `--course-root` argument;
2. an active course path recorded in the current run plan;
3. the nearest parent containing `course.yaml`;
4. a newly created course under the default workspace course directory.

Return a machine-readable result containing the absolute course root, stable course ID, manifest path, and resolved artifact paths. Put `course_root` and `course_id` in every worker brief, log event, script invocation, and web-app launch. Never ask an LLM to reconstruct paths from prose or assume its current working directory is the course.

### Source layout

Keep the root of `source/` limited to Markdown knowledge records plus the `media/` directory:

```text
source/
  SRC-001.md
  SRC-002.md
  media/
    SRC-VIDEO-003/
      acquisition.json
      original.info.json
      captions.en.vtt
      transcript.json
      transcript.md
      audio.opus
      video.mp4
```

Each root Markdown record summarizes the extracted knowledge, precise locators, provenance, rights basis, processing history, original URL, local media path, and content hashes. A media folder may omit files that were never needed; subtitle-first processing should not create an audio or video file.

### Bounded video pipeline

Use an explicit pipeline, not recursive downloader fallback:

1. Inspect metadata and available human captions.
2. If authorized captions exist, run `yt-dlp --skip-download --write-subs` and normalize them.
3. Otherwise inspect authorized automatic captions and, if acceptable, run `yt-dlp --skip-download --write-auto-subs` and label their origin.
4. Only if no usable captions exist and media downloading is authorized, download the smallest suitable audio stream.
5. Transcribe locally with `faster-whisper` when available and permitted.
6. Preserve raw captions or ASR output, normalized timestamped transcript, hashes, model/version provenance, and failures.

`yt-dlp` is still the tool used to acquire platform subtitles; `--skip-download` skips the media payload, not the downloader itself.

### Python runtime and dependency location

Use the `yt-dlp` Python package rather than downloading its standalone executable. The supported integration is either the `yt_dlp.YoutubeDL` Python API or the same installed module invoked as `<runtime-python> -m yt_dlp`. Keep one resolved Python runtime per application installation so every script uses the same package version and dependency set.

Do not vendor the `yt_dlp` package source into the skill and do not create a virtual environment inside a course. The standalone application installer owns a locked Python environment. For source checkouts and recovery, package one deterministic bootstrapper:

```text
python <repo-root>/scripts/bootstrap_runtime.py ensure --profile core
```

Resolve the runtime in this order:

1. an installed Mastery Ledger application runtime;
2. an explicitly configured compatible Python environment whose locked packages validate;
3. the managed per-user Mastery Ledger virtual environment;
4. a `needs_user_action` result containing the official application installation action.

The bootstrapper may create or repair the managed environment only after the learner has approved application/runtime installation. It must not install packages into the caller's global Python environment. Return the absolute runtime-Python path and an environment-manifest hash; all media scripts consume that exact result.

Keep reproducible dependency profiles in the standalone repository:

```text
requirements/
  core.lock
  transcription.lock
  media-export.lock
```

`core.lock` contains the tested `yt-dlp` Python package and the application runtime. `transcription.lock` adds `faster-whisper` and its tested dependencies. `media-export.lock` is optional and contains any separately approved transcoding dependency. Generate locks as part of a release; an LLM must not edit or refresh them during a course run.

Keep automatic installation separate from automatic updating. The installed app uses its release lock until an explicit application update replaces it. Never update `yt-dlp` in response to an individual extractor failure, and never create a recursive install/update/retry loop.

Whisper models belong in the managed user cache, not in the skill, application source tree, or course, unless the learner explicitly requests a portable course bundle. Show the expected model download size before acquisition and record the selected model revision and hashes.

### FFmpeg boundary

FFmpeg is a native multimedia suite, not a pure-Python replacement that should be copied into the repository. Python projects called `ffmpeg-python` wrap an existing FFmpeg installation; they do not provide the codecs and native implementation.

Do not require an external `ffmpeg` executable for the core workflow:

- yt-dlp metadata inspection and subtitle download do not need FFmpeg;
- download the selected original audio stream without `--extract-audio` or format conversion;
- `faster-whisper` decodes supported media through PyAV, whose wheels bundle the FFmpeg libraries, so normal local transcription does not require a system FFmpeg executable.

Require a native FFmpeg tool only for optional operations such as merging separate video/audio streams, transcoding unsupported media, creating exports, or applying filters. Do not commit FFmpeg binaries to the repository or place them inside the skill. If a later media-export profile uses a Python wheel that carries a platform FFmpeg binary, treat it as a native binary dependency: pin it, audit its platform coverage and licensing, record its binary hash, and install it through the standalone application environment. Keep that profile optional.

### Extractor discovery and URL probing

After runtime resolution, record capabilities from the installed package:

```text
<runtime-python> -m yt_dlp --ignore-config --list-extractors
```

Store the package version, environment-manifest hash, extractor-list SHA-256, and generation time in the managed runtime cache. The UI may say that Exam Ledger can try URLs from thousands of supported extractors, but it must not promise that a particular URL will work until the metadata probe succeeds.

Probe each submitted URL before requesting subtitles or media:

```text
<runtime-python> -m yt_dlp --ignore-config --dump-single-json --skip-download \
  --no-playlist <video-url>
```

Use `--ignore-config` so unknown machine-level or user-level yt-dlp configuration cannot silently add cookies, change paths, enable playlists, or alter the skill's safety policy. Default to `--no-playlist`; playlist ingestion requires an explicit course-scope choice and a declared item cap.

The probe produces a sanitized `probe.json` under the source's `.work/` task directory. Before any durable promotion, record at least the submitted URL, canonical webpage URL, extractor and extractor key, remote item ID, title, duration when available, live-stream state, available human subtitle languages, available automatic-caption languages, playlist relationship, yt-dlp package version, environment-manifest hash, probe time, and probe-output hash. Do not store cookies, authorization headers, browser profiles, or raw secrets.

Classify the result as `metadata_ready`, `unsupported_url`, `authentication_required`, `live_or_upcoming`, `playlist_scope_required`, `temporarily_unavailable`, or `failed`. Do not treat every extractor error as permission to download media or update the tool.

### Exact subtitle-first acquisition

Keep human and automatic captions as separate stages so provenance cannot be blurred:

1. Probe metadata and list available subtitle languages.
2. If an authorized human subtitle matches the course language policy, run `--skip-download --write-subs` only.
3. Normalize and validate the downloaded caption. If it is usable, stop; do not download media.
4. Otherwise, if an authorized automatic caption matches, run `--skip-download --write-auto-subs` only and label every derived segment `platform_auto_caption`.
5. Normalize and validate it. If usable, stop.
6. Only then, when the rights gate permits local transcription, download the smallest suitable audio stream and invoke the ASR stage.

All yt-dlp invocations must include `--ignore-config`, an explicit playlist choice, an output directory inside the assigned `.work/` task, and a stable filename containing the remote item ID. Write metadata JSON and `acquisition.json`; hash every produced file. Do not use a title alone as a filename identity.

Use a per-course download archive only for explicitly approved playlist or recurring-feed ingestion. Store it under the course's operational state, not the installed skill, and record archive changes as events. A single-item retry may occur once after a transient failure; there is no recursive downloader fallback.

### Acquisition script surface

Keep the fragile behavior in packaged Python scripts rather than LLM-generated shell commands:

| Script | Responsibility |
|---|---|
| `bootstrap_runtime.py` | Resolve or create the locked standalone Python runtime without modifying global Python or a course |
| `inspect_media.py` | Probe one URL and produce sanitized metadata and capability classifications |
| `download_media.py` | Acquire authorized human captions, automatic captions, or original media streams using the resolved `yt_dlp` package |
| `normalize_subtitles.py` | Convert SRT/VTT captions into timestamped canonical transcript artifacts |
| `transcribe_media.py` | Run permitted local ASR and record model/version provenance |

`download_media.py` currently detects only a `yt-dlp` executable on `PATH`; implementation must replace that behavior with the resolved runtime Python and either the supported `YoutubeDL` API or `python -m yt_dlp`. It must also add ignored ambient configuration, separate human-caption and automatic-caption modes, stable source-ID output paths, and the structured result protocol before Item 7 is complete.

### Item 7 decisions to confirm

1. Keep the installed skill immutable and store generated course data outside it.
2. Default to `<workspace>/mastery-ledger-courses/<course-id>` with a user-data fallback.
3. Pass an explicit resolved `course_root` through every agent, script, log, and web-app action.
4. Keep only source Markdown and `media/` at the root of `source/`.
5. Use a bounded subtitle-first `yt-dlp` pipeline, followed by authorized audio download and local ASR only when needed.
6. Install locked Python dependencies into the standalone application's managed environment after one-time setup approval; do not modify global Python, the installed skill, or a course.
7. Use the `yt-dlp` Python package and one resolved runtime Python rather than downloading or locating a standalone yt-dlp executable.
8. Discover extractor support from the resolved `yt-dlp` package and probe each URL; never equate a listed extractor with guaranteed current support.
9. Ignore ambient yt-dlp configuration, default to one item, and keep human subtitles, automatic captions, media download, and ASR as distinct provenance-preserving stages.
10. Keep tool updates explicit and non-recursive; a download failure or unsupported URL must not trigger uncontrolled updater fallback.
11. Keep FFmpeg out of the core installation path; use PyAV-backed faster-whisper for decoding and add native FFmpeg only as an audited optional media-export profile.

## 8. Logs and assets

Generated logs belong in each course's `logs/` folder. Reusable event schemas, blank templates, renderers, and validators belong in the packaged skill's `assets/`, `references/`, and `scripts/` folders. An example `action-event.json` is an asset; a real `events.jsonl` is a runtime log.

## 9. `SKILL.md` frontmatter

The packaged skill frontmatter must contain only:

```yaml
---
name: mastery-ledger
description: <trigger description>
---
```

License, compatibility, author, and version metadata must not be placed in the `SKILL.md` YAML frontmatter. This decision is implemented, and the structure test now enforces the exact allowed keys.

## 10. Standalone product boundary and installation

This project is no longer a LinkVault feature. The standalone product is **Mastery Ledger**. Reserve LinkVault for an optional future source connector and do not make the application depend on LinkVault software, storage, APIs, or naming. **Exam Ledger** remains the approved exam-interface concept inside Mastery Ledger.

### One repository, two installable surfaces

Keep the application and skill adapter in one repository initially so schemas, runtime commands, question formats, and web assets are released together:

```text
mastery-ledger/
  pyproject.toml
  src/mastery_ledger/       # Python application, runtime, scheduler, and local server
  web/                      # frontend source
  src/mastery_ledger/web/   # prebuilt frontend included in application releases
  requirements/             # release lock files
  scripts/                  # developer/release bootstrap tools
  skills/mastery-ledger/    # optional thin Codex skill adapter
  tests/
```

Do not create a separate dependency repository. Third-party Python packages come from their official package indexes under release lock files. Native or model artifacts come from explicitly declared providers under recorded hashes. A second repository would add version skew without improving the learner experience at this stage.

Produce two release artifacts from the same version:

1. **Mastery Ledger application/runtime** — installed once and usable without Codex. It owns the web app, course workspace, scheduler, Python environment, yt-dlp integration, transcription, logs, and local API/CLI.
2. **Mastery Ledger skill adapter** — optional and lightweight. It teaches Codex when and how to call the installed runtime, how to ask intake questions, and how to interpret structured results. It does not contain the web application, third-party packages, models, native binaries, or generated course data.

The skill may be bundled as an optional component of the application installer or installed separately from the same release. In either case, the skill first runs `mastery-ledger doctor --json`. If the application runtime is absent or incompatible, return `needs_user_action` with the official installer location. Do not make the skill clone a repository, run an unpinned package installation, or assemble its own competing runtime.

### Installation and onboarding boundary

Keep installation and onboarding distinct:

```text
Install application release
  -> validate locked Python runtime and bundled web assets
  -> optionally install the matching Codex skill adapter
  -> run mastery-ledger doctor
  -> start first-run learner onboarding
```

Installation may acquire the locked Python packages, including `yt-dlp`. First-run learner onboarding may:

- select or create the learning workspace;
- invite sources and exclusions;
- select language and accessibility preferences;
- select a transcription profile;
- show an ASR model's size and request approval before downloading it.

Onboarding must not clone or pull application source, mutate the skill directory, update packages, or download an optional native FFmpeg tool merely because a video URL was supplied.

For development, cloning the single repository and running `bootstrap_runtime.py` is acceptable. For learners, prefer a versioned application release or installer so they do not need Git, Node.js, or knowledge of the repository layout. Build the frontend during release and ship its static output with the Python application; do not require Node.js on the learner's machine.

### LinkVault compatibility

Move any existing LinkVault-specific workflow into a clearly optional adapter after the standalone migration:

```text
connectors/
  linkvault/
```

The core source contract accepts files, URLs, pasted text, and local media without LinkVault. A LinkVault connector may later translate LinkVault records into the same source contract, but it must not own courses, exams, progress, or orchestration.

### Rename status and guardrail

The standalone identity migration is complete: the skill folder, decision record, metadata, command contract, Python package plan, default directories, tests, and documentation use `mastery-ledger`. Keep **Exam Ledger** as the assessment interface name and LinkVault as an optional connector. Do not reintroduce historical product identifiers into core schemas, storage paths, commands, or web-app labels.

### Item 10 decisions to confirm

1. Make Mastery Ledger a standalone application that functions without LinkVault or Codex; Exam Ledger is its assessment interface.
2. Keep application source and the optional Codex skill adapter in one repository and version them together.
3. Install the application/runtime separately; keep the skill adapter thin and incapable of silently constructing another runtime.
4. Install locked Python dependencies with the application, while downloading ASR models only on demand after displaying their size.
5. Ship prebuilt web assets so learner installations do not require Node.js.
6. Keep LinkVault as an optional connector rather than part of the product identity or core storage model.

## 11. Product and skill naming

Use different naming layers intentionally:

- the **product name** describes the learner's enduring outcome;
- the **skill name** identifies the full product workflow to Codex;
- **commands** describe individual operations such as ingestion;
- **interface areas** may use narrower names such as Exam Ledger and Knowledge Wiki.

Do not name the main skill `ingest`. Ingestion covers adding, downloading, extracting, and transcribing sources, but not research, evidence verification, contradiction handling, wiki construction, exam generation, learner scoring, or spaced review. Use `ingest` as a command and workflow name.

### Shortlist

| Candidate | Strength | Weakness | Recommended use |
|---|---|---|---|
| **Mastery Ledger** | Connects the long ownership curve with durable evidence, questions, attempts, and progress | The phrase is not completely unused and still needs formal name/domain checks | Best overall product and main-skill name |
| Learning Ledger | Broad and immediately understandable | Generic; may imply credentials or blockchain learning records | Descriptive fallback |
| Knowledge Ledger | Strong fit for evidence and wiki provenance | Understates tutoring, exams, and review | Internal evidence/wiki component |
| Recall Ledger | Strong spaced-repetition signal | Understates source research and course building | Review scheduler component |
| Exam Ledger | Strong, already approved interface language | Too narrow for the whole knowledge and tutoring system | Exam workspace/module |
| Tutor AI | Familiar description | Generic, difficult to distinguish, and makes the implementation technique the brand | Retire as the product name |

### Recommended naming system

```text
Product:            Mastery Ledger
Repository:         mastery-ledger
Python package:     mastery_ledger
CLI:                mastery-ledger
Main Codex skill:   mastery-ledger
Default user data:  <user-data>/MasteryLedger/

Interface areas:
  Source Inbox
  Knowledge Wiki
  Exam Ledger
  Review Queue
  Evidence & Activity

CLI operations:
  mastery-ledger init
  mastery-ledger ingest
  mastery-ledger research
  mastery-ledger verify
  mastery-ledger build-exam
  mastery-ledger review
  mastery-ledger serve
  mastery-ledger doctor --json
```

Keep one main skill initially:

```yaml
---
name: mastery-ledger
description: Build and maintain source-grounded learning courses from documents, websites, video, audio, or researched material; create a cited knowledge wiki and exam-style assessments; track attempts and schedule long-term mastery reviews. Use when a learner asks to study, understand, research, ingest learning sources, generate an exam, revisit a course, or review due questions.
---
```

Put the source workflow in `workflows/ingest-material.md` and expose it through `mastery-ledger ingest`. Split out a separate `mastery-ledger-ingest` skill only if ingestion later becomes independently useful without the course, wiki, exam, and review lifecycle. Avoid multiple overlapping skills during the first standalone release.

The preliminary search is a collision screen, not trademark, package-index, domain, or legal clearance. Perform exact repository, package, domain, application-store, and trademark checks immediately before the atomic rename and public release.

### Item 11 accepted decision

Adopt **Mastery Ledger** for the standalone product, application, CLI namespace, and main Codex skill. Retain **Exam Ledger** as the exam interface and use **ingest** as an operation rather than the skill's identity.

## 12. Application stack and onboarding ownership

### Accepted stack

Use one local application with a separately built frontend:

```text
React + TypeScript source
        │ release build
        ▼
prebuilt static assets
        │ served same-origin
        ▼
FastAPI on 127.0.0.1
        ├── validated /api/v1 routes
        ├── workspace boundary service
        ├── SQLite application index and durable job queue
        └── course folders remain portable files
```

**Backend:** CPython 3.11 or newer, FastAPI, Uvicorn, Pydantic models, and the standard-library `sqlite3` driver initially. FastAPI owns the loopback API, validation boundary, application lifespan, and delivery of the prebuilt web assets. Bind only to `127.0.0.1`, use a random per-launch session token, keep the UI and API same-origin, and never expose an arbitrary filesystem route.

SQLite stores application-level state that benefits from transactions and queries: the workspace registry, course index, durable job queue, schema versions, and recoverable processing status. It does not replace the course folder. Sources, knowledge pages, exams, attempts, question banks, review history, and auditable logs remain portable course artifacts in the learner-selected workspace.

Media download, subtitle extraction, and transcription are durable application jobs. Do not implement them with FastAPI request-scoped background tasks. Persist a job before execution, run the worker outside the request lifecycle, write outputs through staging and atomic promotion, and recover interrupted jobs after restart.

**Frontend:** React with TypeScript, built as a static single-page application with Vite. React fits the shared state and reusable interaction surfaces in the approved designs: workspace switching, scrollable exam lists, answer-sheet navigation, question feedback states, collapsed citation panels, due queues, and editable review curves. Keep canonical state in backend schemas; store only UI state and unsaved form state in React. Use semantic controls such as real buttons, radio groups, headings, and dialogs.

Vite and Node.js are development and release-build dependencies only. The release pipeline builds the frontend once and copies its output into `src/mastery_ledger/web/`. Learners receive those prebuilt assets and do not need Node.js. Use a pinned lockfile and a relative or explicitly configured base path so packaged assets resolve correctly.

Do not adopt Electron, Next.js, a remote hosted service, or a second Node backend for the first release. They duplicate Python-owned filesystem and media responsibilities or add a runtime the learner does not otherwise need. A thin native shell can be evaluated later if browser-mode folder selection or OS integration proves insufficient.

### Onboarding belongs to the application

The standalone application is the canonical owner of onboarding because onboarding creates durable state and must work without Codex. It owns:

1. the welcome, local-first, and processing-privacy explanation;
2. workspace selection, path canonicalization, write testing, and registry persistence;
3. language and accessibility preferences;
4. dependency and capability checks;
5. explicit approval before downloading an ASR model, including its expected size;
6. the initial review-curve profile, with safe defaults and later editing;
7. an invitation to add the first source now or continue to an empty dashboard.

The skill is an adapter, not a second onboarding implementation. At the beginning of a run it calls `mastery-ledger doctor --json` when the runtime is available. If the runtime reports `onboarding_required`, the skill launches the application's documented onboarding entry point when the runtime supports it, or tells the learner how to open the application. It may pass user-provided source URLs, learning goals, or a proposed workspace path as onboarding hints, but the application must display, validate, and confirm them before persistence.

If the application runtime is unavailable, the skill returns `needs_user_action` with installation guidance. A limited file-only fallback may ask for an output folder for the current run, but it must label that folder provisional and must not pretend it completed application onboarding or write the application registry itself.

### Doctor and automatic launch contract

Keep the root `SKILL.md` as a router and put the exact state machine, JSON shapes, commands, install boundary, and fallback rules in `workflows/runtime-onboarding.md`. This is a conditionally loaded workflow, not a second skill: creating a separate onboarding skill would introduce overlapping triggers and another product identity without providing an independent learner capability.

`mastery-ledger doctor --json` is read-only. It never opens the browser, installs or updates packages, writes a workspace, or downloads a model. For operational course, ingestion, exam, or review requests, the skill interprets its versioned result:

| Doctor result | Behavior |
| --- | --- |
| `ready` | Continue the requested workflow |
| `onboarding_required` | State that first-time setup is needed, then invoke the fixed `mastery-ledger onboard --open --json` command once |
| `workspace_unavailable` | Open application workspace repair when implemented; never silently relocate data |
| `incompatible` | Stop and offer only the verified official update action |
| invalid result or runtime error | Stop and report the observable error |
| launcher not found | Classify as `not_installed`; do not attempt a substitute installation |

Automatic launch is appropriate after `onboarding_required` because an operational Mastery Ledger request already expresses intent to use the local application. Do not launch anything for architecture questions, documentation review, or other non-operational requests. The application command owns loopback startup and browser opening, returns promptly, and is idempotent. Codex does not construct a URL, execute a command returned in JSON, or wait indefinitely for onboarding to finish. On the learner's next continuation, rerun doctor and continue only after `ready`.

Do not automatically download or install Mastery Ledger. When it is absent, offer the verified signed release page or official package-manager action and obtain explicit approval before opening or executing it. Do not ask where to install the software in the normal flow: the installer uses the OS-standard per-user application location. Ask where to store the **learning workspace** during application onboarding. These are different decisions and must not share one path prompt.

The installer owns the application and locked Python environment, including `yt-dlp`. Onboarding may request a learner-approved ASR model download after displaying its expected size. Optional native media-export tools require separate approval. None of these dependencies, models, sources, or generated courses belong in the skill directory.

### First-run and later-run flow

```text
Application launch or skill invocation
  -> mastery-ledger doctor --json
  -> configured: open the active workspace dashboard
  -> onboarding required: open application onboarding
       -> validate and save workspace
       -> record privacy and accessibility preferences
       -> run capability checks
       -> request approval for optional model downloads
       -> optionally add the first source
       -> open Source Inbox or dashboard
```

Workspace changes after onboarding also go through application settings. The skill may request the change, but it must not silently switch, migrate, or rewrite registered workspaces.

### Item 12 accepted decision

Build the standalone runtime with **FastAPI + SQLite** and the interface with **React + TypeScript + Vite**, shipping prebuilt frontend assets inside the Python release. Put canonical onboarding in the application; keep the skill responsible only for detection, launch, context handoff, and a clearly limited fallback.

### Item 12 implementation status

The first executable slice implements:

- the `mastery-ledger` Python package and CLI;
- read-only `doctor-v1` JSON with `ready`, `onboarding_required`, and `workspace_unavailable` behavior;
- an idempotent `onboarding-launch-v1` loopback launcher;
- a random local session bootstrap, HttpOnly same-site cookie, and protected onboarding API;
- SQLite schema creation for workspaces, settings, and the durable job-queue boundary;
- workspace validation and persisted onboarding completion;
- a React and TypeScript onboarding interface with an editable ownership curve;
- a Vite release build copied into the Python package;
- Python contract tests, frontend unit tests, and a real-browser visual acceptance capture.

The following remain release gates rather than completed functionality: signed installers and release manifests, application/skill compatibility-range enforcement, native folder-picker integration, workspace repair UI, the dashboard, durable worker execution, ingestion, exam rendering, and review scheduling.

### Item 12 implementation references

- [FastAPI lifespan events](https://fastapi.tiangolo.com/advanced/events/)
- [FastAPI static files](https://fastapi.tiangolo.com/tutorial/static-files/)
- [FastAPI background-task caveats](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- [React state structure](https://react.dev/learn/choosing-the-state-structure)
- [React guidance on unnecessary effects](https://react.dev/learn/you-might-not-need-an-effect)
- [Vite production builds](https://vite.dev/guide/build.html)

## 13. Codex skill distribution

Keep the `mastery-ledger/` folder as the canonical skill package inside the main repository. Its valid `SKILL.md` frontmatter and one-level package layout are already discovered correctly from the public GitHub repository by the open [`skills` CLI](https://github.com/vercel-labs/skills).

### Recommended one-command install

```text
npx skills add Howard-Starfield/Mastery-Ledger@mastery-ledger -g -a codex -y --copy
```

- `@mastery-ledger` selects the single skill from the mixed application repository.
- `-g` installs to the global user scope.
- `-a codex` prevents installation into unrelated agents.
- `-y` makes the documented command non-interactive.
- `--copy` materializes the skill rather than relying on symlink behavior, which is safer for Codex discovery and Windows installations.

This is a third-party open installer maintained by Vercel Labs, not a native OpenAI command. Retain Codex's bundled `$skill-installer` as the first-party-style fallback: the learner can ask Codex to install the direct tree URL `https://github.com/Howard-Starfield/Mastery-Ledger/tree/main/mastery-ledger`, or run the bundled `install-skill-from-github.py` helper.

Do not publish a custom Mastery Ledger npm installer merely to wrap these existing mechanisms. It would create another package, release channel, and supply-chain surface without improving discovery. Reconsider a dedicated installer only when the standalone application has signed releases and can coordinate application and skill compatibility as one verified installation experience.

Installing the skill never implies that the standalone application is installed. The skill must still run `mastery-ledger doctor --json` and follow the missing-runtime contract.

### Item 13 accepted decision

Document the one-command `npx skills add` flow as the easiest cross-agent installation, explicitly target Codex global scope, use copy mode, retain the bundled Codex installer as a fallback, and keep application installation separate.

## 14. Preview application distribution

The application package can be installed directly from the official GitHub repository with `uv`:

```text
uv tool install "git+https://github.com/Howard-Starfield/Mastery-Ledger.git@main"
```

This path was verified in an isolated tool directory: `uv` resolved and built the package, installed the `mastery-ledger` executable, and `mastery-ledger doctor --json` returned the expected `doctor-v1` `onboarding_required` response. The bundled React assets were available without Node.js.

Treat this as a development-preview channel, not a signed release. The `main` reference is mutable, the source distribution is built on the learner's machine, and no checksum manifest currently freezes the complete dependency graph. The README must label those limits instead of presenting the command as a production installer.

Keep the three user actions distinct:

1. `uv tool install ...` installs the local application in an isolated per-user tool environment.
2. `npx skills add ...` installs the Codex skill adapter.
3. `mastery-ledger onboard --open --json` asks where learner-owned course data should live.

The skill continues to prohibit silent application installation. When the runtime is absent, it may point the learner to the documented preview command for voluntary testing, but it must not execute that command without explicit approval or describe the preview as a signed learner release. Stable distribution remains gated on a versioned tag, immutable artifacts, checksums, compatibility metadata, and release verification.

### Item 14 accepted decision

Use direct `uv tool install` from the official repository as the no-clone preview installation, retain editable installs for contributors, clearly label the mutable unsigned channel, and preserve the separate application, skill, and workspace-onboarding trust boundaries.
