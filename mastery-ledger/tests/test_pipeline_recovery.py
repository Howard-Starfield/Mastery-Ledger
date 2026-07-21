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

    def initialize(self, parent: Path) -> Path:
        self.run_script("init_study.py", "Recovery Course", "--mode", "topic-research", "--studies-dir", str(parent))
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
            "0",
            "--accepted-branch",
            "approved-branch",
            "--excluded",
            "excluded-branch",
            "--assumed-level",
            "intermediate",
        )
        knowledge = course / "records" / "source" / "SRC-001.md"
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
            "records/source/SRC-001.md",
        )
        reconciled = self.run_script("reconcile_workflow.py", str(course), "--json", check=False)
        self.assertEqual(2, reconciled.returncode, reconciled.stdout + reconciled.stderr)
        self.assertEqual("CORPUS_MAPPED", json.loads(reconciled.stdout)["current_state"])
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
            self.run_script("init_study.py", "Empty Course", "--mode", "topic-research", "--studies-dir", str(parent))
            course = parent / "empty-course"
            manifest = yaml.safe_load((course / "records" / "source-manifest.yaml").read_text(encoding="utf-8"))
            self.assertEqual([], manifest["sources"])
            rejected = self.run_script(
                "create_research_plan.py",
                str(course),
                "--research-workers",
                "0",
                "--authorized",
                check=False,
            )
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn("SOURCES_READY", rejected.stderr)

    def test_source_less_topic_requires_scout_and_links_finished_discovery_to_research(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            self.run_script("init_study.py", "Scout Course", "--mode", "topic-research", "--studies-dir", str(parent))
            course = parent / "scout-course"
            self.run_script("record_calibration.py", "start", str(course), "--count", "0", "--concept-questions", "0", "--scenario-questions", "0", "--disposition", "skip")
            self.run_script("record_scope_approval.py", str(course), "--summary", "Research with delegated discovery", "--source-limit", "3", "--research-workers", "0")
            missing = self.run_script("reconcile_workflow.py", str(course), "--json", check=False)
            missing_payload = json.loads(missing.stdout)
            self.assertEqual("SCOPED", missing_payload["current_state"])
            self.assertEqual("sources.discovery_plan_missing", missing_payload["requirements"][0]["code"])

            self.run_script("create_source_discovery_plan.py", str(course), "--authorized")
            discovery_plan_path = course / ".work" / "orchestration" / "run-plan.yaml"
            discovery_run = yaml.safe_load(discovery_plan_path.read_text(encoding="utf-8"))["run_id"]
            self.run_script("compile_worker_context.py", str(course), "TASK-SOURCE-SCOUT", "--json")
            plan = yaml.safe_load(discovery_plan_path.read_text(encoding="utf-8"))
            self.assertEqual("capacity_queue", plan["execution_requirements"]["dispatch_mode"])
            self.assertEqual(3, plan["execution_requirements"]["normal_active_limit"])
            self.assertEqual(4, plan["execution_requirements"]["hard_agent_limit"])
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

            knowledge = course / "records" / "source" / "SRC-001.md"
            knowledge.write_text("# Official source\n\nExtracted, locator-preserving knowledge from the retained candidate.\n", encoding="utf-8")
            self.run_script("register_source.py", str(course), "--source-id", "SRC-001", "--title", "Official source", "--location", "https://example.invalid/official", "--knowledge-path", "records/source/SRC-001.md")
            ready = self.run_script("reconcile_workflow.py", str(course), "--json", check=False)
            self.assertEqual("CORPUS_MAPPED", json.loads(ready.stdout)["current_state"])
            self.run_script("create_research_plan.py", str(course), "--research-workers", "0", "--authorized")
            research_plan = yaml.safe_load(discovery_plan_path.read_text(encoding="utf-8"))
            self.assertEqual(discovery_run, research_plan["predecessor_run_id"])
            self.assertTrue((course / ".work" / "runs" / discovery_run / "run-plan.yaml").is_file())

    def test_hybrid_requires_registered_anchor_then_corroborating_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            self.run_script("init_study.py", "Hybrid Course", "--mode", "hybrid", "--studies-dir", str(parent))
            course = parent / "hybrid-course"
            self.run_script("record_calibration.py", "start", str(course), "--count", "0", "--concept-questions", "0", "--scenario-questions", "0", "--disposition", "skip")
            self.run_script("record_scope_approval.py", str(course), "--summary", "Learn from an anchor with bounded corroboration", "--source-limit", "3", "--research-workers", "0")

            anchor = course / "records" / "source" / "SRC-ANCHOR.md"
            anchor.write_text("# Anchor\n\nThe learner-supplied source with stable locators for comparison.\n", encoding="utf-8")
            self.run_script("register_source.py", str(course), "--source-id", "SRC-ANCHOR", "--title", "Anchor", "--location", "https://example.invalid/anchor", "--knowledge-path", "records/source/SRC-ANCHOR.md")

            missing = self.run_script("reconcile_workflow.py", str(course), "--json", check=False)
            missing_payload = json.loads(missing.stdout)
            self.assertEqual("SCOPED", missing_payload["current_state"])
            self.assertEqual("sources.discovery_plan_missing", missing_payload["requirements"][0]["code"])

            self.run_script("create_source_discovery_plan.py", str(course), "--authorized")
            plan_path = course / ".work" / "orchestration" / "run-plan.yaml"
            plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
            scout = plan["task_graph"][0]
            self.assertEqual(["SRC-ANCHOR"], scout["input_source_ids"])
            self.assertEqual(2, scout["source_limit"])
            self.run_script("compile_worker_context.py", str(course), "TASK-SOURCE-SCOUT", "--json")
            context = json.loads((course / scout["context_path"]).read_text(encoding="utf-8"))
            context_paths = {item["path"] for item in context["allowed_inputs"]}
            self.assertIn("records/source/SRC-ANCHOR.md", context_paths)

            ledger = {
                "schema_version": "source-candidate-ledger-v1",
                "task_id": "TASK-SOURCE-SCOUT",
                "status": "proposed_unapproved",
                "scope_summary": "Learn from an anchor with bounded corroboration",
                "candidates": [
                    {
                        "candidate_id": "CAND-DUPLICATE-ANCHOR",
                        "title": "Duplicate anchor",
                        "url": "https://example.invalid/anchor",
                        "source_type": "web_article",
                        "publisher": "Anchor publisher",
                        "published_at": None,
                        "authority_rationale": "Must not satisfy independent corroboration",
                        "coverage": ["approved-topic"],
                        "known_limitations": ["Duplicates the supplied anchor"],
                        "recommended_action": "retain",
                    },
                    {
                        "candidate_id": "CAND-CORROBORATING",
                        "title": "Corroborating official source",
                        "url": "https://example.invalid/corroborating",
                        "source_type": "official_documentation",
                        "publisher": "Official publisher",
                        "published_at": None,
                        "authority_rationale": "Independent authoritative corroboration",
                        "coverage": ["approved-topic"],
                        "known_limitations": [],
                        "recommended_action": "retain",
                    },
                ],
                "search_gaps": [],
                "scope_drift": [],
            }
            self.write_worker_return(course, "TASK-SOURCE-SCOUT", ledger, valid_completion=True)
            routed = self.run_script("route_worker_completion.py", str(course), "TASK-SOURCE-SCOUT", check=False)
            self.assertEqual("accepted", json.loads(routed.stdout)["status"])

            unregistered = self.run_script("reconcile_workflow.py", str(course), "--json", check=False)
            self.assertEqual("sources.candidates_unregistered", json.loads(unregistered.stdout)["requirements"][0]["code"])

            corroborating = course / "records" / "source" / "SRC-CORROBORATING.md"
            corroborating.write_text("# Corroborating source\n\nIndependent extracted evidence with stable locators.\n", encoding="utf-8")
            self.run_script("register_source.py", str(course), "--source-id", "SRC-CORROBORATING", "--title", "Corroborating official source", "--location", "https://example.invalid/corroborating", "--knowledge-path", "records/source/SRC-CORROBORATING.md")

            ready = self.run_script("reconcile_workflow.py", str(course), "--json", check=False)
            self.assertEqual("CORPUS_MAPPED", json.loads(ready.stdout)["current_state"])
            self.run_script("create_research_plan.py", str(course), "--research-workers", "0", "--authorized")
            research_plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
            extractors = [item for item in research_plan["task_graph"] if item["role"] == "source-extractor"]
            self.assertEqual({"SRC-ANCHOR", "SRC-CORROBORATING"}, {item["input_source_ids"][0] for item in extractors})
            self.assertTrue(any(item["role"] == "contradiction-reviewer" for item in research_plan["task_graph"]))

    def test_scope_propagates_and_active_plan_cannot_be_silently_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            course = self.initialize(Path(directory))
            self.run_script("create_research_plan.py", str(course), "--research-workers", "0", "--authorized")
            plan_path = course / ".work" / "orchestration" / "run-plan.yaml"
            plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
            self.assertEqual("capacity_queue", plan["execution_requirements"]["dispatch_mode"])
            self.assertEqual(3, plan["execution_requirements"]["normal_active_limit"])
            self.assertEqual(1, plan["execution_requirements"]["reserve_agent_slots"])
            self.assertNotIn("capabilities", plan)
            run_id = plan["run_id"]
            extractors = [item for item in plan["task_graph"] if item["role"] == "source-extractor"]
            self.assertEqual(1, len(extractors))
            self.assertEqual(["SRC-001"], extractors[0]["input_source_ids"])
            self.assertEqual(1, extractors[0]["source_limit"])
            citation = next(item for item in plan["task_graph"] if item["task_id"] == "TASK-CITATIONS")
            self.assertEqual(["SRC-001"], citation["input_source_ids"])
            self.assertEqual({"TASK-CONTRADICTIONS", extractors[0]["task_id"]}, set(citation["dependencies"]))

            replaced = self.run_script(
                "create_research_plan.py",
                str(course),
                "--research-workers",
                "0",
                "--authorized",
                check=False,
            )
            self.assertNotEqual(0, replaced.returncode)
            self.assertIn("active run already exists", replaced.stderr)
            self.assertEqual(run_id, yaml.safe_load(plan_path.read_text(encoding="utf-8"))["run_id"])

            self.run_script("compile_worker_context.py", str(course), extractors[0]["task_id"], "--json")
            context = json.loads((course / extractors[0]["context_path"]).read_text(encoding="utf-8"))
            self.assertEqual(["SRC-001"], [Path(item["path"]).stem for item in context["allowed_inputs"] if item["path"].endswith("SRC-001.md")])

    def test_malformed_completion_repairs_same_run_then_exhausts_to_unverified_draft(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            course = self.initialize(Path(directory))
            self.run_script("create_research_plan.py", str(course), "--research-workers", "0", "--authorized")
            plan_path = course / ".work" / "orchestration" / "run-plan.yaml"
            run_id = yaml.safe_load(plan_path.read_text(encoding="utf-8"))["run_id"]
            extractor_id = "TASK-EXTRACT-SRC-001"
            self.run_script("compile_worker_context.py", str(course), extractor_id, "--json")
            extractor_output = {
                "schema_version": "evidence-packet-v1", "source_ref_schema": "source-ref-v1",
                "report_id": f"REPORT-{extractor_id}", "task_id": extractor_id, "worker_role": "source-extractor",
                "scope": {"included": ["approved-branch"], "excluded": ["excluded-branch"]},
                "sources_used": ["SRC-001"], "claims": [], "contradictions": [], "unresolved_questions": [],
                "suggested_concepts": [], "scope_drift": [], "quality_notes": [],
            }
            self.write_worker_return(course, extractor_id, extractor_output, valid_completion=False)
            first = self.run_script("route_worker_completion.py", str(course), extractor_id, check=False)
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            first_payload = json.loads(first.stdout)
            self.assertEqual("changes_required", first_payload["status"])
            self.assertEqual(run_id, first_payload["run_id"])
            self.assertTrue(Path(first_payload["repair_dispatch_path"]).is_file())

            self.write_worker_return(course, extractor_id, extractor_output, valid_completion=True)
            accepted = self.run_script("route_worker_completion.py", str(course), extractor_id, check=False)
            self.assertEqual(0, accepted.returncode, accepted.stdout + accepted.stderr)
            self.assertEqual("accepted", json.loads(accepted.stdout)["status"])
            self.assertEqual(run_id, yaml.safe_load(plan_path.read_text(encoding="utf-8"))["run_id"])

            self.run_script("compile_worker_context.py", str(course), "TASK-CONTRADICTIONS", "--json")
            contradiction_output = {"schema_version": "contradiction-review-v1", "status": "complete", "retained_claim_ids": [], "rejected_claim_ids": [], "contradictions": [], "gaps": []}
            self.write_worker_return(course, "TASK-CONTRADICTIONS", contradiction_output, valid_completion=False)
            repair = self.run_script("route_worker_completion.py", str(course), "TASK-CONTRADICTIONS", check=False)
            self.assertEqual("changes_required", json.loads(repair.stdout)["status"])
            exhausted = self.run_script("route_worker_completion.py", str(course), "TASK-CONTRADICTIONS", check=False)
            self.assertEqual(3, exhausted.returncode)
            exhausted_payload = json.loads(exhausted.stdout)
            self.assertEqual("retry_exhausted", exhausted_payload["status"])
            self.assertEqual("DRAFT_UNVERIFIED", exhausted_payload["publication_status"])
            study = yaml.safe_load((course / "study.yaml").read_text(encoding="utf-8"))
            self.assertEqual("CORPUS_MAPPED", study["workflow_state"])
            self.assertEqual("DRAFT_UNVERIFIED", study["publication_status"])
            self.assertEqual(run_id, yaml.safe_load(plan_path.read_text(encoding="utf-8"))["run_id"])


if __name__ == "__main__":
    unittest.main()
