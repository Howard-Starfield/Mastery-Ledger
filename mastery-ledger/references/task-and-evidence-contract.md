# Task and evidence contract

## Task brief

Every delegated task must use this conceptual shape:

```yaml
task_id: TASK-001
run_id: RUN-001
role: research-worker
objective: Explain the policy-gradient theorem and REINFORCE
scope_included:
  - policy-gradient theorem
  - likelihood-ratio estimator
scope_excluded:
  - PPO
  - actor-critic implementation
concept_ids: [policy-gradient, reinforce]
input_source_ids: []
source_limit: 5
dependencies: [TASK-000]
output_path: .work/orchestration/reports/REPORT-001.json
completion_path: .work/orchestration/completions/TASK-001.json
required_schema: evidence-packet-v1
reviewer_role: citation-verifier
acceptance_criteria:
  - Every factual claim has a source ID and precise locator
  - Contradictions and gaps are preserved
status: planned
```

Every worker writes only its assigned output plus one `completion-envelope-v1` JSON record shaped like `assets/completion-envelope.json`. The envelope contains an observable summary, artifacts, blockers, and next actions; it must not contain prompts, hidden reasoning, scratch notes, or chain-of-thought. Scratch work remains under `.work/scratch/` and is never promoted.

## Evidence packet

```json
{
  "source_ref_schema": "source-ref-v1",
  "report_id": "REPORT-001",
  "task_id": "TASK-001",
  "worker_role": "research-worker",
  "scope": {
    "included": ["policy-gradient theorem"],
    "excluded": ["PPO"]
  },
  "sources_used": ["SRC-001"],
  "claims": [
    {
      "claim_id": "CLM-001",
      "concept_ids": ["policy-gradient"],
      "claim": "The basic estimator can have high variance.",
      "claim_type": "source_fact",
      "source_refs": [
        {
          "source_id": "SRC-001",
          "locator": {
            "kind": "page_range",
            "start": 8,
            "end": 9,
            "label": "Section 4, pages 8–9"
          },
          "supports": ["claim"],
          "supporting_excerpt": "Short excerpt for review.",
          "support_strength": "direct"
        }
      ],
      "confidence": 0.94,
      "assumptions": [],
      "limitations": [],
      "counterevidence": []
    }
  ],
  "contradictions": [],
  "unresolved_questions": [],
  "suggested_concepts": [],
  "scope_drift": [],
  "quality_notes": []
}
```

## Claim types

- `source_fact`: directly supported by source evidence.
- `interpretation`: a reasoned reading of evidence.
- `inference`: conclusion extending beyond direct wording.
- `disputed`: credible sources disagree.
- `outdated`: formerly correct or superseded.
- `not_covered`: requested point absent from approved sources.

## Source-reference requirements

Follow [citation contract](citation-contract.md). Each factual source reference needs:

- valid source ID;
- structured, precise locator;
- non-empty `supports` list;
- support strength: `direct`, `partial`, or `contextual`;
- optional short excerpt for reviewer convenience.

The excerpt is not the durable citation. The source ID and locator are.

## Review decision

```yaml
review_id: REVIEW-001
report_id: REPORT-001
reviewer_role: citation-verifier
decision: verified
checks:
  source_ids: pass
  locators: pass
  claim_support: pass
  counterevidence: pass
issues: []
verified_claim_ids: [CLM-001]
rejected_claim_ids: []
sampled_claim_ids: []
required_actions: []
approved_by: null
reviewed_at: "2026-07-19T00:00:00Z"
```

The main agent records `approved_by: main-agent` and changes the decision to `approved` before aggregation.
