# Intake and scope

## Primary course paths

- Supplied attachment, path, pasted material, or link: announce a **Fast Course**, use the supplied material, and begin without open-web corroboration.
- Topic only: announce a **Verified Course**, obtain a bounded source-search scope, and use independent source discovery and review.

Keep internal source modes separate from publication status. A Fast Course may become `VERIFIED` after its required checks pass. Offer `hybrid` corroboration only as a later explicit upgrade.

## Purpose

Turn the user’s request into an explicit learning contract and an approved boundary before expensive ingestion or research.

## 0. Consume the first-turn signal

The `SKILL.md` first-turn gate runs before this workflow for a new topic-only course request. Use the learner's open response to form provisional assumptions about starting level, vocabulary, prerequisites, misconceptions, and likely branches. Never treat the learner's statements as factual evidence for course material.

Do not ask `What do you already know?` again. For a topic-research course, pass the response into `calibrate-and-authorize.md` as the opening calibration seed. If the learner answered `nothing` or equivalent, assume a beginner starting point and continue.

When the first request contains an attachment, local path, URL, pasted source excerpt, or identified existing source, the first-turn gate is skipped. Acknowledge the supplied material, classify the source mode, and continue intake without asking whether the learner has a source. Additional sources may be added later under the same approved course scope.

For supplied material, select the Fast Course mode directly: `local-media` for video or audio processing, `existing-library` for an imported course tree, or `provided-material-only` otherwise. Do not ask for corroboration before producing the first course. If the learner later requests external checking or expansion, show a bounded upgrade card before switching to legacy-compatible `hybrid`.

## 1. Resume or create

After resolving the learner-approved workspace, check for a matching existing study before creating a new one. Match by stable study ID, source IDs, learning outcome, and concept overlap—not folder name alone.

Create a new study only when the request has a materially different outcome or satisfies the split criteria in `references/topic-splitting-policy.md`.

## 2. Establish the learning contract

Determine or safely default:

- learning outcome;
- current level and missing prerequisites;
- intended use: overview, working competence, project application, exam, or long-term review;
- target depth;
- time available and deadline;
- preferred learning mode: Socratic, coached, direct instruction, exam simulation, or review;
- source mode and whether external research is allowed;
- processing mode: `local_only`, `cloud_allowed`, or `metadata_only`;
- worker budget: lean, standard, or deep.

Ask no more than two blocking questions in one turn. If the user already supplied enough information, summarize assumptions and proceed to a scope proposal.

## 3. Cheap scout

Before multiple workers, inspect the supplied corpus or run one bounded scouting pass. The scout may identify:

- candidate concepts;
- prerequisite chains;
- likely source availability;
- current or disputed areas;
- estimated module count;
- adjacent branches;
- likely separate studies.

The scout is provisional. It does not approve claims or write the final curriculum.

For `topic-research` and `hybrid`, run the learner calibration in `calibrate-and-authorize.md` before the scope card. Do not let repeated conversational questions substitute for the research task graph.

## 4. Present a scope card

Use this shape:

```markdown
## Proposed study

**Outcome:**
**Assumed level:**
**Learning mode:**
**Source policy:**
**Core concepts:**
**Required prerequisites:**
**Helpful soon:**
**Optional deep dives:**
**Separate studies recommended:**
**Excluded this run:**
**Proposed sources:**
**Proposed workers:**
**Expected modules:**
**Output contract:** PROPOSED_CHAPTER_COUNT `lesson-v1` book-like chapters, 1,200-1,800 words each, exactly the standard 10-question tier per chapter unless an expanded tier is approved, and one independently validated ready exam.
```

Show a blast-radius classification:

- `REQUIRED_NOW`
- `HELPFUL_SOON`
- `OPTIONAL_DEEP_DIVE`
- `SEPARATE_STUDY_RECOMMENDED`
- `EXCLUDED_THIS_RUN`

## 5. Worker budget

- **Fast:** supplied sources only, one extractor task per source through the three-slot queue, then ordered validation.
- **Verified:** one scout, normally three retained authoritative sources, queued extractors, contradiction review, citation verification, and assessment validation.
- **Expanded verified:** at most five retained sources after explicit scope expansion; tasks remain queued rather than increasing simultaneous workers.

Do not estimate dollar cost unless the runtime exposes reliable pricing. Explain cost in worker runs, source count, and verification depth.

## 6. Approval

Obtain user approval before:

- expanding a Verified Course beyond three retained sources;
- adding external sources to a supplied-material Fast Course;
- ingesting or transcribing substantial media;
- changing the learning outcome;
- branching into a separate study.

Approval may be an explicit acceptance or an explicit edit to the scope card.
For a researched course, include the exact worker topology in the same approval card; do not ask for a second approval unless the run later expands.

Choose and display an exact chapter count, normally 1-3, before approval. After explicit approval, persist it with `record_scope_approval.py` using `--chapter-count PROPOSED_CHAPTER_COUNT` and an absolute script path resolved from `SKILL_ROOT`, then return to the original `reconcile_workflow.py` target. Do not enter `SCOPED` from conversational inference alone.

Initialize only after the source policy is known:

```bash
python scripts/init_study.py "COURSE_TITLE" --mode provided-material-only --studies-dir "PARENT"
# Use --mode topic-research when the learner supplied only a topic.
# Reserve hybrid for a later explicitly approved corroboration upgrade.
```

## Exit gate

The phase is complete only when:

- `study.yaml` has a stable ID and mode;
- learning outcome and assumptions are recorded;
- scope and exclusions are explicit;
- source and privacy policies are recorded;
- worker budget is approved;
- likely separate topics are identified;
- next workflow is selected.
