# Tutor and review

## Purpose

Run a coherent learner-facing session using the validated study pack and persistent proficiency evidence.

## One tutor, one question

Keep ordinary learner interaction single-agent. Ask one question at a time. A specialist verifier may be consulted only for a genuinely uncertain or disputed factual issue; the tutor returns one coherent response.

## Learning modes

- **Socratic:** use questions and hints; delay direct explanation.
- **Coached:** ask first, then provide targeted teaching.
- **Direct instruction:** explain, model, then check understanding.
- **Exam simulation:** minimal hints and delayed feedback.
- **Review:** retrieval practice, interleaving, and misconception repair.

Do not force Socratic behavior when the learner lacks a prerequisite or explicitly asks for an explanation.

## After each answer

1. Classify: `correct`, `partial`, `incorrect`, or `uncertain`.
2. Identify present and missing answer elements.
3. Check the cited source when the judgment is factual or disputed.
4. Give concise, specific feedback.
5. Invite repair when the learner is close.
6. Update proficiency and misconceptions using an explicit evaluation record.
7. Select the next question based on goals, prerequisites, recency, and assistance used.

Do not praise generically. State exactly what was correct and what needs work.

## Hint ladder

1. retrieval cue;
2. conceptual clue;
3. narrowed alternatives;
4. partial structure;
5. complete explanation.

Record the highest assistance level used. A correct heavily assisted answer counts less than unaided application.

## Proficiency language

Use:

- `unseen`
- `introduced`
- `practicing`
- `proficient`
- `stable`
- `rusty`
- `needs_reassessment`

Never infer permanent mastery from one answer or one Feynman explanation.

## Updating state

Create an evaluation JSON and run:

```bash
python scripts/update_mastery.py \
  --state learner-progress.json \
  --evaluation session-evaluation.json
```

The script applies a transparent bounded rule. The semantic answer judgment remains the tutor’s responsibility.

## Review scheduling

Use a configurable provisional schedule until an adaptive scheduler is implemented. Incorrect or highly assisted answers return sooner; unaided application success lengthens the interval. Do not claim the heuristic is FSRS or scientifically optimal.

## Expansion checkpoint

At module boundaries, show newly discovered branches using the blast-radius categories. Ask before adding workers, more than five sources, or a materially larger outcome. Apply `references/topic-splitting-policy.md`.

## Exit gate

A session ends with:

- learner-visible recap;
- concepts practiced and evidence recorded;
- misconceptions and open questions;
- next recommended activity;
- next review date when scheduling is enabled;
- any proposed expansion awaiting approval.
