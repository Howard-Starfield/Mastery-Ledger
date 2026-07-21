# Process video

## Purpose

Acquire or process authorized media, prefer existing captions, and produce timestamp-preserving transcript artifacts suitable for citation.

## Metadata probe and rights gate

Inspecting a public page or running `download_media.py --mode probe` does not download captions, audio, or video and must not trigger a rights question. Run the probe without `--rights-basis`; it records `not_applicable_metadata_probe`.

Only when the next step will save remote captions, audio, or video, display this plain-language question and end the response while waiting:

```text
May I save captions or audio from this video locally for your personal study? Please confirm you have the necessary permission. If not or unsure, I’ll continue without downloading and use only the public page and other sources.
```

Do not display internal enum names. After a clear confirmation, record the most specific known basis, or `user_attested_authorized_use` when the learner confirms authorization without identifying a more specific category:

- `user_owned`
- `platform_permitted_download`
- `public_license`
- `explicit_permission`
- `user_attested_authorized_use`

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

First promote the selected raw subtitle from staging into the durable source bundle:

```text
python "<SKILL_ROOT>/scripts/promote_media_artifact.py" studies/my-study \
  --source-id SRC-001 \
  --input studies/my-study/.work/ingestion/JOB-001/media/source.en.vtt \
  --filename source.en.vtt --kind raw_caption
```

Normalize the promoted durable copy, not the disposable staging path:

```text
python "<SKILL_ROOT>/scripts/normalize_subtitles.py" \
  studies/my-study/records/source/media/SRC-001/source.en.vtt \
  --output-dir studies/my-study/records/source/media/SRC-001 \
  --source-id SRC-001 --item-id LESSON-003 \
  --origin human_caption --language en
```

Outputs:

- `transcript.json` with raw cues, normalized segments, cue IDs, and timestamps;
- `transcript.md` with readable timestamped segments.

### Download permitted remote material

Probe first without a rights declaration:

```text
python "<SKILL_ROOT>/scripts/download_media.py" "https://example.invalid/video" \
  --output-dir studies/my-study/.work/ingestion/JOB-001/probe \
  --source-id SRC-001 --mode probe
```

After learner authorization, pass the internal basis only to the acquisition command:

```text
python "<SKILL_ROOT>/scripts/download_media.py" "https://example.invalid/video" \
  --output-dir studies/my-study/.work/ingestion/JOB-001/media \
  --source-id SRC-001 \
  --rights-basis user_attested_authorized_use \
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

Keep probe output, completion manifests, observable events, and recovery guidance in that staging folder. Retry only after inspecting the recorded failure and correcting an observable cause; do not recursively rerun a failed downloader.

After acquisition succeeds:

1. Promote the selected raw caption, audio, or video with `promote_media_artifact.py` so the original no longer depends on disposable `.work/` state.
2. Normalize or transcribe from that durable copy into `records/source/media/<source-id>/transcript.json` and `transcript.md`.
3. Write locator-preserving extracted knowledge—not metadata alone—to `records/source/<source-id>.md`.
4. Register the source and every transcript artifact in one command. Use the learner-confirmed rights basis and real provider explicitly:

```text
python "<SKILL_ROOT>/scripts/register_source.py" studies/my-study \
  --source-id SRC-001 --title "SOURCE TITLE" \
  --location "ORIGINAL URL" --provider "YouTube" \
  --source-type youtube_video_auto_caption \
  --knowledge-path records/source/SRC-001.md \
  --author "AUTHOR" --rights-basis user_attested_authorized_use \
  --processing-mode local_only --language en \
  --artifact raw_caption=records/source/media/SRC-001/source.en.vtt \
  --artifact transcript_markdown=records/source/media/SRC-001/transcript.md \
  --artifact transcript_json=records/source/media/SRC-001/transcript.json
```

If the source was registered before its transcript artifacts existed, rerun the same command with `--update-existing`; never hand-edit the manifest. Then compile a fresh evidence plan. A `local-media` evidence plan refuses to compile until each registered source exposes a durable transcript artifact.

Merge the short action event only after completion. Never call the local application for ingestion, transcription, retry, or promotion.

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

- acquisition rights basis is recorded, or metadata-only work records `not_applicable_metadata_probe`;
- the original media or subtitle remains intact;
- each transcript segment has source and item IDs plus timestamps;
- provenance identifies human, platform, auto-caption, or local ASR;
- failed stages have recovery guidance;
- transcript artifacts are registered in the source manifest.
