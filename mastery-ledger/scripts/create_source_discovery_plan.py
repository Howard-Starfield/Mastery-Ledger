#!/usr/bin/env python3
"""Compile the pre-source scout run for a researched course."""

from __future__ import annotations

import argparse
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from create_research_plan import task
from plan_store import is_placeholder, load_active_plan, save_active_plan
from record_action import append_event


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    parser.add_argument("--authorized", action="store_true")
    args = parser.parse_args()
    if not args.authorized:
        parser.error("Explicit scope and source-search authorization is required.")

    root = args.course_root.resolve()
    study = yaml.safe_load((root / "study.yaml").read_text(encoding="utf-8"))
    if not isinstance(study, dict):
        parser.error("study.yaml must contain a YAML object")
    if study.get("mode") not in {"topic-research", "hybrid"}:
        parser.error("Source discovery is only for topic-research or hybrid studies.")
    state = str(study.get("workflow_state", "")).strip().replace("-", "_").upper()
    if state != "SCOPED":
        parser.error("Source discovery planning requires workflow_state SCOPED.")
    approval = study.get("learning_contract")
    if not isinstance(approval, dict) or approval.get("status") != "approved":
        parser.error("Source discovery requires the approved canonical learning contract.")
    source_limit = int(approval.get("source_limit") or 0)
    if not 1 <= source_limit <= 20:
        parser.error("The approved learning contract has an invalid source limit.")

    active_path = root / ".work" / "orchestration" / "run-plan.yaml"
    if active_path.is_file() and not is_placeholder(load_active_plan(root)):
        parser.error("An active run already exists; resume it instead of creating another source scout.")

    run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"
    goal = str(approval.get("goal") or study.get("learner_goal") or "Approved learning scope")
    included = [str(item) for item in approval.get("accepted_branches", [])] or [goal]
    excluded = [str(item) for item in approval.get("excluded", [])]
    scout = task(
        run_id,
        "TASK-SOURCE-SCOUT",
        "source-scout",
        [],
        schema="source-candidate-ledger-v1",
        scope_included=included,
        scope_excluded=excluded,
        source_limit=source_limit,
    )
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "source-discovery-plan-v1",
        "run_id": run_id,
        "study_id": study.get("study_id"),
        "goal": goal,
        "course_target": study.get("workflow_target", "LEARNING_ACTIVE"),
        "authorization": {
            "status": "approved",
            "approved_at": approval.get("approved_at") or now,
            "scope": goal,
            "source_limit": source_limit,
            "source_scouts": 1,
        },
        "publication_intent": True,
        "capabilities": {"filesystem": True, "web": True, "citations": True, "scripts": True, "subagents": True, "parallel_subagents": False},
        "workflow_state": "source_discovery",
        "task_graph": [scout],
        "created_at": now,
        "updated_at": now,
    }
    path = save_active_plan(root, payload)
    append_event(root, {
        "action": "source.discovery_plan_compiled",
        "actor": "main-agent",
        "status": "complete",
        "summary": "Compiled one bounded source-scout task before source acquisition.",
        "artifacts": [".work/orchestration/run-plan.yaml"],
        "decision": "approved",
        "justification": "A researched course requires an observable delegated source search before evidence work.",
    })
    print(yaml.safe_dump({
        "status": "complete",
        "run_id": run_id,
        "path": str(path),
        "first_context_task_ids": ["TASK-SOURCE-SCOUT"],
        "first_ready_task_ids": [],
    }, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
