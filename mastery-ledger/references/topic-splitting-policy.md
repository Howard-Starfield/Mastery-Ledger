# Topic splitting policy

## Purpose

Decide whether a newly discovered branch remains in the current study or becomes a separately tracked study.

## Blast-radius classes

- `REQUIRED_NOW`: blocks the approved outcome.
- `HELPFUL_SOON`: improves understanding but does not block progress.
- `OPTIONAL_DEEP_DIVE`: adds depth within the same goal.
- `SEPARATE_STUDY_RECOMMENDED`: coherent independent outcome.
- `EXCLUDED_THIS_RUN`: intentionally outside scope.

## Split rule

Recommend a separate study when at least two are true:

1. The branch has a materially different learning outcome.
2. It introduces a mostly separate prerequisite graph.
3. It adds roughly 25–30% or more to the current planned scope.
4. It requires a substantially different corpus or vocabulary.
5. It needs independent assessments or review scheduling.
6. It changes the deadline or expected deliverable.
7. It can stand alone as one or more complete modules.
8. The user wants independent tracking.

Otherwise relate it as:

- `prerequisite_of`
- `supports`
- `deep_dive_of`
- `adjacent_to`
- `example_of`

## Expansion checkpoint

Pause and ask the user before expansion when any of these occurs:

- another worker beyond the approved budget is needed;
- more than five additional sources are proposed;
- the outcome changes materially;
- a branch moves from optional to required;
- a new study is recommended.

## Scope proposal format

```markdown
### Newly discovered branch: [name]

**Relationship to current study:**
**Why it appeared:**
**Estimated added modules:**
**Estimated added sources/workers:**
**Recommendation:** include now | defer | create separate study
**Trade-off:**
```

Do not create new studies automatically. Record the proposal and obtain approval.
