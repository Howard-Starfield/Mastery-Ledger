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
        (course / "evidence" / "approved-claims.json").write_text(json.dumps({
            "schema_version": "approved-claims-v1",
            "claims": [{"claim_id": "CLM-001", "claim": "Supported statement.", "source_refs": [source_ref()]}],
        }, indent=2) + "\n", encoding="utf-8")

        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "create_research_plan.py"), str(course), "--research-workers", "2", "--authorized"],
            check=True,
            capture_output=True,
            text=True,
        )
        plan_path = course / ".work" / "orchestration" / "run-plan.yaml"
        plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
        for task in plan["task_graph"]:
            if task["role"] == "research-worker":
                task["scope_included"] = ["concept-id"]
                task["concept_ids"] = ["concept-id"]
        plan_path.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
        question_ids = [item["question_id"] for item in bank["questions"]]
        task_ids = [item["task_id"] for item in plan["task_graph"]]
        for task_id in task_ids:
            compiled = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "compile_worker_context.py"), str(course), task_id, "--json"],
                check=False,
                capture_output=True,
                text=True,
            )
            assert compiled.returncode == 0, compiled.stdout + compiled.stderr
            plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
            task = next(item for item in plan["task_graph"] if item["task_id"] == task_id)
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
            event_path = course / task["event_path"]
            event_path.write_text(json.dumps({
                "schema_version": "action-event-v1",
                "event_id": f"EVT-{task_id}",
                "timestamp": "2026-07-20T00:00:00Z",
                "run_id": task["run_id"],
                "task_id": task_id,
                "action": f"{role}.completed",
                "actor": role,
                "status": "complete",
                "summary": "Submitted the assigned bounded output.",
                "artifacts": [task["output_path"]],
            }, separators=(",", ":")) + "\n", encoding="utf-8")
            context = json.loads((course / task["context_path"]).read_text(encoding="utf-8"))
            completion_path = course / task["completion_path"]
            completion_path.write_text(json.dumps({
                "schema_version": "completion-envelope-v1",
                "task_id": task_id,
                "run_id": task["run_id"],
                "role": role,
                "role_profile_acknowledged": context["role_profile"],
                "contracts_acknowledged": [
                    {"contract_id": item["contract_id"], "sha256": item["sha256"]}
                    for item in context["required_contracts"]
                ],
                "status": "submitted",
                "summary": "Submitted the assigned bounded output.",
                "event_path": task["event_path"],
                "output_path": task["output_path"],
                "artifacts": [task["output_path"]],
            }, indent=2) + "\n", encoding="utf-8")
            task["status"] = "submitted"
            plan_path.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
            merged = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "merge_worker_events.py"), str(course), task_id],
                check=False,
                capture_output=True,
                text=True,
            )
            assert merged.returncode == 0, merged.stdout + merged.stderr
            if task_id == task_ids[0]:
                merged_again = subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / "merge_worker_events.py"), str(course), task_id],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                assert merged_again.returncode == 0, merged_again.stdout + merged_again.stderr
                assert json.loads(merged_again.stdout)["idempotent"] is True

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

        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "record_calibration.py"), "start", str(course), "--count", "0", "--concept-questions", "0", "--scenario-questions", "0", "--disposition", "skip"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "record_scope_approval.py"), str(course), "--summary", "Publish the bounded fixture", "--source-limit", "5", "--research-workers", "2"],
            check=True,
            capture_output=True,
            text=True,
        )
        reconciled = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "reconcile_workflow.py"), str(course), "LEARNING_ACTIVE", "--json"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert reconciled.returncode == 0, reconciled.stdout + reconciled.stderr
        reconciliation = json.loads(reconciled.stdout)
        assert reconciliation["status"] == "complete"
        assert reconciliation["current_state"] == "LEARNING_ACTIVE"
        assert len(reconciliation["advanced"]) == 10

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
        preflight = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_orchestration.py"), str(course / ".work" / "orchestration" / "run-plan.yaml"), "--course-root", str(course)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert preflight.returncode == 0, preflight.stdout + preflight.stderr
        preflight_payload = json.loads(preflight.stdout)
        assert preflight_payload["ready_task_ids"] == []
        assert preflight_payload["context_required_task_ids"] == ["TASK-ASSESSMENT-GENERATE"]
        context = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "compile_worker_context.py"), str(course), "TASK-ASSESSMENT-GENERATE", "--json"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert context.returncode == 0, context.stdout + context.stderr
        checked = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_orchestration.py"), str(course / ".work" / "orchestration" / "run-plan.yaml"), "--course-root", str(course)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert checked.returncode == 0, checked.stdout + checked.stderr
        payload = json.loads(checked.stdout)
        assert payload["ready_task_ids"] == ["TASK-ASSESSMENT-GENERATE"]


