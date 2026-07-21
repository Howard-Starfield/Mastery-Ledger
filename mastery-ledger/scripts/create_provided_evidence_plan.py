#!/usr/bin/env python3
"""Compile the evidence-verification graph for a provided-material course."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from create_research_plan import scheduler_requirements, task
from plan_store import is_placeholder, load_active_plan, save_active_plan
from record_action import append_event
from source_registry import load_manifest, source_errors


PROVIDED_MODES = {"provided-material-only", "existing-library", "local-media"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    parser.add_argument("--authorized", action="store_true")
    parser.add_argument("--supersede-reason")
    args = parser.parse_args()
    if not args.authorized:
        parser.error("Explicit scope and worker authorization is required.")

    root = args.course_root.resolve()
    study = yaml.safe_load((root / "study.yaml").read_text(encoding="utf-8"))
    mode = str(study.get("mode", ""))
    if mode not in PROVIDED_MODES:
        parser.error("This compiler is only for provided-material, existing-library, or local-media studies.")
    state = str(study.get("workflow_state", "")).strip().replace("-", "_").upper()
    if state not in {"SOURCES_READY", "CORPUS_MAPPED"}:
        parser.error("Provided evidence planning requires workflow_state SOURCES_READY or CORPUS_MAPPED.")
    approval = study.get("learning_contract")
    if not isinstance(approval, dict) or approval.get("status") != "approved":
        parser.error("Provided evidence planning requires an approved canonical learning contract.")
    if int(approval.get("research_workers") or 0) != 0:
        parser.error("Provided-material evidence planning requires research_workers=0.")

    manifest = load_manifest(root)
    problems = source_errors(root, manifest, require_nonempty=True)
    if problems:
        parser.error("Source gate failed: " + "; ".join(problems))
    sources = [item for item in manifest["sources"] if isinstance(item, dict)]
    approved_limit = int(approval.get("source_limit") or 0)
    if len(sources) > approved_limit:
        parser.error(f"Ready source count {len(sources)} exceeds approved limit {approved_limit}")

    active_to_archive = None
    predecessor_run_id = None
    predecessor_relation = None
    active_path = root / ".work" / "orchestration" / "run-plan.yaml"
    if active_path.is_file():
        active = load_active_plan(root)
        if not is_placeholder(active):
            if not args.supersede_reason:
                parser.error("An active run already exists; repair it or provide --supersede-reason explicitly.")
            active_to_archive = active
            predecessor_run_id = active.get("run_id")
            predecessor_relation = "supersedes"

    source_ids = [str(item["source_id"]) for item in sources]
    summary = str(approval.get("goal") or approval.get("summary") or study.get("learner_goal") or "Approved provided-source scope")
    accepted_branches = [str(item) for item in approval.get("accepted_branches", [])]
    excluded = [str(item) for item in approval.get("excluded", [])]
    run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"
    extractors = [
        task(
            run_id,
            f"TASK-EXTRACT-{source_id}",
            "source-extractor",
            [],
            scope_included=accepted_branches or [summary],
            scope_excluded=excluded,
            input_source_ids=[source_id],
            source_limit=1,
        )
        for source_id in source_ids
    ]
    extractor_ids = [item["task_id"] for item in extractors]
    citation = task(
        run_id,
        "TASK-CITATIONS",
        "citation-verifier",
        extractor_ids,
        "reviews",
        "citation-review-v1",
        scope_included=accepted_branches or [summary],
        scope_excluded=excluded,
        input_source_ids=source_ids,
        source_limit=len(source_ids),
    )
    tasks = [*extractors, citation]
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "provided-evidence-plan-v1",
        "run_id": run_id,
        "study_id": study.get("study_id"),
        "goal": summary,
        "mode": mode,
        "course_target": study.get("workflow_target", "LEARNING_ACTIVE"),
        "authorization": {
            "status": "approved",
            "approved_at": approval.get("approved_at") or now,
            "scope": summary,
            "source_limit": approved_limit,
            "research_workers": 0,
        },
        "predecessor_run_id": predecessor_run_id,
        "predecessor_relation": predecessor_relation,
        "supersession_reason": args.supersede_reason,
        "publication_intent": True,
        "plan_origin": {"kind": "generated", "compiler": "create_provided_evidence_plan.py"},
        "execution_requirements": scheduler_requirements(),
        "workflow_state": "tasks_planned",
        "task_graph": tasks,
        "created_at": now,
        "updated_at": now,
    }
    if active_to_archive is not None:
        save_active_plan(root, active_to_archive)
    path = save_active_plan(root, payload)
    append_event(
        root,
        {
            "action": "evidence.plan_compiled",
            "actor": "main-agent",
            "status": "complete",
            "summary": f"Compiled {len(extractors)} source extraction task(s) and ordered independent citation verification.",
            "artifacts": [".work/orchestration/run-plan.yaml"],
            "decision": "approved",
            "justification": "Provided-source courses use the fast extraction and final evidence-validation path without open-web research.",
        },
    )
    print(yaml.safe_dump({
        "status": "complete",
        "run_id": run_id,
        "path": str(path),
        "first_context_task_ids": extractor_ids,
        "first_ready_task_ids": [],
    }, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
