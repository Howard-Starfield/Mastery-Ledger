#!/usr/bin/env python3
"""Compile the mandatory researched-course task graph from approved inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from record_action import append_event


ROLE_PROFILES_PATH = Path(__file__).resolve().parents[1] / "references" / "agent-role-profiles.json"


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def load_role_profiles() -> dict[str, dict]:
    payload = json.loads(ROLE_PROFILES_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "agent-role-profiles-v1" or not isinstance(payload.get("profiles"), dict):
        raise ValueError("references/agent-role-profiles.json must use agent-role-profiles-v1")
    return payload["profiles"]


def task(
    run_id: str,
    task_id: str,
    role: str,
    dependencies: list[str],
    folder: str = "reports",
    schema: str = "evidence-packet-v1",
    *,
    scope_included: list[str] | None = None,
    input_artifacts: list[str] | None = None,
) -> dict:
    del folder  # Retained for caller compatibility; every task now owns one isolated directory.
    profile = load_role_profiles().get(role)
    if not isinstance(profile, dict):
        raise ValueError(f"No deterministic role profile exists for {role}")
    task_root = f".work/runs/{run_id}/tasks/{task_id}"
    return {
        "task_id": task_id,
        "run_id": run_id,
        "role": role,
        "role_profile_id": role,
        "role_profile_version": profile["version"],
        "role_profile_sha256": _canonical_hash(profile),
        "objective": profile["mission"],
        "scope_included": scope_included or [],
        "scope_excluded": [],
        "concept_ids": [],
        "input_source_ids": [],
        "input_artifacts": input_artifacts or [],
        "source_limit": 5,
        "dependencies": dependencies,
        "task_work_dir": task_root,
        "brief_path": f"{task_root}/task-brief.json",
        "context_path": f"{task_root}/context-manifest.json",
        "dispatch_path": f"{task_root}/dispatch-message.txt",
        "event_path": f"{task_root}/events.jsonl",
        "output_path": f"{task_root}/submission.json",
        "completion_path": f"{task_root}/completion.json",
        "required_schema": schema,
        "reviewer_role": "main-agent",
        "acceptance_criteria": [*profile["best_practices"], "Use assigned scope only."],
        "context_status": "pending",
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
    mapper = task(
        run_id,
        "TASK-MAP",
        "corpus-mapper",
        [],
        schema="corpus-map-v1",
        scope_included=[str(study.get("learner_goal") or "Approved course scope")],
        input_artifacts=["source-manifest.yaml"],
    )
    research = [task(run_id, f"TASK-RESEARCH-{index:02d}", "research-worker", ["TASK-MAP"]) for index in range(1, args.research_workers + 1)]
    research_ids = [item["task_id"] for item in research]
    contradiction = task(run_id, "TASK-CONTRADICTIONS", "contradiction-reviewer", research_ids, schema="contradiction-review-v1")
    citation = task(run_id, "TASK-CITATIONS", "citation-verifier", ["TASK-CONTRADICTIONS"], "reviews", "citation-review-v1")
    generator = task(
        run_id,
        "TASK-ASSESSMENT-GENERATE",
        "assessment-generator",
        ["TASK-CITATIONS"],
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
    print(yaml.safe_dump({
        "status": "complete",
        "run_id": run_id,
        "path": str(path),
        "first_context_task_ids": ["TASK-MAP"],
        "first_ready_task_ids": [],
    }, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
