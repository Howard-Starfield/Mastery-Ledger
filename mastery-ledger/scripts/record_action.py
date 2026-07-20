#!/usr/bin/env python3
"""Append one observable action event to a course log."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


PROHIBITED_FIELDS = {
    "authorization",
    "authorization_header",
    "chain_of_thought",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "hidden_reasoning",
    "model_context",
    "password",
    "prompt",
    "reasoning",
    "secret",
    "secrets",
    "token",
}


def _validated_event(event: dict[str, object]) -> dict[str, object]:
    forbidden = sorted(PROHIBITED_FIELDS & set(event))
    if forbidden:
        raise ValueError("Event contains prohibited private fields: " + ", ".join(forbidden))
    for field in ("action", "actor", "status", "summary"):
        if not isinstance(event.get(field), str) or not str(event[field]).strip():
            raise ValueError(f"Event field is required: {field}")
    if len(str(event["summary"])) > 1_000:
        raise ValueError("Event summary must be 1,000 characters or fewer.")
    if event.get("justification") is not None and len(str(event["justification"])) > 1_000:
        raise ValueError("Event justification must be 1,000 characters or fewer.")
    return event


def append_event(course_root: Path, event: dict[str, object]) -> Path:
    root = course_root.resolve()
    path = root / "logs" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.resolve(strict=False).parent != (root / "logs").resolve():
        raise ValueError("Event log must remain inside COURSE_ROOT/logs.")
    event = _validated_event(event)
    payload = {
        **event,
        "event_id": f"EVT-{uuid.uuid4().hex[:16].upper()}",
        "schema_version": "action-event-v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    parser.add_argument("action")
    parser.add_argument("summary")
    parser.add_argument("--actor", default="main-agent")
    parser.add_argument("--status", default="complete")
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--decision")
    parser.add_argument("--justification")
    parser.add_argument("--run-id")
    parser.add_argument("--task-id")
    args = parser.parse_args()
    path = append_event(
        args.course_root,
        {
            "action": args.action,
            "actor": args.actor,
            "status": args.status,
            "summary": args.summary,
            "artifacts": args.artifact,
            "decision": args.decision,
            "justification": args.justification,
            "run_id": args.run_id,
            "task_id": args.task_id,
        },
    )
    print(json.dumps({"status": "complete", "log": str(path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
