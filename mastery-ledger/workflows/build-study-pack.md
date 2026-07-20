# Build study pack

## Purpose

Turn approved evidence into a coherent curriculum, concept map, glossary, and assessment bank.

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

- `study-guide.md`
- one source-grounded `lessons/<chapter-id>.md` file for every declared chapter
- `concept-map.md`
- `glossary.md`
- `wiki/wiki.json` and approved Markdown pages under `wiki/pages/`
- `questions/question-bank.json`
- `questions/question-bank.md`, generated from the JSON bank
- `progress/learner-progress.json`
- `evidence/contradictions.json`
- `evidence/gaps.json`
- `evidence/approved-claims.json`
- at least one `exams/<exam-id>/exam.json` for an exam-building run

Use templates from `assets/`.

Keep all drafts, worker reports, reviewer notes, temporary extraction, and scratch files under `.work/`. Only the main agent may promote approved wiki, evidence, question, exam, and learner-state artifacts into their canonical course folders.

## Study-guide shape

Include:

1. learning outcome and assumptions;
2. prerequisite check;
3. concise map of the subject;
4. essential understanding;
5. working understanding;
6. advanced understanding;
7. optional deep dives;
8. worked examples;
9. common misconceptions;
10. comparisons between confusing concepts;
11. applications and limitations;
12. unresolved or disputed questions;
13. summary and suggested sequence;
14. source IDs and precise locators.

Label source facts, interpretation, inference, disputes, outdated claims, and material not covered by the supplied corpus.

## Concept map

Use stable concept IDs and explicit relations:

- `prerequisite_of`
- `supports`
- `deep_dive_of`
- `adjacent_to`
- `example_of`

Hard prerequisites require main-agent or user approval. LLM-proposed relationships remain provisional until approved.

## Questions

Each question must map to objectives, concepts, and canonical `source-ref-v1` objects from [citation contract](../references/citation-contract.md). Important concepts need recall and application questions. Explanations must address common wrong answers without exposing answers before an attempt.

Follow [assessment contract](../references/assessment-contract.md) exactly. Core chapters contain 10 selectable items: 8 `standalone_mcq` and 2 `passage_mcq`. Short or optional chapters contain 5: 4 standalone and 1 passage. Use four options and exactly one correct option. Generate the Markdown review copy and build the ready exam only after independent assessment validation:

```bash
# For a provided-source course without a research graph:
python scripts/create_assessment_plan.py studies/my-study --authorized
# Dispatch only the validator-reported ready task IDs, then:
python scripts/render_question_bank.py studies/my-study/questions/question-bank.json
python scripts/build_exam.py studies/my-study --exam-id EXAM-001 --title "Course exam" --ready
```

## Validation

Run:

```bash
python scripts/validate_study_pack.py studies/my-study --publication
```

Also perform semantic audits for citation faithfulness, pedagogy, and assessment ambiguity. An independent evaluator is preferred when available.

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
