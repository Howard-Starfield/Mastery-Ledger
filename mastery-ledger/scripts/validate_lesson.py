#!/usr/bin/env python3
"""Validate one Mastery Ledger book-like lesson Markdown file."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

from validate_evidence import load_source_ids, validate_source_ref


REQUIRED_HEADINGS = (
    "Why this matters",
    "Connect to what you know",
    "What you will be able to do",
    "Big picture",
    "Core explanation",
    "Worked example 1",
    "Worked example 2",
    "Pause and retrieve",
    "Common misconceptions",
    "Limitations and uncertainty",
    "Transfer and practical use",
    "Key takeaways",
    "What comes next",
    "Sources used",
)
REF_ID = re.compile(r"^REF-[A-Za-z0-9._-]+$")
FOOTNOTE_MARKER = re.compile(r"\[\^(REF-[A-Za-z0-9._-]+)\]")


def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n", text, re.DOTALL)
    if not match:
        return {}, text
    try:
        payload = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}, text[match.end():]
    return (payload if isinstance(payload, dict) else {}), text[match.end():]


def _sections(body: str) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", body))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        result[match.group(1).strip()] = body[match.end():end].strip()
    return result


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text, re.UNICODE))


def _list_count(text: str) -> int:
    return len(re.findall(r"(?m)^\s*(?:[-*+] |\d+[.)] )\S", text))


def validate_lesson(
    path: Path,
    *,
    source_ids: set[str],
    publication: bool = False,
    expected_chapter_id: str | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return [f"Cannot read lesson: {error}"], warnings
    metadata, body = _frontmatter(text)
    prefix = path.name
    if metadata.get("schema_version") != "lesson-v1":
        errors.append(f"{prefix} must use lesson-v1 YAML frontmatter")
    chapter_id = str(metadata.get("chapter_id") or "").strip()
    if not chapter_id:
        errors.append(f"{prefix} frontmatter requires chapter_id")
    elif expected_chapter_id and chapter_id != expected_chapter_id:
        errors.append(f"{prefix} chapter_id must match {expected_chapter_id}")
    if not str(metadata.get("title") or "").strip():
        errors.append(f"{prefix} frontmatter requires title")
    objectives = metadata.get("objective_ids")
    if not isinstance(objectives, list) or not 2 <= len(objectives) <= 5 or any(not str(item).strip() for item in objectives):
        errors.append(f"{prefix} objective_ids must contain 2-5 non-empty IDs")
    concepts = metadata.get("concept_ids")
    if not isinstance(concepts, list) or not concepts or any(not str(item).strip() for item in concepts):
        errors.append(f"{prefix} concept_ids must be non-empty")
    prerequisites = metadata.get("prerequisite_chapter_ids")
    if not isinstance(prerequisites, list):
        errors.append(f"{prefix} prerequisite_chapter_ids must be a list")
    minutes = metadata.get("estimated_minutes")
    if not isinstance(minutes, int) or minutes <= 0:
        errors.append(f"{prefix} estimated_minutes must be a positive integer")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(metadata.get("last_updated") or "")):
        errors.append(f"{prefix} last_updated must be an ISO date")
    if publication and metadata.get("status") != "validated":
        errors.append(f"{prefix} status must be validated for publication")

    refs = metadata.get("source_refs")
    refs = refs if isinstance(refs, list) else []
    if publication and not refs:
        errors.append(f"{prefix} source_refs must be non-empty for publication")
    ref_ids: set[str] = set()
    for index, ref in enumerate(refs):
        if not isinstance(ref, dict):
            errors.append(f"{prefix} source_refs[{index}] must be an object")
            continue
        ref_id = str(ref.get("ref_id") or "").strip()
        if not REF_ID.fullmatch(ref_id):
            errors.append(f"{prefix} source_refs[{index}].ref_id must match REF-...")
        elif ref_id in ref_ids:
            errors.append(f"{prefix} has duplicate source ref ID: {ref_id}")
        ref_ids.add(ref_id)
        canonical = {key: value for key, value in ref.items() if key != "ref_id"}
        errors.extend(validate_source_ref(canonical, source_ids, f"{prefix} source_refs[{index}]"))

    prose_without_definitions = "\n".join(
        line for line in body.splitlines() if not re.match(r"^\[\^REF-[A-Za-z0-9._-]+\]:", line.strip())
    )
    used = set(FOOTNOTE_MARKER.findall(prose_without_definitions))
    definitions = set(re.findall(r"(?m)^\[\^(REF-[A-Za-z0-9._-]+)\]:", body))
    for missing in sorted(used - ref_ids):
        errors.append(f"{prefix} inline marker has no structured source ref: {missing}")
    for unused in sorted(ref_ids - used):
        errors.append(f"{prefix} structured source ref is unused in prose: {unused}")
    for missing in sorted(used - definitions):
        errors.append(f"{prefix} inline marker has no learner-readable footnote: {missing}")
    for orphan in sorted(definitions - ref_ids):
        errors.append(f"{prefix} footnote has no structured source ref: {orphan}")

    sections = _sections(body)
    for heading in REQUIRED_HEADINGS:
        if heading not in sections:
            errors.append(f"{prefix} is missing required heading: {heading}")
    if "What you will be able to do" in sections:
        count = _list_count(sections["What you will be able to do"])
        if not 2 <= count <= 5:
            errors.append(f"{prefix} must present 2-5 learner-facing objectives")
    if "Pause and retrieve" in sections:
        count = _list_count(sections["Pause and retrieve"])
        if not 2 <= count <= 4:
            errors.append(f"{prefix} must contain 2-4 retrieval checks")
    for heading in ("Worked example 1", "Worked example 2"):
        if heading in sections and _word_count(sections[heading]) < 80:
            errors.append(f"{prefix} {heading} must contain at least 80 words")
    for heading in ("Common misconceptions", "Limitations and uncertainty"):
        if heading in sections and _word_count(sections[heading]) < 40:
            errors.append(f"{prefix} {heading} must contain at least 40 words")
    if publication:
        for heading in ("Core explanation", "Worked example 1", "Worked example 2"):
            if heading in sections and not FOOTNOTE_MARKER.search(sections[heading]):
                errors.append(f"{prefix} {heading} must contain a structured citation marker")

    words = _word_count(body)
    if words < 1200:
        message = f"{prefix} has {words} words; standard publication requires at least 1200"
        (errors if publication else warnings).append(message)
    if words > 2500:
        errors.append(f"{prefix} has {words} words; split content above 2500 words")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lesson", type=Path)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--publication", action="store_true")
    parser.add_argument("--chapter-id")
    args = parser.parse_args()
    errors, warnings = validate_lesson(
        args.lesson,
        source_ids=load_source_ids(args.source_manifest),
        publication=args.publication,
        expected_chapter_id=args.chapter_id,
    )
    print(json.dumps({"status": "pass" if not errors else "fail", "errors": errors, "warnings": warnings}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

