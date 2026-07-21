# Orchestrate research

## Purpose

Delegate independent, bounded work without surrendering evidence control or final synthesis.

## Execution gate

Inspect whether the current runtime supports:

- spawning subagents;
- parallel workers;
- isolated worker context;
- shared filesystem;
- web and file tools inside workers;
- independent model selection.

Search both directly exposed tools and any deferred tool catalog before declaring a worker facility unavailable. Record that observation in the action log; do not write availability Booleans into a run plan. The plan records required execution properties, and accepted routed completions prove they were satisfied.

For `topic-research` or `hybrid`, independent workers are a publication requirement. If they are unavailable or declined, preserve provisional work under `.work/`, set publication status to `DRAFT_UNVERIFIED`, and stop before evidence approval, study-pack validation, learning activation, or a ready exam. A sequential main-agent pass may support the live conversation but cannot publish researched material.

Before planning or dispatch, read [artifact lifecycle](../references/artifact-lifecycle.md), [event contract](../references/event-contract.md), [agent roles](../references/agent-roles.md), and [task and evidence contract](../references/task-and-evidence-contract.md) in full.

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

Use `scripts/route_worker_completion.py` as the receptionist for every worker return. It checks the exact prefilled completion envelope, runs the orchestration gate, and either accepts the submission or returns a same-task repair packet. It has no authority to approve evidence or bypass dependencies.

## Two-pass decomposition

### Pass A: corpus mapping

Use one mapper to propose concept IDs, prerequisite edges, source coverage, ambiguities, and task boundaries. In the same first wave, use one isolated source extractor per retained source; each receives exactly one registered source and cannot synthesize across the corpus. The mapper output must match `corpus-map-v1` and name exactly the pre-authorized research task IDs. Wait for the whole mapper/extractor wave. After the completion router accepts the mapper, the main agent reviews it and runs `freeze_corpus_map.py`; this binds those existing concept-research tasks in the same run. Never replace the run plan merely because mapping finished.

### Pass B: bounded investigation

Create tasks by independent concept group, source subset, or verification function. Parallelize only tasks without dependencies.

### Pass C: contradiction-first review

After every source extractor and research worker in the run has submitted, route their reports together to one contradiction reviewer. Reject, narrow, or mark disputed material here. Do not start citation verification while any extraction, research, or contradiction task is unfinished.

### Pass D: final citation verification

Run citation verification only on the claims retained after contradiction review. This is the final worker phase before the main agent approves evidence, which avoids reopening locators for material already rejected as contradictory, stale, duplicated, or out of scope.

Assessment generation is a separate authorized run created only after final citation verification, main-agent evidence approval, and substantive study-pack drafts. See `build-study-pack.md`. Keeping assessment out of the research graph prevents it from becoming ready against rejected or superseded claims.

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
- a unique task directory under `.work/runs/<run-id>/tasks/<task-id>/` containing compiled brief, context, dispatch, event, submission, and completion paths.

Never assign two workers to the same output path. Do not expose the entire corpus when a bounded subset is sufficient.

All output, completion, review, draft, and scratch paths must be relative descendants of the assigned task directory. A worker that writes outside its assigned paths is rejected. Final course artifacts are promoted only by the main agent after approval and validation.

## Worker prompt recipe

Do not compose the worker prompt. Compile the deterministic context packet and pass its generated dispatch message. The compiler also writes a role-specific output template and a prefilled `completion-template.json`; the worker must copy that exact completion template and fill only the declared result fields. The packet provides only:

1. role and objective;
2. included and excluded scope;
3. approved concept IDs;
4. source policy;
5. source subset or search limit;
6. required evidence-packet schema;
7. output path;
8. instruction to preserve contradictions and gaps;
9. versioned role profile and required contract hashes;
10. exact event, submission, completion-template, and completion paths.

Do not leak the expected conclusion. Do not ask the worker to “make the guide coherent”; that is the main agent’s job.

## Status lifecycle

`PLANNED → IN_PROGRESS → SUBMITTED → VERIFIED → APPROVED → MERGED`

Alternative states: `CHANGES_REQUIRED`, `REJECTED`, `BLOCKED`, `SUPERSEDED`.

A citation verifier may mark `VERIFIED`; only the main agent may mark `APPROVED`.

## Executable dispatch gate

Once reconciliation reports `SOURCES_READY`, compile the approved plan instead of hand-authoring or editing `.work/orchestration/run-plan.yaml`, then run the gate before spawning any task and whenever a completion arrives:

```bash
python scripts/create_research_plan.py studies/my-study --research-workers 3 --authorized
python scripts/compile_worker_context.py studies/my-study TASK-MAP --json
python scripts/validate_orchestration.py studies/my-study/.work/orchestration/run-plan.yaml \
  --course-root studies/my-study
```

Compile IDs listed in `context_required_task_ids`, rerun the gate, and dispatch only task IDs listed in `ready_task_ids`. Pass the generated `dispatch-message.txt` without substantive edits. Route every return with:

```bash
python scripts/route_worker_completion.py studies/my-study TASK-ID
```

If it returns `changes_required`, send the generated repair dispatch to the same task and worker context. Do not create a replacement run. When `TASK-MAP` is accepted, run `freeze_corpus_map.py`, compile the now-bound research tasks, validate, and dispatch only the returned ready wave. Citation verification remains unavailable until every research and contradiction task submits. A submitted task without a matching event shard, contract acknowledgements, role-profile acknowledgement, output, and exact `completion-envelope-v1` fails validation. Only accepted completions are merged into durable events.

After each complete ready wave, run `reconcile_workflow.py COURSE_ROOT --json`; it reads the course's persistent `workflow_target`. The returned next gate determines whether another wave, evidence review, study-pack repair, or learner input is allowed. Never self-dispatch by recursively calling the worker topology.

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
- failed tasks have a bounded same-task recovery decision;
- submitted reports are routed to evidence verification.
- every submitted task has a matching completion envelope;
- contradiction review finished before citation verification;
- the orchestration validator reports no path, dependency, cycle, or phase-order error.
