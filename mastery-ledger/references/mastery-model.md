# Proficiency and review model

## Terminology

Use evidence-based states rather than absolute mastery:

- `unseen`
- `introduced`
- `practicing`
- `proficient`
- `stable`
- `rusty`
- `needs_reassessment`

## Separate dimensions

Track:

- `proficiency_score`: demonstrated performance from 0 to 1;
- `confidence_score`: learner confidence from 0 to 1;
- attempts and result counts;
- assistance used;
- application success;
- misconceptions;
- last and next review timestamps;
- evidence events.

Correctness and confidence are not the same. A learner can be correct but uncertain, or confidently wrong.

## Deterministic update

The bundled `update_mastery.py` applies a transparent provisional rule:

- result base: correct `+0.12`, partial `+0.04`, uncertain `-0.03`, incorrect `-0.10`;
- difficulty multiplier: `0.8 + 0.1 × difficulty`, difficulty 1–5;
- assistance multiplier: `1 - 0.15 × assistance_level`, assistance 0–5, with a floor of `0.25`;
- application bonus: `+0.03` for an application or transfer success;
- proficiency is clamped to `[0, 1]`;
- confidence moves 20% toward the explicit evaluation confidence;
- misconceptions are deduplicated and retained until explicitly resolved.

This is a product heuristic, not FSRS, SM-2, or a validated cognitive model.

## State mapping

A suggested provisional mapping:

- `<0.15`: unseen or introduced depending on attempts;
- `0.15–0.44`: practicing;
- `0.45–0.69`: proficient;
- `0.70–0.84`: stable if supported by repeated reviews;
- `≥0.85`: stable, still subject to decay and reassessment;
- any recent repeated failure: rusty or needs_reassessment.

Do not map score alone. Recency, repeated evidence, and unresolved misconceptions matter.

## Review schedule

Until an adaptive scheduler is implemented, use configurable intervals such as:

- incorrect: same session or next day;
- partial or heavily assisted: 1–3 days;
- correct recall: 3–7 days;
- unaided application: 7–14 days;
- stable repeated performance: lengthen conservatively.

Record the scheduling rule and make it inspectable. Do not claim a fixed doubling curve is universal or optimal.
