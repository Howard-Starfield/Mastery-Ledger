# Workflow reconciliation

## Purpose

Converge a course toward one declared target without skipping gates, repeatedly asking broad questions, or recursively spawning agents. The loop is iterative and bounded: inspect one gate, return observable missing work, perform that work, and inspect again.

## Required command

Resolve the installed skill root from the location of `SKILL.md`, then run:

```text
python "<SKILL_ROOT>/scripts/reconcile_workflow.py" "<COURSE_ROOT>" "<TARGET_STATE>" --json
```

Use absolute paths. Never copy a bundled script into a course, create dependencies inside a course, or assume the shell's current directory.

## Response contract

The command emits one `workflow-reconciliation-v1` object:

- `complete`: the target is reached; `advanced` lists gates that were already satisfied and advanced atomically.
- `needs_work`: perform only `next_actions`, then rerun the exact `rerun_argv`.
- `needs_user_input`: ask the learner only for the identified approval, source, or choice; record it with the named script, then rerun.
- `retry_exhausted`: three consecutive inspections returned the identical gate and requirements. Stop, preserve state, and report the exact requirement. Do not silently add sources, workers, retries, or scope.

Exit code `0` means complete, `2` means work or user input is required, and `3` means the identical blocker retry limit was reached.

## Main-agent algorithm

1. Declare one target state.
2. Run reconciliation once.
3. If work is returned, read only the listed workflow files.
4. Run the deterministic helper or the exact `ready_task_ids` reported by `validate_orchestration.py`.
5. Wait for the entire dispatched wave and route completion envelopes before rerunning the gate.
6. Record observable actions, decisions, evidence, and short justifications. Never record hidden reasoning.
7. Rerun reconciliation after an artifact, task status, source, learner decision, or validation result changed.
8. Stop on completion, required user input, declined/unavailable independent workers, or retry exhaustion.

Do not call the script in a tight loop. A return is a work order for the main agent, not permission to fabricate the missing artifact. Do not create a worker to run reconciliation; the main agent owns the loop.

## Gate routing

| Entering state | Observable requirement | Workflow that owns repair |
| --- | --- | --- |
| `SCOPED` | Learning contract, calibration disposition when applicable, and recorded scope approval | `intake-and-scope.md`, `calibrate-and-authorize.md` |
| `SOURCES_READY` | At least one retained source with ready status, real hash, and non-empty `source/SRC-NNN.md` | `ingest-material.md`, `process-video.md`, or `research-topic.md` |
| `CORPUS_MAPPED` | Submitted corpus mapper for researched modes; provided-source modes pass without one | `orchestrate-research.md` |
| `TASKS_PLANNED` | Authorized, valid, non-empty dependency graph | `orchestrate-research.md` |
| `EVIDENCE_SUBMITTED` | Required research/extraction and contradiction wave submitted, or direct provided-source claims recorded | `orchestrate-research.md`, `verify-evidence.md` |
| `EVIDENCE_VERIFIED` | Final citation verifier submitted after contradiction review for researched modes | `verify-evidence.md` |
| `EVIDENCE_APPROVED` | Non-empty main-agent-approved claims | `verify-evidence.md` |
| `STUDY_PACK_DRAFTED` | Draft structure validates | `build-study-pack.md` |
| `STUDY_PACK_VALIDATED` | Full publication validation, including independent assessment validation, passes | `build-study-pack.md` |
| `LEARNING_ACTIVE` | Publication remains valid at activation time | `tutor-and-review.md` |

## Scope approval recording

After the learner explicitly approves the displayed scope card, record the observable decision:

```text
python "<SKILL_ROOT>/scripts/record_scope_approval.py" "<COURSE_ROOT>" \
  --summary "<APPROVED_SCOPE>" --source-limit 10 --research-workers 3
```

Use `--accepted-branch` and `--excluded` once per item when applicable. Provided-source modes use `--research-workers 0`; the independent assessment validator is still required for a ready exam.

## Failure boundaries

- If independent workers are unavailable or declined for a researched publishable course, enter `DRAFT_UNVERIFIED`; do not keep reconciling toward `LEARNING_ACTIVE`.
- If a task returns `blocked` or `failed`, record its completion envelope and decide whether the authorized plan permits a bounded retry. Do not rewrite history or start dependent tasks.
- If requirements change after work, the fingerprint resets because progress is observable. If the identical requirement recurs three times, the loop stops.
