#!/usr/bin/env python3
"""Validate a worker completion, advance its task, or issue a bounded same-task repair."""

from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from advance_workflow import advance_state
from compile_worker_context import atomic_json, atomic_text
from merge_worker_events import merge_events
from plan_store import load_active_plan, save_active_plan
from record_action import append_event
from validation_receipts import write_validation_receipt
from validate_orchestration import context_required_task_ids, validate_plan


def _task(plan: dict[str, Any], task_id: str) -> dict[str, Any]:
    for item in plan.get("task_graph", []):
        if isinstance(item, dict) and item.get("task_id") == task_id:
            return item
    raise ValueError(f"Unknown task ID: {task_id}")


def _candidate_errors(root: Path, plan: dict[str, Any], task_id: str) -> list[str]:
    candidate = copy.deepcopy(plan)
    task = _task(candidate, task_id)
    task["status"] = "submitted"
    errors, _, _ = validate_plan(candidate, course_root=root)
    return errors


def _completion_status(root: Path, task: dict[str, Any]) -> str:
    path = root / str(task.get("completion_path") or "")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "malformed"
    return str(payload.get("status") or "malformed") if isinstance(payload, dict) else "malformed"


def route(root: Path, task_id: str) -> dict[str, Any]:
    root = root.resolve()
    plan = load_active_plan(root)
    task = _task(plan, task_id)
    if task.get("context_status") != "compiled":
        raise ValueError(f"Task context is not compiled: {task_id}")
    accepted_task_states = {"submitted", "verified", "approved", "merged"}
    if task.get("status") in {"blocked", "rejected", "superseded"}:
        raise ValueError(f"Task is terminal and cannot accept another completion: {task_id}")
    lease = task.get("worker_runtime")
    if isinstance(lease, dict):
        lease_state = str(lease.get("lease_state") or "idle")
        managed = bool(lease.get("agent_id")) or lease_state != "idle"
        allowed_lease_states = {"returned"}
        if task.get("status") in accepted_task_states:
            allowed_lease_states.add("closed")
        if managed and lease_state not in allowed_lease_states:
            raise ValueError(
                f"Managed worker must be marked returned before completion routing: {task_id} "
                f"(lease_state={lease_state})"
            )
    if task.get("status") in accepted_task_states:
        errors, warnings, ready = validate_plan(plan, course_root=root)
        if errors:
            return {
                "status": "invalidated",
                "idempotent": True,
                "task_id": task_id,
                "errors": errors,
                "warnings": warnings,
                "context_required_task_ids": [],
                "ready_task_ids": [],
            }
        merged = merge_events(root, task_id)
        receipt = write_validation_receipt(root, plan, task)
        return {
            "status": "accepted",
            "idempotent": True,
            "task_id": task_id,
            "errors": errors,
            "warnings": warnings,
            "context_required_task_ids": context_required_task_ids(plan) if not errors else [],
            "ready_task_ids": ready,
            "event_merge": merged,
            "validation_receipt": receipt.relative_to(root).as_posix(),
        }

    errors = _candidate_errors(root, plan, task_id)
    completion_status = _completion_status(root, task)
    if not errors and completion_status in {"failed", "blocked"}:
        errors = [f"{task_id} completion reported {completion_status}; resolve the blocker in the same assigned task."]
    if errors:
        task["attempt_count"] = int(task.get("attempt_count", 0)) + 1
        maximum = int(task.get("max_attempts", 2))
        task_root = root / str(task["task_work_dir"])
        error_path = task_root / "repair-errors.json"
        repair_path = task_root / "repair-dispatch-message.txt"
        atomic_json(error_path, {
            "schema_version": "worker-repair-v1",
            "run_id": task.get("run_id"),
            "task_id": task_id,
            "attempt_count": task["attempt_count"],
            "max_attempts": maximum,
            "errors": errors,
        })
        exhausted = task["attempt_count"] >= maximum
        task["status"] = "blocked" if exhausted else "changes_required"
        task["repair_errors_path"] = error_path.relative_to(root).as_posix()
        if not exhausted:
            message = (
                f"Repair the existing Mastery Ledger task {task_id} in run {task.get('run_id')}.\n"
                f"Read the field-level errors at:\n{error_path.resolve()}\n\n"
                f"Copy the exact completion template at:\n{(root / str(task['completion_template_path'])).resolve()}\n"
                f"to:\n{(root / str(task['completion_path'])).resolve()}\n"
                "Preserve the accepted submission and event shard unless an error explicitly names them. "
                "Do not create a new run, rename fields, expand scope, or edit canonical course artifacts.\n"
            )
            atomic_text(repair_path, message)
            task["repair_dispatch_path"] = repair_path.relative_to(root).as_posix()
        plan["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_active_plan(root, plan)
        append_event(root, {
            "action": "worker.completion_repair_required",
            "actor": "completion-router",
            "status": "retry_exhausted" if exhausted else "changes_required",
            "summary": f"Completion routing found {len(errors)} observable contract error(s) for {task_id}.",
            "artifacts": [task["repair_errors_path"]] + ([] if exhausted else [task["repair_dispatch_path"]]),
            "decision": "draft_unverified" if exhausted else "same_task_repair",
            "justification": "The returned output, event, or completion envelope did not pass the deterministic task contract.",
            "run_id": task.get("run_id"),
            "task_id": task_id,
        })
        draft_path = None
        if exhausted:
            draft_path = root / ".work" / "drafts" / f"retry-exhausted-{task_id}.md"
            atomic_text(
                draft_path,
                "\n".join([
                    f"# Unverified task draft: {task_id}",
                    "",
                    f"Run: `{task.get('run_id')}`",
                    f"Provisional output: `{task.get('output_path')}`",
                    f"Completion errors: `{task.get('repair_errors_path')}`",
                    "",
                    "This task exhausted its bounded completion-contract repairs. Its provisional output remains under `.work/` and is not approved evidence.",
                    "",
                ]),
            )
            advance_state(
                root,
                "DRAFT_UNVERIFIED",
                reason=f"{task_id} exhausted its bounded same-task completion repairs.",
            )
        return {
            "status": "retry_exhausted" if exhausted else "changes_required",
            "run_id": task.get("run_id"),
            "task_id": task_id,
            "attempt_count": task["attempt_count"],
            "max_attempts": maximum,
            "errors": errors,
            "repair_dispatch_path": None if exhausted else str(repair_path),
            "new_run_allowed": False,
            "publication_status": "DRAFT_UNVERIFIED" if exhausted else None,
            "draft_path": str(draft_path) if draft_path is not None else None,
        }

    task["status"] = "submitted"
    task["accepted_at"] = datetime.now(timezone.utc).isoformat()
    plan["updated_at"] = task["accepted_at"]
    save_active_plan(root, plan)
    merged = merge_events(root, task_id)
    receipt = write_validation_receipt(root, plan, task)
    append_event(root, {
        "action": "worker.completion_accepted",
        "actor": "completion-router",
        "status": "complete",
        "summary": f"Accepted the contract-valid completion for {task_id}.",
        "artifacts": [
            str(task.get("output_path")),
            str(task.get("completion_path")),
            receipt.relative_to(root).as_posix(),
        ],
        "decision": "accepted",
        "justification": "The output, event shard, identity, acknowledgements, and completion envelope passed validation.",
        "run_id": task.get("run_id"),
        "task_id": task_id,
        "validation_receipt": receipt.relative_to(root).as_posix(),
    })
    plan = load_active_plan(root)
    validation_errors, warnings, ready = validate_plan(plan, course_root=root)
    return {
        "status": "accepted",
        "idempotent": False,
        "run_id": task.get("run_id"),
        "task_id": task_id,
        "event_merge": merged,
        "errors": validation_errors,
        "warnings": warnings,
        "context_required_task_ids": context_required_task_ids(plan) if not validation_errors else [],
        "ready_task_ids": ready,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    parser.add_argument("task_id")
    args = parser.parse_args()
    try:
        payload = route(args.course_root, args.task_id)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] in {"accepted", "changes_required"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
