# Build study pack

## Purpose

Turn approved evidence into a coherent learner-facing course, book-like lessons, and assessment bank.

## Main-agent synthesis

The main agent owns final synthesis. It may ask module drafters to work from approved evidence and a frozen outline, but it must normalize:

- terminology and notation;
- assumptions and prerequisites;
- difficulty and depth;
- duplicated concepts;
- cross-module references;
- citation format;
- uncertainty and disagreements.

Do not concatenate worker reports.

## Required artifacts

Create:

- `index.md`, a concise course map linking every chapter
- one source-grounded `lessons/<chapter-id>.md` file for every declared chapter
- `questions/question-bank.json`
- `questions/question-bank.md`, generated from the JSON bank
- `progress/learner-progress.json`
- `records/evidence/contradictions.json`
- `records/evidence/gaps.json`
- `records/evidence/approved-claims.json`
- durable accepted-worker receipts under `records/evidence/validation/`
- at least one `exams/<exam-id>/exam.json` for an exam-building run

Use templates from `assets/`.

Keep all drafts, worker reports, reviewer notes, temporary extraction, and scratch files under `.work/`. Only the main agent may promote approved lessons, evidence, questions, exams, and learner-state artifacts into their canonical course folders. `records/` is durable and auditable; `.work/` is disposable after accepted receipts are recorded.

## Lesson shape

Read and follow [lesson contract](../references/lesson-contract.md). A standard lesson is 1,200-1,800 words; an expanded lesson is 1,800-2,500 words. It must teach in a deliberate sequence, include two worked examples, retrieval pauses, misconceptions, limitations, transfer, and precise citations. A raw extraction, outline, catalog entry, or compressed source summary does not satisfy this contract.

## Questions

Each question must map to objectives, concepts, and canonical `source-ref-v1` objects from [citation contract](../references/citation-contract.md). Important concepts need recall and application questions. Explanations must address common wrong answers without exposing answers before an attempt.

Follow [assessment contract](../references/assessment-contract.md) exactly. Every chapter declares a question tier: standard 10 (8 standalone, 2 passage), expanded 15 (12/3), or large 20 (16/4). Use four options and exactly one correct option. After evidence approval, write and validate `index.md` and every lesson, then create a separate assessment run. Generate the Markdown review copy and build the ready exam only after independent assessment validation:

```bash
python scripts/create_assessment_plan.py studies/my-study --authorized
# Compile, dispatch, and route only validator-reported ready task IDs, then:
python scripts/render_question_bank.py studies/my-study/questions/question-bank.json
python scripts/build_exam.py studies/my-study --exam-id EXAM-001 --title "Course exam" --ready
```

`create_assessment_plan.py` requires `EVIDENCE_APPROVED` (or a later draft state), non-empty approved claims, a substantive index, contract-valid lessons, and a finished predecessor evidence run when one exists. It records that predecessor before activating the assessment plan. This deliberate phase boundary ensures rejected evidence never consumes assessment-generation tokens.

If validation identifies an invalid legacy or hand-authored active plan, do not edit that YAML. After showing the exact validation errors and obtaining learner approval to replace that run, invoke `create_assessment_plan.py --authorized --supersede-reason "<observable reason>"`. The compiler snapshots the rejected plan, creates a clean assessment run, and excludes the superseded plan from the publication chain.

## Validation

Run:

```bash
python scripts/validate_study_pack.py studies/my-study --publication
```

Also perform semantic audits for citation faithfulness, pedagogy, and assessment ambiguity. An independent evaluator is preferred when available.

Return to `reconcile_workflow.py` after each repair. Do not manually set `STUDY_PACK_DRAFTED`, `STUDY_PACK_VALIDATED`, or `LEARNING_ACTIVE`; the reconciliation gate advances them only after the corresponding validation passes.

## Exit gate

The phase is complete only when:

- every core objective has concept and assessment coverage;
- all final factual claims are supported or labeled inference;
- no unapproved report entered the pack;
- contradictions and gaps are visible;
- prerequisite order is coherent;
- validators pass;
- the question mix and app-compatible schema pass;
- an independently validated ready exam exists;
- limitations and untested assumptions are recorded.
