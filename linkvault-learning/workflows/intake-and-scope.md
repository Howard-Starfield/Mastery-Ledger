# Intake and scope

## Purpose

Turn the user’s request into an explicit learning contract and an approved boundary before expensive ingestion or research.

## 1. Resume or create

Check for a matching existing study before creating a new one. Match by stable study ID, source IDs, learning outcome, and concept overlap—not folder name alone.

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
```

Show a blast-radius classification:

- `REQUIRED_NOW`
- `HELPFUL_SOON`
- `OPTIONAL_DEEP_DIVE`
- `SEPARATE_STUDY_RECOMMENDED`
- `EXCLUDED_THIS_RUN`

## 5. Worker budget

- **Lean:** main agent or one worker, up to 5 inspected sources.
- **Standard:** 2–4 bounded workers, normally 8–15 inspected sources.
- **Deep:** 5 or more workers, broader corpus, independent citation and pedagogy review.

Do not estimate dollar cost unless the runtime exposes reliable pricing. Explain cost in worker runs, source count, and verification depth.

## 6. Approval

Obtain user approval before:

- launching more than one research worker;
- adding more than five sources after the approved scope;
- ingesting or transcribing substantial media;
- changing the learning outcome;
- branching into a separate study.

Approval may be an explicit acceptance or an explicit edit to the scope card.

## Exit gate

The phase is complete only when:

- `study.yaml` has a stable ID and mode;
- learning outcome and assumptions are recorded;
- scope and exclusions are explicit;
- source and privacy policies are recorded;
- worker budget is approved;
- likely separate topics are identified;
- next workflow is selected.
