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

## Application runtime and optional connectors

The skill may call an installed Mastery Ledger runtime when exposed. Tool names and schemas must be discovered rather than invented. If no runtime exists, use workspace files and bundled scripts for the supported subset. Read the optional LinkVault connector contract only when the learner asks to use it.

The durable application service should own operational state. The skill should not open or mutate an application database directly unless that database contract explicitly allows it.

Application onboarding is also runtime-owned. The skill may detect onboarding state, launch the documented onboarding entry point, and pass proposed context. The application must validate and confirm workspace paths, privacy choices, model downloads, and registry changes. A script-only fallback may ask for a provisional output folder for the current run, but it must not claim to have configured the application.

## Optional dependencies

- Python 3.11+ for bundled utilities;
- `yt-dlp` for permitted remote media acquisition;
- `faster-whisper` for optional local ASR;
- media codecs supported by the ASR stack.

Scripts must fail with actionable errors when dependencies are missing.
