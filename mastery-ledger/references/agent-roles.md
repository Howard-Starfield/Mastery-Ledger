# Agent roles

## Main orchestrator

Accountable owner of the study. It interprets the learner, freezes scope, assigns tasks, approves evidence, resolves conflicts, synthesizes the curriculum, and conducts tutoring.

It may reject a verifier’s pass when the evidence is weak or the claim is pedagogically misleading.

## Corpus mapper

Broadly inspects an approved corpus and proposes:

- concept IDs and names;
- prerequisite candidates;
- source coverage;
- module boundaries;
- ambiguities and gaps;
- independent research tasks.

It does not approve claims or draft the final guide.

## Research worker

Investigates one bounded concept group or source subset. It returns a structured evidence packet with exact source locators, limitations, contradictions, and scope drift.

It must not:

- cite another worker report as an original source;
- silently broaden scope;
- write final learner-facing conclusions;
- approve its own report.

## Citation verifier

Independently opens cited sources and checks claim support, locator accuracy, quote accuracy, source status, counterevidence, and inference labels.

It returns a review decision and exact required changes. It does not rewrite the worker’s report or approve final merge.

## Module drafter

Optionally drafts one module from a frozen outline and approved evidence. It may not introduce new unsupported claims. Its output remains a draft until main-agent synthesis.

## Assessment generator

Creates questions from approved concepts and evidence. It must map questions to concept IDs, objectives, correct-answer elements, common errors, hints, and source locators.

## Assessment validator

Checks whether a question is answerable, unambiguous, appropriately difficult, free from answer leakage, and supported by cited evidence. It flags multiple-valid-answer cases.

## Pedagogy reviewer

Reviews prerequisite order, cognitive load, examples, misconceptions, practice variety, and whether direct explanation or Socratic questioning is appropriate.

## Red-team evaluator

Attempts to find unsupported claims, misleading simplifications, stale facts, source-policy violations, ambiguous questions, and workflow bypasses.

## Independence rules

- Initial research workers should not see one another’s conclusions unless a dependency requires it.
- Verifiers receive the source, report, and rubric—not the expected verdict.
- Evaluators submit recommendations; they do not silently edit approved artifacts.
- When no subagents are available, the main agent performs separated passes and labels the loss of independence.
