#!/usr/bin/env python3
"""Atomic active-run and run-snapshot persistence."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml


ACTIVE_PLAN = Path(".work/orchestration/run-plan.yaml")


def atomic_yaml(path: Path, payload: dict[str, Any]) -> None:
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


def read_plan(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ValueError(f"Cannot read run plan: {error}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("task_graph"), list):
        raise ValueError("Run plan must contain a task_graph list")
    return payload


def load_active_plan(root: Path) -> dict[str, Any]:
    return read_plan(root / ACTIVE_PLAN)


def is_placeholder(plan: dict[str, Any]) -> bool:
    return (
        not plan.get("task_graph")
        and plan.get("publication_intent") is not True
        and plan.get("authorization", {}).get("status") != "approved"
    )


def save_active_plan(root: Path, payload: dict[str, Any]) -> Path:
    run_id = str(payload.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("Run plan has no run_id")
    active = root / ACTIVE_PLAN
    snapshot = root / ".work" / "runs" / run_id / "run-plan.yaml"
    atomic_yaml(snapshot, payload)
    atomic_yaml(active, payload)
    return active
