# Verify evidence

## Purpose

Check that worker claims are supported, correctly scoped, and safe to merge.

## Structural validation first

Run:

```bash
python scripts/validate_evidence.py \
  --source-manifest studies/my-study/source-manifest.yaml \
  orchestration/reports/REPORT-001.json
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
  --reports-dir orchestration/reports \
  --reviews-dir orchestration/reviews \
  --output evidence/approved-claims.json
```

The aggregator combines structured approved claims only. It does not write study-guide prose or choose a side in disputes.

## Exit gate

The phase is complete only when:

- every report has a review decision;
- required corrections are resolved or recorded as gaps;
- important locators were inspected;
- contradictions are preserved;
- the main agent approved each mergeable report;
- approved evidence is aggregated without duplicate IDs.
