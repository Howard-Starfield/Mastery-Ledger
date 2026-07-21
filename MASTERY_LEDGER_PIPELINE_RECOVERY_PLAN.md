# Mastery Ledger Pipeline Recovery Plan

Status: implemented, verified, and integrated into `main`.
Incident: Codex task `019f8291-6499-7d81-aa8d-2b490b532493`.
Scope: topic-research course creation through evidence handoff; wiki-format migration remains deferred

## Outcome

A learner request to build a researched course must retain `LEARNING_ACTIVE` as its terminal target and make observable progress toward it. An internal worker-format failure must repair or retry the same task without discarding accepted work. The run may end only as:

1. `LEARNING_ACTIVE` with substantive, validated learner artifacts;
2. `DRAFT_UNVERIFIED` with a labelled source-grounded draft and exact remaining verification work; or
3. `needs_user_input` for a decision that cannot be inferred safely.

Blank canonical templates plus conversational tutoring are not a valid course-build outcome.

## Incident facts to preserve

- The installed skill matched the repository; stale installation was not the cause.
- Four corpus-mapper workers ran, but no research worker ran.
- Planning was allowed while the initialized manifest contained a fake ready source.
- The approved learner scope was stored under `scope_approval`, while task scope still used the generic template `learner_goal`.
- A fixed five-source task limit caused an eight-source corpus to be mapped incompletely.
- Recreating `run-plan.yaml` discarded a valid map and populated research lanes.
- One YAML punctuation repair invalidated the active context and triggered a whole-run restart.
- The final worker used semantically similar but invalid completion-envelope field names.
- The documented completion receptionist had no executable implementation.
- Reconciliation was invoked with intermediate targets rather than retaining `LEARNING_ACTIVE`.

## Non-negotiable invariants

### Course target

- New course initialization records `workflow_target: LEARNING_ACTIVE`.
- Course-building reconciliation uses the recorded target. Intermediate gates are progress, not terminal success.
- Reconciliation and task routing persist the same target until completion or an explicit terminal fallback.

### Source readiness

- A new source manifest starts with `sources: []`; examples remain documentation only.
- A topic-research course with no supplied source compiles one bounded source-scout run at `SCOPED`; the accepted candidate ledger is not evidence.
- The main agent reviews retained candidates, extracts locator-preserving Markdown, and registers sources before evidence planning.
- A source is registered atomically through a script that validates its knowledge path and computes its content hash.
- Research-plan compilation fails unless the course has reached `SOURCES_READY` and every retained manifest source passes the source gate.

### Approved scope

- The learner-visible scope summary, accepted branches, exclusions, source limit, and worker count form one canonical learning contract.
- Plan compilation derives its goal and task boundaries from that contract, not placeholder fields.
- The mapper receives the complete ready corpus. Bounded source subsets begin with research workers.
- Every retained source receives one isolated source-extractor task; contradiction review waits for all extractors and concept-research workers.

### Plan lifecycle

- An active publication-intent run cannot be silently overwritten.
- Supersession is explicit, records a reason and predecessor, and preserves the old plan under its run directory.
- A task repair or retry remains in the same run and does not reset accepted dependencies.
- Task status and mapper-to-research routing change only through deterministic scripts.

### Worker contracts

- Context compilation writes a prefilled task-specific `completion-template.json` and records its hash.
- The dispatch message names that exact template; workers do not reconstruct the envelope from prose.
- The completion router validates the envelope, output, event shard, identity, acknowledgements, and paths before changing task state.
- A malformed completion produces `changes_required` plus a bounded same-task repair packet. It never silently becomes a fresh run.

### Phase boundaries

- The research graph ends at contradiction review and citation verification.
- The main agent approves and aggregates evidence before learner-material synthesis.
- Assessment generation and independent validation use a separate assessment run after approved evidence and a substantive draft exist.
- Provisional material remains under `.work/`; canonical learner artifacts are promoted only after their gate passes.

## Target workflow

```text
initialize course (target=LEARNING_ACTIVE)
  -> calibrate and approve canonical learning contract
  -> when no source is supplied: compile/dispatch/route one source-scout run
  -> review candidate ledger, extract, and atomically register sources
  -> reconcile SOURCES_READY as progress toward LEARNING_ACTIVE
  -> compile one protected research run
  -> compile context and dispatch mapper plus one isolated extractor per retained source
  -> route completion
       valid: freeze map and bind research lanes in the same run
       malformed: repair/retry TASK-MAP in the same run
  -> dispatch bounded research wave
  -> contradiction review
  -> citation verification
  -> main-agent approval and evidence aggregation
  -> synthesize staged study pack
  -> compile separate assessment run
  -> generate and independently validate questions
  -> promote learner artifacts and ready exam
  -> reconcile to LEARNING_ACTIVE
```

