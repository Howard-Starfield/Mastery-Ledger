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

- execute task contracts sequentially;
- use fresh bounded passes where possible;
- record `self-review-fallback`;
- avoid claiming evaluator independence.

## MCP and LinkVault

The skill may call an installed LinkVault MCP or local service when exposed by the runtime. Tool names and schemas must be discovered rather than invented. If no service exists, use workspace files and bundled scripts for the supported subset.

The durable application service should own operational state. The skill should not open or mutate an application database directly unless that database contract explicitly allows it.

## Optional dependencies

- Python 3.10+ for bundled utilities;
- `yt-dlp` for permitted remote media acquisition;
- `faster-whisper` for optional local ASR;
- media codecs supported by the ASR stack.

Scripts must fail with actionable errors when dependencies are missing.
