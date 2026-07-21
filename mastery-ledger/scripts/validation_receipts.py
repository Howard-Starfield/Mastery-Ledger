"""Persist and load durable receipts for accepted worker completions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from compile_worker_context import atomic_json, sha256_file
from course_paths import VALIDATION


RECEIPT_SCHEMA = "validation-receipt-v1"
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
RESULT_FIELDS = {
    "status",
    "decision",
    "validated_question_ids",
    "rejected_question_ids",
    "verified_claim_ids",
    "retained_claim_ids",
    "checked_source_ids",
    "issues",
    "limitations",
}


def _safe_id(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not SAFE_ID.fullmatch(text):
        raise ValueError(f"{label} is not safe for a validation-receipt path: {text!r}")
    return text


def receipt_path(root: Path, run_id: object, task_id: object) -> Path:
    return root / VALIDATION / _safe_id(run_id, "run_id") / f"{_safe_id(task_id, 'task_id')}.json"


def write_validation_receipt(root: Path, plan: dict[str, Any], task: dict[str, Any]) -> Path:
    """Record the accepted result facts needed after disposable `.work` is removed."""
    output_path = root / str(task.get("output_path") or "")
    completion_path = root / str(task.get("completion_path") or "")
    output = json.loads(output_path.read_text(encoding="utf-8"))
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    context_path = root / str(task.get("context_path") or "")
    context = json.loads(context_path.read_text(encoding="utf-8"))
    result = {key: output[key] for key in RESULT_FIELDS if key in output}
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "run_id": task.get("run_id"),
        "task_id": task.get("task_id"),
        "role": task.get("role"),
        "accepted_at": task.get("accepted_at"),
        "task_status": task.get("status"),
        "plan": {
            "schema_version": plan.get("schema_version"),
            "compiler": (plan.get("plan_origin") or {}).get("compiler") if isinstance(plan.get("plan_origin"), dict) else None,
            "publication_intent": plan.get("publication_intent"),
            "authorization": plan.get("authorization"),
        },
        "role_profile": {
            "id": task.get("role_profile_id"),
            "version": task.get("role_profile_version"),
            "sha256": task.get("role_profile_sha256"),
        },
        "dependency_task_ids": task.get("dependencies", []),
        "context_sha256": task.get("context_sha256"),
        "input_artifacts": context.get("allowed_inputs", []),
        "output": {
            "path": task.get("output_path"),
            "sha256": sha256_file(output_path),
        },
        "completion": {
            "path": task.get("completion_path"),
            "sha256": sha256_file(completion_path),
            "status": completion.get("status"),
        },
        "result": result,
    }
    destination = receipt_path(root, task.get("run_id"), task.get("task_id"))
    atomic_json(destination, receipt)
    return destination


def load_validation_receipts(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    receipts: list[dict[str, Any]] = []
    errors: list[str] = []
    validation_root = root / VALIDATION
    if not validation_root.is_dir():
        return receipts, errors
    for path in sorted(validation_root.glob("*/*.json")):
        if path.is_symlink():
            errors.append(f"Validation receipt cannot be a symlink: {path.relative_to(root)}")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            errors.append(f"Unreadable validation receipt {path.relative_to(root)}: {error}")
            continue
        if not isinstance(payload, dict) or payload.get("schema_version") != RECEIPT_SCHEMA:
            errors.append(f"Invalid validation receipt schema: {path.relative_to(root)}")
            continue
        receipts.append(payload)
    return receipts, errors
