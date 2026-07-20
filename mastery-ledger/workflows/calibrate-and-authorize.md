# Calibrate and authorize

## Purpose

Measure the learner's starting point without letting conversation replace research, then obtain one explicit approval for scope and the required worker topology.

## 1. Announce before asking

Choose 3-8 calibration questions across the proposed course; use 10 only when the learner requests a deeper diagnostic. Ask one at a time. Before question 1, state the exact count, mix, estimated time, and what will be recorded.

Default announcement:

```text
I will ask 8 calibration questions, one at a time: 6 concise concept questions and 2 short scenarios. This should take about 10 minutes. I will record each question, your answer, confidence when given, and the feedback I show you. After question 8, I will propose up to 5 related branches and show the research-worker plan. You can begin, adjust the count, or skip calibration.
```

Accept `begin`, `adjust`, or `skip`. Do not ask unrelated intake questions between calibration items. Calibration is provisional: do not write durable proficiency scores from unsourced questions.

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
Research plan: 3 bounded research workers -> 1 contradiction reviewer -> 1 final citation verifier -> 1 assessment generator -> 1 independent assessment validator. Later phases wait for their dependencies. Drafts and logs stay under the course .work/ and logs/ folders. Approve this scope and worker plan, or tell me what to adjust.
```

The learner's approval covers the displayed worker count, accepted branches, source limit, and publication target. Ask again only when exceeding that boundary.

## 5. Compile, do not improvise

After approval, generate the task graph with:

```bash
python scripts/create_research_plan.py COURSE_ROOT --research-workers 3 --authorized
python scripts/validate_orchestration.py COURSE_ROOT/.work/orchestration/run-plan.yaml --course-root COURSE_ROOT
```

Spawn only `ready_task_ids`. Wait for every task in a wave before advancing. Never spawn the contradiction reviewer early; never spawn citation verification before contradiction review; never mark assessment ready before independent assessment validation.

If subagents are unavailable or the learner declines them, run:

```bash
python scripts/advance_workflow.py COURSE_ROOT DRAFT_UNVERIFIED --reason "Independent workers unavailable or declined"
```

You may still teach conversationally or preserve provisional notes, but do not publish a durable researched course, activate its mastery schedule, or create a `ready` exam.

## Exit gate

Exit only when calibration is completed, adjusted, or explicitly skipped; accepted branches are recorded; the scope card includes the worker topology; approval is recorded; and the deterministic run plan validates.
