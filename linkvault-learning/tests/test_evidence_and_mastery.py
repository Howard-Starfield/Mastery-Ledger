from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EvidenceAndMasteryTests(unittest.TestCase):
    def test_evidence_validator_rejects_missing_locator(self) -> None:
        tool = load_module("validate_evidence", "scripts/validate_evidence.py")
        sources = {"SRC-1"}
        packet = {
            "source_ref_schema": "source-ref-v1",
            "report_id": "REPORT-1",
            "task_id": "TASK-1",
            "worker_role": "research-worker",
            "claims": [
                {
                    "claim_id": "CLM-1",
                    "concept_ids": ["concept-a"],
                    "claim": "A factual claim.",
                    "claim_type": "source_fact",
                    "source_refs": [{"source_id": "SRC-1", "locator": ""}],
                    "confidence": 0.8,
                    "limitations": [],
                    "counterevidence": [],
                }
            ],
        }
        errors = tool.validate_packet(packet, sources)
        self.assertTrue(any("locator" in error.lower() for error in errors))

    def test_source_ref_v1_accepts_precise_video_locator(self) -> None:
        tool = load_module("validate_evidence_source_ref", "scripts/validate_evidence.py")
        ref = {
            "source_id": "SRC-1",
            "item_id": "LESSON-1",
            "locator": {
                "kind": "timestamp_range",
                "start_ms": 143200,
                "end_ms": 151000,
                "label": "Lesson 1, 00:02:23.200–00:02:31.000",
            },
            "supports": ["correct_answer", "explanation"],
            "support_strength": "direct",
        }
        self.assertEqual([], tool.validate_source_ref(ref, {"SRC-1"}, "source_ref"))

    def test_source_ref_v1_rejects_bare_locator_and_missing_support_target(self) -> None:
        tool = load_module("validate_evidence_bare_ref", "scripts/validate_evidence.py")
        ref = {
            "source_id": "SRC-1",
            "locator": "page 9",
            "supports": [],
            "support_strength": "direct",
        }
        errors = tool.validate_source_ref(ref, {"SRC-1"}, "source_ref")
        self.assertTrue(any("source-ref-v1 object" in error for error in errors))
        self.assertTrue(any("supports" in error for error in errors))

    def test_aggregator_includes_only_main_agent_approved_reports(self) -> None:
        tool = load_module("aggregate_approved_evidence", "scripts/aggregate_approved_evidence.py")
        reports = {
            "REPORT-1": {"report_id": "REPORT-1", "claims": [{"claim_id": "CLM-1"}]},
            "REPORT-2": {"report_id": "REPORT-2", "claims": [{"claim_id": "CLM-2"}]},
        }
        reviews = [
            {"report_id": "REPORT-1", "decision": "approved", "approved_by": "main-agent"},
            {"report_id": "REPORT-2", "decision": "verified", "approved_by": "citation-verifier"},
        ]
        merged, errors = tool.aggregate(reports, reviews)
        self.assertEqual([], errors)
        self.assertEqual(["CLM-1"], [item["claim_id"] for item in merged])

    def test_mastery_update_is_bounded_and_assistance_sensitive(self) -> None:
        tool = load_module("update_mastery", "scripts/update_mastery.py")
        current = {
            "concept_id": "concept-a",
            "proficiency_score": 0.50,
            "confidence_score": 0.50,
            "attempt_count": 2,
            "correct_count": 1,
            "partial_count": 1,
            "assisted_count": 0,
            "application_success_count": 0,
            "misconceptions": [],
            "evidence": [],
        }
        unaided = tool.apply_evaluation(current, {
            "evaluation_id": "EV-1",
            "result": "correct",
            "difficulty": 4,
            "assistance_level": 0,
            "confidence": 0.7,
            "is_application": True,
            "misconceptions": [],
            "evaluated_at": "2026-07-19T00:00:00Z",
        })
        aided = tool.apply_evaluation(current, {
            "evaluation_id": "EV-2",
            "result": "correct",
            "difficulty": 4,
            "assistance_level": 4,
            "confidence": 0.7,
            "is_application": True,
            "misconceptions": [],
            "evaluated_at": "2026-07-19T00:00:00Z",
        })
        self.assertGreater(unaided["proficiency_score"], aided["proficiency_score"])
        self.assertGreaterEqual(unaided["proficiency_score"], 0.0)
        self.assertLessEqual(unaided["proficiency_score"], 1.0)


if __name__ == "__main__":
    unittest.main()
