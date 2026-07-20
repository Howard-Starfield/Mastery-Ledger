#!/usr/bin/env python3
"""Validate the structural integrity of a Mastery Ledger course workspace."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from validate_evidence import load_source_ids, validate_source_ref

REQUIRED_FILES = [
    "study.yaml",
    "source-manifest.yaml",
    "study-guide.md",
    "concept-map.md",
    "glossary.md",
    "wiki/wiki.json",
    "questions/question-bank.json",
    "progress/learner-progress.json",
]
QUESTION_TYPES = {"free-recall", "multiple-choice", "application", "calculation", "explain", "compare", "synthesis"}
RELATION_TYPES = {"prerequisite_of", "supports", "deep_dive_of", "adjacent_to", "example_of", "related_to"}


def normalized(value: str) -> str:
    return re.sub(r"\W+", " ", value.casefold()).strip()


def validate_question_bank(
    payload: dict[str, Any],
    *,
    source_ids: set[str],
    concept_ids: set[str],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if payload.get("source_ref_schema") != "source-ref-v1":
        errors.append("question-bank.json source_ref_schema must be source-ref-v1")
    questions = payload.get("questions")
    if not isinstance(questions, list):
        return ["question-bank.json must contain a questions list"], warnings

    seen_ids: set[str] = set()
    signatures: set[tuple[str, tuple[str, ...]]] = set()
    concepts_with_application: set[str] = set()

    for index, question in enumerate(questions):
        prefix = f"questions[{index}]"
        if not isinstance(question, dict):
            errors.append(f"{prefix} must be an object")
            continue
        question_id = str(question.get("question_id", "")).strip()
        if not question_id:
            errors.append(f"{prefix}.question_id is required")
        elif question_id in seen_ids:
            errors.append(f"Duplicate question_id: {question_id}")
        else:
            seen_ids.add(question_id)

        qtype = question.get("type")
        if qtype not in QUESTION_TYPES:
            errors.append(f"{prefix}.type must be one of {sorted(QUESTION_TYPES)}")
        difficulty = question.get("difficulty")
        if not isinstance(difficulty, int) or not 1 <= difficulty <= 5:
            errors.append(f"{prefix}.difficulty must be an integer from 1 to 5")

        prompt = str(question.get("prompt", "")).strip()
        answer = str(question.get("correct_answer", "")).strip()
        if not prompt:
            errors.append(f"{prefix}.prompt is required")
        if not answer:
            errors.append(f"{prefix}.correct_answer is required")
        if answer and len(normalized(answer)) >= 8 and normalized(answer) in normalized(prompt):
            errors.append(f"{prefix} appears to leak the correct answer in the prompt")

        q_concepts = question.get("concept_ids")
        if not isinstance(q_concepts, list) or not q_concepts:
            errors.append(f"{prefix}.concept_ids must be a non-empty list")
            q_concepts = []
        for concept_id in q_concepts:
            if concept_ids and concept_id not in concept_ids:
                errors.append(f"{prefix} references unknown concept_id: {concept_id}")
            if qtype in {"application", "calculation", "synthesis"}:
                concepts_with_application.add(str(concept_id))

        objectives = question.get("objective_ids")
        if not isinstance(objectives, list) or not objectives:
            errors.append(f"{prefix}.objective_ids must be a non-empty list")

        refs = question.get("source_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{prefix}.source_refs must be a non-empty list")
            refs = []
        for ref_index, ref in enumerate(refs):
            errors.extend(validate_source_ref(ref, source_ids, f"{prefix}.source_refs[{ref_index}]"))

        if qtype == "multiple-choice":
            distractors = question.get("distractors")
            if not isinstance(distractors, list) or len(distractors) < 2:
                errors.append(f"{prefix}.distractors must contain at least two items")
            elif len({normalized(str(item)) for item in distractors}) != len(distractors):
                errors.append(f"{prefix}.distractors contains duplicates")

        signature = (normalized(prompt), tuple(sorted(str(item) for item in q_concepts)))
        if signature in signatures:
            errors.append(f"Near-exact duplicate question prompt: {question_id or prefix}")
        signatures.add(signature)

    important_concepts = {
        str(item.get("concept_id"))
        for item in payload.get("important_concepts", [])
        if isinstance(item, dict) and item.get("concept_id")
    }
    for concept_id in sorted(important_concepts - concepts_with_application):
        warnings.append(f"Important concept lacks application or synthesis question: {concept_id}")
    return errors, warnings


def validate_wiki(
    root: Path, payload: dict[str, Any], *, source_ids: set[str], learner_concept_ids: set[str]
) -> tuple[list[str], list[str], set[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if payload.get("schema_version") != "wiki-v1":
        errors.append("wiki/wiki.json schema_version must be wiki-v1")
    concepts = payload.get("concepts")
    if not isinstance(concepts, list):
        return ["wiki/wiki.json must contain a concepts list"], warnings, set()
    concept_ids: set[str] = set()
    for index, concept in enumerate(concepts):
        prefix = f"wiki concepts[{index}]"
        if not isinstance(concept, dict) or not str(concept.get("concept_id", "")).strip():
            errors.append(f"{prefix}.concept_id is required")
            continue
        concept_id = str(concept["concept_id"])
        if concept_id in concept_ids:
            errors.append(f"Duplicate wiki concept_id: {concept_id}")
        concept_ids.add(concept_id)
        if not str(concept.get("title", "")).strip() or not str(concept.get("summary", "")).strip():
            errors.append(f"{prefix} requires title and summary")
        page_path = concept.get("page_path")
        if page_path:
            candidate = (root / str(page_path)).resolve(strict=False)
            try:
                candidate.relative_to(root.resolve(strict=False))
            except ValueError:
                errors.append(f"{prefix}.page_path escapes the course folder")
            else:
                if candidate.suffix.casefold() != ".md" or not candidate.is_file() or candidate.is_symlink():
                    errors.append(f"{prefix}.page_path must resolve to a regular Markdown file")
        refs = concept.get("source_refs", [])
        if not isinstance(refs, list):
            errors.append(f"{prefix}.source_refs must be a list")
        else:
            for ref_index, ref in enumerate(refs):
                errors.extend(validate_source_ref(ref, source_ids, f"{prefix}.source_refs[{ref_index}]"))
    for missing in sorted(learner_concept_ids - concept_ids):
        warnings.append(f"Learner concept has no wiki page: {missing}")
    relationships = payload.get("relationships", [])
    if not isinstance(relationships, list):
        errors.append("wiki/wiki.json relationships must be a list")
    else:
        for index, edge in enumerate(relationships):
            prefix = f"wiki relationships[{index}]"
            if not isinstance(edge, dict):
                errors.append(f"{prefix} must be an object")
                continue
            source = str(edge.get("from", ""))
            target = str(edge.get("to", ""))
            if source not in concept_ids or target not in concept_ids:
                errors.append(f"{prefix} must reference two known concept IDs")
            if edge.get("kind") not in RELATION_TYPES:
                errors.append(f"{prefix}.kind must be one of {sorted(RELATION_TYPES)}")
            if edge.get("status") not in {"approved", "provisional"}:
                errors.append(f"{prefix}.status must be approved or provisional")
    return errors, warnings, concept_ids


def validate_workspace(root: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            errors.append(f"Missing required file: {relative}")
    if errors:
        return errors, warnings

    source_ids = load_source_ids(root / "source-manifest.yaml")
    if not source_ids:
        warnings.append("No source IDs found in source-manifest.yaml")

    progress = json.loads((root / "progress" / "learner-progress.json").read_text(encoding="utf-8"))
    concepts = progress.get("concepts")
    if not isinstance(concepts, list):
        errors.append("progress/learner-progress.json must contain a concepts list")
        concept_ids: set[str] = set()
    else:
        concept_ids = set()
        for index, concept in enumerate(concepts):
            if not isinstance(concept, dict) or not concept.get("concept_id"):
                errors.append(f"learner-progress concepts[{index}] must have concept_id")
                continue
            concept_id = str(concept["concept_id"])
            if concept_id in concept_ids:
                errors.append(f"Duplicate learner concept_id: {concept_id}")
            concept_ids.add(concept_id)
            for field in ("proficiency_score", "confidence_score"):
                value = concept.get(field)
                if not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
                    errors.append(f"Concept {concept_id} has invalid {field}")

    wiki_payload = json.loads((root / "wiki" / "wiki.json").read_text(encoding="utf-8"))
    wiki_errors, wiki_warnings, wiki_concept_ids = validate_wiki(
        root,
        wiki_payload,
        source_ids=source_ids,
        learner_concept_ids=concept_ids,
    )
    errors.extend(wiki_errors)
    warnings.extend(wiki_warnings)

    question_payload = json.loads((root / "questions" / "question-bank.json").read_text(encoding="utf-8"))
    question_errors, question_warnings = validate_question_bank(
        question_payload,
        source_ids=source_ids,
        concept_ids=wiki_concept_ids or concept_ids,
    )
    errors.extend(question_errors)
    warnings.extend(question_warnings)

    for markdown_name in ("study-guide.md", "concept-map.md", "glossary.md"):
        text = (root / markdown_name).read_text(encoding="utf-8").strip()
        if len(text) < 20:
            warnings.append(f"{markdown_name} is nearly empty")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()
    if not args.workspace.is_dir():
        parser.error(f"Workspace does not exist: {args.workspace}")
    try:
        errors, warnings = validate_workspace(args.workspace)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(json.dumps({"status": "fail", "errors": [str(exc)], "warnings": []}, indent=2))
        return 1
    print(
        json.dumps(
            {"status": "pass" if not errors else "fail", "errors": errors, "warnings": warnings},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
