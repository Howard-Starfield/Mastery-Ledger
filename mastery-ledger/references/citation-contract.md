# Citation contract

Use `source-ref-v1` for every claim, question, explanation, and exam citation. Keep source identity and provenance in `source-manifest.yaml`; keep only the reference and precise locator in the consuming artifact. Never use a bare URL, source ID alone, or prose-only citation as the durable record.

## Canonical object

```json
{
  "source_id": "SRC-004",
  "item_id": "LESSON-003",
  "locator": {
    "kind": "timestamp_range",
    "start_ms": 143200,
    "end_ms": 151000,
    "label": "Lesson 3, 00:02:23.200–00:02:31.000"
  },
  "supports": ["correct_answer", "explanation"],
  "support_strength": "direct",
  "supporting_excerpt": "A short verification excerpt.",
  "href": "https://example.invalid/video?t=143"
}
```

Required fields:

- `source_id`: an existing ID from `source-manifest.yaml`;
- `locator`: one structured locator object with `kind`, kind-specific fields, and a human-readable `label`;
- `supports`: one or more of `claim`, `question_prompt`, `correct_answer`, `explanation`, `distractor`, `context`, or `counterevidence`;
- `support_strength`: `direct`, `partial`, or `contextual`.

Optional fields:

- `item_id`: required when the source contains lessons, chapters, episodes, or other addressable items;
- `supporting_excerpt`: short reviewer convenience text, not the durable citation;
- `href`: a validated convenience link; never treat it as the durable locator.

## Locator kinds

| Kind | Required locator fields | Example label |
|---|---|---|
| `page` | `page` | `p. 17` |
| `page_range` | `start`, `end` | `pp. 8–9` |
| `section` | `value` | `§ 4.2` |
| `paragraph` | `value` | `paragraph 3` |
| `heading` | `value` | `Limitations` |
| `heading_path` | non-empty `path` array | `API › Responses › Inputs` |
| `timestamp` | `start_ms` | `00:02:23.200` |
| `timestamp_range` | `start_ms`, `end_ms` | `00:02:23.200–00:02:31.000` |
| `slide` | `value` | `slide 12` |
| `figure` | `value` | `figure 4` |
| `table` | `value` | `table 2` |
| `line_range` | `start`, `end` | `lines 41–55` |
| `url_fragment` | `value` | `#rate-limits` |
| `whole_source` | no additional field | `entire source` |

Use the narrowest locator that lets a reviewer reopen the supporting passage. Use `whole_source` only when the entire work is genuinely the evidence and no narrower locator exists. Page values are one-based; millisecond and line values are non-negative; ranges must end after they start.

## Examples

PDF:

```json
{"source_id":"SRC-002","locator":{"kind":"page_range","start":8,"end":9,"label":"pp. 8–9"},"supports":["claim"],"support_strength":"direct"}
```

Webpage:

```json
{"source_id":"SRC-003","locator":{"kind":"heading_path","path":["API","Responses","Inputs"],"label":"API › Responses › Inputs"},"supports":["correct_answer","explanation"],"support_strength":"direct","href":"https://example.invalid/docs#inputs"}
```

Local Markdown:

```json
{"source_id":"SRC-005","locator":{"kind":"line_range","start":41,"end":55,"label":"lines 41–55"},"supports":["context"],"support_strength":"contextual"}
```

## Learner-facing rendering

Resolve source metadata from the manifest and render:

```text
[SRC-003] Responses API documentation — API › Responses › Inputs
Publisher · publication date · retrieved date
Open source
```

Keep `Sources used in this question: <count>` collapsed unless the learner explicitly opens it. Do not auto-expand it after any answer. Enable detailed citations after a correct answer and for every question in final review mode; keep them unavailable after an incorrect answer until final review.

## Enforcement

Reject a reference when its source ID is unknown, locator is a string instead of an object, required kind-specific fields are missing, a range is reversed, `supports` is empty, or `support_strength` is invalid. Validate structure first, then have a human or verifier check that the cited passage actually supports the claim.
