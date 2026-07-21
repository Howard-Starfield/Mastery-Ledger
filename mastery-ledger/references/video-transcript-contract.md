# Video and transcript contract

## Source bundle

A media source should preserve its original hierarchy:

```yaml
source_id: SRC-001
provider: local
source_type: local_video
title: Example course
rights_basis: user_owned
permitted_uses: [personal_study, transcription, derived_notes]
processing_mode: local_only
retrieved_at: "2026-07-19T00:00:00Z"
content_hash: sha256:...
manifest_version: "1.0"
items:
  - item_id: LESSON-001
    parent_item_id: MODULE-001
    kind: lesson
    title: Introduction
    order: 1
artifacts:
  - artifact_id: ART-001
    item_id: LESSON-001
    kind: video
    local_path: videos/lesson-001.mp4
    content_hash: sha256:...
  - kind: transcript_markdown
    path: records/source/media/SRC-001/transcript.md
    content_hash: sha256:...
  - kind: transcript_json
    path: records/source/media/SRC-001/transcript.json
    content_hash: sha256:...
processing_status: complete
```

The source manifest is the worker input authority. Merely mentioning a transcript path inside `records/source/<source-id>.md` does not grant workers access to it. Register durable transcript artifacts explicitly; context compilation includes registered readable artifacts and excludes unregistered or disposable `.work/` files.

## Transcript artifact

Preserve raw cues and normalized segments:

```json
{
  "source_id": "SRC-001",
  "item_id": "LESSON-001",
  "origin": "human_caption",
  "language": "en",
  "source_hash": "sha256:...",
  "transcription_model": null,
  "raw_cues": [
    {
      "cue_id": "12",
      "start_ms": 143200,
      "end_ms": 146900,
      "text": "..."
    }
  ],
  "segments": [
    {
      "segment_id": "SEG-0001",
      "start_ms": 143200,
      "end_ms": 151000,
      "cue_ids": ["12", "13"],
      "speaker": null,
      "text": "...",
      "confidence": null
    }
  ]
}
```

## Origins

- `human_caption`
- `platform_caption`
- `auto_caption`
- `local_asr`
- `user_transcript`

Do not merge origins without preserving provenance.

## Locator format

A learning artifact must use [citation contract](citation-contract.md):

```json
{
  "source_id": "SRC-001",
  "item_id": "LESSON-001",
  "locator": {
    "kind": "timestamp_range",
    "start_ms": 143200,
    "end_ms": 151000,
    "label": "Lesson 1, 00:02:23.200–00:02:31.000"
  },
  "supports": ["claim"],
  "support_strength": "direct"
}
```

Resolve course, module, and lesson titles from the source manifest for human-readable display. Do not encode them only in an unvalidated prose locator.

## Quality checks

- cue and segment timestamps are non-negative and ordered;
- `start_ms < end_ms`;
- segment cue IDs exist in raw cues;
- segment order is monotonic;
- source hash matches the processed original;
- language and origin are recorded;
- ASR model and version are recorded for `local_asr`;
- gaps and low-confidence areas are visible;
- no transcript text is used without a locator.

## Durable job contract

For application integration, use:

```yaml
job_id: JOB-001
attempt_id: ATTEMPT-001
kind: media_download | subtitle_extract | transcription
state: queued | running | needs_user_action | partial | complete | failed | cancelled
source_id: SRC-001
item_id: LESSON-001
progress: 0.0
staging_path: .staging/JOB-001
output_manifest: null
retry_count: 0
error_code: null
recovery_suggestion: null
created_at: "..."
updated_at: "..."
```

The durable Mastery Ledger runtime—not the agent conversation—should own job state, retries, cancellation, and crash recovery.
