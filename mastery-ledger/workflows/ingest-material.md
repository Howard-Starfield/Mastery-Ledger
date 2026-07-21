# Ingest material

## Purpose

Turn supplied files, an existing course folder, or an authorized local corpus into a traceable source bundle without flattening its original structure.

## Supported modes

- `provided-material-only`: use only the supplied corpus.
- `existing-library`: import an existing course or lesson tree.
- `local-media`: authorized local video, audio, subtitles, or transcript.
- `hybrid`: supplied corpus remains primary; research fills explicit gaps.

## Source manifest first

Initialization deliberately creates `records/source-manifest.yaml` with `sources: []`. A sample source is never a ready source. Extract each source into a non-empty `records/source/SRC-NNN.md`, then register it atomically with:

```bash
python scripts/register_source.py COURSE_ROOT --source-id SRC-NNN --title "TITLE" --source-type "TYPE" --knowledge-path records/source/SRC-NNN.md --location "URL_OR_PATH"
```

Do not hand-edit a source to `status: ready`; `register_source.py` computes the content hash, validates the entire manifest, and records the observable registration event. Assign stable source and item IDs. Record:

- title, author, publisher, source type, and dates;
- original location and local path;
- content hash;
- rights basis and permitted uses;
- processing mode;
- language;
- primary or secondary classification;
- included and excluded sections;
- processing status;
- version and supersession links.

`assets/source-manifest.yaml` is intentionally empty. Use `assets/source-record.example.yaml` only to understand the generated record fields; `register_source.py` remains the sole writer for ready records.

## Preserve four structures

Do not collapse these into one graph:

1. **Source hierarchy:** course → module → lesson → media/artifact.
2. **Concept graph:** concepts and semantic relationships.
3. **Study-plan graph:** selected modules and learning order.
4. **Proficiency ledger:** learner evidence over time.

## Existing course folder

Inspect the real folder rather than assuming a fixed layout. Identify:

- manifest or metadata files;
- course, module, and lesson order;
- videos and audio;
- subtitle and transcript files;
- exercises, readings, and attachments;
- missing or partial artifacts;
- source hashes and download state.

Create a normalized SourceBundle that points to originals. Do not move or rewrite originals unless the user authorizes it.

## Documents and notes

For each long document, create section-level locators:

- page and heading path;
- paragraph or block ID;
- slide number;
- table or figure number.

Store short source notes separately from the original file. Do not replace a source with an LLM summary.

## Gaps and conflicts

Record:

- unreadable or unsupported files;
- missing pages or lessons;
- duplicated material;
- stale or contradictory versions;
- corpus questions that cannot be answered in material-only mode.

## Exit gate

The phase is complete only when:

- every included source has a stable ID and hash;
- originals are preserved;
- all derived text maps back to locators;
- rights and processing modes are explicit;
- source hierarchy is represented;
- missing or failed artifacts are recorded;
- the corpus is ready for mapping or topic research.

After at least one source registers successfully, rerun `reconcile_workflow.py COURSE_ROOT --json`. In anchor-only mode, reconciliation may pass through the no-op `CORPUS_MAPPED` state before requesting the provided-evidence plan. In hybrid mode, the registered anchor is followed by authorized corroborating source discovery and registration. Compile only the plan named by reconciliation; never edit the state backward by hand.
