#!/usr/bin/env python3
"""Compile the independent assessment plan for a provided-source course."""

from __future__ import annotations

import argparse
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from create_research_plan import atomic_yaml, task
from record_action import append_event


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    parser.add_argument("--authorized", action="store_true")
    args = parser.parse_args()
    if not args.authorized:
        parser.error("Explicit assessment authorization is required.")
    root = args.course_root.resolve()
    study = yaml.safe_load((root / "study.yaml").read_text(encoding="utf-8"))
    mode = str(study.get("mode", ""))
    if mode in {"topic-research", "hybrid"}:
        parser.error("Use create_research_plan.py for topic-research or hybrid studies.")
    run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"
    generator = task(run_id, "TASK-ASSESSMENT-GENERATE", "assessment-generator", [], schema="question-bank-v2")
    validator = task(run_id, "TASK-ASSESSMENT-VALIDATE", "assessment-validator", ["TASK-ASSESSMENT-GENERATE"], "reviews", "assessment-validation-v1")
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "assessment-run-plan-v1",
        "run_id": run_id,
        "study_id": study.get("study_id"),
        "goal": "Generate and independently validate a ready exam from approved provided-source evidence",
        "mode": mode,
        "authorization": {"status": "approved", "approved_at": now, "scope": "displayed-assessment-card"},
        "publication_intent": True,
        "capabilities": {"filesystem": True, "citations": True, "scripts": True, "subagents": True, "parallel_subagents": False},
        "workflow_state": "tasks_planned",
        "task_graph": [generator, validator],
        "created_at": now,
        "updated_at": now,
    }
    path = root / ".work" / "orchestration" / "run-plan.yaml"
    atomic_yaml(path, payload)
    append_event(root, {
        "action": "assessment.plan_compiled", "actor": "main-agent", "status": "complete",
        "summary": "Compiled an authorized generation and independent validation plan.",
        "artifacts": [".work/orchestration/run-plan.yaml"], "decision": "approved",
        "justification": "A ready exam requires independent assessment validation.",
    })
    print(yaml.safe_dump({"status": "complete", "run_id": run_id, "path": str(path), "first_ready_task_ids": ["TASK-ASSESSMENT-GENERATE"]}, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
