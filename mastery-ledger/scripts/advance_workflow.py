#!/usr/bin/env python3
"""Advance study.yaml through allowed transitions after deterministic gates pass."""

from __future__ import annotations

import argparse
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from record_action import append_event
from validate_orchestration import validate_plan
from validate_study_pack import validate_workspace

ORDER = [
    "INTAKE", "SCOPED", "SOURCES_READY", "CORPUS_MAPPED", "TASKS_PLANNED",
    "EVIDENCE_SUBMITTED", "EVIDENCE_VERIFIED", "EVIDENCE_APPROVED",
    "STUDY_PACK_DRAFTED", "STUDY_PACK_VALIDATED", "LEARNING_ACTIVE",
]


def normalize(value: object) -> str:
    return str(value or "").strip().replace("-", "_").upper()


def atomic_yaml(path: Path, payload: dict) -> None:
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
    parser.add_argument("target_state")
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    root = args.course_root.resolve()
    path = root / "study.yaml"
    study = yaml.safe_load(path.read_text(encoding="utf-8"))
    current = normalize(study.get("workflow_state"))
    target = normalize(args.target_state)
    if target == "DRAFT_UNVERIFIED":
        pass
    elif current not in ORDER or target not in ORDER or ORDER.index(target) != ORDER.index(current) + 1:
        parser.error(f"Illegal workflow transition: {current or '<missing>'} -> {target}.")

    plan_path = root / ".work" / "orchestration" / "run-plan.yaml"
    plan = yaml.safe_load(plan_path.read_text(encoding="utf-8")) if plan_path.is_file() else {}
    tasks = plan.get("task_graph", []) if isinstance(plan, dict) else []

    if target == "SOURCES_READY":
        manifest = yaml.safe_load((root / "source-manifest.yaml").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or not manifest.get("sources"):
            parser.error("SOURCES_READY gate failed: source manifest is empty.")
    if target == "CORPUS_MAPPED":
        mapper_tasks = [task for task in tasks if isinstance(task, dict) and task.get("role") == "corpus-mapper"]
        if not mapper_tasks or any(task.get("status") not in {"submitted", "verified", "approved", "merged"} for task in mapper_tasks):
            parser.error("CORPUS_MAPPED gate failed: the corpus mapper has not submitted.")
    if target == "TASKS_PLANNED":
        errors, _, _ = validate_plan(plan, course_root=root)
        if errors or not plan.get("task_graph"):
            parser.error("TASKS_PLANNED gate failed: " + "; ".join(errors or ["task graph is empty"]))
    if target == "EVIDENCE_SUBMITTED":
        required = [task for task in tasks if isinstance(task, dict) and task.get("role") in {"research-worker", "source-extractor", "contradiction-reviewer"}]
        unfinished = [str(task.get("task_id")) for task in required if task.get("status") not in {"submitted", "verified", "approved", "merged"}]
        if not required or unfinished:
            parser.error("EVIDENCE_SUBMITTED gate failed: " + (", ".join(unfinished) if unfinished else "required research tasks are missing"))
    if target == "EVIDENCE_VERIFIED":
        verifiers = [task for task in tasks if isinstance(task, dict) and task.get("role") == "citation-verifier"]
        if len(verifiers) != 1 or verifiers[0].get("status") not in {"submitted", "verified", "approved", "merged"}:
            parser.error("EVIDENCE_VERIFIED gate failed: final citation verification is incomplete.")
        verifier_output = root / str(verifiers[0].get("output_path", ""))
        decision = yaml.safe_load(verifier_output.read_text(encoding="utf-8")) if verifier_output.is_file() else {}
        if not isinstance(decision, dict) or decision.get("decision") not in {"verified", "approved"}:
            parser.error("EVIDENCE_VERIFIED gate failed: final citation decision is not verified.")
    if target == "EVIDENCE_APPROVED":
        approved = root / "evidence" / "approved-claims.json"
        payload = yaml.safe_load(approved.read_text(encoding="utf-8")) if approved.is_file() else {}
        if not isinstance(payload, dict) or not payload.get("claims"):
            parser.error("EVIDENCE_APPROVED gate failed: no main-agent-approved claims exist.")
    if target == "STUDY_PACK_DRAFTED":
        errors, _ = validate_workspace(root, publication=False)
        if errors:
            parser.error("STUDY_PACK_DRAFTED gate failed: " + "; ".join(errors))
    if target in {"STUDY_PACK_VALIDATED", "LEARNING_ACTIVE"}:
        errors, _ = validate_workspace(root, publication=True)
        if errors:
            parser.error(f"{target} publication gate failed: " + "; ".join(errors))

    now = datetime.now(timezone.utc).isoformat()
    study["workflow_state"] = target
    study["updated_at"] = now
    history = study.setdefault("workflow_history", [])
    history.append({"from": current, "to": target, "at": now, "reason": args.reason})
    atomic_yaml(path, study)
    append_event(root, {
        "action": "workflow.advance", "actor": "main-agent", "status": "complete",
        "summary": f"Advanced workflow from {current} to {target}.",
        "artifacts": ["study.yaml"], "decision": target, "justification": args.reason,
    })
    print(yaml.safe_dump({"status": "complete", "from": current, "to": target}, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
