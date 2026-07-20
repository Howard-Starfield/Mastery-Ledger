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
            ROOT / "workflows" / "runtime-onboarding.md",
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
            ROOT / "references" / "assessment-contract.md",
            ROOT / "references" / "mastery-model.md",
            ROOT / "references" / "quality-rubric.md",
            ROOT / "references" / "runtime-portability.md",
            ROOT / "references" / "linkvault-connector.md",
            ROOT / "assets" / "wiki.json",
            ROOT / "assets" / "wiki-page.md",
            ROOT / "assets" / "completion-envelope.json",
            ROOT / "assets" / "exam.json",
            ROOT / "assets" / "question-bank.md",
            ROOT / "assets" / "lesson.md",
            ROOT / "assets" / "approved-claims.json",
            ROOT / "assets" / "assessment-validation.json",
            ROOT / "assets" / "contradiction-review.json",
            ROOT / "assets" / "runtime-compatibility.json",
            ROOT / "scripts" / "compile_worker_context.py",
            ROOT / "scripts" / "merge_worker_events.py",
            ROOT / "scripts" / "adopt_course.py",
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

    def test_runtime_compatibility_asset_matches_application_version(self) -> None:
        compatibility = json.loads(
            (ROOT / "assets" / "runtime-compatibility.json").read_text(encoding="utf-8")
        )
        package = tomllib.loads((ROOT.parent / "pyproject.toml").read_text(encoding="utf-8"))
        version = package["project"]["version"]
        self.assertEqual(version, compatibility["skill_version"])
        self.assertEqual(
            f"mastery-ledger doctor --json --skill-version {version}",
            compatibility["application_command"],
        )
        workflow = (ROOT / "workflows" / "runtime-onboarding.md").read_text(encoding="utf-8")
        self.assertIn(compatibility["application_command"], workflow)

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

    def test_course_initializer_uses_canonical_clean_layout(self) -> None:
        content = (ROOT / "scripts" / "init_study.py").read_text(encoding="utf-8")
        self.assertIn('"source/media"', content)
        self.assertIn('"lessons"', content)
        self.assertIn('"wiki/pages"', content)
        self.assertIn('".work/runs"', content)
        self.assertIn('"questions/question-bank.json"', content)
        self.assertIn('"progress/learner-progress.json"', content)
        self.assertIn('"questions/question-bank.md"', content)
        self.assertIn('"evidence/approved-claims.json"', content)
        self.assertNotIn('"source-notes"', content)
        self.assertNotIn('"orchestration/tasks"', content)

        self.assertTrue((ROOT / "scripts" / "create_assessment_plan.py").is_file())

    def test_role_profiles_are_bounded_and_versioned(self) -> None:
        payload = json.loads((ROOT / "references" / "agent-role-profiles.json").read_text(encoding="utf-8"))
        self.assertEqual("agent-role-profiles-v1", payload["schema_version"])
        required_roles = {
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
