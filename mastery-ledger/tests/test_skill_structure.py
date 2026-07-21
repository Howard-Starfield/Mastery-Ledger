from __future__ import annotations

import json
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SkillStructureTests(unittest.TestCase):
    def test_required_skill_files_exist(self) -> None:
        required = [
            ROOT / "SKILL.md",
            ROOT / "agents" / "openai.yaml",
            ROOT / "workflows" / "intake-and-scope.md",
            ROOT / "workflows" / "calibrate-and-authorize.md",
            ROOT / "workflows" / "orchestrate-research.md",
            ROOT / "workflows" / "ingest-material.md",
            ROOT / "workflows" / "process-video.md",
            ROOT / "workflows" / "research-topic.md",
            ROOT / "workflows" / "verify-evidence.md",
            ROOT / "workflows" / "build-study-pack.md",
            ROOT / "workflows" / "tutor-and-review.md",
            ROOT / "workflows" / "update-study.md",
            ROOT / "references" / "agent-roles.md",
            ROOT / "references" / "agent-role-profiles.json",
            ROOT / "references" / "artifact-lifecycle.md",
            ROOT / "references" / "event-contract.md",
            ROOT / "references" / "source-policy.md",
            ROOT / "references" / "citation-contract.md",
            ROOT / "references" / "video-transcript-contract.md",
            ROOT / "references" / "task-and-evidence-contract.md",
            ROOT / "references" / "topic-splitting-policy.md",
            ROOT / "references" / "pedagogy.md",
            ROOT / "references" / "lesson-contract.md",
            ROOT / "references" / "assessment-contract.md",
            ROOT / "references" / "mastery-model.md",
            ROOT / "references" / "quality-rubric.md",
            ROOT / "references" / "runtime-portability.md",
            ROOT / "references" / "linkvault-connector.md",
            ROOT / "assets" / "index.md",
            ROOT / "assets" / "completion-envelope.json",
            ROOT / "assets" / "exam.json",
            ROOT / "assets" / "question-bank.md",
            ROOT / "assets" / "lesson.md",
            ROOT / "assets" / "approved-claims.json",
            ROOT / "assets" / "assessment-validation.json",
            ROOT / "assets" / "contradiction-review.json",
            ROOT / "assets" / "corpus-map.json",
            ROOT / "assets" / "citation-review.json",
            ROOT / "assets" / "source-candidate-ledger.json",
            ROOT / "assets" / "source-record.example.yaml",
            ROOT / "scripts" / "compile_worker_context.py",
            ROOT / "scripts" / "register_source.py",
            ROOT / "scripts" / "route_worker_completion.py",
            ROOT / "scripts" / "freeze_corpus_map.py",
            ROOT / "scripts" / "create_source_discovery_plan.py",
            ROOT / "scripts" / "merge_worker_events.py",
            ROOT / "scripts" / "adopt_course.py",
            ROOT / "scripts" / "migrate_course_layout.py",
            ROOT / "scripts" / "validate_lesson.py",
            ROOT / "scripts" / "validation_receipts.py",
        ]
        missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
        self.assertEqual([], missing, f"Missing required files: {missing}")

    def test_skill_frontmatter_is_portable(self) -> None:
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
        self.assertIsNotNone(match, "SKILL.md must begin with YAML frontmatter")
        frontmatter = match.group(1) if match else ""
        keys = re.findall(r"(?m)^([a-zA-Z][a-zA-Z0-9_-]*):", frontmatter)
        self.assertEqual(["name", "description"], keys)
        self.assertRegex(frontmatter, r"(?m)^name: mastery-ledger$")
        self.assertRegex(frontmatter, r"(?m)^description: .+")

    def test_package_uses_mastery_ledger_identity(self) -> None:
        self.assertEqual("mastery-ledger", ROOT.name)
        metadata = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn('display_name: "Mastery Ledger"', metadata)
        self.assertIn("$mastery-ledger", metadata)

    def test_skill_has_no_application_runtime_dependency(self) -> None:
        self.assertFalse((ROOT / "assets" / "runtime-compatibility.json").exists())
        self.assertFalse((ROOT / "workflows" / "runtime-onboarding.md").exists())
        controller = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("mastery-ledger doctor", controller)
        self.assertIn("Never invoke, inspect, install, launch, or configure the Mastery Ledger application", controller)

    def test_linkvault_is_isolated_to_optional_connector(self) -> None:
        allowed = {
            ROOT / "SKILL.md",
            ROOT / "references" / "runtime-portability.md",
            ROOT / "references" / "linkvault-connector.md",
        }
        violations: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or path in allowed or "tests" in path.parts:
                continue
            if path.suffix.lower() not in {".md", ".py", ".yaml", ".yml", ".json"}:
                continue
            content = path.read_text(encoding="utf-8")
            if re.search(r"linkvault", content, re.IGNORECASE):
                violations.append(str(path.relative_to(ROOT)))
        self.assertEqual([], violations, f"LinkVault leaked outside optional connector: {violations}")

    def test_root_controller_stays_small_and_portable(self) -> None:
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(content.splitlines()), 220)
        self.assertNotIn(".claude/skills", content)
        self.assertNotIn(".codex/skills", content)
        self.assertNotIn("confirmed_by", content)

    def test_first_turn_and_runtime_routes_are_explicit(self) -> None:
        controller = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        intake = (ROOT / "workflows" / "intake-and-scope.md").read_text(encoding="utf-8")
        media = (ROOT / "workflows" / "process-video.md").read_text(encoding="utf-8")

        self.assertIn("## First-turn learning gate", controller)
        self.assertIn("ask exactly one open prior-knowledge question and end the turn", controller)
        self.assertIn("If supplied material exists, skip the open question", controller)
        self.assertIn("ask once for the absolute parent directory", controller)
        self.assertIn("deferred tool catalog", controller)
        self.assertIn("not a guessed Boolean in the run plan", controller)
        self.assertIn("Never treat the learner's statements as factual evidence", intake)
        self.assertNotIn("Source Inbox", media)
        self.assertNotIn("application-owned release runtime", media)
        self.assertIn("local application has no source-ingestion API", media)

    def test_run_plan_template_has_requirements_not_capability_guesses(self) -> None:
        plan = (ROOT / "assets" / "run-plan.yaml").read_text(encoding="utf-8")
        self.assertIn("schema_version: run-plan-placeholder-v1", plan)
        self.assertIn("execution_requirements:", plan)
        self.assertNotIn("subagents:", plan)
        self.assertNotIn("parallel_subagents:", plan)

    def test_retired_application_authoring_surfaces_are_absent(self) -> None:
        application_root = ROOT.parent / "src" / "mastery_ledger"
        for name in (
            "ingestion_worker.py",
            "knowledge_service.py",
            "media_processing.py",
            "source_service.py",
        ):
            self.assertFalse((application_root / name).exists(), name)

        database = (application_root / "database.py").read_text(encoding="utf-8")
        models = (application_root / "models.py").read_text(encoding="utf-8")
        package = tomllib.loads((ROOT.parent / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertNotIn("CREATE TABLE IF NOT EXISTS jobs", database)
        self.assertNotIn("class SourceInboxResult", models)
        self.assertNotIn("class KnowledgeWikiResult", models)
        self.assertNotIn("pypdf", "\n".join(package["project"]["dependencies"]))
        self.assertNotIn("python-docx", "\n".join(package["project"]["dependencies"]))

    def test_course_initializer_uses_canonical_clean_layout(self) -> None:
        content = (ROOT / "scripts" / "course_paths.py").read_text(encoding="utf-8")
        self.assertIn('SOURCE_MEDIA = SOURCE / "media"', content)
        self.assertIn('LESSONS = Path("lessons")', content)
        self.assertIn('RUNS = WORK / "runs"', content)
        self.assertIn('QUESTION_BANK = QUESTIONS / "question-bank.json"', content)
        self.assertIn('PROGRESS = Path("progress")', content)
        self.assertIn('QUESTION_BANK_REVIEW = QUESTIONS / "question-bank.md"', content)
        self.assertIn('APPROVED_CLAIMS = EVIDENCE / "approved-claims.json"', content)
        self.assertIn('RECORDS = Path("records")', content)
        self.assertNotIn('Path("wiki")', content)

        self.assertTrue((ROOT / "scripts" / "create_assessment_plan.py").is_file())

    def test_role_profiles_are_bounded_and_versioned(self) -> None:
        payload = json.loads((ROOT / "references" / "agent-role-profiles.json").read_text(encoding="utf-8"))
        self.assertEqual("agent-role-profiles-v1", payload["schema_version"])
        required_roles = {
            "source-scout",
            "corpus-mapper",
            "source-extractor",
            "research-worker",
            "contradiction-reviewer",
            "citation-verifier",
            "assessment-generator",
            "assessment-validator",
        }
        self.assertEqual(required_roles, set(payload["profiles"]))
        for role, profile in payload["profiles"].items():
            self.assertEqual("1.0", profile["version"], role)
            self.assertTrue(profile["mission"], role)
            self.assertTrue(profile["best_practices"], role)
            self.assertTrue(profile["stop_conditions"], role)
            self.assertTrue(profile["prohibited_actions"], role)
            self.assertIn("references/event-contract.md", profile["required_contracts"], role)

    def test_question_template_matches_application_delivery_contract(self) -> None:
        payload = json.loads((ROOT / "assets" / "question-bank.json").read_text(encoding="utf-8"))
        question = payload["questions"][0]
        self.assertEqual("multiple-choice", question["type"])
        self.assertEqual(4, len(question["options"]))
        self.assertIn(question["correct_option_id"], {item["option_id"] for item in question["options"]})
        self.assertNotIn("correct_answer", question)

    def test_direct_references_resolve(self) -> None:
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        links = re.findall(r"\[[^\]]+\]\(([^)]+\.md)\)", content)
        self.assertGreaterEqual(len(links), 15)
        missing = [link for link in links if not (ROOT / link).exists()]
        self.assertEqual([], missing, f"Broken Markdown links: {missing}")


if __name__ == "__main__":
    unittest.main()
