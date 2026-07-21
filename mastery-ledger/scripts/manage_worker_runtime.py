#!/usr/bin/env python3
"""Manage capacity-bounded worker leases for the active Mastery Ledger run."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from advance_workflow import advance_state
from plan_store import load_active_plan, save_active_plan
from record_action import append_event
from validate_orchestration import context_required_task_ids, validate_plan


HARD_AGENT_LIMIT = 4
NORMAL_ACTIVE_LIMIT = 3
PROBE_AFTER_SILENT_POLLS = 3
STALL_AFTER_SILENT_POLLS = 5
MAX_STALL_RESTARTS = 1
ACTIVE_LEASE_STATES = {"reserved", "active", "returned", "repairing", "close_required"}
TERMINAL_TASK_STATES = {"submitted", "verified", "approved", "merged", "blocked", "rejected", "superseded"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def task_by_id(plan: dict[str, Any], task_id: str) -> dict[str, Any]:
    for task in plan.get("task_graph", []):
        if isinstance(task, dict) and task.get("task_id") == task_id:
            return task
    raise ValueError(f"Unknown task ID: {task_id}")


def runtime(task: dict[str, Any]) -> dict[str, Any]:
    value = task.get("worker_runtime")
    if not isinstance(value, dict):
        value = {
            "lease_state": "idle",
            "agent_id": None,
            "reservation_id": None,
            "silent_polls": 0,
            "stall_restart_count": 0,
            "agent_history": [],
        }
        task["worker_runtime"] = value
    value.setdefault("silent_polls", 0)
    value.setdefault("stall_restart_count", 0)
    value.setdefault("agent_history", [])
    return value


def active_tasks(plan: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for task in plan.get("task_graph", []):
        if not isinstance(task, dict):
            continue
        state = runtime(task).get("lease_state")
        if state in ACTIVE_LEASE_STATES:
            result.append(task)
    return result


def scheduler_status(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    errors, warnings, ready = validate_plan(plan, course_root=root)
    active = active_tasks(plan)
    active_ids = [str(item.get("task_id")) for item in active]
    close_required = [
        str(item.get("task_id"))
        for item in active
        if runtime(item).get("lease_state") == "close_required"
        or item.get("status") in TERMINAL_TASK_STATES
    ]
    probe_required = [
        str(item.get("task_id"))
        for item in active
        if runtime(item).get("lease_state") == "active"
        and int(runtime(item).get("silent_polls", 0)) >= PROBE_AFTER_SILENT_POLLS
        and int(runtime(item).get("silent_polls", 0)) < STALL_AFTER_SILENT_POLLS
    ]
    stalled = [
        str(item.get("task_id"))
        for item in active
        if int(runtime(item).get("silent_polls", 0)) >= STALL_AFTER_SILENT_POLLS
    ]
    available = max(0, NORMAL_ACTIVE_LIMIT - len(active))
    return {
        "schema_version": "worker-runtime-status-v1",
        "status": "blocked" if errors else "ready",
        "run_id": plan.get("run_id"),
        "hard_agent_limit": HARD_AGENT_LIMIT,
        "normal_active_limit": NORMAL_ACTIVE_LIMIT,
        "reserve_slots": HARD_AGENT_LIMIT - NORMAL_ACTIVE_LIMIT,
        "active_task_ids": active_ids,
        "active_count": len(active),
        "available_normal_slots": available,
        "context_required_task_ids": context_required_task_ids(plan) if not errors else [],
        "ready_task_ids": ready if not errors else [],
        "dispatch_task_ids": ready[:available] if not errors and not close_required else [],
        "probe_required_task_ids": probe_required,
        "stalled_task_ids": stalled,
        "close_required_task_ids": close_required,
        "errors": errors,
        "warnings": warnings,
    }


def reserve(root: Path, task_id: str) -> dict[str, Any]:
    plan = load_active_plan(root)
    status = scheduler_status(root, plan)
    if status["errors"]:
        raise ValueError("Active run plan is invalid: " + "; ".join(status["errors"]))
    if status["close_required_task_ids"]:
        raise ValueError("Close returned or terminal workers before reserving another slot.")
    if task_id not in status["dispatch_task_ids"]:
        raise ValueError(f"Task is not dispatchable within the normal three-worker limit: {task_id}")
    task = task_by_id(plan, task_id)
    lease = runtime(task)
    reservation_id = f"LEASE-{uuid.uuid4().hex[:10].upper()}"
    timestamp = now()
    task["status"] = "in_progress"
    lease.update({
        "lease_state": "reserved",
        "reservation_id": reservation_id,
        "agent_id": None,
        "reserved_at": timestamp,
        "last_progress_at": timestamp,
        "silent_polls": 0,
        "stage": "awaiting_spawn",
    })
    plan["updated_at"] = timestamp
    save_active_plan(root, plan)
    append_event(root, {
        "action": "worker.slot_reserved", "actor": "main-agent", "status": "complete",
        "summary": f"Reserved one worker slot for {task_id} before spawning.",
        "artifacts": [".work/orchestration/run-plan.yaml"], "decision": reservation_id,
        "justification": "Sequential reservation prevents duplicate and over-capacity dispatch.",
        "run_id": plan.get("run_id"), "task_id": task_id,
    })
    return {
        "status": "reserved", "run_id": plan.get("run_id"), "task_id": task_id,
        "reservation_id": reservation_id, "dispatch_path": str(root / str(task.get("dispatch_path"))),
    }


def attach(root: Path, task_id: str, reservation_id: str, agent_id: str) -> dict[str, Any]:
    plan = load_active_plan(root)
    task = task_by_id(plan, task_id)
    lease = runtime(task)
    if lease.get("lease_state") != "reserved" or lease.get("reservation_id") != reservation_id:
        raise ValueError("Reservation does not match the task's active worker lease.")
    if not agent_id.strip():
        raise ValueError("agent_id is required")
    timestamp = now()
    lease.update({
        "lease_state": "active", "agent_id": agent_id.strip(), "attached_at": timestamp,
        "last_progress_at": timestamp, "silent_polls": 0, "stage": "dispatched",
    })
    lease["agent_history"].append({"agent_id": agent_id.strip(), "attached_at": timestamp})
    plan["updated_at"] = timestamp
    save_active_plan(root, plan)
    return {"status": "attached", "task_id": task_id, "agent_id": agent_id.strip()}


def release_failed_spawn(root: Path, task_id: str, reservation_id: str, reason: str) -> dict[str, Any]:
    plan = load_active_plan(root)
    task = task_by_id(plan, task_id)
    lease = runtime(task)
    if lease.get("lease_state") != "reserved" or lease.get("reservation_id") != reservation_id:
        raise ValueError("Reservation does not match the task's active worker lease.")
    timestamp = now()
    task["status"] = "planned"
    lease.update({
        "lease_state": "idle", "reservation_id": None, "agent_id": None,
        "released_at": timestamp, "last_release_reason": reason, "stage": "queued",
    })
    lease["capacity_failure_count"] = int(lease.get("capacity_failure_count", 0)) + 1
    plan["updated_at"] = timestamp
    save_active_plan(root, plan)
    append_event(root, {
        "action": "worker.spawn_released", "actor": "main-agent", "status": "deferred",
        "summary": f"Released the unfilled reservation for {task_id}.",
        "artifacts": [".work/orchestration/run-plan.yaml"], "decision": "queued",
        "justification": reason, "run_id": plan.get("run_id"), "task_id": task_id,
    })
    return {"status": "queued", "task_id": task_id, "publication_status_changed": False}


def progress(root: Path, task_id: str, stage: str) -> dict[str, Any]:
    plan = load_active_plan(root)
    task = task_by_id(plan, task_id)
    lease = runtime(task)
    if lease.get("lease_state") not in {"active", "repairing"}:
        raise ValueError("Progress can be recorded only for an active or repairing worker.")
    timestamp = now()
    lease.update({"last_progress_at": timestamp, "silent_polls": 0, "stage": stage.strip() or "working"})
    plan["updated_at"] = timestamp
    save_active_plan(root, plan)
    return {"status": "progress_recorded", "task_id": task_id, "stage": lease["stage"]}


def silent_poll(root: Path, task_id: str) -> dict[str, Any]:
    plan = load_active_plan(root)
    task = task_by_id(plan, task_id)
    lease = runtime(task)
    if lease.get("lease_state") not in {"active", "repairing"}:
        raise ValueError("Silence can be recorded only for an active or repairing worker.")
    lease["silent_polls"] = int(lease.get("silent_polls", 0)) + 1
    count = lease["silent_polls"]
    if count >= STALL_AFTER_SILENT_POLLS:
        lease["lease_state"] = "close_required"
        decision = "stall_suspected"
    elif count >= PROBE_AFTER_SILENT_POLLS:
        decision = "probe_required"
    else:
        decision = "wait"
    plan["updated_at"] = now()
    save_active_plan(root, plan)
    return {
        "status": decision, "task_id": task_id, "silent_polls": count,
        "agent_id": lease.get("agent_id"), "close_required": decision == "stall_suspected",
    }


def returned(root: Path, task_id: str) -> dict[str, Any]:
    plan = load_active_plan(root)
    task = task_by_id(plan, task_id)
    lease = runtime(task)
    if lease.get("lease_state") not in {"active", "repairing"}:
        raise ValueError("Only an active worker may be marked returned.")
    timestamp = now()
    lease.update({"lease_state": "returned", "returned_at": timestamp, "last_progress_at": timestamp, "silent_polls": 0, "stage": "routing"})
    plan["updated_at"] = timestamp
    save_active_plan(root, plan)
    return {"status": "returned", "task_id": task_id, "next_action": "route_worker_completion.py"}


def repair(root: Path, task_id: str) -> dict[str, Any]:
    plan = load_active_plan(root)
    task = task_by_id(plan, task_id)
    lease = runtime(task)
    if task.get("status") != "changes_required" or lease.get("lease_state") != "returned":
        raise ValueError("Same-agent repair requires changes_required and a returned live worker.")
    timestamp = now()
    lease.update({"lease_state": "repairing", "last_progress_at": timestamp, "silent_polls": 0, "stage": "repairing"})
    plan["updated_at"] = timestamp
    save_active_plan(root, plan)
    return {
        "status": "repairing", "task_id": task_id, "agent_id": lease.get("agent_id"),
        "repair_dispatch_path": str(root / str(task.get("repair_dispatch_path"))),
    }


def confirm_close(root: Path, task_id: str, reason: str) -> dict[str, Any]:
    plan = load_active_plan(root)
    task = task_by_id(plan, task_id)
    lease = runtime(task)
    prior_state = str(lease.get("lease_state") or "")
    if prior_state not in ACTIVE_LEASE_STATES:
        raise ValueError("Task has no active worker lease to close.")
    timestamp = now()
    stalled = prior_state == "close_required" and task.get("status") not in TERMINAL_TASK_STATES
    agent_id = lease.get("agent_id")
    if lease.get("agent_history"):
        lease["agent_history"][-1]["closed_at"] = timestamp
        lease["agent_history"][-1]["close_reason"] = reason
    lease.update({
        "lease_state": "closed", "agent_id": None, "reservation_id": None,
        "closed_at": timestamp, "close_reason": reason, "silent_polls": 0,
    })
    retry_allowed = False
    exhausted = False
    if stalled:
        restarts = int(lease.get("stall_restart_count", 0))
        if restarts < MAX_STALL_RESTARTS:
            lease["stall_restart_count"] = restarts + 1
            lease["lease_state"] = "idle"
            lease["stage"] = "queued_after_stall"
            task["status"] = "planned"
            retry_allowed = True
        else:
            task["status"] = "blocked"
            lease["stage"] = "stall_retry_exhausted"
            exhausted = True
    plan["updated_at"] = timestamp
    save_active_plan(root, plan)
    if exhausted:
        advance_state(root, "DRAFT_UNVERIFIED", reason=f"{task_id} stalled twice and exhausted its one fresh-worker restart.")
    append_event(root, {
        "action": "worker.agent_closed", "actor": "main-agent", "status": "complete",
        "summary": f"Confirmed closure of the worker for {task_id}.",
        "artifacts": [".work/orchestration/run-plan.yaml"],
        "decision": "queued_retry" if retry_allowed else "draft_unverified" if exhausted else "closed",
        "justification": reason, "run_id": plan.get("run_id"), "task_id": task_id,
    })
    return {
        "status": "queued_retry" if retry_allowed else "retry_exhausted" if exhausted else "closed",
        "task_id": task_id, "closed_agent_id": agent_id, "restart_allowed": retry_allowed,
        "publication_status": "DRAFT_UNVERIFIED" if exhausted else None,
    }


def print_payload(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status",):
        command = sub.add_parser(name)
        command.add_argument("course_root", type=Path)
    command = sub.add_parser("reserve")
    command.add_argument("course_root", type=Path)
    command.add_argument("task_id")
    command = sub.add_parser("attach")
    command.add_argument("course_root", type=Path)
    command.add_argument("task_id")
    command.add_argument("--reservation-id", required=True)
    command.add_argument("--agent-id", required=True)
    command = sub.add_parser("release")
    command.add_argument("course_root", type=Path)
    command.add_argument("task_id")
    command.add_argument("--reservation-id", required=True)
    command.add_argument("--reason", required=True)
    for name in ("progress",):
        command = sub.add_parser(name)
        command.add_argument("course_root", type=Path)
        command.add_argument("task_id")
        command.add_argument("--stage", required=True)
    for name in ("silent-poll", "returned", "repair"):
        command = sub.add_parser(name)
        command.add_argument("course_root", type=Path)
        command.add_argument("task_id")
    command = sub.add_parser("confirm-close")
    command.add_argument("course_root", type=Path)
    command.add_argument("task_id")
    command.add_argument("--reason", required=True)
    args = parser.parse_args()
    root = args.course_root.resolve()
    try:
        if args.command == "status":
            payload = scheduler_status(root, load_active_plan(root))
        elif args.command == "reserve":
            payload = reserve(root, args.task_id)
        elif args.command == "attach":
            payload = attach(root, args.task_id, args.reservation_id, args.agent_id)
        elif args.command == "release":
            payload = release_failed_spawn(root, args.task_id, args.reservation_id, args.reason)
        elif args.command == "progress":
            payload = progress(root, args.task_id, args.stage)
        elif args.command == "silent-poll":
            payload = silent_poll(root, args.task_id)
        elif args.command == "returned":
            payload = returned(root, args.task_id)
        elif args.command == "repair":
            payload = repair(root, args.task_id)
        else:
            payload = confirm_close(root, args.task_id, args.reason)
    except ValueError as error:
        parser.error(str(error))
    print_payload(payload)
    return 3 if payload.get("status") == "retry_exhausted" else 0


if __name__ == "__main__":
    raise SystemExit(main())
