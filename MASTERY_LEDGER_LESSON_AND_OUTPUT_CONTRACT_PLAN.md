# Mastery Ledger lesson and course-output contract plan

Status: implemented and deterministically tested; fresh-runtime acceptance remains  
Date: 2026-07-21  
Incident re-examined: Codex task `019f83bb-0af7-73a0-9849-9800fc0a5e5b`

## Purpose

Make Mastery Ledger reliably produce a small, source-grounded course that reads like a short book, includes a validated question bank and ready exam, and leaves a clean course folder. Remove the Knowledge Wiki from the skill because it duplicates lesson content and is not required by the offline exam application.

This document records the implementation contract and incident rationale. `MASTERY_LEDGER_DESIGN_DECISIONS.md` now reflects the implemented repository contract.

## Fresh findings

The latest failed run did create useful material, but it exposed five separate contract problems:

1. The installed runtime exposed `multi_agent_v1__spawn_agent`, but the run never invoked it. The course therefore has no accepted worker task directories under `.work/runs/`.
2. The approved course used `provided-material-only` with `research_workers: 0`. The workflow still treated a non-empty research graph as a prerequisite for `TASKS_PLANNED`, so it stopped at `CORPUS_MAPPED` even though the supplied video had been downloaded, transcribed, and registered.
3. The generated chapter is only about 407 words. The current lesson asset contains two headings and one sentence of guidance, while publication validation accepts any lesson longer than 100 characters. That is a structural check, not a book-like lesson contract.
4. The draft bank has eight questions, including one free-response item, and no `exams/<exam-id>/exam.json`. It therefore cannot meet the current 10-item, 80/20 selectable-response contract or appear as a ready exam in the application.
5. Publication validation currently depends on orchestration plans and worker completions under `.work/`, even though the artifact lifecycle describes `.work/` as disposable. Accepted validation receipts need a durable home before `.work/` can be cleaned safely.

The failure is not simply “the test bank is missing.” A draft bank exists. The missing result is a source-grounded lesson plus an independently validated bank and app-compatible ready exam.

## Product boundary

### The skill will

- ask where the course workspace belongs before its first durable write;
- ask whether the learner has preferred or required sources and allow later sources to join the same course;
- acquire or inspect only authorized sources;
- preserve source locators and human-verifiable provenance;
- use bounded subagents for independent extraction, research, contradiction review, citation checking, assessment generation, and assessment validation when the selected mode requires them;
- synthesize approved evidence into a coherent course index and book-like lessons;
- create a canonical question bank, Markdown review copy, and at least one independently validated ready exam;
- keep observable action records without storing hidden chain-of-thought.

### The skill will not

- create or maintain a knowledge wiki;
- require the offline application to be installed in order to build a course;
- install or update `yt-dlp`, FFmpeg, transcription models, or other dependencies silently;
- browse beyond the learner-approved topic, source policy, and source budget;
- publish facts from model memory when the approved evidence does not support them;
- convert missing evidence into confident prose or filler questions;
- treat a structurally valid draft as a verified course;
- claim that a ready exam exists until an independent assessment validator and the deterministic publication checks pass.

## Output decision

### Keep `exams/`

The root `exams/` folder should remain. It is not redundant with `questions/`:

- `questions/question-bank.json` is the canonical authoring and review bank;
- `exams/<exam-id>/exam.json` is a read-only delivery snapshot consumed by the application, even though the skill may explicitly rebuild it later;
- a course may have chapter, cumulative, and mock exams without changing the bank;
- the application currently discovers only ready files at `exams/<exam-id>/exam.json`.

Removing `exams/` would couple the application to draft authoring data and require a larger application migration. Keeping it preserves the clean skill/application boundary.

### Remove duplicate learner artifacts

Retire these generated outputs:

- `wiki/` and `wiki/wiki.json`;
- `study-guide.md`;
- `concept-map.md` as a separate learner document;
- `glossary.md` as a separate learner document.

Replace them as follows:

- `index.md` becomes the concise course landing page, chapter sequence, prerequisite map, and course-level limitations record. It is navigation, not a wiki.
- Definitions, examples, misconceptions, and limitations live where the learner needs them inside each lesson.
- The staged curriculum/concept map remains under `.work/` during synthesis. Stable concept IDs remain durable in `questions/question-bank.json` and `progress/learner-progress.json`.

