# ChatGPT upload test card

## Build under test

- Date:
- Tester:
- ChatGPT plan:
- Surface: web / desktop / mobile
- Workspace Agent or ordinary chat:
- Model:
- Uploaded file: `dist/mastery-ledger-chatgpt-upload/SKILL.md`
- SKILL.md SHA-256:
- Upload scan: passed / needs review / blocked
- Administrator restrictions:

## Capability observations

Record only behavior observed in the test conversation.

| Capability | Available | Evidence |
| --- | --- | --- |
| Reads uploaded `SKILL.md` |  |  |
| Works without companion references |  |  |
| Works without companion assets |  |  |
| Works without bundled scripts |  |  |
| Creates downloadable files |  |  |
| Has persistent agent memory |  |  |
| Has public web search |  |  |
| Can deliberately start or consume Deep research |  |  |
| Has configured external apps or tools |  |  |

Do not add a worker-spawn row unless the surface exposes a documented callable facility. The base skill must work without it.

## Required prompts

Run these in fresh conversations when possible:

1. `Use Mastery Ledger to teach me causal inference.`
2. `Build a course from https://www.youtube.com/watch?v=VIDEO_ID.`
3. `Use Mastery Ledger to build a Fast Course from the transcript I uploaded. Use only that transcript.`
4. `Now fact-check your result and mark it verified.`
5. `Save this course so I can continue in a new conversation.`
6. `Export the completed draft for the Mastery Ledger app.`

For prompt 3, upload a short, rights-cleared transcript with stable paragraph or timestamp locators.

## Artifact checks

| Check | Pass | Notes |
| --- | --- | --- |
| Topic-only first turn asks one prior-knowledge question and stops |  |  |
| YouTube-only path does not claim transcript access |  |  |
| Supplied transcript activates Fast Course |  |  |
| Uploaded `SKILL.md` works without any companion file |  |  |
| No downloader, local transcription, or delegated-agent attempt occurs |  |  |
| Claim ledger uses canonical source references |  |  |
| Rechecks use frozen artifacts |  |  |
| Rechecks remain labeled same-agent |  |  |
| Publication remains `DRAFT_UNVERIFIED` |  |  |
| Temporary storage produces a downloadable handoff or reports inability |  |  |
| Export is one ZIP containing one top-level course folder |  |  |
| ZIP contains every `mastery-ledger-course-bundle-v1` required path |  |  |
| Application importer accepts the ZIP as `DRAFT_UNVERIFIED` |  |  |
| Imported lessons appear with a Draft preview notice |  |  |

## Final verdict

- Verdict: pass / conditional / fail
- Blocking defects:
- Scan warnings:
- Files actually loaded:
- Files created:
- Data-retention or privacy observations:
- Recommended skill changes:
