#!/usr/bin/env python3
"""Validate task dependencies, clean paths, and phase readiness for one research run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

SUBMITTED_STATES = {"submitted", "verified", "approved", "merged"}
STARTED_STATES = {"in_progress", *SUBMITTED_STATES}
RESEARCH_ROLES = {"corpus-mapper", "source-extractor", "research-worker"}
CONTRADICTION_ROLE = "contradiction-reviewer"
CITATION_ROLE = "citation-verifier"
ASSESSMENT_GENERATOR_ROLE = "assessment-generator"
ASSESSMENT_VALIDATOR_ROLE = "assessment-validator"


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
    raw_tasks = payload.get("task_graph")
    if not isinstance(raw_tasks, list):
        return ["run-plan task_graph must be a list"], warnings, []
    tasks: dict[str, dict[str, Any]] = {}
    output_paths: set[str] = set()
    completion_paths: set[str] = set()
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
        if not str(task.get("role", "")).strip():
            errors.append(f"{task_id}.role is required")
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

    ready: list[str] = []
    for task_id, task in tasks.items():
        if task.get("status") != "planned":
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
    print(json.dumps({"status": "pass" if not errors else "fail", "errors": errors, "warnings": warnings, "ready_task_ids": ready}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
