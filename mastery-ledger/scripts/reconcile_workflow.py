#!/usr/bin/env python3
"""Converge a course toward a target state or return its exact next work."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from advance_workflow import ORDER, advance_state, gate_requirements, normalize, recover_legacy_draft_state
from record_action import append_event

SCHEMA_VERSION = "workflow-reconciliation-v1"


def _bounded_requirement_summary(next_state: str, requirements: list[dict[str, Any]]) -> str:
    prefix = f"Workflow requires work before {next_state}: "
    messages = "; ".join(str(item.get("message") or item.get("code") or "unspecified requirement") for item in requirements)
    summary = prefix + messages
    return summary if len(summary) <= 1_000 else summary[:997].rstrip() + "..."


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_study(root: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load((root / "study.yaml").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ValueError(f"Cannot read study.yaml: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("study.yaml must contain a YAML object")
    return payload


def _tracker(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _fingerprint(current: str, blocked_state: str, requirements: list[dict[str, Any]]) -> str:
    stable = {
        "current_state": current,
        "blocked_state": blocked_state,
        "requirements": [
            {"code": item.get("code"), "message": item.get("message")}
            for item in requirements
        ],
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def reconcile(root: Path, target: str, *, max_same_blocker: int) -> tuple[dict[str, Any], int]:
    target = normalize(target)
    if target not in ORDER and target != "DRAFT_UNVERIFIED":
        raise ValueError(f"Unknown target state: {target}")
    tracker_path = root / ".work" / "orchestration" / "reconciliation.json"
    advanced: list[dict[str, str]] = []
    recover_legacy_draft_state(root)

    if target == "DRAFT_UNVERIFIED":
        study = _read_study(root)
        current = normalize(study.get("workflow_state"))
        if normalize(study.get("publication_status")) != target:
            advance_state(root, target, reason="Reconciliation recorded an unverified publication draft.")
        _atomic_json(tracker_path, {"schema_version": SCHEMA_VERSION, "status": "complete", "target_state": target})
        return {"schema_version": SCHEMA_VERSION, "status": "complete", "target_state": target, "current_state": current, "publication_status": target, "advanced": advanced}, 0

    while True:
        study = _read_study(root)
        current = normalize(study.get("workflow_state"))
        if current not in ORDER:
            raise ValueError(f"Current workflow state is not on the primary path: {current or '<missing>'}")
        if ORDER.index(current) >= ORDER.index(target):
            _atomic_json(tracker_path, {
                "schema_version": SCHEMA_VERSION,
                "status": "complete",
                "target_state": target,
                "current_state": current,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            return {
                "schema_version": SCHEMA_VERSION,
                "status": "complete",
                "target_state": target,
                "current_state": current,
                "advanced": advanced,
            }, 0

        next_state = ORDER[ORDER.index(current) + 1]
        requirements = gate_requirements(root, next_state)
        if not requirements:
            previous, entered = advance_state(
                root,
                next_state,
                reason=f"Reconciliation confirmed the {next_state} gate.",
            )
            advanced.append({"from": previous, "to": entered})
            continue

        fingerprint = _fingerprint(current, next_state, requirements)
        prior = _tracker(tracker_path)
        attempts = int(prior.get("consecutive_identical_passes", 0)) + 1 if prior.get("fingerprint") == fingerprint else 1
        needs_user = any(bool(item.get("user_input_required")) for item in requirements)
        status = "needs_user_input" if needs_user else "needs_work"
        if attempts >= max_same_blocker:
            status = "retry_exhausted"
        now = datetime.now(timezone.utc).isoformat()
        state = {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "target_state": target,
            "current_state": current,
            "blocked_state": next_state,
            "fingerprint": fingerprint,
            "consecutive_identical_passes": attempts,
            "max_same_blocker": max_same_blocker,
            "requirements": requirements,
            "updated_at": now,
        }
        _atomic_json(tracker_path, state)
        if prior.get("fingerprint") != fingerprint or status == "retry_exhausted":
            append_event(root, {
                "action": "workflow.reconcile",
                "actor": "main-agent",
                "status": status,
                "summary": _bounded_requirement_summary(next_state, requirements),
                "artifacts": [".work/orchestration/reconciliation.json"],
                "decision": next_state,
                "justification": "Deterministic gate inspection; no hidden reasoning recorded.",
            })
        result = {
            **state,
            "advanced": advanced,
            "next_actions": [
                {
                    "code": item["code"],
                    "workflow": item["workflow"],
                    "action": item["action"],
                    "user_input_required": item["user_input_required"],
                }
                for item in requirements
            ],
            "rerun_argv": [
                sys.executable,
                str(Path(__file__).resolve()),
                str(root),
                "--json",
                "--max-same-blocker",
                str(max_same_blocker),
            ],
        }
        return result, 3 if status == "retry_exhausted" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    parser.add_argument("target_state", nargs="?", help="Defaults to study.yaml workflow_target")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--max-same-blocker", type=int, default=3)
    args = parser.parse_args()
    if not 2 <= args.max_same_blocker <= 10:
        parser.error("--max-same-blocker must be 2-10")
    try:
        root = args.course_root.resolve()
        target = args.target_state
        if target is None:
            target = str(_read_study(root).get("workflow_target") or "").strip()
            if not target:
                parser.error("No target supplied and study.yaml has no workflow_target")
        payload, return_code = reconcile(root, target, max_same_blocker=args.max_same_blocker)
    except ValueError as error:
        parser.error(str(error))
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
