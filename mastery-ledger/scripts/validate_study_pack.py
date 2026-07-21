#!/usr/bin/env python3
"""Validate the structural integrity of a Mastery Ledger course workspace."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

from source_registry import sha256_file
from validate_evidence import load_source_ids, validate_source_ref
from validate_orchestration import SUBMITTED_STATES, validate_plan

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
                chapter_class = chapter.get("class")
                if not chapter_id or chapter_id in seen_chapters:
                    errors.append(f"{prefix}.chapter_id is missing or duplicated")
                    continue
                seen_chapters.add(chapter_id)
                expected = {"core": (10, 8, 2), "short": (5, 4, 1), "optional": (5, 4, 1)}.get(str(chapter_class))
                if expected is None:
                    errors.append(f"{prefix}.class must be core, short, or optional")
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


def _publication_errors(root: Path, source_ids: set[str]) -> list[str]:
    errors: list[str] = []
    study = yaml.safe_load((root / "study.yaml").read_text(encoding="utf-8"))
    research_mode = isinstance(study, dict) and study.get("mode") in {"topic-research", "hybrid"}
    manifest = yaml.safe_load((root / "source-manifest.yaml").read_text(encoding="utf-8"))
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
        if not isinstance(knowledge_path, str) or not knowledge_path.startswith("source/") or not knowledge_path.endswith(".md"):
            errors.append(f"{prefix}.knowledge_path must name a Markdown file under source/")
            continue
        candidate = (root / knowledge_path).resolve(strict=False)
        try:
            candidate.relative_to((root / "source").resolve())
        except ValueError:
            errors.append(f"{prefix}.knowledge_path escapes source/")
        else:
            if not candidate.is_file() or candidate.is_symlink() or len(candidate.read_text(encoding="utf-8").strip()) < 20:
                errors.append(f"{prefix}.knowledge_path must resolve to non-empty extracted knowledge")
            elif re.fullmatch(r"sha256:[0-9a-fA-F]{64}", content_hash) and sha256_file(candidate).casefold() != content_hash.casefold():
                errors.append(f"{prefix}.content_hash does not match its extracted knowledge")

    source_root = root / "source"
    if source_root.is_dir():
        for child in source_root.iterdir():
            if child.is_file() and child.suffix.casefold() != ".md":
                errors.append(f"Only Markdown files may live at source/ root: {child.name}")
            if child.is_dir() and child.name != "media":
                errors.append(f"Only the media/ directory may live under source/: {child.name}")

    log = root / "logs" / "events.jsonl"
    if not log.is_file() or log.is_symlink() or not log.read_text(encoding="utf-8").strip():
        errors.append("Publication requires a non-empty logs/events.jsonl action log")
    else:
        substantive_events = 0
        for line_number, line in enumerate(log.read_text(encoding="utf-8").splitlines(), 1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                errors.append(f"logs/events.jsonl line {line_number} is invalid JSON")
                continue
            required = {"event_id", "schema_version", "timestamp", "action", "actor", "status", "summary"}
            if not isinstance(event, dict) or event.get("schema_version") != "action-event-v1" or not required.issubset(event):
                errors.append(f"logs/events.jsonl line {line_number} is not a complete action-event-v1")
            elif event.get("action") != "course.initialized":
                substantive_events += 1
        if substantive_events == 0:
            errors.append("Publication requires an action log beyond the course initialization event")

    plan_path = root / ".work" / "orchestration" / "run-plan.yaml"
    if not plan_path.is_file():
        errors.append("Publication requires .work/orchestration/run-plan.yaml")
    else:
        plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
        plans: list[dict] = []
        seen_runs: set[str] = set()
        cursor = plan
        while isinstance(cursor, dict):
            run_id = str(cursor.get("run_id") or "").strip()
            if not run_id:
                errors.append("Publication orchestration plan has no run_id")
                break
            if run_id in seen_runs:
                errors.append(f"Publication orchestration predecessor cycle includes {run_id}")
                break
            seen_runs.add(run_id)
            plans.append(cursor)
            predecessor = str(cursor.get("predecessor_run_id") or "").strip()
            if not predecessor:
                break
            predecessor_relation = str(cursor.get("predecessor_relation") or "").strip()
            if predecessor_relation == "supersedes":
                break
            predecessor_path = root / ".work" / "runs" / predecessor / "run-plan.yaml"
            if not predecessor_path.is_file() or predecessor_path.is_symlink():
                errors.append(f"Publication orchestration predecessor is missing: {predecessor}")
                break
            try:
                cursor = yaml.safe_load(predecessor_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, yaml.YAMLError):
                errors.append(f"Publication orchestration predecessor is unreadable: {predecessor}")
                break
            if not isinstance(cursor, dict) or cursor.get("run_id") != predecessor:
                errors.append(f"Publication orchestration predecessor identity is invalid: {predecessor}")
                break

        tasks = []
        for chained_plan in plans:
            plan_errors, _, _ = validate_plan(chained_plan, course_root=root)
            errors.extend(plan_errors)
            tasks.extend(chained_plan.get("task_graph", []) if isinstance(chained_plan.get("task_graph"), list) else [])
        if not tasks:
            errors.append("Publication requires a non-empty orchestration task graph")
        roles = {str(task.get("role")) for task in tasks if isinstance(task, dict)}
        required_roles = {"assessment-generator", "assessment-validator"}
        if research_mode:
            required_roles.update({"corpus-mapper", "source-extractor", "research-worker", "contradiction-reviewer", "citation-verifier"})
        for role in sorted(required_roles - roles):
            errors.append(f"Publication orchestration is missing required role: {role}")
        unfinished = [str(task.get("task_id")) for task in tasks if isinstance(task, dict) and task.get("status") not in SUBMITTED_STATES]
        if unfinished:
            errors.append("Publication has unfinished orchestration tasks: " + ", ".join(unfinished))
        if not plans or any(item.get("authorization", {}).get("status") != "approved" for item in plans):
            errors.append("Publication requires recorded scope and worker authorization")
        assessment_plans = [
            item for item in plans
            if any(isinstance(task, dict) and task.get("role") == "assessment-validator" for task in item.get("task_graph", []))
        ]
        if not assessment_plans:
            errors.append("A ready exam requires a generated independent assessment-validation plan")
        question_bank = json.loads((root / "questions" / "question-bank.json").read_text(encoding="utf-8"))
        bank_ids = {str(item.get("question_id")) for item in question_bank.get("questions", []) if isinstance(item, dict)}
        for task in tasks:
            if not isinstance(task, dict) or task.get("status") not in SUBMITTED_STATES:
                continue
            output_path = task.get("output_path")
            if not isinstance(output_path, str):
                continue
            output = root / output_path
            if not output.is_file():
                continue
            payload = json.loads(output.read_text(encoding="utf-8"))
            role = task.get("role")
            if role == "contradiction-reviewer" and payload.get("status") != "complete":
                errors.append("Contradiction review output must have status=complete")
            if role == "citation-verifier" and payload.get("decision") not in {"verified", "approved"}:
                errors.append("Final citation review must have decision=verified or approved")
            if role == "assessment-validator":
                if payload.get("decision") != "approved":
                    errors.append("Independent assessment validation must have decision=approved")
                validated_ids = {str(item) for item in payload.get("validated_question_ids", [])}
                if validated_ids != bank_ids:
                    errors.append("Assessment validation must cover every published question ID")

    question_bank = json.loads((root / "questions" / "question-bank.json").read_text(encoding="utf-8"))
    bank_ids = {str(item.get("question_id")) for item in question_bank.get("questions", []) if isinstance(item, dict)}
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
            if not lesson.is_file() or lesson.is_symlink() or len(lesson.read_text(encoding="utf-8").strip()) < 100:
                errors.append(f"{prefix}.lesson_path must resolve to a substantive lesson")

    approved = root / "evidence" / "approved-claims.json"
    if not approved.is_file():
        errors.append("Publication requires evidence/approved-claims.json")
    else:
        payload = json.loads(approved.read_text(encoding="utf-8"))
        if not isinstance(payload.get("claims"), list) or not payload["claims"]:
            errors.append("evidence/approved-claims.json must contain approved claims")
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

    markdown_bank = root / "questions" / "question-bank.md"
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
    if ready_exams == 0:
        errors.append("Publication requires at least one app-compatible ready exam")
    return errors


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


def validate_workspace(root: Path, *, publication: bool = False) -> tuple[list[str], list[str]]:
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
        publication=publication,
    )
    errors.extend(question_errors)
    warnings.extend(question_warnings)

    for markdown_name in ("study-guide.md", "concept-map.md", "glossary.md"):
        text = (root / markdown_name).read_text(encoding="utf-8").strip()
        if len(text) < 100:
            if publication:
                errors.append(f"{markdown_name} is not substantive enough for publication")
            else:
                warnings.append(f"{markdown_name} is nearly empty")
    if publication:
        errors.extend(_publication_errors(root, source_ids))
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
