from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent


def source_ref() -> dict:
    return {
        "source_id": "SRC-001",
        "locator": {"kind": "section", "value": "1", "label": "Section 1"},
        "supports": ["correct_answer", "explanation"],
        "support_strength": "direct",
    }


def question(index: int) -> dict:
    return {
        "question_id": f"Q-CH1-{index:03d}",
        "chapter_id": "CH-001",
        "concept_ids": ["concept-id"],
        "objective_ids": ["OBJ-001"],
        "type": "multiple-choice",
        "format": "standalone_mcq" if index <= 8 else "passage_mcq",
        "difficulty": 2 if index <= 8 else 3,
        "prompt": f"Which source-grounded option answers item {index}?",
        "options": [
            {"option_id": "A", "text": f"Misconception {index}"},
            {"option_id": "B", "text": f"Supported answer {index}"},
            {"option_id": "C", "text": f"Adjacent concept {index}"},
            {"option_id": "D", "text": f"Overgeneralization {index}"},
        ],
        "correct_option_id": "B",
        "correct_explanation": f"Section 1 directly supports answer {index}.",
        "distractor_rationales": {
            "A": "Targets a documented misconception.",
            "C": "Confuses an adjacent concept.",
            "D": "Extends the claim beyond its evidence.",
        },
        "source_refs": [source_ref()],
        "quality_status": "validated",
    }


def test_full_publication_fixture_passes_skill_gate_and_app_parser() -> None:
    with tempfile.TemporaryDirectory() as directory:
        studies = Path(directory)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "init_study.py"), "Publishable Course", "--studies-dir", str(studies)],
            check=True,
            capture_output=True,
            text=True,
        )
        course = studies / "publishable-course"

        knowledge = "# Extracted knowledge\n\n## Section 1\n\nA source-grounded statement used by the assessment.\n"
        (course / "source" / "SRC-001.md").write_text(knowledge, encoding="utf-8")
        manifest_path = course / "source-manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["sources"][0]["knowledge_path"] = "source/SRC-001.md"
        manifest["sources"][0]["processing_status"] = "ready"
        manifest["sources"][0]["content_hash"] = "sha256:" + hashlib.sha256(knowledge.encode()).hexdigest()
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

        bank_path = course / "questions" / "question-bank.json"
        bank = {
            "schema_version": "question-bank-v2",
            "source_ref_schema": "source-ref-v1",
            "study_id": yaml.safe_load((course / "study.yaml").read_text(encoding="utf-8"))["study_id"],
            "chapters": [{"chapter_id": "CH-001", "title": "Core chapter", "class": "core", "lesson_path": "lessons/CH-001.md"}],
            "questions": [question(index) for index in range(1, 11)],
        }
        bank_path.write_text(json.dumps(bank, indent=2) + "\n", encoding="utf-8")
        substantive = (
            "# Course material\n\nThis source-grounded chapter explains the central concept, its prerequisite, "
            "a worked example, a common misconception, a practical limitation, and the exact Section 1 locator.\n"
        )
        (course / "lessons" / "CH-001.md").write_text(substantive, encoding="utf-8")
        (course / "study-guide.md").write_text(substantive.replace("Course material", "Study guide"), encoding="utf-8")
        (course / "concept-map.md").write_text(substantive.replace("Course material", "Concept map"), encoding="utf-8")
        (course / "glossary.md").write_text(substantive.replace("Course material", "Glossary"), encoding="utf-8")

        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "create_research_plan.py"), str(course), "--research-workers", "2", "--authorized"],
            check=True,
            capture_output=True,
            text=True,
        )
        plan_path = course / ".work" / "orchestration" / "run-plan.yaml"
        plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
        question_ids = [item["question_id"] for item in bank["questions"]]
        for task in plan["task_graph"]:
            role = task["role"]
            schema = task["required_schema"]
            if role == "contradiction-reviewer":
                output = {"schema_version": schema, "status": "complete", "retained_claim_ids": ["CLM-001"], "rejected_claim_ids": [], "contradictions": [], "gaps": []}
            elif role == "citation-verifier":
                output = {"schema_version": schema, "decision": "verified", "verified_claim_ids": ["CLM-001"], "issues": []}
            elif role == "assessment-generator":
                output = bank
            elif role == "assessment-validator":
                output = {"schema_version": schema, "decision": "approved", "validated_question_ids": question_ids, "rejected_question_ids": [], "issues": []}
            elif role == "research-worker":
                output = {"schema_version": schema, "source_ref_schema": "source-ref-v1", "report_id": task["task_id"], "task_id": task["task_id"], "worker_role": role, "claims": []}
            else:
                output = {"schema_version": schema, "concepts": ["concept-id"], "gaps": []}
            output_path = course / task["output_path"]
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
            completion_path = course / task["completion_path"]
            completion_path.parent.mkdir(parents=True, exist_ok=True)
            completion_path.write_text(json.dumps({
                "schema_version": "completion-envelope-v1",
                "task_id": task["task_id"],
                "status": "submitted",
                "output_path": task["output_path"],
            }, indent=2) + "\n", encoding="utf-8")
            task["status"] = "submitted"
        plan_path.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")

        (course / "evidence" / "approved-claims.json").write_text(json.dumps({
            "schema_version": "approved-claims-v1",
            "claims": [{"claim_id": "CLM-001", "claim": "Supported statement.", "source_refs": [source_ref()]}],
        }, indent=2) + "\n", encoding="utf-8")

        build = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_exam.py"), str(course), "--exam-id", "EXAM-001", "--title", "Publishable exam", "--ready"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert build.returncode == 0, build.stdout + build.stderr
        validation = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_study_pack.py"), str(course), "--publication"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert validation.returncode == 0, validation.stdout + validation.stderr

        sys.path.insert(0, str(REPO / "src"))
        from mastery_ledger.exam_service import load_exam
        from mastery_ledger.models import WorkspaceState

        workspace = WorkspaceState(workspace_id="TEST", name="Test", path=str(studies), available=True, writable=True)
        loaded = load_exam(workspace, bank["study_id"], "EXAM-001")
        assert len(loaded.questions) == 10
        assert loaded.questions[0].correct_option_id == "B"


