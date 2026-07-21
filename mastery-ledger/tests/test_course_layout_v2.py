from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def run_script(name: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def test_initializer_creates_v2_without_retired_wiki_artifacts() -> None:
    with tempfile.TemporaryDirectory() as directory:
        run_script("init_study.py", "Clean Course", "--studies-dir", directory)
        course = Path(directory) / "clean-course"
        assert (course / "index.md").is_file()
        assert (course / "records" / "source-manifest.yaml").is_file()
        assert (course / "records" / "source" / "media").is_dir()
        assert (course / "records" / "evidence" / "validation").is_dir()
        assert (course / "records" / "logs" / "events.jsonl").is_file()
        assert not (course / "wiki").exists()
        assert not (course / "study-guide.md").exists()
        assert not (course / "concept-map.md").exists()
        assert not (course / "glossary.md").exists()


def test_legacy_migration_preserves_sources_and_quarantines_retired_content() -> None:
    with tempfile.TemporaryDirectory() as directory:
        course = Path(directory) / "legacy"
        (course / "source" / "media").mkdir(parents=True)
        (course / "evidence").mkdir()
        (course / "logs").mkdir()
        (course / "wiki").mkdir()
        (course / "source" / "SRC-001.md").write_text("# Source\n\nSubstantive extracted knowledge.\n", encoding="utf-8")
        (course / "source-manifest.yaml").write_text(yaml.safe_dump({
            "schema_version": "source-manifest-v1",
            "sources": [{"source_id": "SRC-001", "knowledge_path": "source/SRC-001.md"}],
        }, sort_keys=False), encoding="utf-8")
        (course / "study-guide.md").write_text("# Course index\n\nLegacy map.\n", encoding="utf-8")
        (course / "concept-map.md").write_text("legacy concept map\n", encoding="utf-8")
        (course / "wiki" / "wiki.json").write_text("{}\n", encoding="utf-8")
        (course / "study.yaml").write_text(yaml.safe_dump({"study_id": "STUDY-LEGACY"}), encoding="utf-8")

        migrated = run_script("migrate_course_layout.py", str(course))
        payload = json.loads(migrated.stdout)
        assert payload["already_migrated"] is False
        manifest = yaml.safe_load((course / "records" / "source-manifest.yaml").read_text(encoding="utf-8"))
        assert manifest["sources"][0]["knowledge_path"] == "records/source/SRC-001.md"
        assert (course / "records" / "source" / "SRC-001.md").is_file()
        assert (course / "index.md").is_file()
        backups = list((course / ".work" / "migration-backup").glob("*/concept-map.md"))
        assert len(backups) == 1
        assert list((course / ".work" / "migration-backup").glob("*/wiki/wiki.json"))
        assert (course / "records" / "evidence" / "validation" / "layout-migration.json").is_file()


def test_provided_material_plan_orders_extractors_before_reviewers() -> None:
    with tempfile.TemporaryDirectory() as directory:
        run_script("init_study.py", "Provided Course", "--studies-dir", directory)
        course = Path(directory) / "provided-course"
        study_path = course / "study.yaml"
        study = yaml.safe_load(study_path.read_text(encoding="utf-8"))
        study["mode"] = "provided-material-only"
        study["workflow_state"] = "SOURCES_READY"
        study["learning_contract"] = {
            "status": "approved",
            "approved_at": "2026-07-21T00:00:00Z",
            "goal": "Learn from two provided sources",
            "accepted_branches": ["core-topic"],
            "excluded": [],
            "source_limit": 2,
            "research_workers": 0,
        }
        study_path.write_text(yaml.safe_dump(study, sort_keys=False), encoding="utf-8")
        for source_id in ("SRC-001", "SRC-002"):
            knowledge = course / "records" / "source" / f"{source_id}.md"
            knowledge.write_text(f"# {source_id}\n\nSubstantive locator-preserving source knowledge.\n", encoding="utf-8")
            run_script(
                "register_source.py",
                str(course),
                "--source-id",
                source_id,
                "--title",
                source_id,
                "--location",
                f"https://example.invalid/{source_id}",
                "--knowledge-path",
                f"records/source/{source_id}.md",
            )

        run_script("create_provided_evidence_plan.py", str(course), "--authorized")
        plan = yaml.safe_load((course / ".work" / "orchestration" / "run-plan.yaml").read_text(encoding="utf-8"))
        roles = [task["role"] for task in plan["task_graph"]]
        assert roles == ["source-extractor", "source-extractor", "contradiction-reviewer", "citation-verifier"]
        contradiction = next(task for task in plan["task_graph"] if task["role"] == "contradiction-reviewer")
        verifier = next(task for task in plan["task_graph"] if task["role"] == "citation-verifier")
        extractor_ids = {task["task_id"] for task in plan["task_graph"] if task["role"] == "source-extractor"}
        assert set(contradiction["dependencies"]) == extractor_ids
        assert set(verifier["dependencies"]) == extractor_ids | {contradiction["task_id"]}


def test_short_outline_cannot_pass_as_a_published_lesson() -> None:
    with tempfile.TemporaryDirectory() as directory:
        run_script("init_study.py", "Short Lesson", "--studies-dir", directory)
        course = Path(directory) / "short-lesson"
        checked = run_script(
            "validate_lesson.py",
            str(course / "lessons" / "CH-001.md"),
            "--source-manifest",
            str(course / "records" / "source-manifest.yaml"),
            "--publication",
            check=False,
        )
        assert checked.returncode == 1
        payload = json.loads(checked.stdout)
        assert any("standard publication requires at least 1200" in error for error in payload["errors"])