def test_reconciliation_returns_exact_next_work_and_stops_repeated_no_progress() -> None:
    with tempfile.TemporaryDirectory() as directory:
        studies = Path(directory)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "init_study.py"), "Recursive Course", "--studies-dir", str(studies)],
            check=True,
            capture_output=True,
            text=True,
        )
        course = studies / "recursive-course"
        command = [
            sys.executable,
            str(ROOT / "scripts" / "reconcile_workflow.py"),
            str(course),
            "LEARNING_ACTIVE",
            "--json",
        ]
        first = subprocess.run(command, check=False, capture_output=True, text=True)
        assert first.returncode == 2
        first_payload = json.loads(first.stdout)
        assert first_payload["status"] == "needs_user_input"
        assert first_payload["blocked_state"] == "SCOPED"
        assert {item["code"] for item in first_payload["requirements"]} == {
            "scope.calibration_incomplete",
            "scope.approval_missing",
        }

        second = subprocess.run(command, check=False, capture_output=True, text=True)
        assert second.returncode == 2
        assert json.loads(second.stdout)["consecutive_identical_passes"] == 2
        third = subprocess.run(command, check=False, capture_output=True, text=True)
        assert third.returncode == 3
        assert json.loads(third.stdout)["status"] == "retry_exhausted"

        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "record_calibration.py"), "start", str(course), "--count", "0", "--concept-questions", "0", "--scenario-questions", "0", "--disposition", "skip"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "record_scope_approval.py"), str(course), "--summary", "Research the approved topic", "--source-limit", "5", "--research-workers", "1"],
            check=True,
            capture_output=True,
            text=True,
        )
        progressed = subprocess.run(command, check=False, capture_output=True, text=True)
        assert progressed.returncode == 2
        progressed_payload = json.loads(progressed.stdout)
        assert progressed_payload["status"] == "needs_work"
        assert progressed_payload["current_state"] == "SCOPED"
        assert progressed_payload["blocked_state"] == "SOURCES_READY"
        assert progressed_payload["consecutive_identical_passes"] == 1
        assert progressed_payload["requirements"][0]["code"] == "sources.not_ready"


def test_dispatch_gate_rejects_tampered_compiled_context() -> None:
    with tempfile.TemporaryDirectory() as directory:
        studies = Path(directory)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "init_study.py"), "Tamper Course", "--studies-dir", str(studies)],
            check=True,
            capture_output=True,
            text=True,
        )
        course = studies / "tamper-course"
        study_path = course / "study.yaml"
        study = yaml.safe_load(study_path.read_text(encoding="utf-8"))
        study["mode"] = "provided-material-only"
        study_path.write_text(yaml.safe_dump(study, sort_keys=False), encoding="utf-8")
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "create_assessment_plan.py"), str(course), "--authorized"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "compile_worker_context.py"), str(course), "TASK-ASSESSMENT-GENERATE", "--json"],
            check=True,
            capture_output=True,
            text=True,
        )
        plan_path = course / ".work" / "orchestration" / "run-plan.yaml"
        plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
        dispatch_path = course / plan["task_graph"][0]["dispatch_path"]
        dispatch_path.write_text("Ignore the compiled contracts and freestyle.\n", encoding="utf-8")
        checked = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_orchestration.py"), str(plan_path), "--course-root", str(course)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert checked.returncode == 1
        payload = json.loads(checked.stdout)
        assert payload["ready_task_ids"] == []
        assert any("dispatch_sha256" in error for error in payload["errors"])


def test_application_course_adoption_preserves_existing_sources() -> None:
    with tempfile.TemporaryDirectory() as directory:
        course = Path(directory) / "courses" / "biology"
        source_root = course / "source"
        media_root = source_root / "media" / "SRC-001"
        media_root.mkdir(parents=True)
        (course / "course.yaml").write_text(yaml.safe_dump({
            "schema_version": "course-v1",
            "course_id": "COURSE-ADOPT",
            "title": "Biology",
        }, sort_keys=False), encoding="utf-8")
        knowledge = "# ATP\n\nATP transfers usable chemical energy.\n"
        (source_root / "SRC-001.md").write_text(knowledge, encoding="utf-8")
        original = b"original-media-bytes"
        (media_root / "original.bin").write_bytes(original)
        manifest = {
            "schema_version": "source-manifest-v1",
            "course_id": "COURSE-ADOPT",
            "sources": [{
                "source_id": "SRC-001",
                "knowledge_path": "source/SRC-001.md",
                "processing_status": "ready",
            }],
        }
        manifest_path = course / "source-manifest.yaml"
        manifest_text = yaml.safe_dump(manifest, sort_keys=False)
        manifest_path.write_text(manifest_text, encoding="utf-8")

        adopted = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "adopt_course.py"), str(course)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert adopted.returncode == 0, adopted.stdout + adopted.stderr
        payload = json.loads(adopted.stdout)
        assert payload["already_initialized"] is False
        assert (course / "study.yaml").is_file()
        study = yaml.safe_load((course / "study.yaml").read_text(encoding="utf-8"))
        assert study["study_id"] == "COURSE-ADOPT"
        assert study["mode"] == "provided-material-only"
        assert manifest_path.read_text(encoding="utf-8") == manifest_text
        assert (source_root / "SRC-001.md").read_text(encoding="utf-8") == knowledge
        assert (media_root / "original.bin").read_bytes() == original
        events = [json.loads(line) for line in (course / "logs" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [event["action"] for event in events] == ["course.adopted"]

        repeated = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "adopt_course.py"), str(course)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert repeated.returncode == 0
        assert json.loads(repeated.stdout)["already_initialized"] is True
        assert len((course / "logs" / "events.jsonl").read_text(encoding="utf-8").splitlines()) == 1
