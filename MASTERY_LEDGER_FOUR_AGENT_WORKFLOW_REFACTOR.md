# Mastery Ledger four-agent workflow refactor

Status: implemented and validated  
Incident: Codex task `019f85fe-617f-7303-bd2a-4d45603d9be7`  
Date: 2026-07-21

## Problem

The prior workflow exposed every dependency-ready task as an immediate parallel wave. The incident kept completed scout and mapper agents open, attempted four extractor spawns through one parallel promise, lost partial spawn ownership when the child-agent limit was reached, retried the whole set, and incorrectly marked a capacity condition as `DRAFT_UNVERIFIED`.

The same workflow also made an ordinary supplied-source course pay for topic research, mapping, concept workers, separate assessment generation, and repeated learner approvals before producing a usable lesson or exam.

## Product paths

- **Fast Course:** selected whenever the learner supplies material or a link. Use only supplied sources for the first build. External corroboration is a later explicit upgrade.
- **Verified Course:** selected when the learner supplies only a topic. Use one source scout, a small authoritative source set, isolated extraction, contradiction review, and citation verification.

Internal source mode and publication quality remain separate. A Fast Course may become `VERIFIED`; `DRAFT_UNVERIFIED` describes quality, not input mode.

## Active worker graphs

Fast Course:

```text
deterministic acquisition
  -> queued source extractors
  -> citation verifier with cross-source conflict checking
  -> main-agent lesson and question authorship
  -> assessment validator
```

Verified Course:

```text
source scout
  -> main-agent source retention and registration
  -> queued source extractors
  -> contradiction reviewer
  -> citation verifier
  -> main-agent lesson and question authorship
  -> assessment validator
```

New runs do not create corpus-mapper, concept-research, or assessment-generator workers. Their profiles remain readable only for unfinished legacy runs.

## Capacity and lifecycle contract

- Four child agents is the hard limit.
- Three child agents is the normal active limit.
- One slot remains reserved for cleanup or recovery.
- The main agent is scheduler and completion receptionist.
- `ready_task_ids` means dependency-eligible; only `dispatch_task_ids` may be spawned.
- Reserve, spawn, and attach one task at a time. Persist the returned agent ID before another spawn.
- Never use `Promise.all` or another parallel wrapper for spawn calls.
- Route returns immediately and close accepted or exhausted agents before refilling capacity.
- Capacity rejection releases a reservation and never changes publication status.

## Stall policy

- Poll no longer than 60 seconds at a time.
- Three silent observations require one operational status probe.
- Five silent observations require interrupt and close.
- The first confirmed stall requeues the same frozen task for one fresh worker.
- A second confirmed stall blocks the task and marks publication `DRAFT_UNVERIFIED` without replacing the primary workflow state.
- Completion-format repairs reuse the same live worker and have a counter separate from stall restarts and reconciliation no-progress passes.
- A stalled reviewer never causes accepted upstream sources, evidence, lessons, or questions to be regenerated.

## Deterministic implementation

- `scripts/manage_worker_runtime.py` owns reservations, agent IDs, progress, silence, returned state, repair state, closure, capacity release, and one fresh-worker stall restart.
- Generated plans declare the fixed capacity contract and every task carries `worker_runtime` lease state.
- `validate_orchestration.py` rejects plans that omit or change the scheduler contract.
- Assessment plans contain only `TASK-ASSESSMENT-VALIDATE`; the main agent authors the bank and the validator receipt freezes the exact input hash.
- Durable receipts retain validator input hashes so publication can prove the current question bank was checked after `.work/` is cleaned.

## Regression requirements

- Five ready extractors expose only three normal dispatch slots.
- A spawn-capacity rejection returns the reservation to the queue and preserves publication status.
- Completed or returned agents block refill until closure is confirmed.
- A stalled reviewer receives exactly one fresh-worker restart.
- A second reviewer stall preserves workflow position and sets `DRAFT_UNVERIFIED`.
- Topic-only plans contain source extractors, contradiction review, and citation verification, without mapper or concept-research tasks.
- Supplied-source plans contain source extractors and citation verification, without open-web research or contradiction fan-out.
- Assessment plans contain one independent validator and no generator worker.

## Validation record

Validated on 2026-07-21:

- `python -m pytest -q mastery-ledger/tests`: 55 passed.
- `python -m pytest -q`: 78 passed.
- `python -m compileall -q mastery-ledger/scripts mastery-ledger/tests`: passed.
- Skill Creator `quick_validate.py mastery-ledger`: valid.
- `npm.cmd test` under `web/`: 5 passed.
- `npm.cmd run build` under `web/`: passed.
- `git diff --check`: passed; Git reports only the existing line-ending normalization warning for `agents/openai.yaml`.

## Deployment boundary

The repository skill under `D:/AI_projects/Tutor_AI/mastery-ledger` is the source of truth. Codex currently has a different installed copy at `C:/Users/howard/.agents/skills/mastery-ledger`; the refactor is not active there until that copy is reinstalled from the repository and a new Codex task loads it.
