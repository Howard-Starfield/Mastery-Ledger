from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from mastery_ledger.app import create_app
from mastery_ledger.course_import import CourseImportConflictError, CourseImportError, import_course_zip
from mastery_ledger.dashboard import build_dashboard
from mastery_ledger.exam_service import ExamSessionStore
from mastery_ledger.models import WorkspaceState
from mastery_ledger.study_service import study_lesson, study_library


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
        "practice_exam": "exams/PRACTICE-001/exam.json",
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
    assessment_ref = {
        **source_ref,
        "supports": ["question_prompt", "correct_answer", "explanation"],
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
    answer_positions = ["A", "B", "C", "D", "A", "B", "C", "D", "A", "B"]
    questions = [
        {
            "question_id": f"Q-{index_number:03d}",
            "chapter_id": "CH-001",
            "type": "standalone_mcq" if index_number <= 8 else "scenario_mcq",
            "prompt": f"Which answer best applies the causal inference principle in item {index_number}?",
            "options": [
                {
                    "option_id": option_id,
                    "text": f"Option {option_id} for item {index_number}",
                    "rationale": f"Rationale for option {option_id} in item {index_number}.",
                }
                for option_id in ("A", "B", "C", "D")
            ],
            "correct_option_id": answer_positions[index_number - 1],
            "explanation": "The supported answer distinguishes an intervention claim from an observed association.",
            "objective_ids": ["OBJ-001"],
            "concept_ids": ["causal-effect"],
            "source_refs": [assessment_ref],
            "quality_status": "draft",
        }
        for index_number in range(1, 11)
    ]
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
        "questions": questions,
    }
    practice = {
        "schema_version": "exam-v1",
        "exam_id": "PRACTICE-001",
        "course_id": study_id,
        "title": "AI self-checked practice test",
        "status": "practice_ready",
        "verification_status": "self_checked",
        "mastery_eligible": False,
        "question_count": len(questions),
        "estimated_minutes": 15,
        "questions": questions,
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
        prefix + "questions/question-bank.md": "# Question bank\n\nDraft review copy for the included AI self-checked practice test.\n",
        prefix + "exams/PRACTICE-001/exam.json": json.dumps(practice),
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


def add_artifact_hash_manifest(
    files: dict[str, str], *, root: str = "causal-inference"
) -> dict[str, str]:
    prefix = f"{root}/"
    manifest_path = "records/evidence/validation/artifact-hashes.json"
    files[prefix + "records/evidence/claim-ledger.json"] = json.dumps(
        {"schema_version": "claim-ledger-v1", "claims": []}
    )
    source_inputs = ["records/source-manifest.yaml", "records/source/SRC-001.md"]
    check_members = {
        "contradiction-check.json": ["records/evidence/claim-ledger.json", *source_inputs],
        "citation-check.json": [
            "exams/PRACTICE-001/exam.json",
            "lessons/CH-001.md",
            "lessons/glossary.json",
            "questions/question-bank.json",
            "records/evidence/approved-claims.json",
            *source_inputs,
        ],
        "lesson-check.json": [
            "lessons/CH-001.md",
            "records/evidence/approved-claims.json",
            *source_inputs,
        ],
        "assessment-check.json": [
            "exams/PRACTICE-001/exam.json",
            "lessons/CH-001.md",
            "questions/question-bank.json",
            "records/evidence/approved-claims.json",
            *source_inputs,
        ],
    }
    groups = []
    for check_name, paths in check_members.items():
        members = []
        for relative in sorted(paths):
            data = files[prefix + relative].encode("utf-8")
            members.append(
                {
                    "path": relative,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                }
            )
        payload = "".join(f"{item['path']}\t{item['sha256']}\n" for item in members)
        group_id = check_name.removesuffix(".json") + "-inputs-v1"
        group_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        check_path = f"records/evidence/validation/{check_name}"
        receipt = json.loads(files[prefix + check_path])
        receipt["input_artifact_id"] = group_id
        receipt["input_artifact_hash"] = group_hash
        files[prefix + check_path] = json.dumps(receipt)
        groups.append(
            {
                "group_id": group_id,
                "check_path": check_path,
                "members": members,
                "group_sha256": group_hash,
            }
        )

    study = yaml.safe_load(files[prefix + "study.yaml"])
    study["artifact_paths"]["artifact_hashes"] = manifest_path
    files[prefix + "study.yaml"] = yaml.safe_dump(study, sort_keys=False)
    files[prefix + manifest_path] = json.dumps(
        {
            "schema_version": "artifact-hash-manifest-v1",
            "study_id": study["study_id"],
            "hash_algorithm": "sha256",
            "file_digest_recipe": "sha256-raw-bytes-v1",
            "group_digest_recipe": "sorted-path-tab-sha256-lf-v1",
            "groups": groups,
        }
    )
    return files


def write_course_folder(workspace: Path, relative_root: str) -> Path:
    source_root = "causal-inference"
    target_root = workspace.joinpath(*Path(relative_root).parts)
    for bundled_name, content in course_files(root=source_root).items():
        relative = Path(bundled_name).relative_to(source_root)
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return target_root


@pytest.mark.parametrize("relative_root", ["causal-inference", "courses/causal-inference"])
def test_complete_draft_bundle_works_when_placed_directly_in_workspace(
    tmp_path: Path, relative_root: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write_course_folder(workspace, relative_root)
    state = WorkspaceState(
        workspace_id="WORKSPACE-001",
        name="Workspace",
        path=str(workspace),
        available=True,
        writable=True,
    )

    library = study_library(state)

    assert library.warnings == []
    assert [(course.course_id, course.publication_status) for course in library.courses] == [
        ("STUDY-CHATGPT-001", "DRAFT_UNVERIFIED")
    ]
    lesson = study_lesson(state, "STUDY-CHATGPT-001", "CH-001")
    assert lesson.title == "Foundations"
    assert "Causal inference asks" in lesson.content


def test_directly_placed_ai_course_must_pass_the_same_folder_contract(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    course = write_course_folder(workspace, "causal-inference")
    (course / "unexpected.exe").write_bytes(b"not allowed")
    state = WorkspaceState(
        workspace_id="WORKSPACE-001",
        name="Workspace",
        path=str(workspace),
        available=True,
        writable=True,
    )

    library = study_library(state)

    assert library.courses == []
    assert any("Unsupported file at the course root" in warning for warning in library.warnings)


def test_legacy_direct_draft_without_practice_remains_studyable(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    course = write_course_folder(workspace, "causal-inference")
    (course / "exams" / "PRACTICE-001" / "exam.json").unlink()
    study_path = course / "study.yaml"
    study = yaml.safe_load(study_path.read_text(encoding="utf-8"))
    del study["artifact_paths"]["practice_exam"]
    study_path.write_text(yaml.safe_dump(study, sort_keys=False), encoding="utf-8")
    state = WorkspaceState(
        workspace_id="WORKSPACE-001",
        name="Workspace",
        path=str(workspace),
        available=True,
        writable=True,
    )

    library = study_library(state)

    assert library.warnings == []
    assert library.courses[0].course_id == "STUDY-CHATGPT-001"
    assert build_dashboard(state).ready_exams == []


def test_self_checked_practice_runs_without_updating_mastery(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    course = write_course_folder(workspace, "causal-inference")
    state = WorkspaceState(
        workspace_id="WORKSPACE-001",
        name="Workspace",
        path=str(workspace),
        available=True,
        writable=True,
    )
    progress_path = course / "progress" / "learner-progress.json"
    progress_before = progress_path.read_bytes()

    dashboard = build_dashboard(state)
    assert len(dashboard.ready_exams) == 1
    summary = dashboard.ready_exams[0]
    assert summary.exam_id == "PRACTICE-001"
    assert summary.assessment_kind == "practice"
    assert summary.source_status == "self_checked"
    assert summary.mastery_eligible is False

    sessions = ExamSessionStore()
    attempt = sessions.start(state, "STUDY-CHATGPT-001", "PRACTICE-001")
    assert attempt.assessment_kind == "practice"
    assert attempt.mastery_eligible is False
    assert attempt.questions[0].source_status == "self_checked"
    feedback = sessions.submit(
        attempt.attempt_id,
        attempt.course_id,
        attempt.exam_id,
        attempt.questions[0].question_id,
        "A",
    )
    assert feedback.correct is True

    completion = sessions.finish(attempt.attempt_id, attempt.course_id, attempt.exam_id)
    assert completion.assessment_kind == "practice"
    assert completion.mastery_updated is False
    assert progress_path.read_bytes() == progress_before
    assert not (course / "progress" / "review-queue.json").exists()
    stored_attempt = json.loads(next((course / "attempts").glob("*.json")).read_text())
    assert stored_attempt["attempt_kind"] == "practice"
    assert stored_attempt["mastery_eligible"] is False
    assert study_library(state).courses[0].course_id == "STUDY-CHATGPT-001"


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


def test_optional_artifact_hash_manifest_is_verified_byte_for_byte(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    files = add_artifact_hash_manifest(course_files())

    result = import_course_zip(workspace, zip_bytes(files), filename="causal-inference.zip")

    assert result["status"] == "imported"
    manifest = json.loads(
        (workspace / "courses" / "causal-inference" / "records" / "evidence" / "validation" / "artifact-hashes.json").read_text()
    )
    assert len(manifest["groups"]) == 4


def test_artifact_hash_manifest_rejects_changed_member(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    files = add_artifact_hash_manifest(course_files())
    lesson_path = "causal-inference/lessons/CH-001.md"
    files[lesson_path] += "\nChanged after hashing.\n"

    with pytest.raises(CourseImportError, match="does not match the current file"):
        import_course_zip(workspace, zip_bytes(files), filename="causal-inference.zip")


def test_artifact_hash_manifest_rejects_omitted_required_input(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    files = add_artifact_hash_manifest(course_files())
    manifest_path = "causal-inference/records/evidence/validation/artifact-hashes.json"
    manifest = json.loads(files[manifest_path])
    group = next(item for item in manifest["groups"] if item["group_id"] == "citation-check-inputs-v1")
    group["members"] = [
        item for item in group["members"] if item["path"] != "records/source/SRC-001.md"
    ]
    payload = "".join(f"{item['path']}\t{item['sha256']}\n" for item in group["members"])
    group["group_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    receipt_path = "causal-inference/records/evidence/validation/citation-check.json"
    receipt = json.loads(files[receipt_path])
    receipt["input_artifact_hash"] = group["group_sha256"]
    files[receipt_path] = json.dumps(receipt)
    files[manifest_path] = json.dumps(manifest)

    with pytest.raises(CourseImportError, match="missing required check inputs"):
        import_course_zip(workspace, zip_bytes(files), filename="causal-inference.zip")


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


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda files: files.__setitem__(
                "causal-inference/exams/PRACTICE-001/exam.json",
                json.dumps(
                    {
                        **json.loads(files["causal-inference/exams/PRACTICE-001/exam.json"]),
                        "status": "ready",
                        "verification_status": "verified",
                        "mastery_eligible": True,
                    }
                ),
            ),
            "status must be practice_ready",
        ),
        (
            lambda files: files.__setitem__(
                "causal-inference/progress/learner-progress.json",
                json.dumps(
                    {
                        **json.loads(files["causal-inference/progress/learner-progress.json"]),
                        "applied_attempt_ids": ["ATTEMPT-SEEDED"],
                    }
                ),
            ),
            "may not import applied mastery attempts",
        ),
    ],
)
def test_rejects_practice_promotion_and_seeded_mastery(
    tmp_path: Path,
    mutate,
    message: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    files = course_files()
    mutate(files)

    with pytest.raises(CourseImportError, match=message):
        import_course_zip(workspace, zip_bytes(files), filename="causal-inference.zip")


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
