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
        run_script("init_study.py", "Clean Course", "--mode", "provided-material-only", "--studies-dir", directory)
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
        run_script("init_study.py", "Provided Course", "--mode", "provided-material-only", "--studies-dir", directory)
        course = Path(directory) / "provided-course"
        study_path = course / "study.yaml"
        study = yaml.safe_load(study_path.read_text(encoding="utf-8"))
        study["workflow_state"] = "CORPUS_MAPPED"
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
        assert roles == ["source-extractor", "source-extractor", "citation-verifier"]
        verifier = next(task for task in plan["task_graph"] if task["role"] == "citation-verifier")
        extractor_ids = {task["task_id"] for task in plan["task_graph"] if task["role"] == "source-extractor"}
        assert set(verifier["dependencies"]) == extractor_ids
        assert plan["execution_requirements"]["normal_active_limit"] == 3
        assert plan["execution_requirements"]["hard_agent_limit"] == 4


def test_one_source_plan_dispatches_extractor_without_contradiction_review() -> None:
    with tempfile.TemporaryDirectory() as directory:
        run_script("init_study.py", "One Source", "--mode", "provided-material-only", "--studies-dir", directory)
        course = Path(directory) / "one-source"
        run_script(
            "record_scope_approval.py",
            str(course),
            "--summary",
            "Learn from the supplied anchor",
            "--source-limit",
            "1",
            "--research-workers",
            "0",
            "--chapter-count",
            "1",
        )
        knowledge = course / "records" / "source" / "SRC-001.md"
        knowledge.write_text("# Anchor\n\nSubstantive locator-preserving source knowledge.\n", encoding="utf-8")
        run_script(
            "register_source.py",
            str(course),
            "--source-id",
            "SRC-001",
            "--title",
            "Anchor",
            "--location",
            "https://example.invalid/anchor",
            "--knowledge-path",
            "records/source/SRC-001.md",
        )
        reconciled = run_script("reconcile_workflow.py", str(course), "--json", check=False)
        assert reconciled.returncode == 2
        assert json.loads(reconciled.stdout)["current_state"] == "CORPUS_MAPPED"

        run_script("create_provided_evidence_plan.py", str(course), "--authorized")
        plan_path = course / ".work" / "orchestration" / "run-plan.yaml"
        plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
        assert [task["role"] for task in plan["task_graph"]] == ["source-extractor", "citation-verifier"]

        run_script("compile_worker_context.py", str(course), "TASK-EXTRACT-SRC-001", "--json")
        checked = run_script("validate_orchestration.py", str(plan_path), "--course-root", str(course))
        payload = json.loads(checked.stdout)
        assert payload["errors"] == []
        assert payload["ready_task_ids"] == ["TASK-EXTRACT-SRC-001"]


def test_short_outline_cannot_pass_as_a_published_lesson() -> None:
    with tempfile.TemporaryDirectory() as directory:
        run_script("init_study.py", "Short Lesson", "--mode", "provided-material-only", "--studies-dir", directory)
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


def test_study_pack_draft_gate_rejects_initialized_lesson_shell() -> None:
    with tempfile.TemporaryDirectory() as directory:
        run_script("init_study.py", "Draft Gate", "--mode", "provided-material-only", "--studies-dir", directory)
        course = Path(directory) / "draft-gate"
        study_path = course / "study.yaml"
        study = yaml.safe_load(study_path.read_text(encoding="utf-8"))
        study["workflow_state"] = "EVIDENCE_APPROVED"
        study_path.write_text(yaml.safe_dump(study, sort_keys=False), encoding="utf-8")
        blocked = run_script(
            "advance_workflow.py",
            str(course),
            "STUDY_PACK_DRAFTED",
            "--reason",
            "Attempt to advance initialized shells",
            check=False,
        )
        assert blocked.returncode != 0
        assert "substantive learner-facing course map" in blocked.stderr
        assert "source_refs must be non-empty for a substantive lesson" in blocked.stderr
