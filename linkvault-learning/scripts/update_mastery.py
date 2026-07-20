#!/usr/bin/env python3
"""Apply a transparent provisional proficiency update to learner state.

The caller must provide the semantic evaluation. This script only validates and
applies deterministic state changes.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

RESULT_BASE = {
    "correct": 0.12,
    "partial": 0.04,
    "uncertain": -0.03,
    "incorrect": -0.10,
}


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def validate_evaluation(evaluation: dict[str, Any]) -> None:
    required = {"evaluation_id", "result", "difficulty", "assistance_level", "confidence", "evaluated_at"}
    missing = sorted(required - set(evaluation))
    if missing:
        raise ValueError(f"Evaluation missing fields: {missing}")
    if evaluation["result"] not in RESULT_BASE:
        raise ValueError(f"Unknown result: {evaluation['result']}")
    difficulty = int(evaluation["difficulty"])
    assistance = int(evaluation["assistance_level"])
    confidence = float(evaluation["confidence"])
    if not 1 <= difficulty <= 5:
        raise ValueError("difficulty must be between 1 and 5")
    if not 0 <= assistance <= 5:
        raise ValueError("assistance_level must be between 0 and 5")
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    if not isinstance(evaluation.get("misconceptions", []), list):
        raise ValueError("misconceptions must be a list")


def status_for(state: dict[str, Any]) -> str:
    attempts = int(state.get("attempt_count", 0))
    score = float(state.get("proficiency_score", 0.0))
    misconceptions = state.get("misconceptions", [])
    if attempts == 0:
        return "unseen"
    if score < 0.15:
        return "introduced"
    if score < 0.45:
        return "practicing"
    if score < 0.70:
        return "proficient"
    if misconceptions:
        return "needs_reassessment"
    return "stable"


def apply_evaluation(current: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    validate_evaluation(evaluation)
    state = copy.deepcopy(current)
    result = str(evaluation["result"])
    difficulty = int(evaluation["difficulty"])
    assistance = int(evaluation["assistance_level"])
    is_application = bool(evaluation.get("is_application", False))

    delta = RESULT_BASE[result]
    difficulty_multiplier = 0.8 + 0.1 * difficulty
    if delta > 0:
        assistance_multiplier = max(0.25, 1.0 - 0.15 * assistance)
        delta *= difficulty_multiplier * assistance_multiplier
        if is_application and result == "correct":
            delta += 0.03 * assistance_multiplier
    else:
        delta *= difficulty_multiplier

    state["proficiency_score"] = round(clamp(float(state.get("proficiency_score", 0.0)) + delta), 4)
    old_confidence = float(state.get("confidence_score", 0.0))
    stated_confidence = float(evaluation["confidence"])
    state["confidence_score"] = round(clamp(old_confidence + 0.2 * (stated_confidence - old_confidence)), 4)

    state["attempt_count"] = int(state.get("attempt_count", 0)) + 1
    if result == "correct":
        state["correct_count"] = int(state.get("correct_count", 0)) + 1
    elif result == "partial":
        state["partial_count"] = int(state.get("partial_count", 0)) + 1
    if assistance > 0:
        state["assisted_count"] = int(state.get("assisted_count", 0)) + 1
    if is_application and result == "correct":
        state["application_success_count"] = int(state.get("application_success_count", 0)) + 1

    misconceptions = list(state.get("misconceptions", []))
    for item in evaluation.get("misconceptions", []):
        text = str(item).strip()
        if text and text not in misconceptions:
            misconceptions.append(text)
    for resolved in evaluation.get("resolved_misconceptions", []):
        misconceptions = [item for item in misconceptions if item != resolved]
    state["misconceptions"] = misconceptions

    evidence = list(state.get("evidence", []))
    evidence.append(copy.deepcopy(evaluation))
    state["evidence"] = evidence
    state["last_reviewed_at"] = evaluation["evaluated_at"]
    if evaluation.get("next_review_at") is not None:
        state["next_review_at"] = evaluation["next_review_at"]
    state["status"] = status_for(state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--concept-id", required=False)
    args = parser.parse_args()

    state_payload = json.loads(args.state.read_text(encoding="utf-8"))
    evaluation = json.loads(args.evaluation.read_text(encoding="utf-8"))
    concepts = state_payload.get("concepts")
    if not isinstance(concepts, list):
        raise SystemExit("learner progress must contain a concepts list")

    concept_id = args.concept_id or evaluation.get("concept_id")
    if not concept_id:
        raise SystemExit("Provide --concept-id or concept_id in the evaluation")
    index = next((i for i, item in enumerate(concepts) if item.get("concept_id") == concept_id), None)
    if index is None:
        raise SystemExit(f"Concept not found: {concept_id}")

    concepts[index] = apply_evaluation(concepts[index], evaluation)
    temp_path = args.state.with_suffix(args.state.suffix + ".tmp")
    temp_path.write_text(json.dumps(state_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(args.state)
    print(json.dumps({"status": "complete", "concept_id": concept_id, "state": concepts[index]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
