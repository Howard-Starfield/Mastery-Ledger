#!/usr/bin/env python3
"""Compile one independent validator for the main-agent-authored assessment."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from course_paths import APPROVED_CLAIMS, INDEX, QUESTION_BANK, SOURCE_MANIFEST, relative_text
from create_research_plan import scheduler_requirements, task
from plan_store import is_placeholder, load_active_plan, save_active_plan
from record_action import append_event
from validate_evidence import load_source_ids
from validate_lesson import validate_lesson
from validate_orchestration import validate_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    parser.add_argument("--authorized", action="store_true")
    parser.add_argument("--supersede-reason")
    args = parser.parse_args()
    if not args.authorized:
        parser.error("Explicit assessment authorization is required.")
    root = args.course_root.resolve()
    study = yaml.safe_load((root / "study.yaml").read_text(encoding="utf-8"))
    mode = str(study.get("mode", ""))
    state = str(study.get("workflow_state", "")).strip().replace("-", "_").upper()
    if state not in {"EVIDENCE_APPROVED", "STUDY_PACK_DRAFTED"}:
        parser.error("Assessment planning requires EVIDENCE_APPROVED and substantive course drafts.")
    claims_path = root / APPROVED_CLAIMS
    try:
        claims_payload = json.loads(claims_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        parser.error(f"Assessment input is unreadable: {relative_text(APPROVED_CLAIMS)}")
    if not isinstance(claims_payload, dict) or not isinstance(claims_payload.get("claims"), list) or not claims_payload["claims"]:
        parser.error(f"Assessment input has no approved claims: {relative_text(APPROVED_CLAIMS)}")
    index_path = root / INDEX
    if not index_path.is_file() or index_path.is_symlink() or len(index_path.read_text(encoding="utf-8").strip()) < 200:
        parser.error(f"Assessment input is missing or not substantive: {relative_text(INDEX)}")
    try:
        bank = json.loads((root / QUESTION_BANK).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        parser.error(f"Assessment input is unreadable: {relative_text(QUESTION_BANK)}")
    chapters = bank.get("chapters", []) if isinstance(bank, dict) else []
    if not isinstance(chapters, list) or not chapters:
        parser.error("Assessment planning requires at least one declared chapter and lesson.")
    source_ids = load_source_ids(root / SOURCE_MANIFEST)
    lesson_artifacts: list[str] = []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            parser.error("Assessment planning found a malformed chapter record.")
        lesson_relative = chapter.get("lesson_path")
        if not isinstance(lesson_relative, str) or not lesson_relative.startswith("lessons/") or not lesson_relative.endswith(".md"):
            parser.error("Assessment planning requires a Markdown lesson_path under lessons/ for every chapter.")
        lesson = (root / lesson_relative).resolve(strict=False)
        try:
            lesson.relative_to((root / "lessons").resolve())
        except ValueError:
            parser.error(f"Assessment lesson path escapes lessons/: {lesson_relative}")
        if lesson.is_symlink():
            parser.error(f"Assessment lesson cannot be a symlink: {lesson_relative}")
        errors, warnings = validate_lesson(
            lesson,
            source_ids=source_ids,
            publication=False,
            substantive=True,
            expected_chapter_id=str(chapter.get("chapter_id") or ""),
        )
        if errors or warnings:
            parser.error("Assessment lesson input is not substantive: " + "; ".join([*errors, *warnings]))
        lesson_artifacts.append(lesson_relative)
    predecessor_run_id = None
    predecessor_relation = None
    active_to_archive = None
    active_path = root / ".work" / "orchestration" / "run-plan.yaml"
    if active_path.is_file():
        active = load_active_plan(root)
        if not is_placeholder(active):
            predecessor_run_id = active.get("run_id")
            active_to_archive = active
            plan_errors, _, _ = validate_plan(active, course_root=root)
            unfinished = [
                str(item.get("task_id"))
                for item in active.get("task_graph", [])
                if isinstance(item, dict) and item.get("status") not in {"submitted", "verified", "approved", "merged"}
            ]
            if (unfinished or plan_errors) and not args.supersede_reason:
                details = ", ".join(unfinished) if unfinished else "; ".join(plan_errors)
                parser.error("Active run is unfinished or invalid; repair it or provide --supersede-reason explicitly: " + details)
            predecessor_relation = "supersedes" if unfinished or plan_errors else "evidence"
    run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"
    validator = task(
        run_id,
        "TASK-ASSESSMENT-VALIDATE",
        "assessment-validator",
        [],
        "reviews",
        "assessment-validation-v1",
        scope_included=["Generated question bank and approved evidence"],
        input_artifacts=[relative_text(APPROVED_CLAIMS), relative_text(INDEX), relative_text(QUESTION_BANK), *lesson_artifacts],
    )
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "assessment-run-plan-v1",
        "run_id": run_id,
        "study_id": study.get("study_id"),
        "goal": "Independently validate the main-agent-authored course assessment against approved evidence",
        "mode": mode,
        "course_target": study.get("workflow_target", "LEARNING_ACTIVE"),
        "predecessor_run_id": predecessor_run_id,
        "predecessor_relation": predecessor_relation,
        "supersession_reason": args.supersede_reason,
        "authorization": {"status": "approved", "approved_at": now, "scope": "displayed-assessment-card"},
        "publication_intent": True,
        "plan_origin": {"kind": "generated", "compiler": "create_assessment_plan.py"},
        "execution_requirements": scheduler_requirements(),
        "workflow_state": "tasks_planned",
        "task_graph": [validator],
        "created_at": now,
        "updated_at": now,
    }
    if active_to_archive is not None:
        save_active_plan(root, active_to_archive)
    path = save_active_plan(root, payload)
    append_event(root, {
        "action": "assessment.plan_compiled", "actor": "main-agent", "status": "complete",
        "summary": "Compiled one independent validation task for the main-agent-authored assessment.",
        "artifacts": [".work/orchestration/run-plan.yaml"], "decision": "approved",
        "justification": "The main agent authors the bank; a distinct worker independently validates every item before readiness.",
    })
    print(yaml.safe_dump({
        "status": "complete",
        "run_id": run_id,
        "path": str(path),
        "first_context_task_ids": ["TASK-ASSESSMENT-VALIDATE"],
        "first_ready_task_ids": [],
    }, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
