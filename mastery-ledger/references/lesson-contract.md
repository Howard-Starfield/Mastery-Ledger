# Lesson contract

## Purpose

Create source-grounded chapters that teach like a short book. Do not publish extracted notes, transcript summaries, worker-report concatenations, or unsupported filler as lessons.

## Required frontmatter

Every lesson uses `lesson-v1` YAML frontmatter with:

- `chapter_id`, `title`, and `status`;
- 2-5 `objective_ids` and non-empty `concept_ids`;
- `prerequisite_chapter_ids`;
- positive `estimated_minutes` and an ISO `last_updated` date;
- non-empty `source_refs` for publication.

Each source reference is a canonical `source-ref-v1` object plus a unique `ref_id`. Bind factual prose to it with a Markdown footnote marker such as `[^REF-001]`, and render the same ID under `## Sources used`. Reject bare URLs, unresolved markers, unused structured references, and prose-only citations.

## Required teaching sequence

1. Open with a problem, scenario, or motivating question.
2. Bridge from prior knowledge and define missing prerequisites.
3. State 2-5 measurable objectives with observable verbs.
4. Give a concise big-picture mental model.
5. Explain definitions, mechanisms, relationships, and consequences in progressive prose.
6. Define vocabulary when first used.
7. Include at least two worked examples: one fully modeled and one transfer, comparison, or counterexample.
8. Include 2-4 ungraded retrieval checks.
9. Explain at least one plausible misconception.
10. State limitations, uncertainty, source disagreement, and uncovered gaps.
11. Show transfer or practical recognition in a new situation.
12. Close with key takeaways, the next dependency, and `## Sources used`.

## Course glossary

After the final lessons are stable, update `lessons/glossary.json` from their vocabulary. Define each technical term once, connect it to every chapter that uses it, and cite the approved evidence behind the definition. Keep definitions self-contained and short enough to scan beside a lesson. Use aliases for abbreviations, spelling variants, and alternate names rather than duplicating terms.

## Size and scope

- Standard core chapter: 1,200-1,800 words.
- Expanded core chapter: 1,800-2,500 words only within approved scope.
- Split material above 2,500 words into prerequisite-ordered chapters.
- Build 1-3 chapters by default and no more than 5 without renewed learner approval.

Word count is a guardrail, not proof. A chapter also needs aligned objectives, coherent narrative, two worked examples, retrieval, misconceptions, limitations, and verified locators. Report an evidence gap instead of padding a chapter.

## Ownership

The main agent writes and normalizes final lesson prose from approved evidence. Workers submit bounded evidence or reviews under `.work/`; they do not write canonical chapters. Require an independent pedagogy reviewer for high-stakes domains, more than three chapters, substantial notation, or deterministic lesson warnings. Independent assessment validation remains mandatory for every ready exam.
