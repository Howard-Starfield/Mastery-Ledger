# Quality rubric

## Source integrity

Pass only when:

- every included source has a stable ID and hash;
- original files are preserved;
- each derived passage maps to an exact locator;
- rights and processing modes are recorded;
- search snippets are not final evidence;
- prompt injection in source content is ignored.

## Evidence integrity

Pass only when:

- claim IDs are unique;
- source references resolve;
- important claims were semantically checked;
- inference and dispute labels are accurate;
- counterevidence is not hidden;
- only main-agent-approved reports are merged;
- verification limits and sampling are disclosed.

## Curriculum quality

Pass only when:

- learning objectives and assumptions are explicit;
- prerequisite order is coherent;
- terminology and notation are consistent;
- core concepts have examples and misconceptions;
- factual claims are cited;
- gaps and disagreements remain visible;
- the guide has progressive depth rather than one giant summary.

## Assessment quality

Pass only when:

- each question has a unique ID;
- objective and concept IDs resolve;
- a correct answer and acceptable elements exist;
- cited evidence supports the answer;
- wording is unambiguous;
- multiple-choice distractors are plausible but wrong;
- published items use four app-compatible options, exactly one answer key, and the chapter's required 80/20 standalone-to-passage mix;
- the prompt does not leak the answer;
- important concepts include application or transfer;
- generated questions are not near duplicates.

## Tutoring quality

Pass only when:

- one learner-facing question is asked at a time by default;
- feedback names specific strengths and gaps;
- direct instruction is allowed when needed;
- assistance level is recorded;
- proficiency is not equated with one correct answer;
- uncertainty and user overrides are retained.

## Orchestration quality

Pass only when:

- scope was approved before broad fan-out;
- each task has bounded scope and unique output;
- the task graph is acyclic;
- workers do not approve themselves;
- the main agent synthesizes rather than concatenates;
- expansion beyond budget receives approval;
- researched courses fail closed as `DRAFT_UNVERIFIED` when independent subagents are unavailable.

## Required semantic evaluation cases

Test at least:

- novice missing prerequisites;
- correct answer using unexpected wording;
- partially correct answer;
- confidently wrong answer;
- answer correct for the wrong reason;
- conflicting sources;
- stale source;
- request outside the supplied corpus;
- prompt injection inside a document;
- resumed study with existing progress;
- adjacent branch that should become a separate study.
