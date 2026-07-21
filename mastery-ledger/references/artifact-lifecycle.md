# Artifact lifecycle

## Purpose

Keep initialization, work-in-progress, approval, promotion, and durable audit state distinct. File existence does not mean publication.

## Storage classes

| Class | Location | Owner | Retention |
| --- | --- | --- | --- |
| Durable configuration | `study.yaml`, `index.md`, progress | deterministic scripts and main agent through scripts | preserve |
| Durable knowledge | `lessons/`, `questions/`, `exams/` | deterministic promotion after main-agent approval | preserve and version |
| Durable records | `records/source/`, `records/evidence/`, `records/source-manifest.yaml` | deterministic registration or promotion | preserve and version |
| Durable audit | `records/logs/events.jsonl` | deterministic application or merge script | append-only |
| Run state | `.work/runs/<run-id>/` | run controller | inspectable, disposable after closure policy |
| Worker state | `.work/runs/<run-id>/tasks/<task-id>/` | assigned worker only | never publish directly |
| Staging | `.work/runs/<run-id>/staging/` | main agent through deterministic helpers | promote only after validation |

Never treat `.work/` as evidence, curriculum, or a durable audit store. Never place hidden reasoning or chain-of-thought in any storage class.

## Initialization

Use `scripts/init_study.py`; do not hand-create a course layout. Initialization creates canonical empty templates, durable audit destination, and disposable run roots. It may create empty or placeholder artifacts, but substantive source-grounded knowledge remains unpublished until evidence approval.

If an existing application-created course has `course.yaml` but lacks `study.yaml`, run `scripts/adopt_course.py <COURSE_ROOT>`. It adds only missing canonical templates and preserves existing source, media, manifest, and audit artifacts. Do not approximate the full layout by hand.

## Run lifecycle

1. When topic research starts without a supplied source, compile one bounded source-discovery run at `SCOPED`. After its accepted ledger is reviewed, sources are atomically registered, and the course reaches `SOURCES_READY`, replace that finished discovery run with the linked evidence run. Refuse every other non-placeholder replacement unless an explicit supersession reason is recorded.
2. Assign every task a unique directory under `.work/runs/<run-id>/tasks/`.
3. Compile and validate the worker context before dispatch.
4. Let the worker write only its brief, context acknowledgement, event shard, submission, completion, and temporary files inside that directory.
5. Route the worker's copy of the prefilled completion template through the deterministic completion router; on failure, repair the same task within its bounded attempt count.
6. Let the main agent approve or reject the proposed result.
7. Promote accepted artifacts with deterministic tooling; workers never write final targets.
8. Merge accepted observable worker events through the packaged merger.
9. Finalize the run. `route_worker_completion.py` writes a compact accepted-result receipt under `records/evidence/validation/<run-id>/`; retain those receipts and the durable action log even if `.work/` is later removed.

## Promotion order

For a multi-file publication, validate staged artifacts first, promote dependency targets before indexes that link to them, validate the promoted view, then atomically replace derived catalogs. Record the accepted event after successful promotion. On failure, leave canonical artifacts unchanged and preserve staging for inspection.

## Ownership

- The learner approves material scope and costly expansion.
- The main agent owns task selection, evidence decisions, synthesis, and promotion authorization.
- Workers propose bounded outputs and observable events only.
- Deterministic scripts own path resolution, context compilation, schema checks, event merging, and final writes.
- The application may append its own deterministic runtime events; it does not merge worker submissions or approve knowledge.

## Failure rules

Return `blocked` rather than inventing a missing initializer, contract, schema, command, or fallback. Quarantine a worker completion when its identity, role profile, contract acknowledgement, hash, event shard, or write boundary fails validation. The worker may submit a new completion for the same task using the generated repair packet; never mutate the quarantined result or create a replacement plan to hide the failure.
