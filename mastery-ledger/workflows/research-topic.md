# Research topic

## Purpose

Build a bounded, current, source-grounded corpus for an on-the-fly learning topic.

## Preconditions

The learning outcome, scope, exclusions, source policy, and worker budget must be approved. If they are not, return to `intake-and-scope.md`.
The calibration disposition and canonical learning contract must also exist. When no source is supplied, reconciliation requires an authorized deterministic source-discovery plan before source acquisition. The evidence run is compiled later, only after retained sources are registered and the course reaches `SOURCES_READY`. If subagents are unavailable, stop at `DRAFT_UNVERIFIED`; do not convert a conversational self-review into publishable evidence.

## Scout before fan-out

Run one bounded source-scout subagent through `create_source_discovery_plan.py`, compiled context, orchestration validation, and `route_worker_completion.py`. The scout identifies:

- canonical terminology;
- prerequisites;
- likely primary sources;
- disputed or fast-changing subareas;
- source availability;
- candidate modules and adjacent branches.

Do not treat scout snippets or its candidate ledger as evidence. The main agent reviews the ledger, opens retained candidates, extracts locator-preserving Markdown, and registers each accepted source with `register_source.py`. Do not create the research/evidence plan until reconciliation reaches `SOURCES_READY`.

## Source priorities

Prefer, in order appropriate to the domain:

1. official specifications, documentation, datasets, and standards;
2. original papers, textbooks, lectures, and first-party material;
3. authoritative institutions and high-quality reviews;
4. reputable secondary explanation;
5. community discussion only for experience reports or unresolved friction.

Open and inspect a source before citing it. Record publication date, subject date, retrieval date, and whether it is superseded.

## Bounded collection

Respect the approved source limit. Stop when objectives and prerequisites are adequately supported. More sources are not automatically better.

Create a source manifest entry for every retained source through `register_source.py`. Workers submit claims through evidence packets, not prose-only summaries.

For every retained source, create `source/SRC-NNN.md` containing the extracted knowledge and exact locators. Keep downloaded originals and media under `source/media/SRC-NNN/`. Set `knowledge_path` in the manifest and do not mark the source `ready` until the Markdown artifact exists and is non-empty.

## Current and disputed material

For claims likely to change:

- compare publication and event dates;
- prefer current primary sources;
- mark the research cutoff date;
- identify superseded information.

For disagreement:

- retain each source-supported position;
- classify the disagreement as factual, definitional, methodological, historical, or interpretive;
- do not manufacture consensus.

## External-research boundaries

In `provided-material-only` mode, do not browse. In `hybrid` mode, use research only to fill approved gaps, prerequisites, corrections, or updates. Clearly label external additions.

## Exit gate

The phase is complete only when:

- inspected sources are in the manifest;
- search snippets are not used as final evidence;
- each proposed claim has a precise locator;
- source limits were respected or expansion was approved;
- current and disputed areas are marked;
- evidence packets are ready for verification.
