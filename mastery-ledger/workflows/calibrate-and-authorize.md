# Calibrate and authorize

## Purpose

Measure the learner's starting point without letting conversation replace research, then obtain one explicit approval for scope and the required worker topology.

## 1. Announce before asking

Choose 3-8 calibration questions across the proposed course; use 10 only when the learner requests a deeper diagnostic. Ask one at a time.

For a topic-only request, count the first-turn open prior-knowledge response as calibration question 1. Once a course root is available, initialize the calibration record, preserve that exact learner-visible question and response, and record only the brief starting-level feedback shown to the learner. Before asking question 2, state the total count, remaining mix, estimated time, and what will be recorded. Use the opening response to avoid redundant follow-ups.

When supplied material caused the first-turn question to be skipped, announce the exact count, mix, estimated time, and recording policy before calibration question 1 as usual.

Default announcement:

```text
I will use what you just told me as calibration question 1 and ask 7 targeted follow-ups, one at a time: 5 concise concept questions and 2 short scenarios. This should take about 9 minutes. I will record each learner-visible question, your answer, confidence when given, and the feedback I show you. After question 8, I will propose up to 5 related branches and show the research-worker plan. You can begin, adjust the remaining count, or skip the follow-ups.
```

For supplied-material runs without an opening seed, say `I will ask 8 calibration questions` and use the original 6-concept/2-scenario mix. Accept `begin`, `adjust`, or `skip`. Do not ask unrelated intake questions between calibration items. Calibration is provisional: do not write durable proficiency scores from unsourced questions, and never treat the learner's opening claims as course evidence.

Record only observable interaction with `scripts/record_calibration.py`. Never record hidden reasoning.

## 2. Ask a bounded diagnostic

Cover the course breadth rather than asking ten variants of one concept. Prefer:

- prerequisite recognition;
- concise free recall;
- discrimination between confusing concepts;
- one or two short application scenarios;
- the learner's intended use and uncertainty only when it changes scope.

After each response, give a concise answer or correction and record both the learner response and learner-visible feedback. Continue until the announced count is complete unless the learner changes it.

## 3. Propose adjacent branches

After calibration, propose 1-5 closely related branches. Classify each as:

- `REQUIRED_NOW`
- `HELPFUL_SOON`
- `OPTIONAL_DEEP_DIVE`
- `SEPARATE_STUDY_RECOMMENDED`

Only learner-accepted branches enter this run. Do not silently expand the course from conversational interest.

## 4. Show one authorization card

For `topic-research` and `hybrid`, show the proposed source limit and topology before spawning workers. Use this shape:

```text
Research plan: 1 bounded source scout when no source is supplied -> 1 isolated extractor per retained source plus 3 bounded concept-research workers -> 1 contradiction reviewer -> 1 final citation verifier. After evidence approval, a separate run uses 1 assessment generator -> 1 independent assessment validator. Later phases wait for their dependencies. Extractor count cannot exceed the approved source limit. Drafts and logs stay under the course .work/ and logs/ folders. Approve this scope and worker plan, or tell me what to adjust.
```

The learner's approval covers the displayed worker count, accepted branches, excluded topics, source limit, assumed level, and publication target. Record that approval as the canonical `learning_contract` in `study.yaml`. Ask again only when exceeding that boundary.

## 5. Compile, do not improvise

After approval, record the contract. Do not create the research/evidence run yet: source acquisition must first produce a valid `SOURCES_READY` course. When the course has no supplied source, reconciliation first requires the separate one-task source-discovery run described in `research-topic.md`.

```bash
python scripts/record_scope_approval.py COURSE_ROOT --summary "APPROVED_SCOPE" --source-limit 10 --research-workers 3 --assumed-level "ASSUMED_LEVEL"
python scripts/reconcile_workflow.py COURSE_ROOT --json
```

The reconciliation response routes the next action to source ingestion or research. Only after registered sources make the course `SOURCES_READY` may the main agent compile the authorized research plan. Every task must receive the approved branches, exclusions, source limit, and learner goal from `learning_contract`; worker prompts must not reconstruct scope from conversation.

Use absolute script paths resolved from `SKILL_ROOT` during an installed-skill run. Inspect direct and deferred runtime tools before concluding that workers are unavailable. If no callable worker facility exists, an actual worker call reports unavailable, or the learner declines them, run:

```bash
python scripts/advance_workflow.py COURSE_ROOT DRAFT_UNVERIFIED --reason "Independent workers unavailable or declined"
```

This sets a resumable publication label; it does not replace the course's primary workflow position. You may still teach conversationally or preserve provisional notes, but do not publish a durable researched course, activate its mastery schedule, or create a `ready` exam.

## Exit gate

Exit only when calibration is completed, adjusted, or explicitly skipped; accepted branches and exclusions are recorded; the scope card includes the worker topology; and the canonical learning contract is approved. The source-discovery plan, when required, validates at `SCOPED`; the research/evidence plan validates only after `SOURCES_READY`.
