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

If workers are unavailable, run each task sequentially as a fresh, bounded pass. Preserve the same task and report files. Mark verification as `self-review-fallback` when no independent reviewer exists.

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

## Two-pass decomposition

### Pass A: corpus mapping

Use one mapper to propose concept IDs, prerequisite edges, source coverage, ambiguities, and task boundaries. The main agent reviews and freezes a versioned provisional map.

### Pass B: bounded investigation

Create tasks by independent concept group, source subset, or verification function. Parallelize only tasks without dependencies.

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

Never assign two workers to the same output path. Do not expose the entire corpus when a bounded subset is sufficient.

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
