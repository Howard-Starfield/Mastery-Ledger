# Mastery Ledger ChatGPT portability plan

Status: revised after official documentation review; no ChatGPT deployment has been validated yet
Date: 2026-07-21

## Outcome

Build two self-contained runtime skills from shared Mastery Ledger contracts:

- `mastery-ledger/` for Codex, with local filesystem, shell, media helpers, and independent worker orchestration;
- one uploaded `mastery-ledger-chatgpt/SKILL.md` for ChatGPT, with uploaded learner files, web or Deep research, multi-pass self-checks, and downloadable course output.

Do not make either runtime skill read the other skill's `SKILL.md`. The current ChatGPT surface observed in live testing accepts only `SKILL.md`, so compile essential schemas, templates, and host-neutral contracts into that one upload file. Keep the richer Codex package separate. A learner should be able to install the appropriate edition, build a source-grounded course within that host's real capabilities, and receive artifacts that the local Mastery Ledger app can identify by quality level.

The first ChatGPT release should not attempt full cloud parity. It should prove that the ChatGPT edition can:

1. install and trigger a dedicated ChatGPT package correctly;
2. preserve the Fast Course and Verified Course rules;
3. use only capabilities that ChatGPT actually exposes in the current conversation;
4. create a downloadable draft course bundle when durable filesystem access is unavailable;
5. handle YouTube links without pretending it can download inaccessible media or captions; and
6. label multi-pass self-checking separately from independent verification.

## Current product facts

- ChatGPT Skills can contain instructions, supporting resources, and code. Eligible users can create a skill with chat, use the Skills editor, or upload a skill from a computer.
- OpenAI says ChatGPT Skills and Codex Skills follow the Agent Skills open standard. The current Mastery Ledger directory already follows its core folder shape: `SKILL.md`, `scripts/`, `references/`, and `assets/`.
- The Agent Skills specification supports relative links from `SKILL.md` to bundled files and recommends shallow, direct references. It does not define a portable mechanism for one skill to load another separately installed skill's `SKILL.md`.
- OpenAI's API guidance requires exactly one `SKILL.md` manifest per uploaded skill bundle. Multiple skills are separate bundles; a plugin is the documented distribution unit for bundling multiple skills or skills plus apps.
- Personal Skills are generally available for ChatGPT Business, Enterprise, Healthcare, and Edu. Enterprise and Edu administrators control creation, upload, installation, and sharing.
- ChatGPT Deep research can use uploaded files, the public web, specified sites, and enabled apps, and produces a report with citations or source links.
- ChatGPT Workspace Agents can attach skills and files, use web search and configured apps or tools, and optionally use a persistent memory folder. This does not document a skill-callable subagent spawning facility.
- OpenAI documents common ChatGPT uploads as documents, spreadsheets, presentations, and text. No official ChatGPT Skill contract promises `yt-dlp`, direct YouTube media or caption download, or arbitrary network access from bundled scripts.
- A ChatGPT plugin can package skills with apps or app templates. An app remains the integration boundary for external data, persistence, and actions.
- Custom GPTs remain a separate product surface. They can combine instructions, uploaded knowledge, capabilities, apps, or Actions. A GPT can use apps or Actions, but not both at the same time.

Sources:

