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
- `lessons/glossary.json`, containing the course terms, concise definitions, chapter links, aliases, and source references
- `questions/question-bank.json`
- `questions/question-bank.md`, generated from the JSON bank
- `progress/learner-progress.json`
- `records/evidence/contradictions.json`
- `records/evidence/gaps.json`
- `records/evidence/approved-claims.json`
- durable accepted-worker receipts under `records/evidence/validation/`
- at least one `exams/<exam-id>/exam.json` for an exam-building run

Read `study.yaml.learning_contract.output_contract` before authoring. Create exactly its `chapter_count` and `chapter_ids`; do not silently collapse an approved multi-chapter course into one lesson. Reconciliation rejects a question bank whose chapter count or order differs from that frozen output contract.

Use templates from `assets/`.

Populate `lessons/glossary.json` only from approved evidence and the final lesson vocabulary. Use `course-glossary-v1`. Give every term a stable `term_id`, a concise learner-facing `term`, a self-contained `definition`, zero or more `aliases`, one or more declared `chapter_ids`, and at least one canonical `source-ref-v1` object. Merge spelling and capitalization variants through `aliases`; do not create duplicate entries. Include the terms a learner needs to read the course, not every ordinary word in the sources.

Keep all drafts, worker reports, reviewer notes, temporary extraction, and scratch files under `.work/`. Only the main agent may promote approved lessons, evidence, questions, exams, and learner-state artifacts into their canonical course folders. `records/` is durable and auditable; `.work/` is disposable after accepted receipts are recorded.

## Lesson shape

Read and follow [lesson contract](../references/lesson-contract.md). A standard lesson is 1,200-1,800 words; an expanded lesson is 1,800-2,500 words. It must teach in a deliberate sequence, include two worked examples, retrieval pauses, misconceptions, limitations, transfer, and precise citations. A raw extraction, outline, catalog entry, or compressed source summary does not satisfy this contract.

## Questions

Each question must map to objectives, concepts, and canonical `source-ref-v1` objects from [citation contract](../references/citation-contract.md). Important concepts need recall and application questions. Explanations must address common wrong answers without exposing answers before an attempt.

Follow [assessment contract](../references/assessment-contract.md) exactly. Every chapter declares a question tier: standard 10 (8 standalone, 2 passage), expanded 15 (12/3), or large 20 (16/4). Use four options and exactly one correct option. After evidence approval, the main agent writes and validates `index.md`, every lesson, and the canonical JSON question bank. Reconciliation requires substantive lessons; source notes, transcript summaries, and initialized shells cannot advance. Generate the Markdown review copy and ready exam only after one independent assessment validator checks that exact bank:

```bash
python scripts/create_assessment_plan.py studies/my-study --authorized
# Compile TASK-ASSESSMENT-VALIDATE, dispatch it through manage_worker_runtime.py,
# route its return, and close the validator agent, then:
python scripts/render_question_bank.py studies/my-study/questions/question-bank.json
python scripts/build_exam.py studies/my-study --exam-id EXAM-001 --title "Course exam" --ready
```

`create_assessment_plan.py` requires `EVIDENCE_APPROVED` (or a later draft state), non-empty approved claims, a substantive index, contract-valid lessons, the main-agent-authored question bank, and a finished predecessor evidence run when one exists. It compiles only `TASK-ASSESSMENT-VALIDATE`; new runs have no assessment-generator worker.

If the validator returns `changes_required` or `rejected`, close that completed validator, repair the canonical bank from its exact item-level issues, and compile a new validation run with `--supersede-reason "OBSERVABLE REASON"`. Never use worker completion repair for a semantic assessment decision, and never build a ready exam from the rejected bank.

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
