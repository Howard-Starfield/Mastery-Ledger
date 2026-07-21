#!/usr/bin/env python3
"""Freeze an accepted corpus map and bind its lanes to research tasks in the same run."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from compile_worker_context import atomic_json
from plan_store import load_active_plan, save_active_plan
from record_action import append_event
from source_registry import load_manifest


def _task_index(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("task_id")): item
        for item in plan.get("task_graph", [])
        if isinstance(item, dict) and item.get("task_id")
    }


def freeze(root: Path) -> dict[str, Any]:
    root = root.resolve()
    plan = load_active_plan(root)
    tasks = _task_index(plan)
    mapper = tasks.get("TASK-MAP")
    if mapper is None or mapper.get("status") not in {"submitted", "verified", "approved", "merged"}:
        raise ValueError("TASK-MAP must have an accepted completion before freezing")
    unfinished_extractors = [
        str(item.get("task_id"))
        for item in tasks.values()
        if item.get("role") == "source-extractor" and item.get("status") not in {"submitted", "verified", "approved", "merged"}
    ]
    if unfinished_extractors:
        raise ValueError("Every source extractor in the first wave must be accepted before freezing: " + ", ".join(unfinished_extractors))
    output_path = root / str(mapper.get("output_path"))
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read corpus map: {error}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != "corpus-map-v1":
        raise ValueError("Corpus map must use corpus-map-v1")
    concepts = payload.get("concepts")
    lanes = payload.get("proposed_tasks")
    if not isinstance(concepts, list) or not concepts:
        raise ValueError("Corpus map must propose at least one concept")
    if not isinstance(lanes, list):
        raise ValueError("Corpus map must contain proposed_tasks")
    research = [item for item in tasks.values() if item.get("role") == "research-worker"]
    if len(lanes) != len(research):
        raise ValueError(f"Corpus map proposed {len(lanes)} lanes; approved plan requires {len(research)}")
    known_concepts = {
        str(item.get("concept_id"))
        for item in concepts
        if isinstance(item, dict) and item.get("concept_id")
    }
    known_sources = {
        str(item.get("source_id"))
        for item in load_manifest(root).get("sources", [])
        if isinstance(item, dict) and item.get("source_id")
    }
    if not known_concepts:
        raise ValueError("Corpus map concepts require stable concept_id values")
    lane_index = {
        str(item.get("task_id")): item
        for item in lanes
        if isinstance(item, dict) and item.get("task_id")
    }
    if set(lane_index) != {str(item["task_id"]) for item in research}:
        raise ValueError("Corpus map proposed_tasks must name each pre-authorized research task exactly once")
    for task in research:
        lane = lane_index[str(task["task_id"])]
        concept_ids = [str(item) for item in lane.get("concept_ids", [])]
        source_ids = [str(item) for item in lane.get("source_ids", [])]
        if not concept_ids or not set(concept_ids).issubset(known_concepts):
            raise ValueError(f"{task['task_id']} has missing or unknown concept IDs")
        if not source_ids or not set(source_ids).issubset(known_sources):
            raise ValueError(f"{task['task_id']} has missing or unknown source IDs")
        task["objective"] = str(lane.get("objective") or task["objective"])
        task["scope_included"] = [str(item) for item in lane.get("scope_included", [])] or concept_ids
        task["scope_excluded"] = list(dict.fromkeys([
            *[str(item) for item in task.get("scope_excluded", [])],
            *[str(item) for item in lane.get("scope_excluded", [])],
        ]))
        task["concept_ids"] = concept_ids
        task["input_source_ids"] = source_ids
        task["source_limit"] = len(source_ids)
        task["context_status"] = "pending"
        task["status"] = "planned"
    mapper["status"] = "approved"
    mapper["approved_at"] = datetime.now(timezone.utc).isoformat()
    frozen_relative = f".work/runs/{plan['run_id']}/frozen-corpus-map.json"
    atomic_json(root / frozen_relative, payload)
    plan["frozen_corpus_map_path"] = frozen_relative
    plan["workflow_state"] = "corpus_mapped"
    plan["updated_at"] = mapper["approved_at"]
    save_active_plan(root, plan)
    append_event(root, {
        "action": "research.map.frozen",
        "actor": "main-agent",
        "status": "complete",
        "summary": f"Frozen the accepted corpus map and bound {len(research)} research lanes.",
        "artifacts": [frozen_relative, ".work/orchestration/run-plan.yaml"],
        "decision": "approved",
        "justification": "Every lane uses approved concepts and registered source IDs from the accepted mapper output.",
        "run_id": plan.get("run_id"),
        "task_id": "TASK-MAP",
    })
    return {
        "status": "complete",
        "run_id": plan.get("run_id"),
        "frozen_corpus_map_path": frozen_relative,
        "context_required_task_ids": [str(item["task_id"]) for item in research],
        "ready_task_ids": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    args = parser.parse_args()
    try:
        payload = freeze(args.course_root)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
