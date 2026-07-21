#!/usr/bin/env python3
"""Validate task dependencies, clean paths, and phase readiness for one research run."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from create_research_plan import _canonical_hash, load_role_profiles

SUBMITTED_STATES = {"submitted", "verified", "approved", "merged"}
STARTED_STATES = {"in_progress", *SUBMITTED_STATES}
RESEARCH_ROLES = {"corpus-mapper", "source-extractor", "research-worker"}
CONTRADICTION_ROLE = "contradiction-reviewer"
CITATION_ROLE = "citation-verifier"
ASSESSMENT_GENERATOR_ROLE = "assessment-generator"
ASSESSMENT_VALIDATOR_ROLE = "assessment-validator"
CONTEXT_PATH_FIELDS = ("brief_path", "context_path", "dispatch_path", "event_path", "completion_template_path")
PROHIBITED_EVENT_FIELDS = {
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


def _clean_work_path(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    path = PurePosixPath(value.replace("\\", "/"))
    return not path.is_absolute() and ".." not in path.parts and len(path.parts) > 1 and path.parts[0] == ".work"


def _safe_course_path(course_root: Path, relative: object) -> Path | None:
    if not _clean_work_path(relative):
        return None
    root = course_root.resolve()
    candidate = root / str(relative)
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root / ".work")
    except (OSError, ValueError):
        return None
    current = candidate.parent
    while current != root:
        if current.is_symlink():
            return None
        current = current.parent
    return candidate


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _task_root(task: dict[str, Any]) -> PurePosixPath | None:
    value = task.get("task_work_dir")
    if not _clean_work_path(value):
        return None
    return PurePosixPath(str(value).replace("\\", "/"))


def _is_task_descendant(task: dict[str, Any], value: object) -> bool:
    root = _task_root(task)
    if root is None or not _clean_work_path(value):
        return False
    path = PurePosixPath(str(value).replace("\\", "/"))
    return path != root and root in path.parents


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _context_errors(
    task_id: str,
    task: dict[str, Any],
    *,
    course_root: Path,
    profile: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if task.get("context_status") != "compiled":
        return errors
    paths: dict[str, Path] = {}
    for field in ("brief_path", "context_path", "dispatch_path", "completion_template_path"):
        path = _safe_course_path(course_root, task.get(field))
        if path is None or not path.is_file() or path.is_symlink():
            errors.append(f"{task_id}.{field} is missing or unsafe")
        else:
            paths[field] = path
    for field, hash_field in (
        ("brief_path", "brief_sha256"),
        ("context_path", "context_sha256"),
        ("dispatch_path", "dispatch_sha256"),
        ("completion_template_path", "completion_template_sha256"),
    ):
        path = paths.get(field)
        if path is not None and task.get(hash_field) != _sha256_file(path):
            errors.append(f"{task_id}.{hash_field} does not match {field}")

    brief = _read_json_file(paths["brief_path"]) if "brief_path" in paths else None
    context = _read_json_file(paths["context_path"]) if "context_path" in paths else None
    if brief is None or brief.get("schema_version") != "worker-task-brief-v1":
        errors.append(f"{task_id} task brief must use worker-task-brief-v1")
    elif brief.get("task_id") != task_id or brief.get("run_id") != task.get("run_id"):
        errors.append(f"{task_id} task brief identity does not match the run plan")
    if context is None or context.get("schema_version") != "worker-context-v1":
        errors.append(f"{task_id} context manifest must use worker-context-v1")
        return errors
    if context.get("task_id") != task_id or context.get("run_id") != task.get("run_id"):
        errors.append(f"{task_id} context identity does not match the run plan")
    expected_profile = {
        "id": task.get("role_profile_id"),
        "version": task.get("role_profile_version"),
        "sha256": task.get("role_profile_sha256"),
    }
    if context.get("role_profile") != expected_profile:
        errors.append(f"{task_id} context role profile does not match the run plan")
    expected_brief_record = {
        "path": str(paths["brief_path"].resolve()) if "brief_path" in paths else "",
        "sha256": task.get("brief_sha256"),
    }
    if context.get("task_brief") != expected_brief_record:
        errors.append(f"{task_id} context task brief does not match the compiled brief")
    expected_writes = [str(task.get("task_work_dir")) + "/"]
    if context.get("allowed_write_paths") != expected_writes:
        errors.append(f"{task_id} context write boundary does not match task_work_dir")
    allowed_inputs = context.get("allowed_inputs")
    if not isinstance(allowed_inputs, list):
        errors.append(f"{task_id} context allowed_inputs must be a list")
    else:
        for index, item in enumerate(allowed_inputs):
            if not isinstance(item, dict):
                errors.append(f"{task_id} allowed_inputs[{index}] must be an object")
                continue
            relative = item.get("path")
            candidate = Path(str(item.get("absolute_path") or ""))
            expected = (course_root / str(relative)).resolve(strict=False) if isinstance(relative, str) else None
            if expected is None or not candidate.is_absolute() or candidate.resolve(strict=False) != expected:
                errors.append(f"{task_id} allowed input path mismatch at index {index}")
            elif not candidate.is_file() or candidate.is_symlink():
                errors.append(f"{task_id} allowed input is missing or unsafe: {relative}")
            elif item.get("sha256") != _sha256_file(candidate):
                errors.append(f"{task_id} allowed input hash mismatch: {relative}")
    contracts = context.get("required_contracts")
    if not isinstance(contracts, list) or not contracts:
        errors.append(f"{task_id} context must contain required contracts")
    else:
        assigned = set(profile.get("required_contracts", []))
        actual: set[str] = set()
        contract_pairs: list[dict[str, str]] = []
        for index, item in enumerate(contracts):
            if not isinstance(item, dict):
                errors.append(f"{task_id} required_contracts[{index}] must be an object")
                continue
            relative = str(item.get("relative_path") or "")
            actual.add(relative)
            path = Path(str(item.get("path") or ""))
            expected_contract = (Path(__file__).resolve().parents[1] / relative).resolve(strict=False)
            if not path.is_absolute() or path.resolve(strict=False) != expected_contract:
                errors.append(f"{task_id} contract path does not match SKILL_ROOT: {relative}")
            elif not path.is_file() or path.is_symlink():
                errors.append(f"{task_id} contract is missing or unsafe: {relative}")
            elif item.get("sha256") != _sha256_file(path):
                errors.append(f"{task_id} contract hash mismatch: {relative}")
            contract_pairs.append({"contract_id": str(item.get("contract_id")), "sha256": str(item.get("sha256"))})
        if actual != assigned:
            errors.append(f"{task_id} context contracts do not match its role profile")
        if task.get("contracts_sha256") != _canonical_hash(contract_pairs):
            errors.append(f"{task_id}.contracts_sha256 does not match the compiled contracts")
    dispatch = paths.get("dispatch_path")
    if dispatch is not None:
        text = dispatch.read_text(encoding="utf-8")
        if (
            str(paths.get("context_path", "")) not in text
            or str(paths.get("completion_template_path", "")) not in text
            or "Read every required contract" not in text
        ):
            errors.append(f"{task_id} dispatch message does not require its compiled context and contracts")
    expected_completion_template = {
        "path": str(paths["completion_template_path"].resolve()) if "completion_template_path" in paths else "",
        "sha256": task.get("completion_template_sha256"),
    }
    if context.get("completion_template") != expected_completion_template:
        errors.append(f"{task_id} context completion template does not match the run plan")
    if brief is not None:
        if brief.get("required_contracts") != context.get("required_contracts"):
            errors.append(f"{task_id} brief and context contracts differ")
        if brief.get("allowed_inputs") != context.get("allowed_inputs"):
            errors.append(f"{task_id} brief and context inputs differ")
        if brief.get("allowed_write_paths") != expected_writes:
            errors.append(f"{task_id} brief write boundary does not match task_work_dir")
        for field in ("event_path", "output_path", "completion_path"):
            if brief.get(field) != task.get(field):
                errors.append(f"{task_id} brief {field} does not match the run plan")
        if brief.get("completion_template") != expected_completion_template:
            errors.append(f"{task_id} brief completion template does not match the run plan")
    return errors


def _worker_event_errors(task_id: str, task: dict[str, Any], path: Path) -> list[str]:
    errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return [f"{task_id} event shard is unreadable"]
    if not lines:
        return [f"{task_id} submitted without an observable event shard"]
    seen: set[str] = set()
    required = {"schema_version", "event_id", "timestamp", "run_id", "task_id", "action", "actor", "status", "summary"}
    for number, line in enumerate(lines, 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"{task_id} event line {number} is invalid JSON")
            continue
        if not isinstance(event, dict) or event.get("schema_version") != "action-event-v1" or not required.issubset(event):
            errors.append(f"{task_id} event line {number} is not a complete worker action-event-v1")
            continue
        event_id = str(event.get("event_id"))
        if event_id in seen:
            errors.append(f"{task_id} event shard contains duplicate event_id {event_id}")
        seen.add(event_id)
        if event.get("run_id") != task.get("run_id") or event.get("task_id") != task_id:
            errors.append(f"{task_id} event line {number} has mismatched run or task identity")
        if event.get("actor") != task.get("role"):
            errors.append(f"{task_id} event line {number} actor must be {task.get('role')}")
        if len(str(event.get("summary", ""))) > 1_000:
            errors.append(f"{task_id} event line {number} summary is too long")
        if event.get("justification") is not None and len(str(event.get("justification"))) > 1_000:
            errors.append(f"{task_id} event line {number} justification is too long")
        if PROHIBITED_EVENT_FIELDS & set(event):
            errors.append(f"{task_id} event line {number} contains prohibited private fields")
        artifacts = event.get("artifacts", [])
        if not isinstance(artifacts, list):
            errors.append(f"{task_id} event line {number} artifacts must be a list")
        else:
            for artifact in artifacts:
                if not _is_task_descendant(task, artifact):
                    errors.append(f"{task_id} event line {number} artifact escapes its task directory: {artifact}")
    return errors


def _ancestors(task_id: str, tasks: dict[str, dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    stack = list(tasks[task_id].get("dependencies", []))
    while stack:
        dependency = str(stack.pop())
        if dependency in result or dependency not in tasks:
            continue
        result.add(dependency)
        stack.extend(tasks[dependency].get("dependencies", []))
    return result


def _cycle_errors(tasks: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str, trail: list[str]) -> None:
        if task_id in visiting:
            errors.append(f"Task graph cycle: {' -> '.join([*trail, task_id])}")
            return
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in tasks[task_id].get("dependencies", []):
            if str(dependency) in tasks:
                visit(str(dependency), [*trail, task_id])
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in tasks:
        visit(task_id, [])
    return errors


def validate_plan(payload: dict[str, Any], *, course_root: Path | None = None) -> tuple[list[str], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    strict_dispatch = course_root is not None or payload.get("publication_intent") is True
    raw_tasks = payload.get("task_graph")
    if not isinstance(raw_tasks, list):
        return ["run-plan task_graph must be a list"], warnings, []
    tasks: dict[str, dict[str, Any]] = {}
    output_paths: set[str] = set()
    completion_paths: set[str] = set()
    isolated_paths: set[str] = set()
    role_profiles = load_role_profiles()
    for index, task in enumerate(raw_tasks):
        prefix = f"task_graph[{index}]"
        if not isinstance(task, dict):
            errors.append(f"{prefix} must be an object")
            continue
        task_id = str(task.get("task_id", "")).strip()
        if not task_id:
            errors.append(f"{prefix}.task_id is required")
            continue
        if task_id in tasks:
            errors.append(f"Duplicate task_id: {task_id}")
            continue
        tasks[task_id] = task
        for field, seen in (("output_path", output_paths), ("completion_path", completion_paths)):
            value = task.get(field)
            if not _clean_work_path(value):
                errors.append(f"{task_id}.{field} must be a relative path under .work/")
            elif str(value) in seen:
                errors.append(f"Duplicate {field}: {value}")
            else:
                seen.add(str(value))
        if strict_dispatch:
            if _task_root(task) is None:
                errors.append(f"{task_id}.task_work_dir must be a relative path under .work/")
            for field in CONTEXT_PATH_FIELDS:
                value = task.get(field)
                if not _clean_work_path(value):
                    errors.append(f"{task_id}.{field} must be a relative path under .work/")
                elif str(value) in isolated_paths:
                    errors.append(f"Duplicate {field}: {value}")
                else:
                    isolated_paths.add(str(value))
                if not _is_task_descendant(task, value):
                    errors.append(f"{task_id}.{field} must be inside its task_work_dir")
            for field in ("output_path", "completion_path"):
                if not _is_task_descendant(task, task.get(field)):
                    errors.append(f"{task_id}.{field} must be inside its task_work_dir")
        role = str(task.get("role", "")).strip()
        if not role:
            errors.append(f"{task_id}.role is required")
        if strict_dispatch:
            profile = role_profiles.get(role)
            if not isinstance(profile, dict):
                errors.append(f"{task_id}.role has no deterministic profile: {role}")
            else:
                if task.get("role_profile_id") != role:
                    errors.append(f"{task_id}.role_profile_id must match role")
                if task.get("role_profile_version") != profile.get("version"):
                    errors.append(f"{task_id}.role_profile_version is stale")
                if task.get("role_profile_sha256") != _canonical_hash(profile):
                    errors.append(f"{task_id}.role_profile_sha256 is stale")
            if task.get("context_status") not in {"pending", "compiled"}:
                errors.append(f"{task_id}.context_status must be pending or compiled")
        if task.get("status") not in {"planned", "in_progress", "submitted", "verified", "approved", "merged", "changes_required", "rejected", "blocked", "superseded"}:
            errors.append(f"{task_id}.status is invalid")
        if not isinstance(task.get("dependencies", []), list):
            errors.append(f"{task_id}.dependencies must be a list")
            task["dependencies"] = []

    for task_id, task in tasks.items():
        for dependency in task.get("dependencies", []):
            if str(dependency) not in tasks:
                errors.append(f"{task_id} depends on unknown task: {dependency}")
    errors.extend(_cycle_errors(tasks))

    for task_id, task in tasks.items():
        role = str(task.get("role"))
        state = str(task.get("status"))
        dependencies = [str(item) for item in task.get("dependencies", [])]
        unmet = [item for item in dependencies if item in tasks and tasks[item].get("status") not in SUBMITTED_STATES]
        if state in STARTED_STATES and unmet:
            errors.append(f"{task_id} started before dependencies were submitted: {', '.join(unmet)}")
        ancestors = _ancestors(task_id, tasks)
        ancestor_roles = {str(tasks[item].get("role")) for item in ancestors}
        if role == CONTRADICTION_ROLE and tasks and not (ancestor_roles & RESEARCH_ROLES):
            errors.append(f"{task_id} must depend on submitted research or extraction work")
        if role == CONTRADICTION_ROLE:
            research_ids = {other_id for other_id, other in tasks.items() if str(other.get("role")) in RESEARCH_ROLES}
            missing_research = research_ids - ancestors
            if missing_research:
                errors.append(f"{task_id} must depend on every research task: {', '.join(sorted(missing_research))}")
        if role == CITATION_ROLE:
            if CONTRADICTION_ROLE not in ancestor_roles:
                errors.append(f"{task_id} must depend on a contradiction-reviewer")
            if not (ancestor_roles & RESEARCH_ROLES):
                errors.append(f"{task_id} must depend transitively on research or extraction work")
            unfinished_early = [
                other_id
                for other_id, other in tasks.items()
                if str(other.get("role")) in {*RESEARCH_ROLES, CONTRADICTION_ROLE}
                and other.get("status") not in SUBMITTED_STATES
            ]
            if state in STARTED_STATES and unfinished_early:
                errors.append(f"{task_id} started before all extraction, research, and contradiction work finished: {', '.join(unfinished_early)}")
        if role == ASSESSMENT_GENERATOR_ROLE:
            has_research = any(str(other.get("role")) in RESEARCH_ROLES for other in tasks.values())
            if has_research and CITATION_ROLE not in ancestor_roles:
                errors.append(f"{task_id} must depend on final citation verification")
            unfinished = [other_id for other_id, other in tasks.items() if str(other.get("role")) == CITATION_ROLE and other.get("status") not in SUBMITTED_STATES]
            if state in STARTED_STATES and unfinished:
                errors.append(f"{task_id} started before citation verification finished: {', '.join(unfinished)}")
        if role == ASSESSMENT_VALIDATOR_ROLE:
            if ASSESSMENT_GENERATOR_ROLE not in ancestor_roles:
                errors.append(f"{task_id} must depend on assessment generation")
            unfinished = [other_id for other_id, other in tasks.items() if str(other.get("role")) == ASSESSMENT_GENERATOR_ROLE and other.get("status") not in SUBMITTED_STATES]
            if state in STARTED_STATES and unfinished:
                errors.append(f"{task_id} started before assessment generation finished: {', '.join(unfinished)}")

        profile = role_profiles.get(role)
        if course_root is not None and isinstance(profile, dict):
            errors.extend(_context_errors(task_id, task, course_root=course_root, profile=profile))

        if course_root is not None and state in SUBMITTED_STATES:
            output_relative = task.get("output_path")
            output = _safe_course_path(course_root, output_relative)
            if output is None:
                errors.append(f"{task_id} output escapes the course .work boundary")
            elif not output.is_file() or output.is_symlink():
                errors.append(f"{task_id} is {state} but its declared output is missing")
            else:
                try:
                    output_payload = json.loads(output.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError):
                    errors.append(f"{task_id} declared output is unreadable JSON")
                else:
                    expected_schema = task.get("required_schema")
                    if expected_schema and (
                        not isinstance(output_payload, dict)
                        or output_payload.get("schema_version") != expected_schema
                    ):
                        errors.append(f"{task_id} output must use {expected_schema}")
                    elif expected_schema == "source-candidate-ledger-v1":
                        if output_payload.get("task_id") != task_id:
                            errors.append(f"{task_id} source candidate ledger task_id does not match")
                        candidates = output_payload.get("candidates")
                        if not isinstance(candidates, list):
                            errors.append(f"{task_id} source candidate ledger requires a candidates list")
                        else:
                            source_limit = int(task.get("source_limit") or 0)
                            if source_limit and len(candidates) > source_limit:
                                errors.append(f"{task_id} source candidate ledger exceeds its approved source limit of {source_limit}")
                            seen_candidate_ids: set[str] = set()
                            seen_urls: set[str] = set()
                            for candidate_index, candidate in enumerate(candidates):
                                prefix = f"{task_id} candidates[{candidate_index}]"
                                if not isinstance(candidate, dict):
                                    errors.append(f"{prefix} must be an object")
                                    continue
                                for field in ("candidate_id", "title", "authority_rationale"):
                                    if not isinstance(candidate.get(field), str) or not candidate.get(field, "").strip():
                                        errors.append(f"{prefix}.{field} is required")
                                candidate_id = str(candidate.get("candidate_id") or "")
                                if candidate_id and candidate_id in seen_candidate_ids:
                                    errors.append(f"{prefix}.candidate_id is duplicated")
                                seen_candidate_ids.add(candidate_id)
                                url = str(candidate.get("url") or "")
                                if not isinstance(candidate.get("url"), str) or re.fullmatch(r"https?://[^\s]+", url) is None:
                                    errors.append(f"{prefix}.url must be an absolute HTTP(S) URL")
                                elif url in seen_urls:
                                    errors.append(f"{prefix}.url is duplicated")
                                seen_urls.add(url)
                    elif expected_schema == "corpus-map-v1":
                        if (
                            output_payload.get("run_id") != task.get("run_id")
                            or output_payload.get("task_id") != task_id
                            or output_payload.get("worker_role") != task.get("role")
                        ):
                            errors.append(f"{task_id} corpus map identity does not match its task brief")
                        if output_payload.get("sources_used") != task.get("input_source_ids", []):
                            errors.append(f"{task_id} corpus map must account for every assigned source ID")
                    elif expected_schema == "evidence-packet-v1":
                        if output_payload.get("task_id") != task_id or output_payload.get("worker_role") != task.get("role"):
                            errors.append(f"{task_id} evidence packet identity does not match its task brief")
                        used = output_payload.get("sources_used")
                        if not isinstance(used, list) or not set(str(item) for item in used).issubset(set(str(item) for item in task.get("input_source_ids", []))):
                            errors.append(f"{task_id} evidence packet uses an unassigned source ID")
            completion_relative = task.get("completion_path")
            completion = _safe_course_path(course_root, completion_relative)
            if completion is None:
                errors.append(f"{task_id} completion envelope escapes the course .work boundary")
            elif not completion.is_file() or completion.is_symlink():
                errors.append(f"{task_id} is {state} but its completion envelope is missing")
            else:
                try:
                    envelope = json.loads(completion.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError):
                    errors.append(f"{task_id} completion envelope is unreadable")
                else:
                    if not isinstance(envelope, dict) or envelope.get("schema_version") != "completion-envelope-v1":
                        errors.append(f"{task_id} completion envelope must use completion-envelope-v1")
                    elif envelope.get("task_id") != task_id or envelope.get("output_path") != task.get("output_path"):
                        errors.append(f"{task_id} completion envelope does not match its task brief")
                    elif envelope.get("status") not in {"submitted", "blocked", "failed"}:
                        errors.append(f"{task_id} completion envelope status is invalid")
                    else:
                        if envelope.get("run_id") != task.get("run_id") or envelope.get("role") != task.get("role"):
                            errors.append(f"{task_id} completion run or role identity does not match its task brief")
                        if not isinstance(envelope.get("summary"), str) or not envelope.get("summary", "").strip():
                            errors.append(f"{task_id} completion summary is required")
                        elif envelope.get("summary") == "REPLACE_WITH_SHORT_OBSERVABLE_SUMMARY":
                            errors.append(f"{task_id} completion summary still contains its template placeholder")
                        expected_profile = {
                            "id": task.get("role_profile_id"),
                            "version": task.get("role_profile_version"),
                            "sha256": task.get("role_profile_sha256"),
                        }
                        if envelope.get("role_profile_acknowledged") != expected_profile:
                            errors.append(f"{task_id} completion did not acknowledge its role profile")
                        context_path = _safe_course_path(course_root, task.get("context_path"))
                        context = _read_json_file(context_path) if context_path is not None else None
                        expected_contracts = [
                            {"contract_id": str(item.get("contract_id")), "sha256": str(item.get("sha256"))}
                            for item in (context or {}).get("required_contracts", [])
                            if isinstance(item, dict)
                        ]
                        if envelope.get("contracts_acknowledged") != expected_contracts:
                            errors.append(f"{task_id} completion did not acknowledge its required contracts")
                        if envelope.get("event_path") != task.get("event_path"):
                            errors.append(f"{task_id} completion event_path does not match its task brief")
                        if envelope.get("artifacts") != [task.get("output_path")]:
                            errors.append(f"{task_id} completion artifacts must contain only its declared output")
                        for field in ("blockers", "next_actions"):
                            if not isinstance(envelope.get(field), list):
                                errors.append(f"{task_id} completion {field} must be a list")
                        completed_at = envelope.get("completed_at")
                        if not isinstance(completed_at, str) or completed_at == "REPLACE_WITH_ISO_8601_TIMESTAMP":
                            errors.append(f"{task_id} completion completed_at must be an ISO-8601 timestamp")
                        else:
                            try:
                                datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                            except ValueError:
                                errors.append(f"{task_id} completion completed_at must be an ISO-8601 timestamp")
            event = _safe_course_path(course_root, task.get("event_path"))
            if event is None or not event.is_file() or event.is_symlink():
                errors.append(f"{task_id} is {state} but its event shard is missing")
            else:
                errors.extend(_worker_event_errors(task_id, task, event))

    ready: list[str] = []
    for task_id, task in tasks.items():
        if task.get("status") != "planned":
            continue
        if strict_dispatch and task.get("context_status") != "compiled":
            continue
        dependencies = [str(item) for item in task.get("dependencies", [])]
        if any(item not in tasks or tasks[item].get("status") not in SUBMITTED_STATES for item in dependencies):
            continue
        if task.get("role") == CITATION_ROLE:
            unfinished = [
                other for other in tasks.values()
                if str(other.get("role")) in {*RESEARCH_ROLES, CONTRADICTION_ROLE}
                and other.get("status") not in SUBMITTED_STATES
            ]
            if unfinished:
                continue
        if task.get("role") == ASSESSMENT_GENERATOR_ROLE:
            if any(str(other.get("role")) == CITATION_ROLE and other.get("status") not in SUBMITTED_STATES for other in tasks.values()):
                continue
        if task.get("role") == ASSESSMENT_VALIDATOR_ROLE:
            if any(str(other.get("role")) == ASSESSMENT_GENERATOR_ROLE and other.get("status") not in SUBMITTED_STATES for other in tasks.values()):
                continue
        ready.append(task_id)
    if errors:
        ready = []
    if not tasks:
        if payload.get("publication_intent") is True:
            errors.append("A publication-intent run plan must contain tasks.")
            ready = []
        else:
            warnings.append("The run plan has no tasks.")
    if tasks and payload.get("publication_intent") is True:
        if payload.get("authorization", {}).get("status") != "approved":
            errors.append("A publication-intent plan requires approved authorization.")
        if not payload.get("capabilities", {}).get("subagents"):
            errors.append("A publication-intent researched course requires subagents.")
        if errors:
            ready = []
    return errors, warnings, ready


def context_required_task_ids(payload: dict[str, Any]) -> list[str]:
    raw_tasks = payload.get("task_graph")
    if not isinstance(raw_tasks, list):
        return []
    tasks = {
        str(item.get("task_id")): item
        for item in raw_tasks
        if isinstance(item, dict) and item.get("task_id")
    }
    required: list[str] = []
    for task_id, task in tasks.items():
        if task.get("status") != "planned" or task.get("context_status") == "compiled":
            continue
        dependencies = [str(item) for item in task.get("dependencies", [])]
        if all(item in tasks and tasks[item].get("status") in SUBMITTED_STATES for item in dependencies):
            required.append(task_id)
    return required


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_plan", type=Path)
    parser.add_argument("--course-root", type=Path)
    args = parser.parse_args()
    try:
        payload = yaml.safe_load(args.run_plan.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        print(json.dumps({"status": "fail", "errors": [str(error)], "warnings": [], "ready_task_ids": []}, indent=2))
        return 1
    if not isinstance(payload, dict):
        errors, warnings, ready = ["run plan must be a YAML object"], [], []
    else:
        errors, warnings, ready = validate_plan(payload, course_root=args.course_root)
    required_context = context_required_task_ids(payload) if isinstance(payload, dict) and not errors else []
    print(json.dumps({
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "warnings": warnings,
        "context_required_task_ids": required_context,
        "ready_task_ids": ready,
    }, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
