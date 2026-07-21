# Worker runtime contract

## Purpose

Keep a dependency-safe worker queue within Codex's four-child-agent limit and recover from stalled or completed workers without losing task identity.

## Fixed capacity

- Hard child-agent limit: four.
- Normal active limit: three.
- Reserved capacity: one slot for cleanup or recovery.
- The main agent is the scheduler and completion receptionist. Never delegate scheduling.
- A run may contain any bounded number of logical tasks; capacity controls only simultaneous agents.

`ready_task_ids` means dependency-eligible. It never authorizes an unbounded parallel spawn. Use `scripts/manage_worker_runtime.py status COURSE_ROOT` and dispatch only `dispatch_task_ids`.

## Dispatch sequence

For each returned `dispatch_task_id`, one at a time:

1. Run `manage_worker_runtime.py reserve COURSE_ROOT TASK_ID`.
2. Read the exact compiled `dispatch_path` returned by the reservation.
3. Spawn one worker with that message. Never use `Promise.all` or another multi-spawn wrapper.
4. Immediately persist the returned agent ID with `manage_worker_runtime.py attach COURSE_ROOT TASK_ID --reservation-id LEASE_ID --agent-id AGENT_ID`.
5. Only after attachment may another task be reserved.

If spawn fails, run `manage_worker_runtime.py release ... --reason "OBSERVABLE ERROR"`. A capacity error returns the task to the queue and does not change publication status.

## Waiting and progress

Wait or poll for no longer than 60 seconds at a time. Count as progress only an observable worker message, a changed assigned artifact, a completed tool operation, or a returned completion envelope.

- On progress, run `manage_worker_runtime.py progress ... --stage SHORT_STAGE`.
- On no progress, run `manage_worker_runtime.py silent-poll ...`.
- After three silent polls, send one short status probe asking only for stage, completed items, remaining items, artifact paths, and blockers.
- After five silent polls, the helper returns `stall_suspected` and the agent must be interrupted and closed.

Never request or record hidden reasoning. A progress checkpoint contains only operational state.

## Return, repair, and close

When a worker returns:

1. Run `manage_worker_runtime.py returned COURSE_ROOT TASK_ID`.
2. Run `route_worker_completion.py COURSE_ROOT TASK_ID` immediately; do not wait for a whole wave.
3. On `changes_required`, run `manage_worker_runtime.py repair ...` and send the generated repair message to the same live agent.
4. On `accepted` or `retry_exhausted`, close the external agent, then run `manage_worker_runtime.py confirm-close ... --reason "..."`.
5. Rerun `status` and refill open capacity from `dispatch_task_ids`.

Completed agents still consume slots until closed. Close only agent IDs recorded for the current course run; never close an untracked agent.

## Stall recovery

After `stall_suspected`, interrupt and close the recorded agent, then call `confirm-close`. The first confirmed stall requeues the same frozen task with a new lease and increments `stall_restart_count`. Do not create a new plan or regenerate upstream artifacts.

A second confirmed stall exhausts the one fresh-worker restart, blocks that task, and marks publication `DRAFT_UNVERIFIED` while preserving the primary workflow state. This stall counter is separate from completion-format repair attempts and reconciliation no-progress passes.

## Reviewer isolation

Contradiction, citation, and assessment validators run only after every dependency is accepted and closed. Dispatch one reviewer at a time. If a reviewer stalls, retry only that frozen review task; never regenerate accepted evidence, lessons, or questions merely to replace the reviewer.

## Runtime restart

On a resumed Codex task, call `status` before spawning. A recorded active lease must be reconciled against observable runtime state. If its recorded agent no longer exists, confirm the stale closure with an observable reason and use the same one-restart rule. Never infer that all in-progress tasks are absent or rerun an entire ready set.
