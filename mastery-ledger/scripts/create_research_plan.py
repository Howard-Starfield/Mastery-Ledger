#!/usr/bin/env python3
"""Compile the mandatory researched-course task graph from approved inputs."""

from __future__ import annotations

import argparse
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from record_action import append_event


def task(run_id: str, task_id: str, role: str, dependencies: list[str], folder: str = "reports", schema: str = "evidence-packet-v1") -> dict:
    output = f".work/orchestration/{folder}/{task_id}.json"
    return {
        "task_id": task_id,
        "run_id": run_id,
        "role": role,
        "objective": f"Complete the bounded {role} phase.",
        "scope_included": [],
        "scope_excluded": [],
        "concept_ids": [],
        "input_source_ids": [],
        "input_artifacts": [],
        "source_limit": 5,
        "dependencies": dependencies,
        "output_path": output,
        "completion_path": f".work/orchestration/completions/{task_id}.json",
        "required_schema": schema,
        "reviewer_role": "main-agent",
        "acceptance_criteria": ["Use assigned scope only", "Preserve contradictions and gaps"],
        "status": "planned",
    }


def atomic_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    parser.add_argument("--research-workers", type=int, default=3)
    parser.add_argument("--authorized", action="store_true")
    args = parser.parse_args()
    if not args.authorized:
        parser.error("Explicit scope and worker authorization is required.")
    if not 1 <= args.research_workers <= 5:
        parser.error("Research worker count must be 1-5.")
    root = args.course_root.resolve()
    study = yaml.safe_load((root / "study.yaml").read_text(encoding="utf-8"))
    mode = str(study.get("mode", ""))
    if mode not in {"topic-research", "hybrid"}:
        parser.error("This compiler is only for topic-research or hybrid studies.")
    run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"
    mapper = task(run_id, "TASK-MAP", "corpus-mapper", [], schema="corpus-map-v1")
    research = [task(run_id, f"TASK-RESEARCH-{index:02d}", "research-worker", ["TASK-MAP"]) for index in range(1, args.research_workers + 1)]
    research_ids = [item["task_id"] for item in research]
    contradiction = task(run_id, "TASK-CONTRADICTIONS", "contradiction-reviewer", research_ids, schema="contradiction-review-v1")
    citation = task(run_id, "TASK-CITATIONS", "citation-verifier", ["TASK-CONTRADICTIONS"], "reviews", "citation-review-v1")
    generator = task(run_id, "TASK-ASSESSMENT-GENERATE", "assessment-generator", ["TASK-CITATIONS"], schema="question-bank-v2")
    validator = task(run_id, "TASK-ASSESSMENT-VALIDATE", "assessment-validator", ["TASK-ASSESSMENT-GENERATE"], "reviews", "assessment-validation-v1")
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "research-run-plan-v1",
        "run_id": run_id,
        "study_id": study.get("study_id"),
        "goal": study.get("learner_goal", "Build a source-grounded study pack"),
        "mode": mode,
        "authorization": {"status": "approved", "approved_at": now, "scope": "displayed-scope-card"},
        "publication_intent": True,
        "capabilities": {"filesystem": True, "web": True, "citations": True, "scripts": True, "subagents": True, "parallel_subagents": True},
        "workflow_state": "tasks_planned",
        "task_graph": [mapper, *research, contradiction, citation, generator, validator],
        "created_at": now,
        "updated_at": now,
    }
    path = root / ".work" / "orchestration" / "run-plan.yaml"
    atomic_yaml(path, payload)
    append_event(root, {
        "action": "research.plan_compiled", "actor": "main-agent", "status": "complete",
        "summary": f"Compiled an authorized plan with {args.research_workers} research workers and ordered review phases.",
        "artifacts": [".work/orchestration/run-plan.yaml"], "decision": "approved",
        "justification": "The learner approved the displayed scope and worker topology."
    })
    print(yaml.safe_dump({"status": "complete", "run_id": run_id, "path": str(path), "first_ready_task_ids": ["TASK-MAP"]}, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
