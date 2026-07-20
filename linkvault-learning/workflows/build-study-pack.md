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
- `concept-map.md`
- `glossary.md`
- `question-bank.json`
- `learner-progress.json`
- `evidence/contradictions.json`
- `evidence/gaps.json`

Use templates from `assets/`.

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

## Validation

Run:

```bash
python scripts/validate_study_pack.py studies/my-study
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
- limitations and untested assumptions are recorded.
