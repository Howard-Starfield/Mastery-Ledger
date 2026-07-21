#!/usr/bin/env python3
"""Advance study.yaml through one allowed transition after its gate passes."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from record_action import append_event
from source_registry import load_manifest, source_errors
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
    try:
        manifest = load_manifest(root)
    except ValueError as error:
        return [requirement(
            "sources.manifest_invalid",
            str(error),
            workflow="ingest-material.md",
            action="Repair source-manifest.yaml through the deterministic source registration workflow.",
            artifacts=["source-manifest.yaml"],
        )]
    problems = source_errors(root, manifest, require_nonempty=True)
    if not problems:
        return []
    if mode in RESEARCH_MODES and not manifest.get("sources"):
        plan = _read_yaml(root / ".work" / "orchestration" / "run-plan.yaml")
        scouts = [
            item for item in plan.get("task_graph", [])
            if isinstance(item, dict) and item.get("role") == "source-scout"
        ] if isinstance(plan.get("task_graph"), list) else []
        if not scouts:
            return [requirement(
                "sources.discovery_plan_missing",
                "No registered source or delegated source-discovery task exists.",
                workflow="research-topic.md",
                action="Compile create_source_discovery_plan.py, compile TASK-SOURCE-SCOUT context, validate the plan, and dispatch only that ready task.",
                artifacts=[".work/orchestration/run-plan.yaml", "source-manifest.yaml"],
            )]
        unfinished = [str(item.get("task_id")) for item in scouts if item.get("status") not in SUBMITTED_STATES]
        if unfinished:
            return [requirement(
                "sources.discovery_unfinished",
                "Delegated source discovery is unfinished: " + ", ".join(unfinished),
                workflow="research-topic.md",
                action="Compile or dispatch the returned source-scout task, route its completion, and keep the same run.",
                artifacts=[".work/orchestration/run-plan.yaml"],
            )]
        ledger = _read_json(root / str(scouts[0].get("output_path", "")))
        if not isinstance(ledger.get("candidates"), list) or not ledger.get("candidates"):
            return [requirement(
                "sources.discovery_no_candidates",
                "Delegated source discovery found no retainable candidates within the approved scope and budget.",
                workflow="research-topic.md",
                action="Ask the learner to supply a source, approve a bounded source-policy expansion, or accept DRAFT_UNVERIFIED.",
                user_input_required=True,
                artifacts=[str(scouts[0].get("output_path", ""))],
            )]
        return [requirement(
            "sources.candidates_unregistered",
            "Source discovery finished, but no retained candidate has been extracted and registered.",
            workflow="research-topic.md",
            action="Review the accepted source-candidate ledger, extract retained candidates into source/SRC-NNN.md, and register each with register_source.py.",
            artifacts=[str(scouts[0].get("output_path", "")), "source-manifest.yaml", "source/"],
        )]
    return [requirement(
        "sources.none" if not manifest.get("sources") else "sources.not_ready",
        "; ".join(problems),
        workflow="ingest-material.md",
        action="Extract retained sources, then register each one with register_source.py; keep originals under source/media and Markdown knowledge at source/ root.",
        user_input_required=mode not in RESEARCH_MODES and not manifest.get("sources"),
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
        approval = study.get("learning_contract")
        if (
            not isinstance(approval, dict)
            or approval.get("status") != "approved"
            or not str(approval.get("goal") or "").strip()
            or not isinstance(approval.get("accepted_branches"), list)
            or not isinstance(approval.get("excluded"), list)
            or not isinstance(approval.get("source_limit"), int)
            or not isinstance(approval.get("research_workers"), int)
        ):
            result.append(requirement(
                "scope.approval_missing",
                "The canonical learner-approved goal, branches, exclusions, source limit, and worker budget are not recorded.",
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
        unfinished = [str(task.get("task_id")) for task in mapper_tasks if task.get("status") not in {"approved", "merged"}]
        if unfinished:
            return [requirement(
                "corpus.mapper_unfinished",
                "Corpus mapping has not been accepted and frozen: " + ", ".join(unfinished),
                workflow="orchestrate-research.md",
                action="Run the ready corpus-mapper task, route its completion envelope, review it, and freeze it with freeze_corpus_map.py.",
                artifacts=[".work/orchestration/run-plan.yaml"],
            )]
        frozen = plan.get("frozen_corpus_map_path")
        frozen_path = root / str(frozen or "")
        if not frozen or not frozen_path.is_file() or frozen_path.is_symlink():
            return [requirement(
                "corpus.map_not_frozen",
                "The accepted corpus map has not been frozen into the active run.",
                workflow="orchestrate-research.md",
                action="Run freeze_corpus_map.py after accepting TASK-MAP; do not create a replacement run.",
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
                artifacts=[".work/orchestration/run-plan.yaml", ".work/runs/<run-id>/tasks/<task-id>/completion.json"],
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


def recover_legacy_draft_state(root: Path) -> bool:
    """Move the retired terminal draft state into the resumable publication field."""
    path = root / "study.yaml"
    study = _read_yaml(path)
    if normalize(study.get("workflow_state")) != "DRAFT_UNVERIFIED":
        return False
    prior_state = ""
    reason = "Migrated the legacy terminal draft state."
    for entry in reversed(study.get("workflow_history", [])):
        if not isinstance(entry, dict) or normalize(entry.get("to")) != "DRAFT_UNVERIFIED":
            continue
        candidate = normalize(entry.get("from"))
        if candidate in ORDER:
            prior_state = candidate
            reason = str(entry.get("reason") or reason)
            break
    if not prior_state:
        raise ValueError("Legacy DRAFT_UNVERIFIED state has no recoverable prior workflow state.")

    now = datetime.now(timezone.utc).isoformat()
    study["workflow_state"] = prior_state
    study["publication_status"] = "DRAFT_UNVERIFIED"
    study["publication_blocker"] = reason
    study["updated_at"] = now
    study.setdefault("publication_history", []).append({
        "from": "LEGACY_WORKFLOW_STATE",
        "to": "DRAFT_UNVERIFIED",
        "at": now,
        "reason": reason,
    })
    atomic_yaml(path, study)
    append_event(root, {
        "action": "publication.legacy_draft_migrated", "actor": "workflow-reconciler", "status": "complete",
        "summary": f"Restored primary workflow state {prior_state} and retained the unverified publication label.",
        "artifacts": ["study.yaml"], "decision": "DRAFT_UNVERIFIED", "justification": reason,
    })
    return True


def advance_state(root: Path, target: str, *, reason: str) -> tuple[str, str]:
    path = root / "study.yaml"
    recover_legacy_draft_state(root)
    study = _read_yaml(path)
    current = normalize(study.get("workflow_state"))
    target = normalize(target)
    if target == "DRAFT_UNVERIFIED":
        if current not in ORDER:
            raise ValueError(f"Cannot label publication from unknown workflow state: {current or '<missing>'}.")
        now = datetime.now(timezone.utc).isoformat()
        previous_status = normalize(study.get("publication_status")) or "DRAFT"
        study["publication_status"] = "DRAFT_UNVERIFIED"
        study["publication_blocker"] = reason
        study["updated_at"] = now
        study.setdefault("publication_history", []).append({
            "from": previous_status,
            "to": "DRAFT_UNVERIFIED",
            "at": now,
            "reason": reason,
        })
        atomic_yaml(path, study)
        append_event(root, {
            "action": "publication.mark_unverified", "actor": "main-agent", "status": "complete",
            "summary": f"Marked publication unverified while preserving workflow state {current}.",
            "artifacts": ["study.yaml"], "decision": "DRAFT_UNVERIFIED", "justification": reason,
        })
        return current, target

    if (
        current not in ORDER or target not in ORDER or ORDER.index(target) != ORDER.index(current) + 1
    ):
        raise ValueError(f"Illegal workflow transition: {current or '<missing>'} -> {target}.")
    missing = gate_requirements(root, target)
    if missing:
        raise ValueError(f"{target} gate failed: " + "; ".join(item["message"] for item in missing))

    now = datetime.now(timezone.utc).isoformat()
    study["workflow_state"] = target
    if target == "LEARNING_ACTIVE":
        study["publication_status"] = "READY"
        study.pop("publication_blocker", None)
    elif target == "STUDY_PACK_VALIDATED":
        study["publication_status"] = "VERIFIED"
        study.pop("publication_blocker", None)
    elif normalize(study.get("publication_status")) == "DRAFT_UNVERIFIED":
        study["publication_status"] = "IN_PROGRESS"
        study.pop("publication_blocker", None)
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
    payload = {"status": "complete", "from": current, "to": target}
    if target == "DRAFT_UNVERIFIED":
        payload = {
            "status": "complete",
            "workflow_state": current,
            "publication_status": target,
        }
    print(yaml.safe_dump(payload, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
