# LinkVault integration

## Principle

Use the real LinkVault service or exported course bundle when available. Do not invent tool names, database tables, folder layouts, or downloader capabilities from this skill.

## Integration order

1. **Audited LinkVault MCP or local service:** discover the exposed tools and schemas, then use them for ingestion jobs, source manifests, transcript retrieval, and durable state.
2. **Existing course folder:** inspect and import its actual manifest, hierarchy, media, captions, transcripts, exercises, and partial-download state.
3. **Authorized local files:** use the bundled normalization and ASR utilities for the supported subset.
4. **No accessible backend:** explain the missing capability and continue with supplied documents or topic research.

## Ownership boundary

There must be one durable operational authority for:

- downloader and transcription jobs;
- SQLite writes;
- retries, cancellation, and crash recovery;
- source hashes and artifact registration;
- file watchers;
- task, evidence, and proficiency events.

The desktop app and MCP adapter must not independently mutate the same state without an explicit single-writer contract. The skill should not open LinkVault’s database directly unless the application publishes that interface.

## Expected service capabilities

Discover rather than assume equivalents of:

- create, inspect, cancel, and retry an ingestion job;
- list sources, course items, and artifacts;
- retrieve transcript segments with timestamp locators;
- register authorized local media;
- read study and learner state;
- submit task reports and review decisions;
- export a study workspace.

If the service exposes different names, use its schemas.

## Existing course import

Preserve:

- course → module → lesson ordering;
- original provider metadata;
- video, audio, subtitle, transcript, reading, exercise, and attachment relationships;
- partial or failed artifact states;
- original hashes and local paths;
- rights and processing mode.

Do not redownload material already present and valid.

## Media work

Prefer LinkVault’s durable ingestion backend over `scripts/download_media.py` when the backend is available and audited. The bundled script is a conservative fallback for permitted remote material, not a replacement for application job management.

## Agent versus service

The main agent performs interpretation, scoping, evidence review, synthesis, and tutoring. The LinkVault service performs deterministic storage, media jobs, manifests, retrieval, and durable state transitions. An MCP process does not automatically inherit the host agent’s model.
