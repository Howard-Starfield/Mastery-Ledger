# Agent roles

`agent-role-profiles.json` is the canonical machine-readable registry. The context compiler freezes one versioned profile and the completion validator requires the worker to acknowledge its exact hash. This page defines only the active topology and ownership rules.

## Main orchestrator and scheduler

The main agent owns the learner conversation, mode selection, source retention, scope, task compilation, capacity queue, agent lifecycle, evidence approval, course organization, lesson and question authorship, promotion, and tutoring.

It is also the completion receptionist through `route_worker_completion.py` and `manage_worker_runtime.py`. Do not spawn a receptionist or nested orchestrator. The main agent may reject a verifier pass when observable evidence remains weak or pedagogically misleading.

## Source scout

Runs once for a topic-only Verified Course. It searches within the approved topic and source limit, opens candidate pages, and returns `source-candidate-ledger-v1` with authority rationale, coverage, limitations, and gaps. It does not register or approve sources, treat snippets as evidence, or write learner material.

## Source extractor

Converts exactly one assigned registered source into faithful, locator-preserving evidence. It preserves hierarchy, separates the source author's claims from interpretation, and reports omissions or internal inconsistency. It does not inspect another source, synthesize across sources, or approve evidence.

Multiple extractor tasks are capacity-queued. At most three child agents run normally; extra tasks remain ready but undispatched.

## Contradiction reviewer

Runs only in a topic-only Verified Course after every source extractor has been accepted and closed. It compares definitions, dates, populations, assumptions, scope, supersession, and unresolved gaps. It rejects or retains candidate claims before citation verification and never verifies its own locators.

## Citation verifier

Independently reopens assigned sources and checks claim support, locator accuracy, quote accuracy, source status, counterevidence, and inference labels.

For a Fast Course, it also compares material conflicts across supplied-source packets because that graph has no separate contradiction reviewer. For a Verified Course, it receives only the contradiction-retained claim set. It does not approve final publication or rewrite reports.

## Assessment validator

Runs after the main agent has authored substantive lessons and the canonical question bank from approved evidence. It independently attempts every item and checks answerability, ambiguity, evidence support, answer isolation, plausible distractors, application compatibility, and the exact per-chapter mix. It rejects multiple-valid-answer cases and never silently rewrites questions.

## Legacy profiles

The registry retains `corpus-mapper`, `research-worker`, and `assessment-generator` profiles only so unfinished older runs can still be read or repaired. New plans must not create these roles.

## Lifecycle and independence

- Read [worker runtime contract](worker-runtime-contract.md) before any spawn.
- Reserve, spawn, and attach one worker at a time; never use a parallel multi-spawn wrapper.
- Give workers compiled bounded inputs, not the full skill or learner conversation.
- Initial source extractors do not see one another's conclusions.
- Reviewers receive source artifacts, accepted dependency packets, and rubrics, not an expected verdict.
- Route each return immediately. Reuse the same live worker for completion repair.
- Close every accepted, exhausted, stalled, or cancelled agent and confirm closure before refilling capacity.
- A stalled reviewer gets one fresh agent on the same frozen inputs; upstream work is not regenerated.
- Evaluators recommend decisions; only the main agent approves evidence and promotes canonical artifacts.
- A capacity limit is queued work, not worker unavailability and not grounds for `DRAFT_UNVERIFIED`.
