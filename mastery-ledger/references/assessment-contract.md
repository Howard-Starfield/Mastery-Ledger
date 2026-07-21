# Assessment contract

## Contents

1. Calibration versus published assessment
2. Required chapter mix
3. Canonical question schema
4. Examples
5. Independent validation
6. Interaction records

## 1. Calibration versus published assessment

Topic-only calibration uses the opening prior-knowledge response plus at most two follow-ups by default. A learner may explicitly request a deeper 5-10 question diagnostic. Supplied-material Fast Courses use early sourced practice instead of blocking pre-course calibration. Calibration never updates durable mastery until sourced material and grading criteria exist.

Published chapter banks are source-grounded selectable-response items. Use them for ready exams and spaced review.

Every chapter record must declare a `lesson_path` under `lessons/`. Questions test the corresponding readable lesson; they do not replace it.

## 2. Required chapter mix

Use one of three exact chapter tiers. Every published chapter has at least 10 questions:

| `question_tier` | Total | `standalone_mcq` | `passage_mcq` |
| --- | ---: | ---: | ---: |
| standard | 10 | 8 | 2 |
| expanded | 15 | 12 | 3 |
| large | 20 | 16 | 4 |

This 80/20 split is a Mastery Ledger product policy, not a universal psychometric law. A passage item contains a short reading, case, data extract, or scenario inside the prompt and still has selectable answers. Never satisfy the ratio with open-response items.

Every published item must have four options, exactly one correct option, a concise supported explanation, misconception-based distractors, objective and concept IDs, difficulty 1-5, and at least one canonical `source-ref-v1` reference. Do not use `all of the above`, `none of the above`, trick wording, grammatical cues, or an option that is only correct because it is longer or more qualified.

## 3. Canonical question schema

Question banks and embedded exam questions use the same delivery fields:

```json
{
  "question_id": "Q-CH1-001",
  "chapter_id": "CH-001",
  "concept_ids": ["concept-retrieval"],
  "objective_ids": ["OBJ-001"],
  "type": "multiple-choice",
  "format": "standalone_mcq",
  "difficulty": 2,
  "prompt": "Which action is retrieval practice?",
  "options": [
    {"option_id": "A", "text": "Rereading a highlighted paragraph"},
    {"option_id": "B", "text": "Answering from memory before checking notes"},
    {"option_id": "C", "text": "Copying a definition word for word"},
    {"option_id": "D", "text": "Watching the same explanation twice"}
  ],
  "correct_option_id": "B",
  "correct_explanation": "Retrieval practice requires attempting to bring the information to mind before consulting the source.",
  "distractor_rationales": {
    "A": "Confuses review exposure with retrieval.",
    "C": "Confuses transcription with retrieval.",
    "D": "Confuses repeated exposure with retrieval."
  },
  "source_refs": [
    {
      "source_id": "SRC-001",
      "locator": {"kind": "heading", "value": "Retrieval practice", "label": "Retrieval practice"},
      "supports": ["correct_answer", "explanation"],
      "support_strength": "direct"
    }
  ],
  "quality_status": "validated"
}
```

`options` and `correct_option_id` are mandatory. Do not emit the legacy `correct_answer` plus `distractors` shape for a selectable item.

## 4. Passage example

```json
{
  "question_id": "Q-CH1-009",
  "chapter_id": "CH-001",
  "concept_ids": ["concept-retrieval"],
  "objective_ids": ["OBJ-002"],
  "type": "multiple-choice",
  "format": "passage_mcq",
  "difficulty": 3,
  "prompt": "A learner reads a section twice, closes the book, writes everything remembered, then checks the section and corrects omissions. Which step most directly provides retrieval practice?\n\nA short case may appear here, but it must contain only information needed to answer.",
  "options": [
    {"option_id": "A", "text": "Reading the section the first time"},
    {"option_id": "B", "text": "Reading the section the second time"},
    {"option_id": "C", "text": "Writing from memory with the book closed"},
    {"option_id": "D", "text": "Correcting omissions while viewing the section"}
  ],
  "correct_option_id": "C",
  "correct_explanation": "The closed-book attempt requires retrieval; checking afterward supplies feedback.",
  "distractor_rationales": {
    "A": "Initial study is exposure.",
    "B": "Repeated reading is restudy.",
    "D": "Checking is feedback after the retrieval attempt."
  },
  "source_refs": [],
  "quality_status": "draft"
}
```

The example's empty references and `draft` status are intentionally non-publishable. A worker must add verified source references before validation.

## 5. Independent validation

The main agent authors the assessment only after retained claims pass final citation verification. Give the independent assessment validator the frozen objectives, approved evidence, and main-agent-authored bank—never hidden reasoning or scratch notes. It must reject or request changes for:

- more than one defensible answer;
- a key unsupported by the cited locator;
- implausible, overlapping, or source-contradicted distractors;
- answer leakage or cueing;
- duplicate prompts;
- missing chapter coverage or an incorrect 80/20 mix;
- legacy fields that the application cannot deliver.

Only the main agent promotes validated questions and runs `scripts/build_exam.py`. A ready exam must load under the same contract as the local web application.

## 6. Interaction records

Record only observable events: prompt or passage shown, option or answer submitted, confidence when supplied, feedback shown, hint level, source-disclosure action, timestamp, and resulting proficiency update. Never record hidden chain-of-thought. Keep calibration interactions in `progress/calibration.json`; application attempts remain under `attempts/`; machine-readable actions remain in `records/logs/events.jsonl`.