def test_calibration_record_is_bounded_and_workflow_cannot_skip_gates() -> None:
    with tempfile.TemporaryDirectory() as directory:
        studies = Path(directory)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "init_study.py"), "Calibration Course", "--studies-dir", str(studies)],
            check=True,
            capture_output=True,
            text=True,
        )
        course = studies / "calibration-course"
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "record_calibration.py"), "start", str(course), "--count", "8", "--concept-questions", "6", "--scenario-questions", "2", "--disposition", "begin"],
            check=True,
            capture_output=True,
            text=True,
        )
        for index in range(1, 9):
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "record_calibration.py"), "add", str(course), "--question-id", f"CAL-{index}", "--format", "concept" if index <= 6 else "scenario", "--question", f"Visible question {index}", "--learner-answer", f"Visible answer {index}", "--feedback-shown", f"Visible feedback {index}"],
                check=True,
                capture_output=True,
                text=True,
            )
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "record_calibration.py"), "finish", str(course), "--branch", "HELPFUL_SOON:Related topic"],
            check=True,
            capture_output=True,
            text=True,
        )
        calibration = json.loads((course / "progress" / "calibration.json").read_text(encoding="utf-8"))
        assert calibration["status"] == "complete"
        assert len(calibration["interactions"]) == 8
        assert set(calibration["interactions"][0]) >= {"question_shown", "learner_answer", "feedback_shown"}
        assert "reasoning" not in json.dumps(calibration).casefold()

        illegal = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "advance_workflow.py"), str(course), "LEARNING_ACTIVE", "--reason", "skip"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert illegal.returncode != 0
        assert "Illegal workflow transition" in illegal.stderr
        draft = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "advance_workflow.py"), str(course), "DRAFT_UNVERIFIED", "--reason", "Independent workers unavailable"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert draft.returncode == 0, draft.stdout + draft.stderr


def test_provided_source_assessment_plan_starts_with_generator_only() -> None:
    with tempfile.TemporaryDirectory() as directory:
        studies = Path(directory)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "init_study.py"), "Provided Course", "--studies-dir", str(studies)],
            check=True,
            capture_output=True,
            text=True,
        )
        course = studies / "provided-course"
        study_path = course / "study.yaml"
        study = yaml.safe_load(study_path.read_text(encoding="utf-8"))
        study["mode"] = "provided-material-only"
        study_path.write_text(yaml.safe_dump(study, sort_keys=False), encoding="utf-8")
        compiled = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "create_assessment_plan.py"), str(course), "--authorized"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert compiled.returncode == 0, compiled.stdout + compiled.stderr
        checked = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_orchestration.py"), str(course / ".work" / "orchestration" / "run-plan.yaml"), "--course-root", str(course)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert checked.returncode == 0, checked.stdout + checked.stderr
        payload = json.loads(checked.stdout)
        assert payload["ready_task_ids"] == ["TASK-ASSESSMENT-GENERATE"]
