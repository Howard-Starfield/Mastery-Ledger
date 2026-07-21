# Orchestrate workers

## Purpose

Execute the smallest independent-worker graph required by the selected course path without exceeding Codex's four-child-agent limit.

Before planning or dispatch, read in full:

- [artifact lifecycle](../references/artifact-lifecycle.md)
- [event contract](../references/event-contract.md)
- [agent roles](../references/agent-roles.md)
- [task and evidence contract](../references/task-and-evidence-contract.md)
- [worker runtime contract](../references/worker-runtime-contract.md)

The main agent owns scope, source retention, course organization, evidence approval, lesson and question authorship, dispatch, completion routing, and final learner communication. Never spawn a receptionist, mapper, assessment generator, or recursive orchestrator.

## Select one graph

### Fast Course: supplied material

```text
deterministic acquisition and registration
  -> one source-extractor task per retained source
  -> one citation-verifier task over all accepted packets
  -> main-agent evidence approval and course authorship
  -> one assessment-validator task
```

Do not browse or spawn open-web research workers. When multiple supplied packets disagree, the citation verifier compares definitions, dates, assumptions, and scope before verifying retained claims.

### Verified Course: topic only

```text
one source-scout task
  -> main-agent source retention, acquisition, and registration
  -> one source-extractor task per retained source
  -> one contradiction-reviewer task
  -> one citation-verifier task
  -> main-agent evidence approval and course authorship
  -> one assessment-validator task
```

Default to three retained authoritative sources. Expand to at most five only when the approved scope needs it. New runs use no corpus mapper, concept-research worker, or assessment-generator worker.

`hybrid` is a legacy-compatible explicit upgrade after a supplied-source Fast Course. It uses the Verified Course evidence graph only after the learner requests corroboration.

## Compile the plan

For Fast Course evidence:

```bash
python scripts/create_provided_evidence_plan.py COURSE_ROOT --authorized
```

For topic-only source discovery:

```bash
python scripts/create_source_discovery_plan.py COURSE_ROOT --authorized
```

After retained researched sources are registered:

```bash
python scripts/create_research_plan.py COURSE_ROOT --research-workers 0 --authorized
```

The compiler creates one protected DAG. Do not hand-edit it, replace it after a partial return, or recreate accepted tasks.

## Compile contexts

Run `compile_worker_context.py` for IDs in `context_required_task_ids`, then rerun `validate_orchestration.py`. Compilation freezes role and contract hashes, bounded inputs, one task-local output, exact templates, and the immutable dispatch message. Workers write only under `.work/runs/<run-id>/tasks/<task-id>/` and never promote canonical course files.

## Capacity-bounded dispatch

Run:

```bash
python scripts/manage_worker_runtime.py status COURSE_ROOT
```

Dispatch only `dispatch_task_ids`. Normal concurrency is three child agents and the hard limit is four. For each task, sequentially reserve it, spawn exactly one worker from the compiled dispatch message, attach the returned agent ID, and only then reserve another task.

Never fan out spawn calls with `Promise.all`. A spawn-capacity error releases the reservation and leaves the course in progress.

Wait in intervals no longer than 60 seconds and follow the progress, probe, stall, return, repair, and closure rules in the worker runtime contract. Route each return immediately. Completed workers remain capacity consumers until the runtime confirms their external agent was closed.

## Ordered reviewers

- The Fast Course citation verifier waits for every supplied-source extractor.
- The Verified Course contradiction reviewer waits for every researched-source extractor.
- The Verified Course citation verifier waits for contradiction review and every extractor.
- The assessment validator is a separate later run and waits for main-agent-authored substantive lessons and question bank.

Run one reviewer at a time after all dependencies are accepted and closed. A stalled reviewer gets one fresh agent on the same frozen task; it does not cause upstream regeneration.

## Exit gate

Evidence work is complete only when every required task has a contract-valid accepted completion, every corresponding agent is closed, the final citation decision is verified, and the main agent explicitly approves mergeable claims. Capacity exhaustion, a queued task, or a worker that has merely returned is not completion.
