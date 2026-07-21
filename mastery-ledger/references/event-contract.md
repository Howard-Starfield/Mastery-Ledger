# Event contract

## Purpose

Record observable actions, decisions, evidence references, failures, and short justifications without persisting prompts or hidden reasoning.

## Durable and worker events

- Durable course audit remains `logs/events.jsonl` during the current compatibility period.
- A worker writes only `.work/runs/<run-id>/tasks/<task-id>/events.jsonl`.
- Workers never append to the durable log.
- The main agent routes every return through `scripts/route_worker_completion.py`; the router invokes `merge_worker_events.py` only after the completion validates and appends a short acceptance or repair decision event of its own.

## `action-event-v1`

Each JSONL line is one object containing:

```json
{
  "schema_version": "action-event-v1",
  "event_id": "EVT-0123456789ABCDEF",
  "timestamp": "2026-07-20T00:00:00Z",
  "run_id": "RUN-001",
  "task_id": "TASK-001",
  "action": "evidence.extraction.completed",
  "actor": "research-worker",
  "status": "complete",
  "summary": "Submitted five located claims and one unresolved gap.",
  "artifacts": [".work/runs/RUN-001/tasks/TASK-001/submission.json"],
  "decision": null,
  "justification": "Only assigned source material was inspected."
}
```

Required fields are `schema_version`, `event_id`, `timestamp`, `action`, `actor`, `status`, and `summary`. Worker shards additionally require the assigned `run_id` and `task_id`.

Use course-relative artifact paths. Keep summaries under 1,000 characters and justifications under 1,000 characters. An event reports what occurred and why an observable decision was made; it never reports private deliberation.

## Prohibited event content

Do not record:

- prompts, model context, hidden reasoning, or chain-of-thought;
- credentials, cookies, authorization headers, or secrets;
- full copyrighted sources or long excerpts;
- unredacted personal data unrelated to the learning record;
- claims that an action completed when its declared artifact is absent.

## Merge rules

The merger validates JSONL structure, task and run identity, role ownership, duplicate event IDs, and course-relative artifact paths. It appends only previously unseen events and writes an idempotent merge receipt inside the task directory. A second merge of the same shard must not duplicate events.

Malformed or mismatched shards remain under `.work/` and are not copied into the durable log.
