from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


class PipelineRecoveryTests(unittest.TestCase):
    def run_script(self, name: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / name), *args],
            check=check,
            capture_output=True,
            text=True,
        )

    def initialize(self, parent: Path, *, workers: int = 1) -> Path:
        self.run_script("init_study.py", "Recovery Course", "--studies-dir", str(parent))
        course = parent / "recovery-course"
        self.run_script(
            "record_calibration.py",
            "start",
            str(course),
            "--count",
            "0",
            "--concept-questions",
            "0",
            "--scenario-questions",
            "0",
            "--disposition",
            "skip",
        )
        self.run_script(
            "record_scope_approval.py",
            str(course),
            "--summary",
            "Learn the approved topic",
            "--source-limit",
            "4",
            "--research-workers",
            str(workers),
            "--accepted-branch",
            "approved-branch",
            "--excluded",
            "excluded-branch",
            "--assumed-level",
            "intermediate",
        )
        knowledge = course / "source" / "SRC-001.md"
        knowledge.write_text(
            "# Registered source\n\nA sufficiently substantive extracted source for deterministic testing.\n",
            encoding="utf-8",
        )
        self.run_script(
            "register_source.py",
            str(course),
            "--source-id",
            "SRC-001",
            "--title",
            "Registered source",
            "--location",
            "https://example.invalid/source",
            "--knowledge-path",
            "source/SRC-001.md",
        )
        reconciled = self.run_script("reconcile_workflow.py", str(course), "--json", check=False)
        self.assertEqual(2, reconciled.returncode, reconciled.stdout + reconciled.stderr)
        self.assertEqual("SOURCES_READY", json.loads(reconciled.stdout)["current_state"])
        return course

    def write_worker_return(self, course: Path, task_id: str, output: dict, *, valid_completion: bool) -> None:
        plan = yaml.safe_load((course / ".work" / "orchestration" / "run-plan.yaml").read_text(encoding="utf-8"))
        task = next(item for item in plan["task_graph"] if item["task_id"] == task_id)
        output_path = course / task["output_path"]
        output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
        (course / task["event_path"]).write_text(
            json.dumps(
                {
                    "schema_version": "action-event-v1",
                    "event_id": f"EVT-{task_id}",
                    "timestamp": "2026-07-20T00:00:00Z",
                    "run_id": task["run_id"],
                    "task_id": task_id,
                    "action": f"{task['role']}.completed",
                    "actor": task["role"],
                    "status": "complete",
                    "summary": "Submitted the bounded worker result.",
                    "artifacts": [task["output_path"]],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        completion_path = course / task["completion_path"]
        if valid_completion:
            completion = json.loads((course / task["completion_template_path"]).read_text(encoding="utf-8"))
            completion["summary"] = "Submitted the bounded worker result."
            completion["completed_at"] = "2026-07-20T00:00:00Z"
            completion_path.write_text(json.dumps(completion, indent=2) + "\n", encoding="utf-8")
        else:
            completion_path.write_text("{}\n", encoding="utf-8")

    def test_initialization_is_empty_and_plan_waits_for_registered_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            self.run_script("init_study.py", "Empty Course", "--studies-dir", str(parent))
            course = parent / "empty-course"
            manifest = yaml.safe_load((course / "source-manifest.yaml").read_text(encoding="utf-8"))
            self.assertEqual([], manifest["sources"])
            rejected = self.run_script(
                "create_research_plan.py",
                str(course),
                "--research-workers",
                "1",
                "--authorized",
                check=False,
            )
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn("SOURCES_READY", rejected.stderr)

    def test_source_less_topic_requires_scout_and_links_finished_discovery_to_research(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            self.run_script("init_study.py", "Scout Course", "--studies-dir", str(parent))
            course = parent / "scout-course"
            self.run_script("record_calibration.py", "start", str(course), "--count", "0", "--concept-questions", "0", "--scenario-questions", "0", "--disposition", "skip")
            self.run_script("record_scope_approval.py", str(course), "--summary", "Research with delegated discovery", "--source-limit", "3", "--research-workers", "1")
            missing = self.run_script("reconcile_workflow.py", str(course), "--json", check=False)
            missing_payload = json.loads(missing.stdout)
            self.assertEqual("SCOPED", missing_payload["current_state"])
            self.assertEqual("sources.discovery_plan_missing", missing_payload["requirements"][0]["code"])

            self.run_script("create_source_discovery_plan.py", str(course), "--authorized")
            discovery_plan_path = course / ".work" / "orchestration" / "run-plan.yaml"
            discovery_run = yaml.safe_load(discovery_plan_path.read_text(encoding="utf-8"))["run_id"]
            self.run_script("compile_worker_context.py", str(course), "TASK-SOURCE-SCOUT", "--json")
            plan = yaml.safe_load(discovery_plan_path.read_text(encoding="utf-8"))
            self.assertEqual(
                {"independent_workers": True, "parallelism_required": False},
                plan["execution_requirements"],
            )
            self.assertNotIn("capabilities", plan)
            scout = plan["task_graph"][0]
            context = json.loads((course / scout["context_path"]).read_text(encoding="utf-8"))
            self.assertEqual("source-candidate-ledger-v1", context["required_output_schema"])
            ledger = {
                "schema_version": "source-candidate-ledger-v1",
                "task_id": "TASK-SOURCE-SCOUT",
                "status": "proposed_unapproved",
                "scope_summary": "Research with delegated discovery",
                "candidates": [{"candidate_id": "CAND-001", "title": "Official source", "url": "https://example.invalid/official", "source_type": "official_documentation", "publisher": "Publisher", "published_at": None, "authority_rationale": "Primary source", "coverage": ["approved-topic"], "known_limitations": [], "recommended_action": "retain"}],
                "search_gaps": [],
                "scope_drift": [],
            }
            self.write_worker_return(course, "TASK-SOURCE-SCOUT", ledger, valid_completion=True)
            routed = self.run_script("route_worker_completion.py", str(course), "TASK-SOURCE-SCOUT", check=False)
            self.assertEqual("accepted", json.loads(routed.stdout)["status"])

            knowledge = course / "source" / "SRC-001.md"
            knowledge.write_text("# Official source\n\nExtracted, locator-preserving knowledge from the retained candidate.\n", encoding="utf-8")
            self.run_script("register_source.py", str(course), "--source-id", "SRC-001", "--title", "Official source", "--location", "https://example.invalid/official", "--knowledge-path", "source/SRC-001.md")
            ready = self.run_script("reconcile_workflow.py", str(course), "--json", check=False)
            self.assertEqual("SOURCES_READY", json.loads(ready.stdout)["current_state"])
            self.run_script("create_research_plan.py", str(course), "--research-workers", "1", "--authorized")
            research_plan = yaml.safe_load(discovery_plan_path.read_text(encoding="utf-8"))
            self.assertEqual(discovery_run, research_plan["predecessor_run_id"])
            self.assertTrue((course / ".work" / "runs" / discovery_run / "run-plan.yaml").is_file())

    def test_scope_propagates_and_active_plan_cannot_be_silently_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            course = self.initialize(Path(directory), workers=2)
            self.run_script("create_research_plan.py", str(course), "--research-workers", "2", "--authorized")
            plan_path = course / ".work" / "orchestration" / "run-plan.yaml"
            plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(
                {"independent_workers": True, "parallelism_required": False, "parallelism_preferred": True},
                plan["execution_requirements"],
            )
            self.assertNotIn("capabilities", plan)
            run_id = plan["run_id"]
            mapper = next(item for item in plan["task_graph"] if item["task_id"] == "TASK-MAP")
            self.assertEqual(["approved-branch"], mapper["scope_included"])
            self.assertEqual(["excluded-branch"], mapper["scope_excluded"])
            self.assertEqual(["SRC-001"], mapper["input_source_ids"])
            extractors = [item for item in plan["task_graph"] if item["role"] == "source-extractor"]
            self.assertEqual(1, len(extractors))
            self.assertEqual(["SRC-001"], extractors[0]["input_source_ids"])
            self.assertEqual(1, extractors[0]["source_limit"])
            citation = next(item for item in plan["task_graph"] if item["task_id"] == "TASK-CITATIONS")
            self.assertEqual(["SRC-001"], citation["input_source_ids"])
            self.assertTrue({"TASK-CONTRADICTIONS", "TASK-RESEARCH-01", "TASK-RESEARCH-02"}.issubset(citation["dependencies"]))

            replaced = self.run_script(
                "create_research_plan.py",
                str(course),
                "--research-workers",
                "2",
                "--authorized",
                check=False,
            )
            self.assertNotEqual(0, replaced.returncode)
            self.assertIn("active run already exists", replaced.stderr)
            self.assertEqual(run_id, yaml.safe_load(plan_path.read_text(encoding="utf-8"))["run_id"])

            self.run_script("compile_worker_context.py", str(course), "TASK-MAP", "--json")
            context = json.loads((course / mapper["context_path"]).read_text(encoding="utf-8"))
            proposed = context["output_template"]["proposed_tasks"]
            self.assertEqual(["TASK-RESEARCH-01", "TASK-RESEARCH-02"], [item["task_id"] for item in proposed])

    def test_malformed_completion_repairs_same_run_then_exhausts_to_unverified_draft(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            course = self.initialize(Path(directory), workers=1)
            self.run_script("create_research_plan.py", str(course), "--research-workers", "1", "--authorized")
            plan_path = course / ".work" / "orchestration" / "run-plan.yaml"
            run_id = yaml.safe_load(plan_path.read_text(encoding="utf-8"))["run_id"]
            self.run_script("compile_worker_context.py", str(course), "TASK-MAP", "--json")
            map_output = {
                "schema_version": "corpus-map-v1",
                "run_id": run_id,
                "task_id": "TASK-MAP",
                "worker_role": "corpus-mapper",
                "status": "proposed_unapproved",
                "sources_used": ["SRC-001"],
                "concepts": [{"concept_id": "concept-id", "name": "Concept", "coverage_source_ids": ["SRC-001"], "prerequisite_candidates": [], "ambiguities": [], "gaps": []}],
                "proposed_tasks": [{"task_id": "TASK-RESEARCH-01", "objective": "Investigate the bounded concept.", "scope_included": ["concept-id"], "scope_excluded": ["excluded-branch"], "concept_ids": ["concept-id"], "source_ids": ["SRC-001"]}],
                "ambiguities": [],
                "gaps": [],
            }
            self.write_worker_return(course, "TASK-MAP", map_output, valid_completion=False)
            first = self.run_script("route_worker_completion.py", str(course), "TASK-MAP", check=False)
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            first_payload = json.loads(first.stdout)
            self.assertEqual("changes_required", first_payload["status"])
            self.assertEqual(run_id, first_payload["run_id"])
            self.assertTrue(Path(first_payload["repair_dispatch_path"]).is_file())

            self.write_worker_return(course, "TASK-MAP", map_output, valid_completion=True)
            accepted = self.run_script("route_worker_completion.py", str(course), "TASK-MAP", check=False)
            self.assertEqual(0, accepted.returncode, accepted.stdout + accepted.stderr)
            self.assertEqual("accepted", json.loads(accepted.stdout)["status"])
            self.assertEqual(run_id, yaml.safe_load(plan_path.read_text(encoding="utf-8"))["run_id"])

            extractor_id = "TASK-EXTRACT-SRC-001"
            self.run_script("compile_worker_context.py", str(course), extractor_id, "--json")
            extractor_output = {
                "schema_version": "evidence-packet-v1",
                "source_ref_schema": "source-ref-v1",
                "report_id": f"REPORT-{extractor_id}",
                "task_id": extractor_id,
                "worker_role": "source-extractor",
                "scope": {"included": ["approved-branch"], "excluded": ["excluded-branch"]},
                "sources_used": ["SRC-001"],
                "claims": [],
                "contradictions": [],
                "unresolved_questions": [],
                "suggested_concepts": [],
                "scope_drift": [],
                "quality_notes": [],
            }
            self.write_worker_return(course, extractor_id, extractor_output, valid_completion=True)
            extracted = self.run_script("route_worker_completion.py", str(course), extractor_id, check=False)
            self.assertEqual("accepted", json.loads(extracted.stdout)["status"])
            self.run_script("freeze_corpus_map.py", str(course))
            self.run_script("compile_worker_context.py", str(course), "TASK-RESEARCH-01", "--json")
            research_output = {
                "schema_version": "evidence-packet-v1",
                "source_ref_schema": "source-ref-v1",
                "report_id": "REPORT-TASK-RESEARCH-01",
                "task_id": "TASK-RESEARCH-01",
                "worker_role": "research-worker",
                "scope": {"included": ["concept-id"], "excluded": ["excluded-branch"]},
                "sources_used": ["SRC-001"],
                "claims": [],
                "contradictions": [],
                "unresolved_questions": [],
                "suggested_concepts": [],
                "scope_drift": [],
                "quality_notes": [],
            }
            self.write_worker_return(course, "TASK-RESEARCH-01", research_output, valid_completion=False)
            repair = self.run_script("route_worker_completion.py", str(course), "TASK-RESEARCH-01", check=False)
            self.assertEqual("changes_required", json.loads(repair.stdout)["status"])
            exhausted = self.run_script("route_worker_completion.py", str(course), "TASK-RESEARCH-01", check=False)
            self.assertEqual(3, exhausted.returncode)
            exhausted_payload = json.loads(exhausted.stdout)
            self.assertEqual("retry_exhausted", exhausted_payload["status"])
            self.assertEqual("DRAFT_UNVERIFIED", exhausted_payload["publication_status"])
            study = yaml.safe_load((course / "study.yaml").read_text(encoding="utf-8"))
            self.assertEqual("SOURCES_READY", study["workflow_state"])
            self.assertEqual("DRAFT_UNVERIFIED", study["publication_status"])
            self.assertEqual(run_id, yaml.safe_load(plan_path.read_text(encoding="utf-8"))["run_id"])


if __name__ == "__main__":
    unittest.main()
