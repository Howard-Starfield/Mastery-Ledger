#!/usr/bin/env python3
"""Validate the structural integrity of a Mastery Ledger course workspace."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

from course_paths import (
    APPROVED_CLAIMS,
    EVENT_LOG,
    INDEX,
    PROGRESS,
    QUESTION_BANK,
    QUESTION_BANK_REVIEW,
    SOURCE,
    SOURCE_MANIFEST,
    relative_text,
)
from source_registry import sha256_file
from validate_evidence import load_source_ids, validate_source_ref
from validate_lesson import validate_lesson
from validation_receipts import load_validation_receipts

REQUIRED_FILES = [
    "study.yaml",
    relative_text(INDEX),
    relative_text(SOURCE_MANIFEST),
    relative_text(QUESTION_BANK),
    relative_text(PROGRESS / "learner-progress.json"),
]
QUESTION_TYPES = {"free-recall", "multiple-choice", "application", "calculation", "explain", "compare", "synthesis"}
QUESTION_TIERS = {
    "standard": (10, 8, 2),
    "expanded": (15, 12, 3),
    "large": (20, 16, 4),
}


def normalized(value: str) -> str:
    return re.sub(r"\W+", " ", value.casefold()).strip()


def validate_question_bank(
    payload: dict[str, Any],
    *,
    source_ids: set[str],
    concept_ids: set[str],
    publication: bool = False,
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
        if not prompt:
            errors.append(f"{prefix}.prompt is required")

        q_concepts = question.get("concept_ids")
        if not isinstance(q_concepts, list) or not q_concepts:
            errors.append(f"{prefix}.concept_ids must be a non-empty list")
            q_concepts = []
        for concept_id in q_concepts:
            if concept_ids and concept_id not in concept_ids:
                errors.append(f"{prefix} references unknown concept_id: {concept_id}")
            if qtype in {"application", "calculation", "synthesis"} or question.get("format") == "passage_mcq":
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
            if question.get("format") not in {"standalone_mcq", "passage_mcq"}:
                errors.append(f"{prefix}.format must be standalone_mcq or passage_mcq")
            options = question.get("options")
            if not isinstance(options, list) or len(options) != 4:
                errors.append(f"{prefix}.options must contain exactly four options")
                options = []
            option_ids: list[str] = []
            option_text: dict[str, str] = {}
            for option_index, option in enumerate(options):
                if not isinstance(option, dict):
                    errors.append(f"{prefix}.options[{option_index}] must be an object")
                    continue
                option_id = str(option.get("option_id", "")).strip()
                text = str(option.get("text", "")).strip()
                if not option_id or not text:
                    errors.append(f"{prefix}.options[{option_index}] requires option_id and text")
                option_ids.append(option_id)
                option_text[option_id] = text
            if len(option_ids) != len(set(option_ids)):
                errors.append(f"{prefix}.options contains duplicate option IDs")
            if len({normalized(value) for value in option_text.values()}) != len(option_text):
                errors.append(f"{prefix}.options contains duplicate option text")
            correct_option_id = str(question.get("correct_option_id", "")).strip()
            if correct_option_id not in option_text:
                errors.append(f"{prefix}.correct_option_id must reference an option")
            explanation = str(question.get("correct_explanation", question.get("explanation", ""))).strip()
            if not explanation:
                errors.append(f"{prefix}.correct_explanation is required")
            correct_text = option_text.get(correct_option_id, "")
            if correct_text and len(normalized(correct_text)) >= 8 and normalized(correct_text) in normalized(prompt):
                errors.append(f"{prefix} appears to leak the correct answer in the prompt")
            rationales = question.get("distractor_rationales")
            expected_distractors = set(option_text) - {correct_option_id}
            if not isinstance(rationales, dict) or set(rationales) != expected_distractors:
                errors.append(f"{prefix}.distractor_rationales must explain every incorrect option only")
            elif any(not str(value).strip() for value in rationales.values()):
                errors.append(f"{prefix}.distractor_rationales cannot be empty")
            if publication and question.get("quality_status") != "validated":
                errors.append(f"{prefix}.quality_status must be validated for publication")
            if publication and not str(question.get("chapter_id", "")).strip():
                errors.append(f"{prefix}.chapter_id is required for publication")
        else:
            answer = str(question.get("correct_answer", "")).strip()
            if not answer:
                errors.append(f"{prefix}.correct_answer is required")
            if answer and len(normalized(answer)) >= 8 and normalized(answer) in normalized(prompt):
                errors.append(f"{prefix} appears to leak the correct answer in the prompt")
            if publication:
                errors.append(f"{prefix} is open-response; published chapter banks must use multiple-choice delivery items")

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
    if publication:
        chapters = payload.get("chapters")
        if not isinstance(chapters, list) or not chapters:
            errors.append("question-bank.json must define chapters for publication")
        else:
            questions_by_chapter: dict[str, list[dict[str, Any]]] = {}
            for question in questions:
                if isinstance(question, dict):
                    questions_by_chapter.setdefault(str(question.get("chapter_id", "")), []).append(question)
            seen_chapters: set[str] = set()
            for index, chapter in enumerate(chapters):
                prefix = f"chapters[{index}]"
                if not isinstance(chapter, dict):
                    errors.append(f"{prefix} must be an object")
                    continue
                chapter_id = str(chapter.get("chapter_id", "")).strip()
                if not chapter_id or chapter_id in seen_chapters:
                    errors.append(f"{prefix}.chapter_id is missing or duplicated")
                    continue
                seen_chapters.add(chapter_id)
                tier = str(chapter.get("question_tier", "")).strip()
                expected = QUESTION_TIERS.get(tier)
                if expected is None:
                    errors.append(f"{prefix}.question_tier must be one of {sorted(QUESTION_TIERS)}")
                    continue
                chapter_questions = questions_by_chapter.get(chapter_id, [])
                standalone = sum(item.get("format") == "standalone_mcq" for item in chapter_questions)
                passage = sum(item.get("format") == "passage_mcq" for item in chapter_questions)
                if (len(chapter_questions), standalone, passage) != expected:
                    errors.append(
                        f"{chapter_id} must contain {expected[0]} questions: "
                        f"{expected[1]} standalone_mcq and {expected[2]} passage_mcq"
                    )
            unknown = set(questions_by_chapter) - seen_chapters - {""}
            for chapter_id in sorted(unknown):
                errors.append(f"Questions reference undeclared chapter_id: {chapter_id}")
    return errors, warnings


def validate_learning_materials(root: Path) -> list[str]:
    """Require substantive book-like chapters before assessment planning begins."""
    errors: list[str] = []
    index_path = root / INDEX
    try:
        index_text = index_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as error:
        return [f"Cannot read {relative_text(INDEX)}: {error}"]
    placeholder_markers = (
        "replace this structural shell",
        "replace with a concise chapter summary",
        "no substantive knowledge is published during initialization",
    )
    if len(index_text) < 200 or any(marker in index_text.casefold() for marker in placeholder_markers):
        errors.append("index.md must be a substantive learner-facing course map before assessment planning")

    try:
        payload = json.loads((root / QUESTION_BANK).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return [*errors, f"Cannot read {relative_text(QUESTION_BANK)}: {error}"]
    chapters = payload.get("chapters") if isinstance(payload, dict) else None
    if not isinstance(chapters, list) or not chapters:
        return [*errors, "question-bank.json must declare at least one chapter before assessment planning"]

    source_ids = load_source_ids(root / SOURCE_MANIFEST)
    seen_chapter_ids: set[str] = set()
    lessons_root = (root / "lessons").resolve()
    for index, chapter in enumerate(chapters):
        prefix = f"chapters[{index}]"
        if not isinstance(chapter, dict):
            errors.append(f"{prefix} must be an object")
            continue
        chapter_id = str(chapter.get("chapter_id") or "").strip()
        if not chapter_id or chapter_id in seen_chapter_ids:
            errors.append(f"{prefix}.chapter_id is missing or duplicated")
            continue
        seen_chapter_ids.add(chapter_id)
        lesson_relative = chapter.get("lesson_path")
        if not isinstance(lesson_relative, str) or not lesson_relative.startswith("lessons/") or not lesson_relative.endswith(".md"):
            errors.append(f"{prefix}.lesson_path must name a Markdown file under lessons/")
            continue
        lesson = (root / lesson_relative).resolve(strict=False)
        try:
            lesson.relative_to(lessons_root)
        except ValueError:
            errors.append(f"{prefix}.lesson_path escapes lessons/")
            continue
        if not lesson.is_file() or lesson.is_symlink():
            errors.append(f"{prefix}.lesson_path must resolve to a regular lesson file")
            continue
        lesson_errors, lesson_warnings = validate_lesson(
            lesson,
            source_ids=source_ids,
            publication=False,
            substantive=True,
            expected_chapter_id=chapter_id,
        )
        errors.extend(f"{lesson_relative}: {message}" for message in [*lesson_errors, *lesson_warnings])
    return errors


def _publication_errors(root: Path, source_ids: set[str], *, require_ready_exam: bool = True) -> list[str]:
    errors: list[str] = []
    study = yaml.safe_load((root / "study.yaml").read_text(encoding="utf-8"))
    research_mode = isinstance(study, dict) and study.get("mode") in {"topic-research", "hybrid"}
    manifest = yaml.safe_load((root / SOURCE_MANIFEST).read_text(encoding="utf-8"))
    sources = manifest.get("sources", []) if isinstance(manifest, dict) else []
    if not isinstance(sources, list) or not sources:
        errors.append("Publication requires at least one source")
        sources = []
    for index, source in enumerate(sources):
        prefix = f"source-manifest sources[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if source.get("processing_status") != "ready":
            errors.append(f"{prefix}.processing_status must be ready")
        content_hash = str(source.get("content_hash", ""))
        if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", content_hash):
            errors.append(f"{prefix}.content_hash must be a real sha256 digest")
        knowledge_path = source.get("knowledge_path")
        source_prefix = relative_text(SOURCE) + "/"
        if not isinstance(knowledge_path, str) or not knowledge_path.startswith(source_prefix) or not knowledge_path.endswith(".md"):
            errors.append(f"{prefix}.knowledge_path must name a Markdown file under {relative_text(SOURCE)}/")
            continue
        candidate = (root / knowledge_path).resolve(strict=False)
        try:
            candidate.relative_to((root / SOURCE).resolve())
        except ValueError:
            errors.append(f"{prefix}.knowledge_path escapes {relative_text(SOURCE)}/")
        else:
            if not candidate.is_file() or candidate.is_symlink() or len(candidate.read_text(encoding="utf-8").strip()) < 20:
                errors.append(f"{prefix}.knowledge_path must resolve to non-empty extracted knowledge")
            elif re.fullmatch(r"sha256:[0-9a-fA-F]{64}", content_hash) and sha256_file(candidate).casefold() != content_hash.casefold():
                errors.append(f"{prefix}.content_hash does not match its extracted knowledge")

    source_root = root / SOURCE
    if source_root.is_dir():
        for child in source_root.iterdir():
            if child.is_file() and child.suffix.casefold() != ".md":
                errors.append(f"Only Markdown files may live at {relative_text(SOURCE)}/ root: {child.name}")
            if child.is_dir() and child.name != "media":
                errors.append(f"Only the media/ directory may live under {relative_text(SOURCE)}/: {child.name}")

    log = root / EVENT_LOG
    if not log.is_file() or log.is_symlink() or not log.read_text(encoding="utf-8").strip():
        errors.append(f"Publication requires a non-empty {relative_text(EVENT_LOG)} action log")
    else:
        substantive_events = 0
        for line_number, line in enumerate(log.read_text(encoding="utf-8").splitlines(), 1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                errors.append(f"{relative_text(EVENT_LOG)} line {line_number} is invalid JSON")
                continue
            required = {"event_id", "schema_version", "timestamp", "action", "actor", "status", "summary"}
            if not isinstance(event, dict) or event.get("schema_version") != "action-event-v1" or not required.issubset(event):
                errors.append(f"{relative_text(EVENT_LOG)} line {line_number} is not a complete action-event-v1")
            elif event.get("action") != "course.initialized":
                substantive_events += 1
        if substantive_events == 0:
            errors.append("Publication requires an action log beyond the course initialization event")

    question_bank = json.loads((root / QUESTION_BANK).read_text(encoding="utf-8"))
    bank_ids = {str(item.get("question_id")) for item in question_bank.get("questions", []) if isinstance(item, dict)}
    bank_hash = sha256_file(root / QUESTION_BANK)
    approved_claim_ids: set[str] = set()
    if (root / APPROVED_CLAIMS).is_file():
        approved_payload = json.loads((root / APPROVED_CLAIMS).read_text(encoding="utf-8"))
        approved_claim_ids = {
            str(item.get("claim_id"))
            for item in approved_payload.get("claims", [])
            if isinstance(item, dict) and item.get("claim_id")
        }
    receipts, receipt_errors = load_validation_receipts(root)
    errors.extend(receipt_errors)
    by_run: dict[str, list[dict[str, Any]]] = {}
    for receipt in receipts:
        by_run.setdefault(str(receipt.get("run_id") or ""), []).append(receipt)
        if receipt.get("task_status") not in {"submitted", "verified", "approved", "merged"}:
            errors.append(f"Validation receipt {receipt.get('task_id')} is not accepted")
        plan = receipt.get("plan")
        if not isinstance(plan, dict) or not isinstance(plan.get("authorization"), dict) or plan["authorization"].get("status") != "approved":
            errors.append(f"Validation receipt {receipt.get('task_id')} lacks approved worker authorization")

    evidence_roles = {"source-extractor", "citation-verifier"}
    if research_mode:
        evidence_roles.add("contradiction-reviewer")
    evidence_runs = [
        items for items in by_run.values()
        if evidence_roles.issubset({str(item.get("role")) for item in items})
    ]
    if not evidence_runs:
        errors.append("Publication requires durable accepted-worker receipts for: " + ", ".join(sorted(evidence_roles)))
    else:
        expected_plan = (
            ("research-run-plan-v1", "create_research_plan.py")
            if research_mode
            else ("provided-evidence-plan-v1", "create_provided_evidence_plan.py")
        )
        verified_evidence_run = False
        for items in evidence_runs:
            plan_pairs = {
                (item.get("plan", {}).get("schema_version"), item.get("plan", {}).get("compiler"))
                for item in items
            }
            if plan_pairs != {expected_plan}:
                continue
            citations = [item for item in items if item.get("role") == "citation-verifier"]
            if not citations or citations[-1].get("result", {}).get("decision") not in {"verified", "approved"}:
                continue
            verified_ids = {str(item) for item in citations[-1].get("result", {}).get("verified_claim_ids", [])}
            if approved_claim_ids and not approved_claim_ids.issubset(verified_ids):
                continue
            if research_mode:
                contradictions = [item for item in items if item.get("role") == "contradiction-reviewer"]
                if not contradictions or contradictions[-1].get("result", {}).get("status") != "complete":
                    continue
            verified_evidence_run = True
            break
        if not verified_evidence_run:
            errors.append("No generated evidence run has durable verification receipts covering every approved claim")

    assessment_roles = {"assessment-validator"}
    assessment_runs = [
        items for items in by_run.values()
        if assessment_roles.issubset({str(item.get("role")) for item in items})
    ]
    if not assessment_runs:
        errors.append("A ready exam requires a durable receipt from an independent assessment validator")
    else:
        validated_assessment_run = False
        for items in assessment_runs:
            plan_pairs = {
                (item.get("plan", {}).get("schema_version"), item.get("plan", {}).get("compiler"))
                for item in items
            }
            if plan_pairs != {("assessment-run-plan-v1", "create_assessment_plan.py")}:
                continue
            validators = [item for item in items if item.get("role") == "assessment-validator"]
            if not validators:
                continue
            result = validators[-1].get("result", {})
            validated_ids = {str(item) for item in result.get("validated_question_ids", [])}
            validated_inputs = {
                (str(item.get("path")), str(item.get("sha256")))
                for item in validators[-1].get("input_artifacts", [])
                if isinstance(item, dict)
            }
            if (
                result.get("decision") == "approved"
                and validated_ids == bank_ids
                and (relative_text(QUESTION_BANK), bank_hash) in validated_inputs
            ):
                validated_assessment_run = True
                break
        if not validated_assessment_run:
            errors.append("No generated assessment run durably validates the current question-bank content and every published question ID")

    for chapter_index, chapter in enumerate(question_bank.get("chapters", [])):
        if not isinstance(chapter, dict):
            continue
        lesson_path = chapter.get("lesson_path")
        prefix = f"question-bank chapters[{chapter_index}]"
        if not isinstance(lesson_path, str) or not lesson_path.startswith("lessons/") or not lesson_path.endswith(".md"):
            errors.append(f"{prefix}.lesson_path must name a Markdown file under lessons/")
            continue
        lesson = (root / lesson_path).resolve(strict=False)
        try:
            lesson.relative_to((root / "lessons").resolve())
        except ValueError:
            errors.append(f"{prefix}.lesson_path escapes lessons/")
        else:
            if not lesson.is_file() or lesson.is_symlink():
                errors.append(f"{prefix}.lesson_path must resolve to a regular lesson file")
            else:
                lesson_errors, lesson_warnings = validate_lesson(
                    lesson,
                    source_ids=source_ids,
                    publication=True,
                    expected_chapter_id=str(chapter.get("chapter_id") or ""),
                )
                errors.extend(f"{lesson_path}: {error}" for error in lesson_errors)
                errors.extend(f"{lesson_path}: {warning}" for warning in lesson_warnings)

    approved = root / APPROVED_CLAIMS
    if not approved.is_file():
        errors.append(f"Publication requires {relative_text(APPROVED_CLAIMS)}")
    else:
        payload = json.loads(approved.read_text(encoding="utf-8"))
        if not isinstance(payload.get("claims"), list) or not payload["claims"]:
            errors.append(f"{relative_text(APPROVED_CLAIMS)} must contain approved claims")
        else:
            for claim_index, claim in enumerate(payload["claims"]):
                prefix = f"approved-claims claims[{claim_index}]"
                if not isinstance(claim, dict) or not str(claim.get("claim_id", "")).strip():
                    errors.append(f"{prefix}.claim_id is required")
                    continue
                refs = claim.get("source_refs")
                if not isinstance(refs, list) or not refs:
                    errors.append(f"{prefix}.source_refs must be non-empty")
                    continue
                for ref_index, ref in enumerate(refs):
                    errors.extend(validate_source_ref(ref, source_ids, f"{prefix}.source_refs[{ref_index}]"))

    index_text = (root / INDEX).read_text(encoding="utf-8").strip()
    if len(index_text) < 200:
        errors.append("index.md must be a substantive learner-facing course map for publication")

    markdown_bank = root / QUESTION_BANK_REVIEW
    if not markdown_bank.is_file() or len(markdown_bank.read_text(encoding="utf-8").strip()) < 20:
        errors.append("Publication requires a non-empty questions/question-bank.md review copy")

    exam_files = sorted((root / "exams").glob("*/exam.json"))
    ready_exams = 0
    for path in exam_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("status") != "ready":
            continue
        ready_exams += 1
        raw_questions = payload.get("questions")
        if not isinstance(raw_questions, list) or not raw_questions:
            errors.append(f"{path.relative_to(root)} has no embedded questions")
            continue
        exam_bank = {"source_ref_schema": "source-ref-v1", "questions": raw_questions}
        exam_errors, _ = validate_question_bank(exam_bank, source_ids=source_ids, concept_ids=set(), publication=False)
        errors.extend(f"{path.relative_to(root)}: {error}" for error in exam_errors)
        exam_ids = [str(item.get("question_id")) for item in raw_questions if isinstance(item, dict)]
        if len(exam_ids) != len(set(exam_ids)):
            errors.append(f"{path.relative_to(root)} contains duplicate question IDs")
        unknown_ids = set(exam_ids) - bank_ids
        if unknown_ids:
            errors.append(f"{path.relative_to(root)} contains questions outside the validated bank: {', '.join(sorted(unknown_ids))}")
    if require_ready_exam and ready_exams == 0:
        errors.append("Publication requires at least one app-compatible ready exam")
    return errors


def validate_workspace(
    root: Path,
    *,
    publication: bool = False,
    require_ready_exam: bool = True,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            errors.append(f"Missing required file: {relative}")
    if errors:
        return errors, warnings

    source_ids = load_source_ids(root / SOURCE_MANIFEST)
    if not source_ids:
        warnings.append(f"No source IDs found in {relative_text(SOURCE_MANIFEST)}")

    progress = json.loads((root / PROGRESS / "learner-progress.json").read_text(encoding="utf-8"))
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

    question_payload = json.loads((root / QUESTION_BANK).read_text(encoding="utf-8"))
    question_errors, question_warnings = validate_question_bank(
        question_payload,
        source_ids=source_ids,
        concept_ids=concept_ids,
        publication=publication,
    )
    errors.extend(question_errors)
    warnings.extend(question_warnings)

    if len((root / INDEX).read_text(encoding="utf-8").strip()) < 100:
        warnings.append("index.md is nearly empty")
    if publication:
        errors.extend(_publication_errors(root, source_ids, require_ready_exam=require_ready_exam))
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--publication", action="store_true", help="Enforce the publishable-course and ready-exam gates")
    args = parser.parse_args()
    if not args.workspace.is_dir():
        parser.error(f"Workspace does not exist: {args.workspace}")
    try:
        errors, warnings = validate_workspace(args.workspace, publication=args.publication)
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
