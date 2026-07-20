# Orchestrate research

## Purpose

Delegate independent, bounded work without surrendering evidence control or final synthesis.

## Capability gate

Record whether the runtime supports:

- spawning subagents;
- parallel workers;
- isolated worker context;
- shared filesystem;
- web and file tools inside workers;
- independent model selection.

For `topic-research` or `hybrid`, independent workers are a publication requirement. If they are unavailable or declined, preserve provisional work under `.work/`, advance to `DRAFT_UNVERIFIED`, and stop before evidence approval, study-pack validation, learning activation, or a ready exam. A sequential main-agent pass may support the live conversation but cannot publish researched material.

## Main-agent responsibilities

The main agent owns:

- concept-map version;
- task graph;
- scope and budget;
- worker briefs;
- report acceptance;
- conflict resolution;
- final curriculum and learner conversation.

Workers never approve their own output and never edit final learner-facing artifacts.

Use a completion router as the receptionist for worker returns. It checks completion envelopes and presents a sorted inbox to the main agent; it has no authority to approve evidence or bypass dependencies.

## Two-pass decomposition

### Pass A: corpus mapping

Use one mapper to propose concept IDs, prerequisite edges, source coverage, ambiguities, and task boundaries. The main agent reviews and freezes a versioned provisional map.

### Pass B: bounded investigation

Create tasks by independent concept group, source subset, or verification function. Parallelize only tasks without dependencies.

### Pass C: contradiction-first review

After every source extractor and research worker in the run has submitted, route their reports together to one contradiction reviewer. Reject, narrow, or mark disputed material here. Do not start citation verification while any extraction, research, or contradiction task is unfinished.

### Pass D: final citation verification

Run citation verification only on the claims retained after contradiction review. This is the final worker phase before the main agent approves evidence, which avoids reopening locators for material already rejected as contradictory, stale, duplicated, or out of scope.

### Pass E: assessment generation and validation

After final citation verification and main-agent evidence approval, dispatch one assessment generator. When it completes, dispatch a different assessment validator. The validator checks answer-key support, ambiguity, distractors, duplicates, chapter coverage, and the exact 80/20 format contract. It must not approve its own generated items.

## Task rules

Every task must declare the fields in `assets/task-brief.yaml` and must have:

- one objective;
- explicit included and excluded scope;
- allowed source IDs or source limit;
- dependencies;
- unique output path;
- required report schema;
- named reviewer role;
- acceptance criteria.
- a unique completion-envelope path under `.work/orchestration/completions/`.

Never assign two workers to the same output path. Do not expose the entire corpus when a bounded subset is sufficient.

All output, completion, review, draft, and scratch paths must be relative descendants of `.work/`. A worker that writes outside its assigned paths is rejected. Final course artifacts are promoted only by the main agent after approval and validation.

## Worker prompt recipe

Provide only:

1. role and objective;
2. included and excluded scope;
3. approved concept IDs;
4. source policy;
5. source subset or search limit;
6. required evidence-packet schema;
7. output path;
8. instruction to preserve contradictions and gaps.

Do not leak the expected conclusion. Do not ask the worker to “make the guide coherent”; that is the main agent’s job.

## Status lifecycle

`PLANNED → IN_PROGRESS → SUBMITTED → VERIFIED → APPROVED → MERGED`

Alternative states: `CHANGES_REQUIRED`, `REJECTED`, `BLOCKED`, `SUPERSEDED`.

A citation verifier may mark `VERIFIED`; only the main agent may mark `APPROVED`.

## Executable dispatch gate

Compile the approved plan instead of hand-authoring it, then run the gate before spawning any task and whenever a completion arrives:

```bash
python scripts/create_research_plan.py studies/my-study --research-workers 3 --authorized
python scripts/validate_orchestration.py studies/my-study/.work/orchestration/run-plan.yaml \
  --course-root studies/my-study
```

Dispatch only task IDs listed in `ready_task_ids`. Citation verification remains unavailable until every extraction, research, and contradiction task submits. Assessment generation remains unavailable until citation verification submits; assessment validation remains unavailable until generation submits. A submitted task without a matching `completion-envelope-v1` fails validation. The main agent updates task state and reruns this gate; workers and the completion router never infer readiness themselves.

After each complete ready wave, return to `reconcile_workflow.py` with the original target. The returned next gate determines whether another wave, evidence review, study-pack repair, or learner input is allowed. Never self-dispatch by recursively calling the worker topology.

## Cost controls

Stop and ask the user before expanding when:

- another worker is required beyond the approved budget;
- more than five additional sources are needed;
- a branch materially increases the scope;
- a disputed or high-stakes claim needs a different model or expert review.

## Exit gate

The phase is complete only when:

- the task graph is acyclic;
- each task has a unique output path and reviewer;
- worker count matches the approved budget;
- reports exist for completed tasks;
- failed tasks have a recovery decision;
- submitted reports are routed to evidence verification.
- every submitted task has a matching completion envelope;
- contradiction review finished before citation verification;
- the orchestration validator reports no path, dependency, cycle, or phase-order error.
