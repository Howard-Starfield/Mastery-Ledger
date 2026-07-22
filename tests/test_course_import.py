from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from mastery_ledger.app import create_app
from mastery_ledger.course_import import CourseImportConflictError, CourseImportError, import_course_zip
from mastery_ledger.models import WorkspaceState
from mastery_ledger.study_service import study_library


@pytest.fixture()
def runtime_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "runtime"
    monkeypatch.setenv("MASTERY_LEDGER_HOME", str(home))
    monkeypatch.setenv("MASTERY_LEDGER_DEFAULT_WORKSPACE", str(tmp_path / "courses"))
    return home


def course_files(*, root: str = "causal-inference", study_id: str = "STUDY-CHATGPT-001") -> dict[str, str]:
    artifact_paths = {
        "course_index": "index.md",
        "source_manifest": "records/source-manifest.yaml",
        "source": "records/source",
        "lessons": "lessons",
        "question_bank": "questions/question-bank.json",
        "question_bank_review": "questions/question-bank.md",
        "learner_progress": "progress/learner-progress.json",
        "approved_claims": "records/evidence/approved-claims.json",
        "contradictions": "records/evidence/contradictions.json",
        "gaps": "records/evidence/gaps.json",
        "validation": "records/evidence/validation",
        "action_log": "records/logs/events.jsonl",
    }
    study = {
        "schema_version": "1.0",
        "layout_schema": "course-layout-v2",
        "bundle_schema": "mastery-ledger-course-bundle-v1",
        "study_id": study_id,
        "title": "Causal Inference",
        "mode": "provided-material-only",
        "workflow_state": "STUDY_PACK_DRAFTED",
        "workflow_target": "LEARNING_ACTIVE",
        "publication_status": "DRAFT_UNVERIFIED",
        "artifact_paths": artifact_paths,
        "created_at": "2026-07-21T00:00:00Z",
        "updated_at": "2026-07-21T00:00:00Z",
    }
    source_ref = {
        "source_id": "SRC-001",
        "locator": {"kind": "paragraph", "value": "1", "label": "paragraph 1"},
        "supports": ["claim"],
        "support_strength": "direct",
    }
    lesson = """---
schema_version: lesson-v1
chapter_id: CH-001
title: Foundations
status: draft
objective_ids: [OBJ-001]
concept_ids: [causal-effect]
prerequisite_chapter_ids: []
estimated_minutes: 8
last_updated: 2026-07-21
source_refs:
  - source_id: SRC-001
    locator: {kind: paragraph, value: "1", label: "paragraph 1"}
    supports: [claim]
    support_strength: direct
---

# Foundations

Causal inference asks what would happen under an intervention rather than merely describing an observed association. This draft lesson connects the distinction to a concrete decision and preserves the inspected source locator for later human review.

## Worked example

Compare an observed outcome with a clearly stated counterfactual question, then identify assumptions and evidence gaps.
"""
    bank = {
        "schema_version": "question-bank-v2",
        "source_ref_schema": "source-ref-v1",
        "study_id": study_id,
        "chapters": [
            {
                "chapter_id": "CH-001",
                "title": "Foundations",
                "class": "core",
                "question_tier": "standard",
                "lesson_path": "lessons/CH-001.md",
            }
        ],
        "questions": [],
    }
    glossary = {
        "schema_version": "course-glossary-v1",
        "course_id": study_id,
        "terms": [
            {
                "term_id": "TERM-001",
                "term": "Causal effect",
                "definition": "The contrast between outcomes under specified alternative interventions.",
                "aliases": [],
                "chapter_ids": ["CH-001"],
                "source_refs": [source_ref],
            }
        ],
    }
    progress = {
        "schema_version": "1.0",
        "study_id": study_id,
        "concepts": [
            {
                "concept_id": "causal-effect",
                "status": "introduced",
                "proficiency_score": 0.0,
                "confidence_score": 0.0,
                "attempt_count": 0,
                "correct_count": 0,
                "partial_count": 0,
                "assisted_count": 0,
                "application_success_count": 0,
                "last_reviewed_at": None,
                "next_review_at": None,
                "misconceptions": [],
                "evidence": [],
            }
        ],
    }
    manifest = {
        "schema_version": "1.0",
        "study_id": study_id,
        "sources": [
            {
                "source_id": "SRC-001",
                "title": "Uploaded notes",
                "source_type": "learner_notes",
                "knowledge_path": "records/source/SRC-001.md",
                "retrieved_at": "2026-07-21",
                "processing_status": "ready",
            }
        ],
    }
    check = {
        "schema_version": "same-agent-check-v1",
        "review_type": "same-agent-recheck",
        "input_artifact_id": "claims-v1",
        "outcome": "pass_self_check",
        "publication_status": "DRAFT_UNVERIFIED",
        "findings": [],
    }
    event = {
        "event_id": "EVT-001",
        "schema_version": "action-event-v1",
        "timestamp": "2026-07-21T00:00:00Z",
        "action": "course.exported",
        "actor": "chatgpt",
        "status": "complete",
        "summary": "Created a DRAFT_UNVERIFIED portable course bundle.",
    }
    prefix = f"{root}/"
    return {
        prefix + "study.yaml": yaml.safe_dump(study, sort_keys=False),
        prefix + "index.md": "# Causal Inference\n\n## Course outcome\n\nDistinguish causal questions from association and identify the evidence needed for an intervention claim.\n\n## Course map\n\n- [Foundations](lessons/CH-001.md)\n",
        prefix + "lessons/CH-001.md": lesson,
        prefix + "lessons/glossary.json": json.dumps(glossary),
        prefix + "questions/question-bank.json": json.dumps(bank),
        prefix + "questions/question-bank.md": "# Question bank\n\nDraft review copy; no ready exam is included.\n",
        prefix + "progress/learner-progress.json": json.dumps(progress),
        prefix + "records/source-manifest.yaml": yaml.safe_dump(manifest, sort_keys=False),
        prefix + "records/source/SRC-001.md": "# Uploaded notes\n\nCausal questions compare outcomes under specified alternative interventions.",
        prefix + "records/evidence/approved-claims.json": json.dumps({"schema_version": "approved-claims-v1", "claims": []}),
        prefix + "records/evidence/contradictions.json": json.dumps({"schema_version": "contradictions-v1", "contradictions": []}),
        prefix + "records/evidence/gaps.json": json.dumps({"schema_version": "gaps-v1", "gaps": []}),
        prefix + "records/evidence/validation/contradiction-check.json": json.dumps(check),
        prefix + "records/evidence/validation/citation-check.json": json.dumps(check),
        prefix + "records/evidence/validation/lesson-check.json": json.dumps(check),
        prefix + "records/evidence/validation/assessment-check.json": json.dumps(check),
        prefix + "records/logs/events.jsonl": json.dumps(event) + "\n",
    }


def zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_imports_complete_draft_bundle_atomically_and_exposes_preview(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = import_course_zip(workspace, zip_bytes(course_files()), filename="causal-inference.zip")

    assert result == {
        "schema_version": "course-import-v1",
        "status": "imported",
        "course_id": "STUDY-CHATGPT-001",
        "title": "Causal Inference",
        "publication_status": "DRAFT_UNVERIFIED",
        "relative_path": "courses/causal-inference",
    }
    target = workspace / "courses" / "causal-inference"
    assert (target / "study.yaml").is_file()
    assert not list((workspace / "courses").glob(".course-import-*"))

    library = study_library(
        WorkspaceState(
            workspace_id="WORKSPACE-001",
            name="Workspace",
            path=str(workspace),
            available=True,
            writable=True,
        )
    )
    assert len(library.courses) == 1
    assert library.courses[0].publication_status == "DRAFT_UNVERIFIED"
    assert library.courses[0].chapters[0].chapter_id == "CH-001"


def test_rejects_path_traversal_without_leaving_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    payload = zip_bytes({"course/../outside.txt": "unsafe"})

    with pytest.raises(CourseImportError, match="Unsafe ZIP path"):
        import_course_zip(workspace, payload, filename="unsafe.zip")

    assert not (workspace / "outside.txt").exists()
    assert not list((workspace / "courses").glob(".course-import-*"))


def test_rejects_multiple_roots_symlinks_and_non_utf8_text(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(CourseImportError, match="exactly one top-level"):
        import_course_zip(
            workspace,
            zip_bytes({"one/study.yaml": "title: One", "two/study.yaml": "title: Two"}),
            filename="two-roots.zip",
        )

    symlink_buffer = io.BytesIO()
    with zipfile.ZipFile(symlink_buffer, "w") as archive:
        link = zipfile.ZipInfo("course/lessons/link.md")
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        archive.writestr(link, "target.md")
    with pytest.raises(CourseImportError, match="Symlinks are not allowed"):
        import_course_zip(workspace, symlink_buffer.getvalue(), filename="symlink.zip")

    utf8_buffer = io.BytesIO()
    with zipfile.ZipFile(utf8_buffer, "w") as archive:
        archive.writestr("course/index.md", b"\xff\xfe")
    with pytest.raises(CourseImportError, match="UTF-8 text"):
        import_course_zip(workspace, utf8_buffer.getvalue(), filename="binary.zip")


def test_rejects_missing_contract_and_duplicate_course(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    incomplete = course_files()
    incomplete.pop("causal-inference/lessons/glossary.json")
    with pytest.raises(CourseImportError, match="missing required files"):
        import_course_zip(workspace, zip_bytes(incomplete), filename="incomplete.zip")

    valid = zip_bytes(course_files())
    import_course_zip(workspace, valid, filename="causal-inference.zip")
    with pytest.raises(CourseImportConflictError, match="already exists"):
        import_course_zip(workspace, valid, filename="causal-inference.zip")


def test_course_import_api_requires_session_and_accepts_raw_zip(
    runtime_home: Path, tmp_path: Path
) -> None:
    app = create_app(session_token="import-session", web_dir=tmp_path / "missing-web")
    workspace = tmp_path / "workspace"
    payload = zip_bytes(course_files())

    with TestClient(app) as client:
        unauthorized = client.post(
            "/api/v1/courses/import?filename=causal-inference.zip",
            content=payload,
            headers={"Content-Type": "application/zip"},
        )
        assert unauthorized.status_code == 401
        client.get("/bootstrap/import-session", follow_redirects=False)
        onboarding = client.post(
            "/api/v1/onboarding/complete",
            json={
                "workspace_path": str(workspace),
                "workspace_name": "Import workspace",
                "language": "en",
                "reduced_motion": False,
                "review_intervals": [1, 3, 7],
            },
        )
        assert onboarding.status_code == 200

        imported = client.post(
            "/api/v1/courses/import?filename=causal-inference.zip",
            content=payload,
            headers={"Content-Type": "application/zip"},
        )
        assert imported.status_code == 201
        assert imported.json()["publication_status"] == "DRAFT_UNVERIFIED"
        library = client.get("/api/v1/study")
        assert library.status_code == 200
        assert library.json()["courses"][0]["course_id"] == "STUDY-CHATGPT-001"
