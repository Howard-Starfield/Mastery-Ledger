#!/usr/bin/env python3
"""Compile one dependency-ready task into a bounded, validated worker context."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from create_research_plan import _canonical_hash, load_role_profiles


SUBMITTED_STATES = {"submitted", "verified", "approved", "merged"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def clean_relative(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Artifact paths must be non-empty strings.")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Artifact path must remain course-relative: {value}")
    return path.as_posix()


def safe_course_file(root: Path, relative: object) -> tuple[str, Path]:
    normalized = clean_relative(relative)
    candidate = root / normalized
    try:
        candidate.resolve(strict=False).relative_to(root.resolve())
    except (OSError, ValueError) as error:
        raise ValueError(f"Artifact escapes the course boundary: {normalized}") from error
    if not candidate.is_file() or candidate.is_symlink():
        raise ValueError(f"Required input is missing or unsafe: {normalized}")
    current = candidate.parent
    while current != root:
        if current.is_symlink():
            raise ValueError(f"Required input crosses a symbolic-link directory: {normalized}")
        current = current.parent
    return normalized, candidate


def atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: Path, payload: object) -> None:
    atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def atomic_yaml(path: Path, payload: object) -> None:
    atomic_text(path, yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))


def _source_artifacts(root: Path, source_ids: list[str]) -> list[str]:
    if not source_ids:
        return []
    manifest_path = root / "source-manifest.yaml"
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ValueError(f"Cannot resolve assigned sources: {error}") from error
    sources = manifest.get("sources", []) if isinstance(manifest, dict) else []
    index = {
        str(item.get("source_id")): item
        for item in sources
        if isinstance(item, dict) and item.get("source_id")
    }
    result: list[str] = ["source-manifest.yaml"]
    for source_id in source_ids:
        record = index.get(source_id)
        if not record:
            raise ValueError(f"Assigned source ID is missing: {source_id}")
        knowledge_path = record.get("knowledge_path")
        if not isinstance(knowledge_path, str):
            raise ValueError(f"Assigned source has no extracted knowledge path: {source_id}")
        result.append(knowledge_path)
    return result


def _required_contracts(skill_root: Path, profile: dict[str, Any]) -> list[dict[str, str]]:
    contracts: list[dict[str, str]] = []
    for relative in profile.get("required_contracts", []):
        normalized = clean_relative(relative)
        path = (skill_root / normalized).resolve(strict=False)
        try:
            path.relative_to(skill_root.resolve())
        except ValueError as error:
            raise ValueError(f"Contract escapes SKILL_ROOT: {normalized}") from error
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Required contract is missing or unsafe: {normalized}")
        contracts.append({
            "contract_id": Path(normalized).stem,
            "path": str(path),
            "relative_path": normalized,
            "sha256": sha256_file(path),
        })
    if not contracts:
        raise ValueError("Role profile does not assign any required contracts.")
    return contracts


def compile_context(root: Path, task_id: str) -> dict[str, Any]:
    root = root.resolve()
    plan_path = root / ".work" / "orchestration" / "run-plan.yaml"
    try:
        plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ValueError(f"Cannot read run plan: {error}") from error
    if not isinstance(plan, dict) or not isinstance(plan.get("task_graph"), list):
        raise ValueError("Run plan must contain a task_graph list.")
    tasks = {
        str(item.get("task_id")): item
        for item in plan["task_graph"]
        if isinstance(item, dict) and item.get("task_id")
    }
    task = tasks.get(task_id)
    if task is None:
        raise ValueError(f"Unknown task ID: {task_id}")
    if task.get("status") != "planned":
        raise ValueError(f"Task must be planned before context compilation: {task_id}")
    unmet = [
        str(dependency)
        for dependency in task.get("dependencies", [])
        if str(dependency) not in tasks or tasks[str(dependency)].get("status") not in SUBMITTED_STATES
    ]
    if unmet:
        raise ValueError("Task dependencies are not submitted: " + ", ".join(unmet))
    if task.get("role") == "research-worker" and not task.get("scope_included") and not task.get("concept_ids"):
        raise ValueError("Research workers require an approved concept group or included scope after corpus mapping.")

    role = str(task.get("role") or "")
    profile = load_role_profiles().get(role)
    if not isinstance(profile, dict):
        raise ValueError(f"No deterministic role profile exists for {role}")
    profile_hash = _canonical_hash(profile)
    if (
        task.get("role_profile_id") != role
        or task.get("role_profile_version") != profile.get("version")
        or task.get("role_profile_sha256") != profile_hash
    ):
        raise ValueError(f"Role profile metadata is stale or mismatched for {task_id}")

    run_id = str(plan.get("run_id") or task.get("run_id") or "")
    if not run_id or task.get("run_id") != run_id:
        raise ValueError(f"Task run identity is invalid for {task_id}")
    expected_root = f".work/runs/{run_id}/tasks/{task_id}"
    if task.get("task_work_dir") != expected_root:
        raise ValueError(f"Task work directory must be {expected_root}")
    expected_root_path = PurePosixPath(expected_root)
    for field in ("brief_path", "context_path", "dispatch_path", "event_path", "output_path", "completion_path"):
        normalized = clean_relative(task.get(field))
        candidate = PurePosixPath(normalized)
        if candidate == expected_root_path or expected_root_path not in candidate.parents:
            raise ValueError(f"{field} must remain inside {expected_root}")

    input_paths: list[str] = []
    input_paths.extend(str(item) for item in task.get("input_artifacts", []))
    input_paths.extend(_source_artifacts(root, [str(item) for item in task.get("input_source_ids", [])]))
    for dependency in task.get("dependencies", []):
        dependency_task = tasks[str(dependency)]
        input_paths.append(str(dependency_task.get("output_path")))
    deduplicated = list(dict.fromkeys(input_paths))
    inputs: list[dict[str, str]] = []
    for relative in deduplicated:
        normalized, path = safe_course_file(root, relative)
        inputs.append({"path": normalized, "absolute_path": str(path.resolve()), "sha256": sha256_file(path)})

    skill_root = Path(__file__).resolve().parents[1]
    contracts = _required_contracts(skill_root, profile)
    task_root = root / expected_root
    task_root.mkdir(parents=True, exist_ok=True)
    if task_root.is_symlink():
        raise ValueError("Assigned task directory cannot be a symbolic link.")
    current = task_root.parent
    while current != root:
        if current.is_symlink():
            raise ValueError("Assigned task directory crosses a symbolic-link directory.")
        current = current.parent

    brief = {
        "schema_version": "worker-task-brief-v1",
        "run_id": run_id,
        "task_id": task_id,
        "role": role,
        "role_profile_id": role,
        "role_profile_version": profile["version"],
        "role_profile_sha256": profile_hash,
        "mission": profile["mission"],
        "best_practices": profile["best_practices"],
        "stop_conditions": profile["stop_conditions"],
        "prohibited_actions": profile["prohibited_actions"],
        "objective": task.get("objective"),
        "scope_included": task.get("scope_included", []),
        "scope_excluded": task.get("scope_excluded", []),
        "concept_ids": task.get("concept_ids", []),
        "source_limit": task.get("source_limit"),
        "dependencies": task.get("dependencies", []),
        "allowed_inputs": inputs,
        "required_contracts": contracts,
        "allowed_write_paths": [expected_root + "/"],
        "event_path": task.get("event_path"),
        "output_path": task.get("output_path"),
        "completion_path": task.get("completion_path"),
        "required_schema": task.get("required_schema"),
        "acceptance_criteria": task.get("acceptance_criteria", []),
    }
    brief_path = root / clean_relative(task.get("brief_path"))
    atomic_json(brief_path, brief)
    brief_hash = sha256_file(brief_path)

    context = {
        "schema_version": "worker-context-v1",
        "run_id": run_id,
        "task_id": task_id,
        "role": role,
        "workflow_state": plan.get("workflow_state"),
        "task_brief": {"path": str(brief_path.resolve()), "sha256": brief_hash},
        "role_profile": {
            "id": role,
            "version": profile["version"],
            "sha256": profile_hash,
        },
        "required_contracts": contracts,
        "allowed_inputs": inputs,
        "allowed_write_paths": [expected_root + "/"],
        "forbidden_actions": profile["prohibited_actions"],
    }
    context_path = root / clean_relative(task.get("context_path"))
    atomic_json(context_path, context)
    context_hash = sha256_file(context_path)

    dispatch = (
        f"Execute the assigned Mastery Ledger task described by:\n{brief_path.resolve()}\n\n"
        f"Before beginning, read the context manifest in full:\n{context_path.resolve()}\n\n"
        "Read every required contract listed there in full. Verify the assigned input and output paths. "
        "If a contract, input, hash, or assigned path is unavailable, write a blocked completion and stop.\n\n"
        "Use only the assigned inputs and scope. Write only inside the assigned task directory. "
        "Produce the declared submission, observable event shard, and completion envelope. "
        "Do not modify canonical course artifacts, approve your own output, expand scope, dispatch another worker, "
        "or record hidden reasoning.\n"
    )
    dispatch_path = root / clean_relative(task.get("dispatch_path"))
    atomic_text(dispatch_path, dispatch)
    dispatch_hash = sha256_file(dispatch_path)

    task["context_status"] = "compiled"
    task["context_sha256"] = context_hash
    task["brief_sha256"] = brief_hash
    task["dispatch_sha256"] = dispatch_hash
    task["contracts_sha256"] = _canonical_hash([
        {"contract_id": item["contract_id"], "sha256": item["sha256"]} for item in contracts
    ])
    plan["updated_at"] = datetime.now(timezone.utc).isoformat()
    atomic_yaml(plan_path, plan)
    return {
        "status": "complete",
        "run_id": run_id,
        "task_id": task_id,
        "context_path": str(context_path),
        "dispatch_path": str(dispatch_path),
        "dispatch_message": dispatch,
        "context_sha256": context_hash,
        "dispatch_sha256": dispatch_hash,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    parser.add_argument("task_id")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    try:
        result = compile_context(args.course_root, args.task_id)
    except ValueError as error:
        parser.error(str(error))
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(yaml.safe_dump(result, sort_keys=False, allow_unicode=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
