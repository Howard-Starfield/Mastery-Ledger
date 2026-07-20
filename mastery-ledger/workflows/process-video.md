# Process video

## Purpose

Acquire or process authorized media, prefer existing captions, and produce timestamp-preserving transcript artifacts suitable for citation.

## Rights gate

For remote media, require one of:

- `user_owned`
- `platform_permitted_download`
- `public_license`
- `explicit_permission`

Refuse `unknown`. Never request browser cookies, credentials, DRM bypass, or access-control circumvention. The user remains responsible for platform terms and permissions.

Local media supplied by the user may be processed as `user_owned` or another declared basis.

## Processing order

1. Human-created subtitle file already present.
2. Platform-provided subtitle file the user is permitted to obtain.
3. Auto-generated captions, clearly labeled.
4. Local ASR over an authorized local media file.
5. Mark unavailable when none succeeds.

Never discard the raw subtitle or media file.

## Bundled utilities

### Normalize SRT or VTT

```bash
python scripts/normalize_subtitles.py input.srt \
  --output-dir studies/my-study/sources/transcripts \
  --source-id SRC-001 --item-id LESSON-003 \
  --origin human_caption
```

Outputs:

- `transcript.json` with raw cues, normalized segments, cue IDs, and timestamps;
- `transcript.md` with readable timestamped segments.

### Download permitted remote material

```bash
python scripts/download_media.py "https://example.invalid/video" \
  --output-dir studies/my-study/sources/SRC-001 \
  --rights-basis explicit_permission \
  --mode subtitles --languages "en.*,zh.*"
```

This wrapper requires `yt-dlp`, does not accept cookies, and writes a job manifest. Use the installed Mastery Ledger runtime instead when it exposes an audited, durable downloader API.

### Local ASR

```bash
python scripts/transcribe_media.py lesson.mp4 \
  --output-dir studies/my-study/sources/transcripts \
  --source-id SRC-001 --item-id LESSON-003 \
  --model small --language en
```

This optionally uses `faster-whisper`. Record model, version, source hash, language, and origin.

## Durable product integration

For the Mastery Ledger application, downloading and transcription should be durable backend jobs, not conversation-only processes. Use states:

`QUEUED`, `RUNNING`, `NEEDS_USER_ACTION`, `PARTIAL`, `COMPLETE`, `FAILED`, `CANCELLED`.

The service should own retries, cancellation, staging directories, completion manifests, and crash recovery. The skill should call that service when available.

## Transcript quality checks

Verify:

- monotonically ordered timestamps;
- no negative or reversed intervals;
- raw cue-to-segment mapping;
- origin and ASR model provenance;
- source hash consistency;
- no unexplained transcript gaps;
- readable language and encoding.

## Exit gate

The phase is complete only when:

- rights basis is recorded;
- the original media or subtitle remains intact;
- each transcript segment has source and item IDs plus timestamps;
- provenance identifies human, platform, auto-caption, or local ASR;
- failed stages have recovery guidance;
- transcript artifacts are registered in the source manifest.
