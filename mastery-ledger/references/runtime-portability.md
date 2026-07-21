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

## Worker detection and fallback

Worker availability is runtime state, not course state. Inspect the current runtime's direct tool inventory and any available deferred tool catalog for a callable worker or subagent facility. Do not infer availability from a run-plan field, template, application command, or prior session. A run plan declares `execution_requirements`; accepted worker completions prove that those requirements were met.

When subagents exist:

- use bounded workers for independent read-heavy tasks;
- keep the main agent accountable;
- use independent verification where justified.

When absent:

- use fresh bounded main-agent passes only for provisional live assistance;
- set publication status to `DRAFT_UNVERIFIED` for `topic-research` and `hybrid` without replacing the primary workflow state;
- do not publish researched evidence, activate mastery, or mark an exam ready;
- avoid claiming evaluator independence.

A single user-provided source may still use the file-only workflow without subagents when no external research or publishable independent verification is requested.

## Application boundary and optional connectors

The skill owns source processing, research, evidence, course files, and exam generation. It never invokes, inspects, installs, launches, or configures the Mastery Ledger application. Course building therefore has no application availability gate.

The application owns exam delivery, attempts, learner progress, review schedules, and its local workspace registration. The skill must not open or mutate the application database. When the learner explicitly points to portable attempt or progress JSON written inside a course, the skill may validate and read that file as learner evidence; it must not discover the path through application state or rewrite completed attempts.

When no course or workspace is supplied, ask the learner for an absolute parent directory and validate it before the first write. Read the optional LinkVault connector contract only when the learner explicitly asks to use it.

## Optional dependencies

- Python 3.11+ for bundled utilities;
- `yt-dlp` for permitted remote media acquisition;
- `faster-whisper` for optional local ASR;
- media codecs supported by the ASR stack.

Scripts must fail with actionable errors when dependencies are missing.
