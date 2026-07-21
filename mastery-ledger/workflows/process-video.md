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

Resolve `SKILL_ROOT` from the installed `SKILL.md` path. Before remote media work, inspect the active runtime without installing or updating anything:

```text
python "<SKILL_ROOT>/scripts/check_media_runtime.py"
```

Use the Python environment executing the installed skill helpers. The skill includes safe Python wrappers, not vendored copies of `yt-dlp` or FFmpeg. If `yt-dlp` is unavailable, return `needs_user_action` with the exact missing dependency; do not require the Mastery Ledger application. FFmpeg is an optional native executable used for separate-stream merging or export; caption acquisition, metadata probing, and single-stream audio acquisition do not trigger its installation. Never run `pip install -U`, `yt-dlp -U`, or an FFmpeg download during a course workflow.

### Normalize SRT or VTT

```text
python "<SKILL_ROOT>/scripts/normalize_subtitles.py" input.srt \
  --output-dir studies/my-study/records/source/media/SRC-001 \
  --source-id SRC-001 --item-id LESSON-003 \
  --origin human_caption
```

Outputs:

- `transcript.json` with raw cues, normalized segments, cue IDs, and timestamps;
- `transcript.md` with readable timestamped segments.

### Download permitted remote material

```text
python "<SKILL_ROOT>/scripts/download_media.py" "https://example.invalid/video" \
  --output-dir studies/my-study/.work/ingestion/JOB-001/media \
  --source-id SRC-001 \
  --rights-basis explicit_permission \
  --mode human_subtitles --languages "en.*,zh.*"
```

If the probe reports no matching human captions, run a separate `--mode automatic_subtitles` acquisition so provenance remains explicit. The wrapper imports the detected `yt-dlp` Python package, ignores ambient configuration, does not accept cookies, and writes `probe.json` plus a structured job manifest. Run it directly from the skill workflow; the local application has no source-ingestion API.

### Local ASR

```text
python "<SKILL_ROOT>/scripts/transcribe_media.py" lesson.mp4 \
  --output-dir studies/my-study/.work/ingestion/JOB-001/media \
  --source-id SRC-001 --item-id LESSON-003 \
  --model small --language en
```

This optionally uses `faster-whisper`. Record model, version, source hash, language, and origin.

For explicitly approved video download/merge, pass an existing executable or containing directory with `--ffmpeg-location`. If the capability probe reports it unavailable, return `needs_user_action`; do not search for or fetch an arbitrary build. Prefer captions or single-stream audio plus local ASR when those meet the learning goal.

## Durable skill-side processing

The main agent creates one bounded staging folder under `.work/ingestion/<job-id>/` for each acquisition and invokes only the packaged wrappers. Use the manifest states:

`QUEUED`, `RUNNING`, `NEEDS_USER_ACTION`, `PARTIAL`, `COMPLETE`, `FAILED`, `CANCELLED`.

Keep probe output, completion manifests, observable events, and recovery guidance in that staging folder. Retry only after inspecting the recorded failure and correcting an observable cause; do not recursively rerun a failed downloader. Promote verified media and transcripts to `records/source/media/<source-id>/`, write locator-preserving extracted knowledge to `records/source/<source-id>.md`, register it with `register_source.py`, and merge the short action event only after completion. Never call the local application for ingestion, transcription, retry, or promotion.

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
