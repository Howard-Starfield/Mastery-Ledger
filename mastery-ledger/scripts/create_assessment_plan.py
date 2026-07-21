#!/usr/bin/env python3
"""Compile the independent assessment plan for a provided-source course."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from create_research_plan import task
from plan_store import is_placeholder, load_active_plan, save_active_plan
from record_action import append_event
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
    claims_path = root / "evidence" / "approved-claims.json"
    try:
        claims_payload = json.loads(claims_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        parser.error("Assessment input is unreadable: evidence/approved-claims.json")
    if not isinstance(claims_payload, dict) or not isinstance(claims_payload.get("claims"), list) or not claims_payload["claims"]:
        parser.error("Assessment input has no approved claims: evidence/approved-claims.json")
    for relative in ("study-guide.md", "concept-map.md"):
        path = root / relative
        if not path.is_file() or path.is_symlink() or len(path.read_text(encoding="utf-8").strip()) < 100:
            parser.error(f"Assessment input is missing or not substantive: {relative}")
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
    generator = task(
        run_id,
        "TASK-ASSESSMENT-GENERATE",
        "assessment-generator",
        [],
        schema="question-bank-v2",
        scope_included=["Approved course objectives and chapter assessment contract"],
        input_artifacts=["evidence/approved-claims.json", "study-guide.md", "concept-map.md"],
    )
    validator = task(
        run_id,
        "TASK-ASSESSMENT-VALIDATE",
        "assessment-validator",
        ["TASK-ASSESSMENT-GENERATE"],
        "reviews",
        "assessment-validation-v1",
        scope_included=["Generated question bank and approved evidence"],
        input_artifacts=["evidence/approved-claims.json"],
    )
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "assessment-run-plan-v1",
        "run_id": run_id,
        "study_id": study.get("study_id"),
        "goal": "Generate and independently validate a ready exam from approved provided-source evidence",
        "mode": mode,
        "course_target": study.get("workflow_target", "LEARNING_ACTIVE"),
        "predecessor_run_id": predecessor_run_id,
        "predecessor_relation": predecessor_relation,
        "supersession_reason": args.supersede_reason,
        "authorization": {"status": "approved", "approved_at": now, "scope": "displayed-assessment-card"},
        "publication_intent": True,
        "plan_origin": {"kind": "generated", "compiler": "create_assessment_plan.py"},
        "execution_requirements": {"independent_workers": True, "parallelism_required": False},
        "workflow_state": "tasks_planned",
        "task_graph": [generator, validator],
        "created_at": now,
        "updated_at": now,
    }
    if active_to_archive is not None:
        save_active_plan(root, active_to_archive)
    path = save_active_plan(root, payload)
    append_event(root, {
        "action": "assessment.plan_compiled", "actor": "main-agent", "status": "complete",
        "summary": "Compiled an authorized generation and independent validation plan.",
        "artifacts": [".work/orchestration/run-plan.yaml"], "decision": "approved",
        "justification": "A ready exam requires independent assessment validation.",
    })
    print(yaml.safe_dump({
        "status": "complete",
        "run_id": run_id,
        "path": str(path),
        "first_context_task_ids": ["TASK-ASSESSMENT-GENERATE"],
        "first_ready_task_ids": [],
    }, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
