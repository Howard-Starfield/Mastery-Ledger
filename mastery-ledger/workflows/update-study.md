# Update study

## Purpose

Incrementally refresh a study when sources, goals, or learner state change without rewriting history.

## Detect changes

Compare:

- source hashes;
- publication and subject dates;
- source versions and supersession links;
- learning outcome and scope;
- concept-map version;
- question and evidence references.

Classify sources as added, unchanged, changed, removed, or superseded.

## Impact analysis

Mark affected:

- claims;
- guide sections;
- concept definitions and edges;
- questions and canonical answers;
- proficiency evidence that depended on invalidated questions;
- scheduled reviews.

Do not invalidate unrelated artifacts.

## Incremental work

Create new bounded tasks only for affected concepts or source sections. Preserve stable IDs when meaning has not changed. Create new IDs when a concept or question changes materially.

Archive superseded artifacts and retain an audit trail. Never silently rewrite learner attempts or judgment overrides.

## Removed sources

Before destructive changes, present exact impact and require explicit approval. Prefer a prepare/commit pattern with a short-lived action token when the backend supports it.

Possible policies:

- `archive`: keep derived notes but mark provenance unavailable;
- `detach`: retain learner-authored notes, remove source-backed claims;
- `drop`: remove source-derived artifacts after approval.

## Revalidation

Rerun evidence, study-pack, and question validation for impacted artifacts. Reopen contradictions when a source changes.

## Exit gate

The update is complete only when:

- changed sources and affected artifacts are recorded;
- only impacted tasks were rerun;
- stable IDs were preserved appropriately;
- learner history remains reconstructable;
- stale claims and questions are removed or labeled;
- validation passes for the updated scope;
- a change summary is shown to the user.
