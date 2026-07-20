#!/usr/bin/env python3
"""Advance study.yaml through one allowed transition after its gate passes."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from record_action import append_event
from validate_orchestration import SUBMITTED_STATES, validate_plan
from validate_study_pack import validate_workspace

ORDER = [
    "INTAKE", "SCOPED", "SOURCES_READY", "CORPUS_MAPPED", "TASKS_PLANNED",
    "EVIDENCE_SUBMITTED", "EVIDENCE_VERIFIED", "EVIDENCE_APPROVED",
    "STUDY_PACK_DRAFTED", "STUDY_PACK_VALIDATED", "LEARNING_ACTIVE",
]
RESEARCH_MODES = {"topic-research", "hybrid"}


def normalize(value: object) -> str:
    return str(value or "").strip().replace("-", "_").upper()


def atomic_yaml(path: Path, payload: dict[str, Any]) -> None:
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


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def requirement(
    code: str,
    message: str,
    *,
    workflow: str,
    action: str,
    user_input_required: bool = False,
    artifacts: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "workflow": workflow,
        "action": action,
        "user_input_required": user_input_required,
        "artifacts": artifacts or [],
    }


def _source_requirements(root: Path, mode: str) -> list[dict[str, Any]]:
    manifest = _read_yaml(root / "source-manifest.yaml")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        return [requirement(
            "sources.none",
            "No source candidates are recorded in source-manifest.yaml.",
            workflow="ingest-material.md",
            action="Ask for or collect sources within the approved source policy, then register them in the manifest.",
            user_input_required=mode not in RESEARCH_MODES,
            artifacts=["source-manifest.yaml"],
        )]

    problems: list[str] = []
    ready_count = 0
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            problems.append(f"sources[{index}] is not an object")
            continue
        source_id = str(source.get("source_id") or f"sources[{index}]")
        knowledge_path = source.get("knowledge_path")
        digest = str(source.get("content_hash", ""))
        ready = source.get("processing_status") == "ready"
        knowledge_ok = False
        if isinstance(knowledge_path, str) and knowledge_path.startswith("source/") and knowledge_path.endswith(".md"):
            candidate = (root / knowledge_path).resolve(strict=False)
            try:
                candidate.relative_to((root / "source").resolve())
            except ValueError:
                pass
            else:
                knowledge_ok = candidate.is_file() and not candidate.is_symlink() and len(candidate.read_text(encoding="utf-8").strip()) >= 20
        hash_ok = re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest) is not None
        if ready and knowledge_ok and hash_ok:
            ready_count += 1
        else:
            missing = []
            if not ready:
                missing.append("processing_status=ready")
            if not knowledge_ok:
                missing.append("non-empty extracted knowledge under source/")
            if not hash_ok:
                missing.append("a real sha256 content hash")
            problems.append(f"{source_id} needs {', '.join(missing)}")
    if ready_count and not problems:
        return []
    return [requirement(
        "sources.not_ready",
        "; ".join(problems) if problems else "No source is ready.",
        workflow="ingest-material.md",
        action="Finish extraction and provenance for each retained source; keep originals under source/media and Markdown knowledge at source/ root.",
        artifacts=["source-manifest.yaml", "source/"],
    )]


def gate_requirements(root: Path, target: str) -> list[dict[str, Any]]:
    """Return observable work still required before ``target`` may be entered."""
    study = _read_yaml(root / "study.yaml")
    mode = str(study.get("mode", ""))
    plan = _read_yaml(root / ".work" / "orchestration" / "run-plan.yaml")
    tasks = plan.get("task_graph", []) if isinstance(plan.get("task_graph"), list) else []

    if target == "SCOPED":
        result: list[dict[str, Any]] = []
        if not str(study.get("learner_goal", "")).strip() or mode not in {
            "provided-material-only", "existing-library", "local-media", "topic-research", "hybrid"
        }:
            result.append(requirement(
                "scope.learning_contract_missing",
                "study.yaml does not contain a complete learning goal and supported source mode.",
                workflow="intake-and-scope.md",
                action="Complete the learning contract in study.yaml and present the scope card.",
                user_input_required=True,
                artifacts=["study.yaml"],
            ))
        if mode in RESEARCH_MODES:
            calibration = _read_json(root / "progress" / "calibration.json")
            if calibration.get("status") not in {"complete", "skipped"}:
                result.append(requirement(
                    "scope.calibration_incomplete",
                    "Research calibration has not been completed or explicitly skipped.",
                    workflow="calibrate-and-authorize.md",
                    action="Announce and finish the bounded calibration, or record the learner's explicit skip.",
                    user_input_required=True,
                    artifacts=["progress/calibration.json"],
                ))
        approval = study.get("scope_approval")
        if not isinstance(approval, dict) or approval.get("status") != "approved":
            result.append(requirement(
                "scope.approval_missing",
                "The learner-approved scope, source limit, and worker budget are not recorded.",
                workflow="intake-and-scope.md",
                action="Present the scope and topology card; after explicit approval, record it with record_scope_approval.py.",
                user_input_required=True,
                artifacts=["study.yaml"],
            ))
        return result

    if target == "SOURCES_READY":
        return _source_requirements(root, mode)

    if target == "CORPUS_MAPPED":
        if mode not in RESEARCH_MODES:
            return []
        mapper_tasks = [task for task in tasks if isinstance(task, dict) and task.get("role") == "corpus-mapper"]
        if not mapper_tasks:
            return [requirement(
                "corpus.mapper_missing",
                "The authorized research plan has no corpus-mapper task.",
                workflow="orchestrate-research.md",
                action="Compile the approved plan with create_research_plan.py, validate it, and dispatch only TASK-MAP.",
                artifacts=[".work/orchestration/run-plan.yaml"],
            )]
        unfinished = [str(task.get("task_id")) for task in mapper_tasks if task.get("status") not in SUBMITTED_STATES]
        if unfinished:
            return [requirement(
                "corpus.mapper_unfinished",
                "Corpus mapping is unfinished: " + ", ".join(unfinished),
                workflow="orchestrate-research.md",
                action="Run the ready corpus-mapper task, route its completion envelope, update its observable status, and rerun reconciliation.",
                artifacts=[".work/orchestration/run-plan.yaml"],
            )]
        return []

    if target == "TASKS_PLANNED":
        errors, _, _ = validate_plan(plan, course_root=root)
        if errors or not tasks:
            return [requirement(
                "tasks.plan_invalid",
                "; ".join(errors or ["task graph is empty"]),
                workflow="orchestrate-research.md",
                action="Compile or repair the authorized deterministic plan, then run validate_orchestration.py.",
                artifacts=[".work/orchestration/run-plan.yaml"],
            )]
        return []

    if target == "EVIDENCE_SUBMITTED":
        if mode not in RESEARCH_MODES:
            approved = _read_json(root / "evidence" / "approved-claims.json")
            if approved.get("claims"):
                return []
            return [requirement(
                "evidence.provided_claims_missing",
                "No source-grounded claims have been approved from the provided corpus.",
                workflow="verify-evidence.md",
                action="Extract claims with canonical source references, inspect their locators, and record the main-agent-approved set.",
                artifacts=["evidence/approved-claims.json"],
            )]
        required_roles = {"research-worker", "source-extractor", "contradiction-reviewer"}
        required = [task for task in tasks if isinstance(task, dict) and task.get("role") in required_roles]
        unfinished = [str(task.get("task_id")) for task in required if task.get("status") not in SUBMITTED_STATES]
        if not required or unfinished:
            return [requirement(
                "evidence.wave_unfinished",
                "Required research or contradiction work is missing" if not required else "Unfinished tasks: " + ", ".join(unfinished),
                workflow="orchestrate-research.md",
                action="Run validate_orchestration.py, dispatch only ready_task_ids, wait for the whole ready wave, route completions, and rerun.",
                artifacts=[".work/orchestration/run-plan.yaml", ".work/orchestration/completions/"],
            )]
        return []

    if target == "EVIDENCE_VERIFIED":
        if mode not in RESEARCH_MODES:
            return []
        verifiers = [task for task in tasks if isinstance(task, dict) and task.get("role") == "citation-verifier"]
        if len(verifiers) != 1 or verifiers[0].get("status") not in SUBMITTED_STATES:
            return [requirement(
                "evidence.citation_verifier_unfinished",
                "Final citation verification is incomplete.",
                workflow="verify-evidence.md",
                action="After contradiction review, dispatch the one ready citation verifier and route its completion.",
                artifacts=[".work/orchestration/run-plan.yaml"],
            )]
        verifier_output = root / str(verifiers[0].get("output_path", ""))
        decision = _read_yaml(verifier_output) if verifier_output.suffix.casefold() in {".yaml", ".yml"} else _read_json(verifier_output)
        if decision.get("decision") not in {"verified", "approved"}:
            return [requirement(
                "evidence.citation_decision_unverified",
                "The final citation decision is not verified.",
                workflow="verify-evidence.md",
                action="Resolve the verifier's reported issues; do not approve unsupported claims.",
                artifacts=[str(verifiers[0].get("output_path", ""))],
            )]
        return []

    if target == "EVIDENCE_APPROVED":
        approved = _read_json(root / "evidence" / "approved-claims.json")
        if not approved.get("claims"):
            return [requirement(
                "evidence.approved_claims_empty",
                "No main-agent-approved claims exist.",
                workflow="verify-evidence.md",
                action="Review verified evidence, record explicit decisions, and aggregate only approved claims.",
                artifacts=["evidence/approved-claims.json"],
            )]
        return []

    if target == "STUDY_PACK_DRAFTED":
        errors, _ = validate_workspace(root, publication=False)
        if errors:
            return [requirement(
                f"study_pack.draft_error.{index:03d}",
                message,
                workflow="build-study-pack.md",
                action="Repair the draft from approved evidence and rerun validate_study_pack.py.",
            ) for index, message in enumerate(errors, 1)]
        return []

    if target in {"STUDY_PACK_VALIDATED", "LEARNING_ACTIVE"}:
        errors, _ = validate_workspace(root, publication=True)
        if errors:
            return [requirement(
                f"study_pack.publication_error.{index:03d}",
                message,
                workflow="build-study-pack.md",
                action="Repair only the reported publication defect, preserve rejected material under .work, and rerun validation.",
            ) for index, message in enumerate(errors, 1)]
        return []

    return []


def advance_state(root: Path, target: str, *, reason: str) -> tuple[str, str]:
    path = root / "study.yaml"
    study = _read_yaml(path)
    current = normalize(study.get("workflow_state"))
    target = normalize(target)
    if target != "DRAFT_UNVERIFIED" and (
        current not in ORDER or target not in ORDER or ORDER.index(target) != ORDER.index(current) + 1
    ):
        raise ValueError(f"Illegal workflow transition: {current or '<missing>'} -> {target}.")
    missing = gate_requirements(root, target) if target != "DRAFT_UNVERIFIED" else []
    if missing:
        raise ValueError(f"{target} gate failed: " + "; ".join(item["message"] for item in missing))

    now = datetime.now(timezone.utc).isoformat()
    study["workflow_state"] = target
    study["updated_at"] = now
    history = study.setdefault("workflow_history", [])
    history.append({"from": current, "to": target, "at": now, "reason": reason})
    atomic_yaml(path, study)
    append_event(root, {
        "action": "workflow.advance", "actor": "main-agent", "status": "complete",
        "summary": f"Advanced workflow from {current} to {target}.",
        "artifacts": ["study.yaml"], "decision": target, "justification": reason,
    })
    return current, target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    parser.add_argument("target_state")
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    root = args.course_root.resolve()
    try:
        current, target = advance_state(root, args.target_state, reason=args.reason)
    except ValueError as error:
        parser.error(str(error))
    print(yaml.safe_dump({"status": "complete", "from": current, "to": target}, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