This removes repeated prose and lets the token budget go toward substantive lessons.

## Proposed course layout

```text
course/
  course.yaml                 # when created by the application
  study.yaml                  # skill workflow, scope, and publication state
  index.md                    # concise learner-facing course map
  lessons/
    CH-001-topic.md           # book-like source-grounded chapters
  questions/
    question-bank.json        # canonical validated question bank
    question-bank.md          # generated human review copy
  exams/
    EXAM-001/
      exam.json               # app-facing ready delivery snapshot
  attempts/                   # application-owned learner history
  progress/                   # calibration, mastery, and review state
  records/                    # durable provenance and audit material
    source-manifest.yaml
    source/
      SRC-001.md              # extracted source knowledge
      media/
        SRC-001/              # originals, captions, transcripts, audio/video
    evidence/
      approved-claims.json
      contradictions.json
      gaps.json
      validation/
        RUN-RESEARCH/
          TASK-CITATION-VERIFY.json
        RUN-ASSESSMENT/
          TASK-ASSESSMENT-VALIDATE.json
        publication-receipt.json
    logs/
      events.jsonl            # append-only observable action log
  .work/                      # disposable and never learner-facing
    ingestion/
    orchestration/
    runs/
      <run-id>/tasks/<task-id>/
    staging/
    drafts/
    scratch/
```

`records/` is durable and human-auditable. `.work/` is temporary execution state. Durable sources, evidence decisions, contradictions, accepted validation receipts, and action events must never be hidden under `.work/`, because `.work/` may be cleaned after a run. The root of `records/source/` contains extracted knowledge Markdown plus `media/`; the manifest stays beside that folder so the source root does not become a mixture of content and control files.

### Path migration

| Current path | Proposed path or disposition |
| --- | --- |
| `source-manifest.yaml` | `records/source-manifest.yaml` |
| `source/` | `records/source/` |
| `evidence/` | `records/evidence/` |
| `logs/` | `records/logs/` |
| `study-guide.md` | merge useful course orientation into `index.md` |
| `concept-map.md` | use `.work/` while drafting; keep durable IDs in bank/progress |
| `glossary.md` | move definitions into the relevant lessons |
| `wiki/` | retire; do not generate for new courses |
| `lessons/` | keep |
| `questions/` | keep |
| `exams/` | keep |
| `attempts/` and `progress/` | keep |

Existing courses require an explicit, non-destructive migration. Obsolete files should be moved to a timestamped `.work/migration-backup/` only after their useful content has been merged and the new layout passes validation. A migration must never silently delete learner content.

## Research basis for the lesson contract

There is no universal best chapter template. The proposed contract combines the strongest compatible parts of several authoritative or established instructional-design sources:

