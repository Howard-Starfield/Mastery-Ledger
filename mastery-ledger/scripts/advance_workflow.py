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

from course_paths import APPROVED_CLAIMS, SOURCE, SOURCE_MANIFEST, relative_text
from record_action import append_event
from source_registry import load_manifest, source_errors
from validate_orchestration import SUBMITTED_STATES, validate_plan
from validate_study_pack import validate_learning_materials, validate_workspace

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
            action=f"Repair {relative_text(SOURCE_MANIFEST)} through the deterministic source registration workflow.",
            artifacts=[relative_text(SOURCE_MANIFEST)],
        )]
    problems = source_errors(root, manifest, require_nonempty=True)

    # Hybrid means a supplied anchor plus separately authorized corroboration.
    # Register the anchor first so the scout receives it as bounded context and
    # can avoid returning the same source as its corroborating candidate.
    if mode == "hybrid" and problems:
        return [requirement(
            "sources.anchor_not_ready",
            "; ".join(problems),
            workflow="ingest-material.md",
            action="Extract and register the learner-supplied anchor source before dispatching corroborating source discovery.",
            user_input_required=not manifest.get("sources"),
            artifacts=[relative_text(SOURCE_MANIFEST), relative_text(SOURCE)],
        )]

    if (mode == "hybrid" and not problems) or (mode in RESEARCH_MODES and not manifest.get("sources")):
        plan = _read_yaml(root / ".work" / "orchestration" / "run-plan.yaml")
        scouts = [
            item for item in plan.get("task_graph", [])
            if isinstance(item, dict) and item.get("role") == "source-scout"
        ] if isinstance(plan.get("task_graph"), list) else []
        if not scouts:
            return [requirement(
                "sources.discovery_plan_missing",
                (
                    "The anchor source is ready, but no delegated corroborating source-discovery task exists."
                    if mode == "hybrid"
                    else "No registered source or delegated source-discovery task exists."
                ),
                workflow="research-topic.md",
                action="Compile create_source_discovery_plan.py, compile TASK-SOURCE-SCOUT context, validate the plan, and dispatch only that ready task.",
                artifacts=[".work/orchestration/run-plan.yaml", relative_text(SOURCE_MANIFEST)],
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
        candidates = ledger.get("candidates")
        retained_candidates = [
            item for item in candidates
            if isinstance(item, dict) and str(item.get("recommended_action") or "").strip().casefold() == "retain"
        ] if isinstance(candidates, list) else []
        if not retained_candidates:
            return [requirement(
                "sources.discovery_no_candidates",
                (
                    "Delegated corroboration found no retainable source beyond the supplied anchor."
                    if mode == "hybrid"
                    else "Delegated source discovery found no retainable candidates within the approved scope and budget."
                ),
                workflow="research-topic.md",
                action="Ask the learner to supply a source, approve a bounded source-policy expansion, or accept DRAFT_UNVERIFIED.",
                user_input_required=True,
                artifacts=[str(scouts[0].get("output_path", ""))],
            )]
        anchor_source_ids = {
            str(item)
            for item in plan.get("authorization", {}).get("registered_anchor_source_ids", [])
        }
        registered_locations = {
            str(item.get("original_location") or "").strip().casefold().rstrip("/")
            for item in manifest.get("sources", [])
            if (
                isinstance(item, dict)
                and item.get("original_location")
                and (mode != "hybrid" or str(item.get("source_id")) not in anchor_source_ids)
            )
        }
        retained_locations = {
            str(item.get("url") or "").strip().casefold().rstrip("/")
            for item in retained_candidates
            if item.get("url")
        }
        if not (registered_locations & retained_locations):
            return [requirement(
                "sources.candidates_unregistered",
                (
                    "Corroborating discovery finished, but no retained corroborating candidate has been extracted and registered."
                    if mode == "hybrid"
                    else "Source discovery finished, but no retained candidate has been extracted and registered."
                ),
                workflow="research-topic.md",
                action="Review the accepted source-candidate ledger, extract retained candidates into records/source/SRC-NNN.md, and register each with register_source.py.",
                artifacts=[str(scouts[0].get("output_path", "")), relative_text(SOURCE_MANIFEST), relative_text(SOURCE)],
            )]
        return []
    if not problems:
        return []
    return [requirement(
        "sources.none" if not manifest.get("sources") else "sources.not_ready",
        "; ".join(problems),
        workflow="ingest-material.md",
        action="Extract retained sources, then register each one with register_source.py; keep originals under records/source/media and Markdown knowledge at records/source root.",
        user_input_required=mode not in RESEARCH_MODES and not manifest.get("sources"),
        artifacts=[relative_text(SOURCE_MANIFEST), relative_text(SOURCE)],
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
        # Retained as a compatibility state. The main agent now owns the small
        # course outline; source-scoped extractors provide the evidence map.
        return []

    if target == "TASKS_PLANNED":
        expected_schema = "research-run-plan-v1" if mode in RESEARCH_MODES else "provided-evidence-plan-v1"
        errors, _, _ = validate_plan(plan, course_root=root)
        if plan.get("schema_version") != expected_schema:
            errors = [f"Active plan must use {expected_schema} for mode {mode}; found {plan.get('schema_version') or '<missing>'}"]
        if errors or not tasks:
            provided = mode not in RESEARCH_MODES
            return [requirement(
                "tasks.plan_invalid",
                "; ".join(errors or ["task graph is empty"]),
                workflow="orchestrate-research.md",
                action=(
                    "Compile create_provided_evidence_plan.py, then compile worker contexts and run validate_orchestration.py."
                    if provided
                    else "Compile or repair the authorized deterministic research plan, then run validate_orchestration.py."
                ),
                artifacts=[".work/orchestration/run-plan.yaml"],
            )]
        return []

    if target == "EVIDENCE_SUBMITTED":
        if mode not in RESEARCH_MODES:
            required = [
                task for task in tasks
                if isinstance(task, dict) and task.get("role") == "source-extractor"
            ]
            extractors = [task for task in required if task.get("role") == "source-extractor"]
            unfinished = [str(task.get("task_id")) for task in required if task.get("status") not in SUBMITTED_STATES]
            if extractors and not unfinished:
                return []
            return [requirement(
                "evidence.provided_wave_unfinished",
                "Provided-source extraction is missing" if not extractors else "Unfinished tasks: " + ", ".join(unfinished),
                workflow="orchestrate-research.md",
                action="Compile create_provided_evidence_plan.py when absent; otherwise dispatch only ready task IDs and route every completion.",
                artifacts=[".work/orchestration/run-plan.yaml"],
            )]
        required_roles = {"source-extractor", "contradiction-reviewer"}
        required = [task for task in tasks if isinstance(task, dict) and task.get("role") in required_roles]
        unfinished = [str(task.get("task_id")) for task in required if task.get("status") not in SUBMITTED_STATES]
        if not required or unfinished:
            return [requirement(
                "evidence.wave_unfinished",
                "Required extraction or contradiction work is missing" if not required else "Unfinished tasks: " + ", ".join(unfinished),
                workflow="orchestrate-research.md",
                action="Run manage_worker_runtime.py status, reserve and spawn only dispatch_task_ids one at a time, route each return immediately, close it, and refill the queue.",
                artifacts=[".work/orchestration/run-plan.yaml", ".work/runs/<run-id>/tasks/<task-id>/completion.json"],
            )]
        return []

    if target == "EVIDENCE_VERIFIED":
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
        approved = _read_json(root / APPROVED_CLAIMS)
        if not approved.get("claims"):
            return [requirement(
                "evidence.approved_claims_empty",
                "No main-agent-approved claims exist.",
                workflow="verify-evidence.md",
                action="Review verified evidence, record explicit decisions, and aggregate only approved claims.",
                artifacts=[relative_text(APPROVED_CLAIMS)],
            )]
        return []

    if target == "STUDY_PACK_DRAFTED":
        errors, _ = validate_workspace(root, publication=False)
        errors.extend(validate_learning_materials(root))
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
