# Verify evidence

## Purpose

Check that worker claims are supported, correctly scoped, and safe to merge.

## Structural validation first

Run:

```bash
python scripts/validate_evidence.py \
  --source-manifest studies/my-study/records/source-manifest.yaml \
  .work/runs/RUN-001/tasks/TASK-RESEARCH-01/submission.json
```

Structural validation checks IDs, confidence bounds, source references, and locators. It does not decide whether a claim is true.

## Citation review

For each foundational, numerical, disputed, current, safety-relevant, or low-confidence claim, open the cited source at the stated locator and check:

- source identity;
- locator accuracy;
- whether the cited passage supports the exact wording;
- whether a short quote is accurate;
- whether inference is mislabeled as fact;
- whether relevant counterevidence was omitted;
- whether the source is stale or superseded.

For a small or moderate study pack, inspect every final factual claim. For a very large corpus, verify all high-risk claims and risk-sample routine supporting claims; record the sampling limits.

## Review decision

Write `assets/review-decision.yaml` shape with one of:

- `verified`
- `changes_required`
- `rejected`
- `blocked`

A citation verifier may mark a report `verified`. The main agent then records an explicit `approved`, `changes_required`, or `rejected` decision. Only `approved` reports are aggregatable.

Every main-agent approval must list `approved_claim_ids` explicitly. Copy only IDs the final citation review verified; never approve a whole report by implication when the verifier rejected individual claims. The aggregator refuses approvals without that allowlist and excludes every claim not named in it.

`route_worker_completion.py` accepts a structurally valid completion envelope; it does not turn a semantic `changes_required` decision into approval. If the verifier reports a missing transcript, locator, or other source input:

1. close the completed verifier normally;
2. repair and register the missing durable source artifact;
3. rerun `create_provided_evidence_plan.py --authorized --supersede-reason "OBSERVABLE REASON"` from `EVIDENCE_SUBMITTED` or `EVIDENCE_VERIFIED`;
4. rerun extraction and citation verification against the new frozen context.

Do not call `manage_worker_runtime.py repair` for a semantic review decision; that command is only for a malformed completion from the same live worker. Do not claim `DRAFT_UNVERIFIED`, publish a chat-only lesson, or begin mastery tracking while reconciliation still returns `needs_work`.

## Contradictions

Do not resolve disagreement by averaging. Record:

- conflicting claim IDs;
- source IDs and locators;
- type of conflict;
- whether both can be true under different assumptions;
- learner-facing explanation required.

## Aggregation

After main-agent approval:

```bash
python scripts/aggregate_approved_evidence.py \
  --reports-dir .work/runs/RUN-001/tasks \
  --reviews-dir .work/runs/RUN-001/tasks \
  --output records/evidence/approved-claims.json
```

The aggregator combines structured approved claims only. It does not write lesson prose or choose a side in disputes.

## Exit gate

The phase is complete only when:

- every report has a review decision;
- required corrections are resolved or recorded as gaps;
- important locators were inspected;
- contradictions are preserved;
- the main agent approved each mergeable report;
- approved evidence is aggregated without duplicate IDs.
