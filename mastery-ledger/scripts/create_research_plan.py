#!/usr/bin/env python3
"""Compile the mandatory researched-course task graph from approved inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from course_paths import SOURCE_MANIFEST, relative_text
from record_action import append_event
from plan_store import is_placeholder, load_active_plan, save_active_plan
from source_registry import load_manifest, source_errors


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
    input_source_ids: list[str] | None = None,
    scope_excluded: list[str] | None = None,
    source_limit: int | None = None,
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
        "scope_excluded": scope_excluded or [],
        "concept_ids": [],
        "input_source_ids": input_source_ids or [],
        "input_artifacts": input_artifacts or [],
        "source_limit": source_limit if source_limit is not None else 5,
        "dependencies": dependencies,
        "task_work_dir": task_root,
        "brief_path": f"{task_root}/task-brief.json",
        "context_path": f"{task_root}/context-manifest.json",
        "dispatch_path": f"{task_root}/dispatch-message.txt",
        "event_path": f"{task_root}/events.jsonl",
        "output_path": f"{task_root}/submission.json",
        "completion_path": f"{task_root}/completion.json",
        "completion_template_path": f"{task_root}/completion-template.json",
        "required_schema": schema,
        "reviewer_role": "main-agent",
        "acceptance_criteria": [*profile["best_practices"], "Use assigned scope only."],
        "context_status": "pending",
        "attempt_count": 0,
        "max_attempts": 2,
        "status": "planned",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    parser.add_argument("--research-workers", type=int, default=3)
    parser.add_argument("--authorized", action="store_true")
    parser.add_argument("--supersede-reason")
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
    if str(study.get("workflow_state", "")).strip().replace("-", "_").upper() != "SOURCES_READY":
        parser.error("Research planning requires workflow_state SOURCES_READY.")
    approval = study.get("learning_contract")
    if not isinstance(approval, dict) or approval.get("status") != "approved":
        parser.error("Research planning requires an approved canonical learning contract.")
    approved_workers = int(approval.get("research_workers") or 0)
    if args.research_workers != approved_workers:
        parser.error(f"--research-workers must match the approved count: {approved_workers}")
    approved_source_limit = int(approval.get("source_limit") or 0)
    manifest = load_manifest(root)
    problems = source_errors(root, manifest, require_nonempty=True)
    if problems:
        parser.error("Source gate failed: " + "; ".join(problems))
    sources = [item for item in manifest["sources"] if isinstance(item, dict)]
    if len(sources) > approved_source_limit:
        parser.error(f"Ready source count {len(sources)} exceeds approved limit {approved_source_limit}")
    active_path = root / ".work" / "orchestration" / "run-plan.yaml"
    predecessor_run_id = None
    predecessor_relation = None
    active_to_archive = None
    if active_path.is_file():
        active = load_active_plan(root)
        if not is_placeholder(active):
            active_to_archive = active
            source_discovery_finished = (
                active.get("schema_version") == "source-discovery-plan-v1"
                and bool(active.get("task_graph"))
                and all(
                    isinstance(item, dict) and item.get("status") in {"submitted", "verified", "approved", "merged"}
                    for item in active.get("task_graph", [])
                )
            )
            if not source_discovery_finished and not args.supersede_reason:
                parser.error("An active run already exists; repair it or provide --supersede-reason explicitly.")
            predecessor_run_id = active.get("run_id")
            predecessor_relation = "source_discovery" if source_discovery_finished else "supersedes"
    source_ids = [str(item["source_id"]) for item in sources]
    scope_summary = str(approval.get("goal") or approval.get("summary") or study.get("learner_goal") or "Approved course scope")
    accepted_branches = [str(item) for item in approval.get("accepted_branches", [])]
    excluded = [str(item) for item in approval.get("excluded", [])]
    run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"
    mapper = task(
        run_id,
        "TASK-MAP",
        "corpus-mapper",
        [],
        schema="corpus-map-v1",
        scope_included=accepted_branches or [scope_summary],
        scope_excluded=excluded,
        input_source_ids=source_ids,
        input_artifacts=[relative_text(SOURCE_MANIFEST)],
        source_limit=len(source_ids),
    )
    extractors = [task(
        run_id,
        f"TASK-EXTRACT-{source_id}",
        "source-extractor",
        [],
        scope_included=accepted_branches or [scope_summary],
        scope_excluded=excluded,
        input_source_ids=[source_id],
        source_limit=1,
    ) for source_id in source_ids]
    extractor_ids = [item["task_id"] for item in extractors]
    research = [task(
        run_id,
        f"TASK-RESEARCH-{index:02d}",
        "research-worker",
        ["TASK-MAP"],
        scope_excluded=excluded,
        source_limit=approved_source_limit,
    ) for index in range(1, args.research_workers + 1)]
    research_ids = [item["task_id"] for item in research]
    contradiction = task(
        run_id,
        "TASK-CONTRADICTIONS",
        "contradiction-reviewer",
        [*extractor_ids, *research_ids],
        schema="contradiction-review-v1",
        scope_included=accepted_branches or [scope_summary],
        scope_excluded=excluded,
    )
    citation = task(
        run_id,
        "TASK-CITATIONS",
        "citation-verifier",
        ["TASK-CONTRADICTIONS", *extractor_ids, *research_ids],
        "reviews",
        "citation-review-v1",
        scope_included=accepted_branches or [scope_summary],
        scope_excluded=excluded,
        input_source_ids=source_ids,
        source_limit=len(source_ids),
    )
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "research-run-plan-v1",
        "run_id": run_id,
        "study_id": study.get("study_id"),
        "goal": scope_summary,
        "course_target": study.get("workflow_target", "LEARNING_ACTIVE"),
        "mode": mode,
        "authorization": {
            "status": "approved",
            "approved_at": approval.get("approved_at") or now,
            "scope": scope_summary,
            "source_limit": approved_source_limit,
            "research_workers": approved_workers,
        },
        "learning_contract": {
            "goal": scope_summary,
            "assumed_level": approval.get("assumed_level"),
            "accepted_branches": accepted_branches,
            "excluded": excluded,
            "source_limit": approved_source_limit,
            "research_workers": approved_workers,
        },
        "predecessor_run_id": predecessor_run_id,
        "predecessor_relation": predecessor_relation,
        "supersession_reason": args.supersede_reason,
        "publication_intent": True,
        "plan_origin": {"kind": "generated", "compiler": "create_research_plan.py"},
        "execution_requirements": {
            "independent_workers": True,
            "parallelism_required": False,
            "parallelism_preferred": args.research_workers > 1,
        },
        "workflow_state": "tasks_planned",
        "task_graph": [mapper, *extractors, *research, contradiction, citation],
        "created_at": now,
        "updated_at": now,
    }
    if active_to_archive is not None:
        save_active_plan(root, active_to_archive)
    path = save_active_plan(root, payload)
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
        "first_context_task_ids": ["TASK-MAP", *extractor_ids],
        "first_ready_task_ids": [],
    }, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
