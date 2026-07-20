from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative: str):
    path = ROOT / relative
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EvidenceAndMasteryTests(unittest.TestCase):
    @staticmethod
    def canonical_question(question_id: str, chapter_id: str, format_name: str) -> dict:
        return {
            "question_id": question_id,
            "chapter_id": chapter_id,
            "concept_ids": ["concept-a"],
            "objective_ids": ["OBJ-1"],
            "type": "multiple-choice",
            "format": format_name,
            "difficulty": 2,
            "prompt": f"What is the supported choice for {question_id}?",
            "options": [
                {"option_id": "A", "text": "First misconception"},
                {"option_id": "B", "text": "Supported answer"},
                {"option_id": "C", "text": "Adjacent concept"},
                {"option_id": "D", "text": "Overgeneralized claim"},
            ],
            "correct_option_id": "B",
            "correct_explanation": "The cited section directly supports option B.",
            "distractor_rationales": {
                "A": "Targets misconception one.",
                "C": "Confuses adjacent concepts.",
                "D": "Overgeneralizes the claim.",
            },
            "source_refs": [{
                "source_id": "SRC-1",
                "locator": {"kind": "section", "value": "1", "label": "Section 1"},
                "supports": ["correct_answer", "explanation"],
                "support_strength": "direct",
            }],
            "quality_status": "validated",
        }

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

    def test_orchestration_gate_orders_contradictions_before_final_citations(self) -> None:
        tool = load_module("validate_orchestration", "scripts/validate_orchestration.py")
        tasks = [
            {
                "task_id": "TASK-RESEARCH",
                "role": "research-worker",
                "status": "submitted",
                "dependencies": [],
                "output_path": ".work/orchestration/reports/research.json",
                "completion_path": ".work/orchestration/completions/research.json",
            },
            {
                "task_id": "TASK-CONTRADICTIONS",
                "role": "contradiction-reviewer",
                "status": "planned",
                "dependencies": ["TASK-RESEARCH"],
                "output_path": ".work/orchestration/reports/contradictions.json",
                "completion_path": ".work/orchestration/completions/contradictions.json",
            },
            {
                "task_id": "TASK-CITATIONS",
                "role": "citation-verifier",
                "status": "planned",
                "dependencies": ["TASK-CONTRADICTIONS"],
                "output_path": ".work/orchestration/reviews/citations.json",
                "completion_path": ".work/orchestration/completions/citations.json",
            },
        ]
        errors, warnings, ready = tool.validate_plan({"task_graph": tasks})
        self.assertEqual([], errors)
        self.assertEqual([], warnings)
        self.assertEqual(["TASK-CONTRADICTIONS"], ready)

        tasks[1]["status"] = "submitted"
        errors, _, ready = tool.validate_plan({"task_graph": tasks})
        self.assertEqual([], errors)
        self.assertEqual(["TASK-CITATIONS"], ready)

    def test_orchestration_gate_orders_assessment_after_citations(self) -> None:
        tool = load_module("validate_orchestration_assessment", "scripts/validate_orchestration.py")
        tasks = [
            {"task_id": "R", "role": "research-worker", "status": "submitted", "dependencies": [], "output_path": ".work/reports/r.json", "completion_path": ".work/completions/r.json"},
            {"task_id": "X", "role": "contradiction-reviewer", "status": "submitted", "dependencies": ["R"], "output_path": ".work/reports/x.json", "completion_path": ".work/completions/x.json"},
            {"task_id": "C", "role": "citation-verifier", "status": "planned", "dependencies": ["X"], "output_path": ".work/reviews/c.json", "completion_path": ".work/completions/c.json"},
            {"task_id": "G", "role": "assessment-generator", "status": "planned", "dependencies": ["C"], "output_path": ".work/reports/g.json", "completion_path": ".work/completions/g.json"},
            {"task_id": "V", "role": "assessment-validator", "status": "planned", "dependencies": ["G"], "output_path": ".work/reviews/v.json", "completion_path": ".work/completions/v.json"},
        ]
        errors, _, ready = tool.validate_plan({"task_graph": tasks})
        self.assertEqual([], errors)
        self.assertEqual(["C"], ready)
        tasks[2]["status"] = "submitted"
        _, _, ready = tool.validate_plan({"task_graph": tasks})
        self.assertEqual(["G"], ready)
        tasks[3]["status"] = "submitted"
        _, _, ready = tool.validate_plan({"task_graph": tasks})
        self.assertEqual(["V"], ready)

    def test_question_bank_enforces_app_schema_and_exact_eighty_twenty_mix(self) -> None:
        tool = load_module("validate_study_pack_mix", "scripts/validate_study_pack.py")
        questions = [
            self.canonical_question(f"Q-{index:02d}", "CH-1", "standalone_mcq" if index <= 8 else "passage_mcq")
            for index in range(1, 11)
        ]
        payload = {
            "source_ref_schema": "source-ref-v1",
            "chapters": [{"chapter_id": "CH-1", "title": "Core", "class": "core", "lesson_path": "lessons/CH-1.md"}],
            "questions": questions,
        }
        errors, _ = tool.validate_question_bank(payload, source_ids={"SRC-1"}, concept_ids={"concept-a"}, publication=True)
        self.assertEqual([], errors)
        payload["questions"][7]["format"] = "passage_mcq"
        errors, _ = tool.validate_question_bank(payload, source_ids={"SRC-1"}, concept_ids={"concept-a"}, publication=True)
        self.assertTrue(any("8 standalone_mcq and 2 passage_mcq" in error for error in errors))
        legacy = self.canonical_question("Q-LEGACY", "CH-1", "standalone_mcq")
        legacy.pop("options")
        legacy.pop("correct_option_id")
        legacy["correct_answer"] = "Supported answer"
        legacy["distractors"] = ["First misconception", "Adjacent concept", "Overgeneralized claim"]
        errors, _ = tool.validate_question_bank({"source_ref_schema": "source-ref-v1", "questions": [legacy]}, source_ids={"SRC-1"}, concept_ids={"concept-a"})
        self.assertTrue(any("exactly four options" in error for error in errors))

    def test_publication_gate_rejects_hollow_learning_active_course(self) -> None:
        tool = load_module("validate_study_pack_regression", "scripts/validate_study_pack.py")
        with tempfile.TemporaryDirectory() as directory:
            studies = Path(directory)
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "init_study.py"), "Hollow Active", "--studies-dir", str(studies)],
                check=True,
                capture_output=True,
                text=True,
            )
            course = studies / "hollow-active"
            study_path = course / "study.yaml"
            study = yaml.safe_load(study_path.read_text(encoding="utf-8"))
            study["workflow_state"] = "LEARNING_ACTIVE"
            study_path.write_text(yaml.safe_dump(study, sort_keys=False), encoding="utf-8")
            errors, _ = tool.validate_workspace(course, publication=True)
            self.assertTrue(any("non-empty orchestration task graph" in error for error in errors))
            self.assertTrue(any("action log" in error for error in errors))
            self.assertTrue(any("ready exam" in error for error in errors))
            self.assertTrue(any("extracted knowledge" in error for error in errors))

    def test_orchestration_gate_rejects_early_verifier_and_workspace_clutter(self) -> None:
        tool = load_module("validate_orchestration_invalid", "scripts/validate_orchestration.py")
        tasks = [
            {
                "task_id": "TASK-RESEARCH",
                "role": "research-worker",
                "status": "in_progress",
                "dependencies": [],
                "output_path": "reports/research.json",
                "completion_path": ".work/orchestration/completions/research.json",
            },
            {
                "task_id": "TASK-CITATIONS",
                "role": "citation-verifier",
                "status": "in_progress",
                "dependencies": ["TASK-RESEARCH"],
                "output_path": ".work/orchestration/reviews/citations.json",
                "completion_path": ".work/orchestration/completions/citations.json",
            },
        ]
        errors, _, ready = tool.validate_plan({"task_graph": tasks})
        self.assertEqual([], ready)
        self.assertTrue(any("under .work" in error for error in errors))
        self.assertTrue(any("contradiction-reviewer" in error for error in errors))
        self.assertTrue(any("before dependencies" in error for error in errors))

    def test_orchestration_gate_requires_matching_completion_envelopes(self) -> None:
        tool = load_module("validate_orchestration_envelopes", "scripts/validate_orchestration.py")
        with tempfile.TemporaryDirectory() as directory:
            studies = Path(directory)
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "init_study.py"), "Envelope Course", "--studies-dir", str(studies)],
                check=True,
                capture_output=True,
                text=True,
            )
            course_root = studies / "envelope-course"
            study_path = course_root / "study.yaml"
            study = yaml.safe_load(study_path.read_text(encoding="utf-8"))
            study["mode"] = "provided-material-only"
            study_path.write_text(yaml.safe_dump(study, sort_keys=False), encoding="utf-8")
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "create_assessment_plan.py"), str(course_root), "--authorized"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "compile_worker_context.py"), str(course_root), "TASK-ASSESSMENT-GENERATE", "--json"],
                check=True,
                capture_output=True,
                text=True,
            )
            plan_path = course_root / ".work" / "orchestration" / "run-plan.yaml"
            plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
            task = plan["task_graph"][0]
            output = course_root / task["output_path"]
            completion = course_root / task["completion_path"]
            event = course_root / task["event_path"]
            output.write_text('{"schema_version":"question-bank-v2"}\n', encoding="utf-8")
            event.write_text(json.dumps({
                "schema_version": "action-event-v1",
                "event_id": "EVT-ENVELOPE",
                "timestamp": "2026-07-20T00:00:00Z",
                "run_id": task["run_id"],
                "task_id": task["task_id"],
                "action": "assessment.generated",
                "actor": task["role"],
                "status": "complete",
                "summary": "Generated the assigned assessment draft.",
            }) + "\n", encoding="utf-8")
            context = json.loads((course_root / task["context_path"]).read_text(encoding="utf-8"))
            completion.write_text(
                json.dumps(
                    {
                        "schema_version": "completion-envelope-v1",
                        "task_id": task["task_id"],
                        "run_id": task["run_id"],
                        "role": task["role"],
                        "role_profile_acknowledged": context["role_profile"],
                        "contracts_acknowledged": [
                            {"contract_id": item["contract_id"], "sha256": item["sha256"]}
                            for item in context["required_contracts"]
                        ],
                        "status": "submitted",
                        "summary": "Submitted the assigned assessment draft.",
                        "event_path": task["event_path"],
                        "output_path": task["output_path"],
                    }
                ),
                encoding="utf-8",
            )
            task["status"] = "submitted"
            plan_path.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
            errors, _, ready = tool.validate_plan(plan, course_root=course_root)
            self.assertEqual([], errors)
            self.assertEqual([], ready)

            completion.write_text("{}", encoding="utf-8")
            errors, _, ready = tool.validate_plan(plan, course_root=course_root)
            self.assertEqual([], ready)
            self.assertTrue(any("completion-envelope-v1" in error for error in errors))

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