- [Skills in ChatGPT](https://help.openai.com/en/articles/20001066)
- [Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Skills in the OpenAI API](https://developers.openai.com/cookbook/examples/skills_in_api)
- [ChatGPT Workspace Agents](https://help.openai.com/en/articles/20001143)
- [Supported ChatGPT file uploads](https://help.openai.com/en/articles/8983675-what-types-of-files-are-supported)
- [Plugins in ChatGPT and Codex](https://help.openai.com/en/articles/20001256)
- [Deep research in ChatGPT](https://help.openai.com/en/articles/10500283-deep-research-faq)
- [Creating and editing GPTs](https://help.openai.com/en/articles/8554397-creating-a-gpt)
- [Configuring actions in GPTs](https://help.openai.com/en/articles/9442513)
- [Agent Skills specification](https://agentskills.io/specification)

## Research verdict

The separate-skill direction is correct, with one important refinement: create a generated, self-contained ChatGPT edition rather than a manually maintained clone.

| Concern | Finding | Design consequence |
| --- | --- | --- |
| YouTube downloader | No documented native ChatGPT Skill capability guarantees media or caption download | Remove `yt-dlp` and local-ASR branches from the ChatGPT package; prefer learner-supplied transcript, captions, notes, or supported documents |
| Subagents | No documented ChatGPT Skill tool guarantees spawning isolated workers | Replace worker orchestration with explicit sequential recheck passes and never call them independent |
| Supporting Markdown | The broader format permits resources, but the tested ChatGPT uploader accepted only `SKILL.md` | Embed every required runtime contract directly in the ChatGPT `SKILL.md`; keep companion files authoring-only |
| Another skill's `SKILL.md` | Cross-skill runtime linking is not an Agent Skills portability contract | Do not depend on the Codex skill being installed or readable |
| Drift between editions | Two hand-edited clones will diverge | Treat the ChatGPT file as a compiled host-specific edition and test the embedded contracts against the canonical Codex rules |

Silence in the documentation is not proof that a capability can never exist. It is enough reason not to make that capability a required workflow dependency until a live ChatGPT test proves it.

### Current package audit

After excluding Python caches, the existing Codex skill contains 99 files totaling 611,721 bytes; its largest file is 39,360 bytes. That is comfortably below the OpenAI API's documented ceilings of 500 files, 50 MB per ZIP, and 25 MB per uncompressed file. ChatGPT UI upload still needs a live test because its scanner and entitlements are a separate product boundary.

The Codex `SKILL.md` has 27 direct local links that resolve inside `mastery-ledger/`, but live ChatGPT upload testing showed that those companions are not accepted by the target surface. Therefore the ChatGPT upload manifest must contain no local runtime links at all.

The ChatGPT source tree keeps only the self-contained `SKILL.md` plus optional repository UI metadata. The builder emits exactly one UTF-8 file named `SKILL.md`; no companion references, assets, scripts, or generated files enter the upload artifact.

## Corrected interpretation of the proposed ChatGPT workflow

The proposed planner, researcher, contrarian, fact-checker, and editor pattern is useful, but in the ChatGPT edition these are named verification passes performed by one agent unless an external reviewer tool is explicitly configured. A role label does not create independence.

Use this mapping instead:

| Proposed role | ChatGPT edition behavior | Quality meaning |
| --- | --- | --- |
| Research planner | Create and freeze the source and question plan | Planning pass, not a separate agent |
| Foundation and evidence researchers | Extract one source at a time into a claim ledger | Source-isolated passes within the same agent run |
| Contrarian reviewer | Re-read the frozen claims specifically for conflicts, omissions, and overstatement | Adversarial self-check |
| Fact checker | Verify each retained claim against its cited locator | Citation self-check |
| Study-guide editor | Author only from the retained claim ledger | Synthesis pass |
| Exam checker | Audit questions after lessons and questions are frozen | Assessment self-check |

Deep research may supply a cited research artifact, but it is not automatically proof that Mastery Ledger's isolated extractor, contradiction, citation, and assessment contracts were satisfied. The ChatGPT skill must register the report as a source and validate its claims like any other source. Same-agent rechecking can catch errors, but it cannot receive the Codex edition's `VERIFIED` publication label.

## Target architecture

```text
                    build-time shared core
       schemas, citation rules, lesson rules, templates, tests
                                  |
                +-----------------+------------------+
                |                                    |
      Codex package generator              ChatGPT manifest compiler
                |                                    |
       mastery-ledger/              mastery-ledger-chatgpt/SKILL.md
    multi-file Codex skill             one-file ChatGPT skill
 local files, yt-dlp, workers       uploads, web/deep research, rechecks
                |                                    |
                +-----------------+------------------+
                                  |
                 portable course artifact schemas
                                  |
                     local Mastery Ledger app

Later full-parity path:

ChatGPT skill -> approved Mastery Ledger app/API -> durable storage + independent review orchestration
```

### Portable core

Keep in the build-time shared core and copy into both skill artifacts:

- the first-turn learning gate;
- Fast Course and Verified Course selection;
- source, citation, lesson, assessment, event, and artifact contracts;
- host-neutral validators and renderers;
- quality labels and fail-closed publication rules;
- the portable course bundle format.

Keep host-specific behavior in the corresponding skill entrypoint and overlay:

- Codex worker tool names and lifecycle calls;
- ChatGPT upload, memory, and export instructions;
- ChatGPT Deep research handoff;
- app or Action authentication;
- local shell and filesystem assumptions.

The ChatGPT artifact is exactly one UTF-8 file named `SKILL.md`, with only `name` and `description` in frontmatter. Embed every required runtime rule and compact artifact contract in that file. Do not use local links, symlinks, repository paths, companion resources, or instructions to open `mastery-ledger/SKILL.md`.

The ChatGPT `SKILL.md` must have zero companion-file dependencies. Keep it below 500 lines and 5,000 words while embedding the intake, media, source, citation, artifact, recheck, lesson, assessment, tutoring, proficiency, and delivery contracts. Omit the entire worker lease, spawn, attach, poll, repair, and close protocol.

### ChatGPT media intake

Use this order:

1. Accept a learner-uploaded transcript, notes file, PDF, presentation, or supported text document. Accept `.srt` or `.vtt` when the live surface permits it; otherwise ask the learner to export the captions as `.txt`.
2. For a public video URL, do not watch, listen to, transcribe, download, or extract captions. Treat any visible page details as metadata only.
3. Ask the learner to upload an existing transcript, captions, or notes. Do not create a course from the title and description while implying the video was reviewed.
4. Do not offer transcription as a ChatGPT capability or redirect the learner to another ChatGPT mode for transcription.
5. Do not include or invoke `yt-dlp`, FFmpeg, local ASR, cookies, media-download scripts, or transcript-extraction tools in the ChatGPT edition.

### ChatGPT recheck contract

Freeze an artifact before each recheck so later passes evaluate observable work instead of silently rewriting it:

1. `source-plan.json`: approved sources and scope.
2. `claim-ledger.json`: claims, locators, uncertainty, and source IDs.
3. `contradiction-check.json`: conflicts, gaps, and required removals.
4. `citation-check.json`: claim-by-claim support decision.
5. Lessons and questions authored from retained claim IDs only.
6. `assessment-check.json`: answer, distractor, citation, and ambiguity audit.

Record these as same-agent checks. Use `DRAFT_UNVERIFIED` until a human or genuinely separate reviewer validates the frozen artifacts. A future schema may add a learner-facing `SELF_CHECKED` badge, but that must not be treated as `VERIFIED` or silently unlock ready exams and spaced-review scheduling.

### Capability contract

At the start of a durable operation, record observed capabilities rather than identifying the host by name:

```json
{
  "schema_version": "runtime-capabilities-v1",
  "persistent_filesystem": "available|temporary|unavailable|unknown",
  "script_execution": "available|unavailable|unknown",
  "web_research": "available|unavailable|unknown",
  "deep_research": "available|unavailable|unknown",
  "independent_workers": "available|unavailable|unknown",
  "downloadable_files": "available|unavailable|unknown",
  "external_app": "available|unavailable|unknown",
  "observations": []
}
```

Do not infer one capability from another. Skill upload does not prove that Python, a persistent workspace, Deep research, or independent workers are available.

### Persistence modes

1. `local-workspace`: Codex or another agent writes directly to the learner-selected course folder.
2. `downloadable-bundle`: ChatGPT creates the course in temporary working storage, validates it, and returns a ZIP for the learner to import into the desktop app.
3. `remote-workspace`: a future Mastery Ledger app/API stores courses durably and returns stable course IDs and exports.
4. `chat-only`: no durable files are possible; tutor provisionally but do not claim a created or published course.

The recommended ChatGPT MVP is `downloadable-bundle`. It preserves the local-first product while avoiding a cloud service before the skill behavior is proven.

## Delivery phases

### Phase 0: capability spike

Goal: learn what the user's actual ChatGPT account and surface expose.

1. Build and upload a minimal one-file `mastery-ledger-chatgpt/SKILL.md` spike.
2. Record plan, surface, administrator policy, upload result, scan result, and installed skill version.
3. Run a non-writing trigger test.
4. Confirm the skill does not request references, assets, or scripts.
5. Test creation and download of a small learner artifact separately from skill upload.
7. Confirm that the base workflow succeeds without any worker/subagent facility; record a worker capability only if ChatGPT exposes a documented callable tool.
8. Test whether Deep research can be deliberately invoked or consumed from the skill workflow; do not assume that ordinary web search is Deep research.
9. Test a YouTube-only prompt and confirm the skill requests usable source content rather than inventing transcript access.
10. Test a supplied transcript and confirm the Fast Course path works without media download.

Exit: a checked capability matrix based on observed behavior, not documentation alone.

### Phase 1: Codex package plus one-file ChatGPT build

Goal: preserve the multi-file Codex skill while compiling a self-contained one-file ChatGPT edition.

1. Keep `mastery-ledger/` unchanged as the working Codex package during the first slice.
2. Compile the ChatGPT workflow, media policy, source and citation rules, compact artifact schemas, recheck contract, lesson rules, assessment rules, and tutoring behavior into its `SKILL.md`.
3. Add a deterministic builder that emits `dist/mastery-ledger-chatgpt-upload/SKILL.md` and rejects all local runtime links or forbidden Codex/media dependencies.
4. Test frontmatter, required embedded contracts, exact output name, one-file output, UTF-8 encoding, and context budget.
5. Forward-test topic-only and YouTube-only behavior using only the manifest.

Exit: the Codex package still passes its existing tests, and the standalone ChatGPT `SKILL.md` passes structure tests and ChatGPT upload scanning.

### Phase 2: ChatGPT downloadable-bundle MVP

Goal: build usable courses without Codex or a hosted backend.

Implementation status: the one-file ChatGPT skill now embeds the exact `mastery-ledger-course-bundle-v1` ZIP layout and preflight. The application exposes a raw-ZIP import endpoint and Study-panel import control; the backend validates a single safe root, text-only paths, size limits, required `course-layout-v2` artifacts, schemas, cross-file IDs, draft status, and source files before an atomic install under `workspace/courses/`. Imported lessons remain visibly `DRAFT_UNVERIFIED`, with exams and mastery updates disabled.

1. Keep the `mastery-ledger-course-bundle-v1` contract embedded in the ChatGPT `SKILL.md`, including exact paths, schemas, publication status, validation records, and archive limits.
2. Keep export validation in the skill's ordered ZIP preflight because the target ChatGPT uploader provides no companion scripts.
3. Maintain the desktop-app import path that validates and atomically copies a course into the selected collection workspace without trusting archive paths.
4. Support Fast Course from uploaded transcripts and documents first.
5. Support topic-only research by registering a Deep research report and its cited sources as evidence inputs.
6. Run the frozen-artifact recheck sequence and retain its receipts.
7. Keep same-agent work `DRAFT_UNVERIFIED`; do not activate mastery or mark an exam ready.
8. Add an explicit draft-import or preview surface to the app before claiming the app can display these bundles.

Exit: a ChatGPT-created ZIP imports as a clearly labeled draft, passes structural validation, and cannot be mistaken for an independently verified Codex course.

### Phase 3: verified-course parity service

Goal: restore durable courses and genuine independent verification from ChatGPT.

Build a narrow Mastery Ledger remote service or ChatGPT app with operations such as:

- create or resume a course;
- upload and register a source;
- propose and approve scope;
- start a bounded research run;
- inspect run status and blockers;
- submit an explicit rights authorization;
- retrieve approved evidence;
- validate and export a course bundle.

The service, not the conversational model, owns durable run state, task leases, worker identities, hashes, validation receipts, and retries. It may use the OpenAI API to run isolated worker contexts, but must preserve the existing rule that only the orchestrator approves evidence.

Package the portable skill and app together as a ChatGPT plugin when the product surface and workspace policy allow it. Keep a Custom GPT with Actions only as a compatibility or demonstration shell; do not make it the source of truth.

Exit: ChatGPT can resume a course in a later conversation, run real independent reviewers, and produce the same validated bundle without local Codex access.

### Phase 4: release and sharing

1. Add cross-host behavior cases for ChatGPT trigger, supplied material, topic-only research, no-worker execution, missing script execution, interrupted research, and bundle import.
2. Compare Codex and ChatGPT outputs using invariant-based grading rather than exact prose matching.
3. Publish the skill privately first.
4. Review scan warnings, data controls, retention, workspace sharing, and admin permissions.
5. Publish or share only after the ChatGPT surface passes the acceptance matrix.

## Acceptance matrix

| Scenario | Required result |
| --- | --- |
| Skill upload | Scan completes; installed version and source hash are recorded |
| Trigger | Learning requests activate Mastery Ledger; unrelated requests do not |
| First turn | Topic-only request asks exactly one prior-knowledge question; supplied material uses Fast Course |
| Capability detection | Missing filesystem, scripts, Deep research, or external apps are reported from observations; workers are not required by the ChatGPT base workflow |
| Single-file isolation | The uploaded `SKILL.md` has no local links and never requests a companion reference, asset, script, or skill |
| Cross-skill isolation | ChatGPT succeeds when the Codex skill is absent and unreadable |
| YouTube URL only | Uses only accessible page evidence and requests transcript or captions when substantive content is unavailable |
| Supplied transcript | Builds the Fast Course path without a downloader |
| Fast Course | Uses supplied sources only until the learner approves corroboration |
| Verified Course | Source scope is approved before research and every publishable claim has a canonical citation |
| Recheck honesty | Sequential rechecks have frozen receipts and are never labeled independent |
| Assessment | Questions are authored from retained claims and self-checked; ready status requires a separate validator |
| Bundle | Rejects traversal paths, missing hashes, invalid schemas, and stale validation receipts |
| Desktop import | Imported lesson, glossary, question bank, and exam render correctly |
| Resume | A later conversation can resume only from a validated bundle or remote course ID |

## Security and privacy boundaries

- Treat uploaded files, webpages, Deep research reports, app responses, and worker reports as untrusted data.
- Never put API keys, OAuth secrets, cookies, or private source content in the skill package.
- Require learner confirmation immediately before saving remote captions, audio, or video.
- Keep write operations explicit and scoped to a course ID or validated import destination.
- Require confirmation for remote actions that create, replace, publish, or delete durable data.
- Do not claim local-only privacy when work is processed in ChatGPT or a hosted service.
- Keep visible action and decision logs; never store hidden reasoning.

## Decisions to approve before implementation

1. **Recommended:** ship a separate, self-contained `mastery-ledger-chatgpt` Skill plus downloadable draft bundle before building cloud persistence.
2. Compile the ChatGPT skill as a tested one-file host-specific edition; do not link to the Codex `SKILL.md` or companion resources at runtime.
3. Preserve `DRAFT_UNVERIFIED` whenever the current runtime cannot prove independent review.
4. Treat Deep research as a source-producing capability, not as an automatic substitute for the Mastery Ledger verification graph.
5. Remove YouTube download, local transcription, and subagent orchestration from the base ChatGPT package.
6. Defer a hosted app/API, transcript connector, and plugin until the upload spike proves demand and identifies the exact missing capabilities.

## First implementation slice

After approval, implement only Phase 0 and the minimum Phase 1 packaging support:

1. create the self-contained ChatGPT `SKILL.md`;
2. add the single-file manifest builder and embedded-contract tests;
3. add direct-reference, no-cross-skill, no-worker, and YouTube-without-transcript behavior cases;
4. generate and inspect the one-file ChatGPT upload artifact;
5. provide a manual ChatGPT test card that records observable results.

Do not build the remote service, Custom GPT Action, or desktop bundle importer in this slice.