## Implementation slices

### Slice A — preflight and canonical scope

- Replace the fake source-manifest record with an empty list.
- Add deterministic source registration/validation.
- Persist `workflow_target` and a canonical learning contract.
- Require source readiness and approved-budget parity in `create_research_plan.py`.
- Give the mapper every ready source and remove assessment tasks from the research graph.
- Require a compiled source-scout subagent before source acquisition for source-less researched courses.

### Slice B — protected plans and exact worker outputs

- Replace the initialized empty placeholder without treating it as a run; snapshot every real run under its run ID.
- Refuse active-plan replacement unless explicit supersession is requested.
- Store a canonical run snapshot under `.work/runs/<run-id>/run-plan.yaml`.
- Compile a prefilled completion template into each task directory.
- Validate the completion-template hash as part of dispatch readiness.

### Slice C — completion routing and bounded recovery

- Add an executable completion router.
- Accept valid `submitted` envelopes; route valid `blocked` and `failed` results through the same bounded repair policy.
- For malformed envelopes, emit field-level validation errors and create a repair dispatch for the same task.
- Track task attempts independently of run creation; default to two repair attempts.
- Merge events only after acceptance.

### Slice D — deterministic mapper handoff

- Add a mapper-freeze/router command that validates the corpus-map output and binds approved lanes to the pre-created research tasks.
- Eliminate direct YAML status and task-scope editing by the main agent.
- Return `context_required_task_ids` and `ready_task_ids` after every accepted completion.

### Slice E — terminal outcome and phase split

- Require course-build instructions to retain the recorded `LEARNING_ACTIVE` target.
- Split assessment planning from research planning for every mode.
- On retry exhaustion, create a labelled draft under `.work/drafts/`, record `DRAFT_UNVERIFIED`, and report exact remaining gates.
- Never treat an intermediate reconciliation target as completion of a course-build request.

## Regression matrix

| Case | Required result |
| --- | --- |
| Fresh topic course | Manifest has no fake source; reconciliation requires a compiled source-scout subagent before acquisition, and evidence planning fails before sources are ready. |
| Approved beginner scope | Mapper brief contains the approved summary/branches/exclusions, not generic template text. |
| Eight sources, limit twelve | Mapper receives all eight; each research task receives only its assigned subset. |
| Active plan exists | A second plan compile fails unless explicit supersession is supplied. |
| Source metadata punctuation repair | Affected context is invalidated or repaired without discarding accepted unrelated tasks. |
| Worker uses `worker_role` instead of `role` | Router returns `changes_required` and a same-task repair dispatch. |
| Repaired completion | Same task becomes submitted; its event merges once; downstream context becomes compilable. |
| Repeated malformed completion | Bounded retry reaches `DRAFT_UNVERIFIED`; no infinite mapper loop and no blank-success response. |
| Research completion | Evidence is approved before study-pack or assessment generation. |
| Course build | Final success requires substantive guide, lessons, question bank, independent assessment validation, ready exam, and `LEARNING_ACTIVE`. |

## Verification gates

- Unit tests for source registration, scope propagation, plan overwrite protection, completion-template compilation, routing, and retry accounting.
- A replay-style test reproducing the malformed completion from the incident and proving same-run recovery.
- A full deterministic fixture from initialization through `LEARNING_ACTIVE` with research and assessment as separate runs.
- Existing application/runtime tests remain unchanged unless a shared contract intentionally changes.
- Run repository Python tests, skill tests, skill package validation, compilation checks, and `git diff --check`.

## Verification record

Verified on 2026-07-20 from `D:\AI_projects\Tutor_AI\.work\pipeline-recovery`:

- `python -m compileall -q mastery-ledger/scripts mastery-ledger/tests`
- Skill Creator `quick_validate.py mastery-ledger` with `PYTHONUTF8=1`
- `python -m pytest -q`: 58 passed
- `git diff --check`

The only test-run warning was an existing `requests` dependency compatibility warning; it did not fail the suite. The implementation remains isolated from the dirty main worktree until an overlap audit and explicit integration step.

## Deferred work

- Global and per-course Markdown wiki/index migration.
- UI rendering changes unrelated to showing pipeline state.
- Live web-search quality evaluation beyond deterministic source registration and provenance checks.
