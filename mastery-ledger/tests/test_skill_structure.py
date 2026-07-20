from __future__ import annotations

import re
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
            ROOT / "workflows" / "orchestrate-research.md",
            ROOT / "workflows" / "ingest-material.md",
            ROOT / "workflows" / "process-video.md",
            ROOT / "workflows" / "research-topic.md",
            ROOT / "workflows" / "verify-evidence.md",
            ROOT / "workflows" / "build-study-pack.md",
            ROOT / "workflows" / "tutor-and-review.md",
            ROOT / "workflows" / "update-study.md",
            ROOT / "references" / "agent-roles.md",
            ROOT / "references" / "source-policy.md",
            ROOT / "references" / "citation-contract.md",
            ROOT / "references" / "video-transcript-contract.md",
            ROOT / "references" / "task-and-evidence-contract.md",
            ROOT / "references" / "topic-splitting-policy.md",
            ROOT / "references" / "pedagogy.md",
            ROOT / "references" / "mastery-model.md",
            ROOT / "references" / "quality-rubric.md",
            ROOT / "references" / "runtime-portability.md",
            ROOT / "references" / "linkvault-connector.md",
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

    def test_direct_references_resolve(self) -> None:
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        links = re.findall(r"\[[^\]]+\]\(([^)]+\.md)\)", content)
        self.assertGreaterEqual(len(links), 15)
        missing = [link for link in links if not (ROOT / link).exists()]
        self.assertEqual([], missing, f"Broken Markdown links: {missing}")


if __name__ == "__main__":
    unittest.main()
