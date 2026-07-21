#!/usr/bin/env python3
"""Validate and idempotently merge one accepted worker event shard into the course audit."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

from compile_worker_context import atomic_json, sha256_file
from course_paths import EVENT_LOG
from validate_orchestration import SUBMITTED_STATES, _safe_course_path, _worker_event_errors, validate_plan


def merge_events(root: Path, task_id: str) -> dict[str, object]:
    root = root.resolve()
    plan_path = root / ".work" / "orchestration" / "run-plan.yaml"
    try:
        plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ValueError(f"Cannot read run plan: {error}") from error
    tasks = {
        str(item.get("task_id")): item
        for item in (plan or {}).get("task_graph", [])
        if isinstance(item, dict) and item.get("task_id")
    }
    task = tasks.get(task_id)
    if task is None:
        raise ValueError(f"Unknown task ID: {task_id}")
    if task.get("status") not in SUBMITTED_STATES:
        raise ValueError(f"Task must be submitted before event merge: {task_id}")
    plan_errors, _, _ = validate_plan(plan, course_root=root)
    if plan_errors:
        raise ValueError("Run plan or completion is invalid: " + "; ".join(plan_errors))
    event_path = _safe_course_path(root, task.get("event_path"))
    if event_path is None or not event_path.is_file() or event_path.is_symlink():
        raise ValueError(f"Worker event shard is missing or unsafe: {task_id}")
    errors = _worker_event_errors(task_id, task, event_path)
    if errors:
        raise ValueError("; ".join(errors))
    completion_path = _safe_course_path(root, task.get("completion_path"))
    if completion_path is None or not completion_path.is_file() or completion_path.is_symlink():
        raise ValueError(f"Worker completion is missing or unsafe: {task_id}")

    receipt_path = event_path.parent / "events-merge.json"
    shard_hash = sha256_file(event_path)
    if receipt_path.is_file() and not receipt_path.is_symlink():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(f"Existing event merge receipt is unreadable: {error}") from error
        if receipt.get("source_sha256") != shard_hash:
            raise ValueError("Worker event shard changed after it was merged.")
        return {
            "status": "complete",
            "task_id": task_id,
            "merged_event_count": int(receipt.get("merged_event_count", 0)),
            "duplicate_event_count": int(receipt.get("duplicate_event_count", 0)),
            "receipt": str(receipt_path),
            "idempotent": True,
        }

    durable = root / EVENT_LOG
    durable.parent.mkdir(parents=True, exist_ok=True)
    if durable.is_symlink():
        raise ValueError("Durable event log cannot be a symbolic link.")
    existing_events: dict[str, dict[str, object]] = {}
    if durable.is_file():
        for line in durable.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                raise ValueError("Durable event log contains invalid JSON and must be repaired before merge.")
            if isinstance(item, dict) and item.get("event_id"):
                existing_events[str(item["event_id"])] = item

    events = [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines()]
    accepted: list[dict[str, object]] = []
    duplicate_count = 0
    for item in events:
        event_id = str(item["event_id"])
        existing = existing_events.get(event_id)
        if existing is None:
            accepted.append(item)
            continue
        if json.dumps(existing, ensure_ascii=False, sort_keys=True) != json.dumps(item, ensure_ascii=False, sort_keys=True):
            raise ValueError(f"Durable event ID collision has different content: {event_id}")
        duplicate_count += 1
    with durable.open("a", encoding="utf-8", newline="\n") as handle:
        for item in accepted:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    receipt = {
        "schema_version": "event-merge-receipt-v1",
        "run_id": task.get("run_id"),
        "task_id": task_id,
        "event_path": task.get("event_path"),
        "source_sha256": shard_hash,
        "merged_event_ids": [str(item["event_id"]) for item in accepted],
        "merged_event_count": len(accepted),
        "duplicate_event_count": duplicate_count,
        "merged_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(receipt_path, receipt)
    return {
        "status": "complete",
        "task_id": task_id,
        "merged_event_count": len(accepted),
        "duplicate_event_count": duplicate_count,
        "receipt": str(receipt_path),
        "idempotent": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    parser.add_argument("task_id")
    args = parser.parse_args()
    try:
        payload = merge_events(args.course_root, args.task_id)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
