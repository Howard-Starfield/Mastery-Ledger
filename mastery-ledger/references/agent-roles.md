# Agent roles

`agent-role-profiles.json` is the canonical machine-readable role registry. Do not describe a worker role from memory. The context compiler selects one profile, hashes it, attaches its mission, best practices, stop conditions, prohibited actions, and required contracts, and the completion validator requires the worker to acknowledge that exact version. This document explains the topology; it does not replace compiled role context.

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

## Source extractor

Converts one assigned source or bounded source subset into faithful, locator-preserving evidence. It preserves hierarchy, separates the source author's claims from interpretation, and reports omissions or internal inconsistency. It does not synthesize across unassigned sources or approve evidence.

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

## Contradiction reviewer

Runs after all bounded extraction and research tasks for the current run have submitted. It compares their claims, source dates, definitions, assumptions, and scope; records conflicts, supersession, and unresolved gaps; and may reject material before citation verification spends tokens reopening locators. It never verifies its own source citations and never edits final learner-facing artifacts.

## Completion router

Acts as the receptionist between workers and the main orchestrator. It reads task briefs and `completion-envelope-v1` records, confirms that declared output paths exist, sorts submissions into ready, blocked, failed, or malformed queues, and reports those queues to the main agent. It does not inspect hidden reasoning, change report content, approve evidence, or dispatch a downstream task that the orchestration validator has not marked ready.

## Module drafter

Optionally drafts one module from a frozen outline and approved evidence. It may not introduce new unsupported claims. Its output remains a draft until main-agent synthesis.

## Assessment generator

Runs only after final citation verification. It creates questions from approved concepts and evidence, follows `assessment-contract.md`, and maps every item to a chapter, format, concept IDs, objectives, four options, one answer key, misconception-based distractor rationales, an explanation, and source locators. It writes only to its assigned `.work/` path.

## Assessment validator

Runs only after assessment generation. It checks whether each question is answerable, unambiguous, appropriately difficult, free from answer leakage, supported by cited evidence, app-compatible, and compliant with the exact per-chapter 80/20 mix. It rejects multiple-valid-answer cases and must not be the assessment generator.

## Pedagogy reviewer

Reviews prerequisite order, cognitive load, examples, misconceptions, practice variety, and whether direct explanation or Socratic questioning is appropriate.

## Red-team evaluator

Attempts to find unsupported claims, misleading simplifications, stale facts, source-policy violations, ambiguous questions, and workflow bypasses.

## Independence rules

- Initial research workers should not see one another’s conclusions unless a dependency requires it.
- Verifiers receive the source, report, and rubric—not the expected verdict.
- Evaluators submit recommendations; they do not silently edit approved artifacts.
- Research and extraction workers submit independently. The contradiction reviewer runs only after their completion envelopes are accepted, and citation verification runs last, after contradiction review has rejected or retained candidate claims.
- When no subagents are available, the main agent may preserve separated provisional passes for the live conversation, but a researched course remains `DRAFT_UNVERIFIED` and cannot become a ready exam or active mastery course.
- Do not force a reviewer to invent a defect or contradiction. A clean result must still name the most fragile assumption or remaining evidence gap.
- Do not give workers the full skill or learner conversation. Give only the compiled role profile, approved scope, required contracts, bounded inputs, declared outputs, and accepted dependency artifacts.
