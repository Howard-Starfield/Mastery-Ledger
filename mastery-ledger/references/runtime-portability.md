# Runtime portability

## Do not assume

- a fixed skills directory;
- automatic skill activation;
- live discovery after writing a new skill;
- slash-command support;
- subagents or parallel execution;
- shared worker filesystem;
- web, PDF, video, or shell tools;
- Python or external binaries;
- cloud or local model execution;
- the MCP server can use the host model.

## Skill discovery

The portable package uses standard `name` and `description` frontmatter. Runtime-specific installation and UI metadata should live outside portable workflow instructions. Codex-specific UI metadata is in `agents/openai.yaml`.

After installing or changing a skill, some clients require a new session or restart. Never claim live refresh unless tested in that runtime.

## Paths

Resolve the current skill root and workspace from runtime context. When no configured study location exists, use a project-local `studies/` directory. Do not hardcode `.claude/skills`, `.codex/skills`, or another client path in workflow logic.

## Subagent fallback

When subagents exist:

- use bounded workers for independent read-heavy tasks;
- keep the main agent accountable;
- use independent verification where justified.

When absent:

- use fresh bounded main-agent passes only for provisional live assistance;
- record `DRAFT_UNVERIFIED` for `topic-research` and `hybrid`;
- do not publish researched evidence, activate mastery, or mark an exam ready;
- avoid claiming evaluator independence.

A single user-provided source may still use the file-only workflow without subagents when no external research or publishable independent verification is requested.

## Application boundary and optional connectors

The skill owns source processing, research, evidence, course files, and exam generation. It may inspect the optional Mastery Ledger application's `doctor-v2` contract to reuse a registered workspace or launch ready-exam playback. A missing application never reduces course building to a provisional fallback.

The application owns only exam delivery, attempts, learner progress, review schedules, and its local workspace registration. The skill must not open or mutate the application database. The application must not ingest sources or edit generated course and exam artifacts.

When no registered workspace is available, ask the learner for an absolute workspace path and validate it before the first write. Do not claim that the path is registered with the application. Read the optional LinkVault connector contract only when the learner explicitly asks to use it.

## Optional dependencies

- Python 3.11+ for bundled utilities;
- `yt-dlp` for permitted remote media acquisition;
- `faster-whisper` for optional local ASR;
- media codecs supported by the ASR stack.

Scripts must fail with actionable errors when dependencies are missing.
