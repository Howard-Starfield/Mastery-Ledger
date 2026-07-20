#!/usr/bin/env python3
"""Render the canonical JSON question bank into a durable Markdown review copy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def render(payload: dict) -> str:
    lines = ["# Question bank", "", "> Generated from `question-bank.json`; edit the JSON source, then regenerate.", ""]
    chapters = {str(item.get("chapter_id")): str(item.get("title") or item.get("chapter_id")) for item in payload.get("chapters", []) if isinstance(item, dict)}
    current = None
    for question in payload.get("questions", []):
        if not isinstance(question, dict):
            continue
        chapter_id = str(question.get("chapter_id", "Unassigned"))
        if chapter_id != current:
            lines.extend([f"## {chapters.get(chapter_id, chapter_id)}", ""])
            current = chapter_id
        lines.extend([
            f"### {question.get('question_id', 'Question')} - {question.get('format', question.get('type', 'unknown'))}",
            "",
            str(question.get("prompt", "")),
            "",
        ])
        for option in question.get("options", []):
            if isinstance(option, dict):
                marker = " (correct)" if option.get("option_id") == question.get("correct_option_id") else ""
                lines.append(f"- **{option.get('option_id')}** {option.get('text')}{marker}")
        lines.extend(["", f"**Explanation:** {question.get('correct_explanation', question.get('explanation', ''))}", "", "**Sources used in this question:**"])
        for ref in question.get("source_refs", []):
            if isinstance(ref, dict):
                locator = ref.get("locator", {})
                label = locator.get("label", "unlabeled locator") if isinstance(locator, dict) else "invalid locator"
                lines.append(f"- `{ref.get('source_id', 'missing')}` - {label}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question_bank", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.question_bank.read_text(encoding="utf-8"))
    output = args.output or args.question_bank.with_suffix(".md")
    output.write_text(render(payload), encoding="utf-8")
    print(json.dumps({"status": "complete", "output": str(output), "questions": len(payload.get("questions", []))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
