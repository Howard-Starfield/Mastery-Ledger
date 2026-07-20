# Demo: Study Ledger to Mastery Ledger

This conceptual demo shows how Mastery Ledger can turn an academic-resource design presentation into a small, source-grounded course. It is a product demonstration, not a claim that the current prototype has executed the complete future pipeline.

## Input

- **Source:** [Introducing Study Ledger: A Comprehensive Academic Resource Management System](https://prezi.com/p/0xgcfk1r4fea/introducing-study-ledger-a-comprehensive-academic-resource-management-system/)
- **Creator:** Ritika Tiwari
- **Public creation date:** November 23, 2025
- **Registered source:** [SRC-001.md](source/SRC-001.md)

The presentation identifies a familiar student problem: digital course files accumulate faster than learners can organize and retrieve them. Its proposed response combines course-based organization, uploads, previews, search, offline behavior, privacy, and useful error feedback.

## Mastery Ledger transformation

```text
Public presentation
  -> source receipt and original URL
  -> paraphrased concept extraction
  -> evidence and scope review
  -> linked knowledge page
  -> focused exam questions
  -> attempt history
  -> long-term review schedule
```

### Knowledge Wiki preview

The generated wiki would organize the source into five connected concepts:

1. **Resource fragmentation** — unmanaged files create retrieval friction and duplication.
2. **Course-aware organization** — stable course and subject groupings reduce navigation cost.
3. **Preview and retrieval** — previews and search reduce unnecessary file opening and folder traversal.
4. **Local-first operation** — local storage can improve offline availability and limit unnecessary data transfer.
5. **Reliable intake** — format validation and actionable errors make uploads recoverable.

These are source-derived concepts, not copied presentation prose. Mastery Ledger would distinguish direct source statements from product inferences and future recommendations.

## Exam Ledger preview

### Question 1

Which capability most directly reduces the time a learner spends opening unrelated files while looking for one course document?

- A. Automatic transcription
- B. Subject filtering and keyword search
- C. Spaced-repetition scheduling
- D. Contradiction adjudication

<details>
<summary>Answer and explanation</summary>

**Correct answer: B.** Subject filtering narrows the collection before retrieval, while keyword search locates matching material without manually opening unrelated folders or documents.

<details>
<summary>Source used in this question</summary>

[SRC-001 — Study Ledger presentation](source/SRC-001.md), concepts: subject browsing and search.

</details>
</details>

### Question 2

What is the strongest privacy property of a browser-local academic organizer described by the source?

- A. Every document is automatically fact-checked.
- B. All files are shared with course members.
- C. Study files can remain on the learner's device.
- D. Search results are stored by a remote service.

<details>
<summary>Answer and explanation</summary>

**Correct answer: C.** Keeping the organizer and its stored files local avoids transferring those files to an application server for ordinary organization and retrieval.

<details>
<summary>Source used in this question</summary>

[SRC-001 — Study Ledger presentation](source/SRC-001.md), concepts: offline support and device-local files.

</details>
</details>

## Ownership curve preview

After a successful attempt, the questions enter the same review history rather than being regenerated and forgotten:

```text
1d -> 3d -> 7d -> 14d -> 28d -> 56d -> 112d -> 224d -> 448d -> 896d -> 1792d -> 3584d
```

Every attempt records the question version, selected answer, correctness, response time, explanation state, source reference, and next due date.

## What this demo adds beyond the source

The source focuses on managing academic files. Mastery Ledger extends that foundation with provenance, extracted knowledge, contradiction and citation review, assessment generation, learner attempts, and long-term mastery scheduling. Those extensions are Mastery Ledger design goals and must not be attributed to the presentation.
