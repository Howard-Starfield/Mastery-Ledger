# Calibrate and authorize

## Purpose

Measure the learner's starting point without letting conversation replace research, then obtain one explicit approval for scope and the required worker topology.

## 1. Announce before asking

For a topic-only Verified Course, use the learner's first open prior-knowledge answer as calibration question 1. Ask at most two additional questions before research. Offer a deeper 5-10 question diagnostic only when the learner explicitly requests it. Ask one at a time.

Every calibration question must appear verbatim in the normal learner-visible response. Internal reasoning may prepare a question, but it does not count as asking it. Never put the only copy in reasoning, a plan, a tool call, `.work/`, or the calibration record. End the response immediately after the single displayed question and wait for the learner's answer.

For a topic-only request, count the first-turn open prior-knowledge response as calibration question 1. Once a course root is available, initialize the calibration record, preserve that exact learner-visible question and response, and record only the brief starting-level feedback shown to the learner. Before asking question 2, state the total count, remaining mix, estimated time, and what will be recorded. Use the opening response to avoid redundant follow-ups.

Supplied-material Fast Courses do not run this blocking calibration workflow. Their first sourced practice questions provide later learner-model evidence.

Default announcement:

```text
I will use what you just told me as calibration question 1 and ask 2 targeted follow-ups, one at a time: 1 concise concept question and 1 short scenario. This should take about 3 minutes. I will record each learner-visible question, your answer, and the feedback I show you. Then I will propose the bounded source and course scope. You can begin, request a deeper diagnostic, or skip the follow-ups.
```

Calibration is provisional: do not write durable proficiency scores from unsourced questions, and never treat the learner's opening claims as course evidence.

Record only observable interaction with `scripts/record_calibration.py`. Never record hidden reasoning.

## Learner-visible turn loop

1. Display the count/mix announcement and exactly one calibration question in learner-visible response text.
2. End the response and wait. Do not answer the question yourself, continue to the next question, or perform hidden calibration as if the learner had responded.
3. After the learner replies, prepare concise learner-visible feedback. Record the exact previously displayed question, learner answer, and feedback with `record_calibration.py`.
4. Display that feedback and, when questions remain, exactly one next question in the same learner-visible response; then end the response and wait again.
5. Do not mark a calibration question asked or answered unless it was actually displayed and the learner responded.

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

For `topic-research` and `hybrid`, show the proposed source limit and topology before spawning workers. In `hybrid`, state that the supplied anchor is registered first and one bounded source scout then finds corroborating candidates within the remaining source budget. Use this shape:

```text
Verified Course plan: use 1 bounded source scout, retain normally 3 authoritative sources, queue 1 isolated extractor per retained source with at most 3 active workers, then run 1 contradiction reviewer and 1 final citation verifier. I will author the lessons and at least 10 questions per chapter from approved evidence; a separate run uses 1 independent assessment validator. The fourth child-agent slot remains reserved for recovery. Approve this source and course scope, or tell me what to adjust.
```

The learner's approval covers the displayed worker count, accepted branches, excluded topics, source limit, assumed level, and publication target. Record that approval as the canonical `learning_contract` in `study.yaml`. Ask again only when exceeding that boundary.

## 5. Compile, do not improvise

After approval, record the contract. Do not create the research/evidence run yet: source acquisition must first produce a valid `SOURCES_READY` course. When the course has no supplied source, reconciliation first requires the separate one-task source-discovery run described in `research-topic.md`.

```bash
python scripts/record_scope_approval.py COURSE_ROOT --summary "APPROVED_SCOPE" --source-limit 3 --research-workers 0 --assumed-level "ASSUMED_LEVEL"
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