| Guidance | What Mastery Ledger adopts |
| --- | --- |
| [Carnegie Mellon Eberly Center: learning objectives](https://www.cmu.edu/teaching/designteach/design/learningobjectives.html) and [alignment](https://www.cmu.edu/teaching/assessment/basics/alignment.html) | Student-centered, measurable objectives; lesson activities and assessments must test the same actions named by the objectives. |
| [IES/What Works Clearinghouse practice guide](https://ies.ed.gov/ncee/wwc/PracticeGuide/1) | Worked examples, concrete-to-abstract connections, active retrieval, spaced review, and deep explanatory questions. |
| [CAST UDL Guidelines 3.0](https://udlguidelines.cast.org/action-expression/) | Clarify vocabulary, connect prior knowledge, highlight relationships, support transfer, and use accessible representations when the source supports them. |
| [Open at Scale chapter template](https://ecampusontario.pressbooks.pub/openatscale/chapter/template/) | Predictable chapter framing: outcomes, prior-knowledge activation, content, reflection, and key takeaways. |
| [OpenStax pedagogical features](https://openstax.org/books/psychiatric-mental-health/pages/preface) | Learning outcomes, definitions in context, checks for understanding, summaries, references, and a separate test bank. |
| [NBME Item-Writing Guide](https://www.nbme.org/sites/default/files/2021-02/NBME_Item%20Writing%20Guide_R_6.pdf) | One-best-answer items, homogeneous plausible distractors, curricular alignment, and avoidance of irrelevant item difficulty. |

The word counts, question counts, 80/20 mix, source budget, and agent limits below are Mastery Ledger product rules. They are not claimed as universal educational laws.

## Normative lesson contract

Every published chapter must read as a guided explanation, not as extracted notes, a transcript summary, or a list of facts.

### Chapter metadata

Each lesson must declare:

- chapter ID and title;
- publication status;
- 2-5 measurable learning objectives;
- prerequisites and the prior chapter, when applicable;
- estimated reading time;
- stable concept IDs;
- source IDs used;
- last-updated date.

Use one machine-readable YAML frontmatter block and stable inline reference IDs. The lesson frontmatter stores complete `source-ref-v1` objects; the prose cites their `ref_id` values. This keeps the Markdown readable while giving validation an exact object to inspect.

```markdown
---
schema_version: lesson-v1
chapter_id: CH-001
title: Why expectations move a stock price
status: validated
objective_ids: [OBJ-001, OBJ-002]
concept_ids: [C-EXPECTATIONS, C-SURPRISE]
prerequisite_chapter_ids: []
estimated_minutes: 12
last_updated: 2026-07-21
source_refs:
  - ref_id: REF-001
    source_id: SRC-001
    item_id: LESSON-001
    locator:
      kind: timestamp_range
      start_ms: 1483200
      end_ms: 1511200
      label: "00:24:43.200-00:25:11.200"
    supports: [claim, explanation]
    support_strength: direct
---

A profitable company can fall when its result is worse than the market had already priced in.[^REF-001]

## Sources used

[^REF-001]: [SRC-001] Video title — 00:24:43.200-00:25:11.200
```

The `ref_id` is a Markdown binding key, not a replacement for the canonical source ID and locator. Every inline `[^REF-NNN]` marker must resolve to exactly one frontmatter object and one learner-readable footnote. Unused references, unresolved markers, bare URLs used as evidence, or footnotes without structured objects fail validation.

### Required narrative order

1. **Opening problem or scenario** — show why the concept matters without assuming the answer.
2. **Prior-knowledge bridge** — connect the lesson to what the learner already knows and define missing prerequisites.
3. **What you will be able to do** — list 2-5 measurable objectives using observable verbs.
4. **Big picture** — give a short mental model before details.
5. **Core explanation** — progress from definitions to mechanism, relationships, and consequences in coherent prose.
6. **Vocabulary in context** — define terms when first used; do not defer basic definitions to a separate glossary.
7. **Worked example 1** — model the complete reasoning or procedure step by step.
8. **Worked example 2** — apply the idea to a different case, counterexample, or comparison.
9. **Pause and retrieve** — include 2-4 ungraded checks that ask the learner to recall, explain, compare, or predict before reading the answer.
10. **Common misconceptions** — explain at least one plausible wrong model and why it fails.
11. **Limitations and uncertainty** — state where the explanation does not apply, where sources disagree, or what the corpus cannot establish.
12. **Transfer or practical use** — show how to recognize or apply the concept in a new situation.
13. **Key takeaways** — return to the objectives with a concise summary.
14. **What comes next** — explain the dependency on the next chapter, if any.
15. **Sources used** — list canonical source IDs and precise locators. These may render collapsed in the application, but must remain in the Markdown.

### Course `index.md` contract

Keep the course landing page concise. It contains only:

- course outcome, intended learner level, and source mode;
- a chapter table with chapter title, one-sentence summary, status, estimated reading time, and question count;
- prerequisite order and recommended reading sequence;
- ready-exam links/status;
- unresolved limitations, source count, and last-updated date.

Do not turn `index.md` into a second textbook, glossary, concept encyclopedia, or global knowledge catalog.

### Depth and size limits

- Standard core chapter: 1,200-1,800 words.
- Expanded core chapter: 1,800-2,500 words only when the approved scope genuinely needs the depth.
- Above 2,500 words: split into prerequisite-ordered chapters instead of continuing one long article.
- Initial build: 1-3 chapters by default and no more than 5 without renewed learner approval.
- Every major factual section must have resolvable source support. A citation at the end of an unrelated long chapter is insufficient.
- The main agent must report a gap rather than pad a short chapter with unsupported detail.

Word count is a guardrail, not the quality proof. Publication also requires objective alignment, narrative continuity, worked examples, retrieval checks, misconceptions, limitations, and verified locators.

### Lesson ownership

The main agent writes and normalizes the final lesson voice from approved evidence. Source extractors and research workers do not write final chapters. This prevents a course from becoming concatenated worker summaries with inconsistent vocabulary, depth, or assumptions.

An independent pedagogy reviewer is conditional, not universal. Require it for high-stakes domains, more than three chapters, substantial notation, or when the deterministic lesson validator reports cognitive-load or alignment warnings. The independent assessment validator remains mandatory for every ready exam.

## Question-bank and exam contract

### Minimum and expansion tiers

Every published chapter has at least 10 selectable-response questions:

| Tier | Total | Concise standalone MCQ | Short-reading/passage MCQ | Approval |
| --- | ---: | ---: | ---: | --- |
| Standard | 10 | 8 | 2 | default |
| Expanded | 15 | 12 | 3 | learner approves expansion or the scope card selects it |
| Large | 20 | 16 | 4 | explicit renewed approval |

Do not emit 11-14 or 16-19 questions, because those sizes make the required 80/20 mix ambiguous. Optional material does not become a mastered chapter until it has at least the standard 10-item bank.

At least one ready exam must contain 10 or more independently validated questions. A multi-chapter course may build additional chapter or cumulative exams from the same validated bank.

### Item requirements

Every published item must:

- be multiple-choice with four options and exactly one defensible best answer;
- map to one or more lesson objectives and stable concept IDs;
- test taught content rather than trivia found only in a source;
- cite support for the answer and explanation with canonical locators;
- use distractors based on plausible misconceptions or reasoning errors;
- include a concise correct-answer explanation and distractor rationales;
- avoid `all of the above`, `none of the above`, trick wording, grammatical cues, and answer-length cues;
- have `quality_status: validated` only after independent validation.

Short-reading questions remain multiple-choice. Open response may be used in calibration or ungraded lesson reflection, but it cannot satisfy the published 80/20 bank or ready-exam minimum.

## Scope and hallucination guardrails

The scope card must state, before fan-out:

- learner outcome and assumed level;
- required concepts and 1-5 proposed adjacent branches;
- excluded topics;
- source mode: `provided-material-only`, `topic-research`, or `hybrid`;
- retained-source limit;
- chapter count and lesson depth tier;
- question tier per chapter;
- expected worker roles and maximum research fan-out;
- permissions required for downloads, captions, or local transcription.

Recommended initial defaults are up to five retained sources, up to three research concept groups, 1-3 chapters, and the standard 10-question tier. These are proposed defaults, not hidden hard caps. If the learner approves eight sources, the plan must account for all eight or explicitly return for a revised scope; it must not silently process only five.

Published material may contain only:

1. facts directly supported by approved evidence;
2. clearly labeled synthesis that follows from multiple supported facts;
3. clearly labeled inference whose premises and uncertainty are visible;
4. learner-visible limitations and unresolved contradictions.

Model memory may help propose a search query, example type, or explanation outline. It may not become a published factual claim without evidence. Search snippets are discovery leads, not evidence. If a source cannot be opened or a locator cannot be resolved, the related claim stays rejected or provisional under `.work/`.

## Deterministic workflow and delegation

### Required ordering

```text
workspace and source intake
  -> learner calibration and approved scope card
  -> source acquisition/registration
  -> mode-specific evidence tasks
  -> contradiction filtering when multiple claims/sources can conflict
  -> final citation verification of retained claims only
  -> main-agent evidence approval
  -> main-agent index and lesson synthesis
  -> deterministic lesson validation
  -> assessment generation
  -> independent assessment validation
  -> question-bank promotion and Markdown rendering
  -> ready-exam build and publication validation
  -> LEARNING_ACTIVE
```

Citation verification runs after contradiction filtering so it does not spend tokens reopening claims that will be rejected. Assessment workers run only after evidence approval and substantive lessons, so rejected research never consumes assessment tokens.

### Mode-specific worker topology

#### One supplied source

```text
source extractor (one assigned source)
  -> citation verifier
  -> main-agent lesson synthesis
  -> assessment generator
  -> independent assessment validator
```

No research worker is required when the approved course is limited to the supplied source. A contradiction reviewer is required only when the source contains internally conflicting claims or the course adds another source. The absence of research workers must not block the provided-material branch.

#### Multiple supplied sources or hybrid course

```text
one isolated source extractor per retained source, in parallel
  + bounded research workers for approved coverage gaps
  -> one contradiction reviewer after all submissions are accepted
  -> one final citation verifier for retained claims
  -> main-agent synthesis
  -> assessment generator
  -> independent assessment validator
```

#### Topic-only researched course

```text
source scout
  -> main-agent candidate selection and registration
  -> one isolated extractor per retained source
  + bounded concept research workers
  -> contradiction reviewer
  -> citation verifier
  -> main-agent synthesis
  -> assessment generator
  -> independent assessment validator
```

### Delegation contract

The main agent must inspect direct and deferred worker tools before declaring workers unavailable. Capability detection is a runtime action, not a persisted assumption in a run plan.

For each task, deterministic tooling must generate:

- one role and one bounded objective;
- exact dependency IDs;
- approved input paths;
- required contract paths;
- one task-local output path under `.work/runs/<run-id>/tasks/<task-id>/`;
- a prefilled completion envelope and event-shard path;
- stop conditions and prohibited actions;
- an immutable dispatch message.

Workers must read the generated brief, role profile, required contracts, output template, and completion template before work. They may write only inside their assigned task directory. The completion router accepts or repairs the same task; workers never promote canonical course files.

After an accepted worker result, deterministic promotion writes a compact receipt under `records/evidence/validation/`. A receipt contains the run/task IDs, role and role-profile hash, accepted input/output hashes, observable decision, validated claim or question IDs, limitations, and timestamp. It contains neither hidden reasoning nor the full worker scratch output. Publication validation uses these durable receipts; it must not require `.work/` to remain forever.

The main agent remains responsible for:

- scope and cost authorization;
- tool-capability inspection;
- dependency-safe dispatch;
- approving or rejecting evidence;
- book-like lesson synthesis;
- promotion into learner-facing paths;
- reporting remaining limitations.

No wiki author, wiki validator, or wiki migration worker should remain in the active topology.

## Workflow-state correction

`TASKS_PLANNED` must be mode-aware:

- `topic-research` and `hybrid`: require the authorized research/extraction graph defined by the scope card;
- `provided-material-only`: require a registered source and the appropriate source-extraction/verification path, but do not require a `research-worker` count greater than zero;
- every mode that promises a ready exam: require a later assessment run with one generator and one different validator.

The workflow must not downgrade to conversational tutoring merely because an intermediate graph is empty. It should return the next actionable task or an exact blocked requirement until it reaches `LEARNING_ACTIVE`, `DRAFT_UNVERIFIED`, or `needs_user_input`.

`DRAFT_UNVERIFIED` is appropriate only when a required independent check is genuinely unavailable, exhausted, or rejected. It is not appropriate when the runtime exposes a spawn tool that the main agent failed to inspect or invoke.

## Implementation impact

The change is broader than editing `SKILL.md`. Hard-coded artifact paths and wiki requirements currently exist in:

- `mastery-ledger/SKILL.md`;
- `mastery-ledger/assets/` templates, including the thin lesson and wiki assets;
- `mastery-ledger/references/artifact-lifecycle.md`, `assessment-contract.md`, role profiles, pedagogy, quality, event, citation, and reconciliation contracts;
- workflow guides for study-pack building, research, evidence verification, tutoring, and updates;
- initialization and adoption scripts;
- source registry, action logging, workflow advancement/reconciliation, assessment planning, exam building, question rendering, and study-pack validation;
- the application source-manifest resolver;
- repository and skill tests;
- README and the canonical design-decision record.

The application exam discovery path does not need to change because `exams/<exam-id>/exam.json` remains stable. Its source-manifest lookup must add the new `records/source-manifest.yaml` path during migration.

## Recommended implementation order

1. Approve this contract and update the canonical design-decision document.
2. Centralize course artifact paths in one small script module so future layout changes do not require scattered string edits.
3. Add `index.md` and the full lesson asset/contract; remove wiki assets and wiki requirements.
4. Update initialization and adoption for the new layout.
5. Add an explicit, recoverable existing-course migration command.
6. Update source, evidence, log, workflow, assessment, and validation scripts to use the new paths.
7. Make workflow reconciliation mode-aware and enforce deferred-tool capability detection before an unavailable-worker conclusion.
8. Update role profiles and compiled worker context; remove wiki work and add the lesson contract to the relevant reviewer context.
9. Update the application source-manifest resolver while retaining exam discovery unchanged.
10. Update documentation and tests.
11. Forward-test the original single-video prompt in a fresh task with no leaked diagnosis.

Do not temporarily support two canonical layouts inside every script indefinitely. Use a single v2 layout plus an explicit migration reader for legacy courses; otherwise path fallbacks will hide incomplete migrations.

## Verification plan

### Deterministic tests

- Fresh initialization creates only the proposed learner, records, and `.work/` roots.
- No wiki, study-guide, concept-map, or standalone glossary template is generated.
- Existing-course migration preserves content and writes a recoverable migration receipt.
- Source registration, hash validation, and citations resolve through `records/source-manifest.yaml` and `records/source/`.
- Observable actions append only to `records/logs/events.jsonl`.
- Provided-material mode with zero research workers advances through its valid evidence branch.
- Runtime worker capability is detected from direct and deferred tools before `DRAFT_UNVERIFIED` is allowed.
- A lesson below the structural contract fails even when it exceeds 100 characters.
- A standard chapter fails with fewer than 10 items, any open-response item, or a mix other than 8/2.
- Expanded and large tiers accept only 12/3 and 16/4.
- Assessment validation must cover every promoted question ID.
- Publication remains valid after the closed run's disposable `.work/` task contents are removed, because durable validation receipts preserve the required verification facts.
- A ready exam cannot be built without validated items and a distinct validator completion.
- The application still lists multiple ready exams and resolves collapsed source disclosures.

### Forward-test acceptance

Re-run the user request from task `019f83bb-0af7-73a0-9849-9800fc0a5e5b` in a fresh Codex task. It passes only if:

- the learner is told the calibration length before questions begin;
- the supplied video is processed through the provided-material branch;
- the exposed worker facility is actually used for required independent tasks;
- the course contains a substantive chapter meeting the lesson contract;
- the question bank contains at least 10 source-grounded MCQs with the correct 80/20 mix;
- a different worker validates the bank;
- `exams/<exam-id>/exam.json` exists with `status: ready`;
- publication validation passes and the course reaches `LEARNING_ACTIVE`;
- no wiki is created;
- the course root remains clean, with provenance under `records/` and temporary work under `.work/`.

## Decision summary

- Remove the Knowledge Wiki and its worker/validation requirements.
- Merge course orientation into `index.md`; place definitions and misconceptions in lessons.
- Keep `questions/` and `exams/` separate because they serve authoring and delivery roles.
- Move source, evidence, validation receipts, and logs under durable `records/`; keep only temporary work in `.work/`.
- Require book-like chapters with a 1,200-word standard floor, structural teaching elements, and source locators.
- Require at least 10 questions per published chapter; use deterministic 10, 15, or 20 tiers with an exact 80/20 standalone/passage mix.
- Make provided-material workflow progression independent of a non-zero research-worker count.
- Require the main agent to inspect and use available worker tools, with independent assessment validation before any ready exam.

## Implementation status

Completed in the repository:

- centralized v2 course paths and clean initialization;
- explicit recoverable legacy-course migration;
- removal of wiki, standalone study-guide, concept-map, and glossary outputs;
- mode-aware provided-material evidence planning;
- `lesson-v1` templates, validation, and assessment-planning gates;
- deterministic 10, 15, and 20-question publication tiers;
- durable accepted-worker receipts that permit `.work/` cleanup;
- ready-exam preflight that preserves the previous exam when a changed bank has not been independently revalidated;
- application lookup for `records/source-manifest.yaml`;
- repository documentation and regression tests.

Still requires an external acceptance run: reinstall the skill, start a fresh Codex task with the original single-video request, and confirm that the runtime actually invokes its exposed worker facility and reaches `LEARNING_ACTIVE` without manual prompting.
