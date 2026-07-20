from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mastery_ledger.app import create_app
from mastery_ledger.cli import main
from mastery_ledger.config import database_path
from mastery_ledger.runtime import build_doctor_result, validate_workspace


@pytest.fixture()
def runtime_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "runtime"
    monkeypatch.setenv("MASTERY_LEDGER_HOME", str(home))
    monkeypatch.setenv("MASTERY_LEDGER_DEFAULT_WORKSPACE", str(tmp_path / "courses"))
    return home


def test_doctor_is_read_only_before_onboarding(runtime_home: Path) -> None:
    result = build_doctor_result()

    assert result.status == "onboarding_required"
    assert result.onboarding_required is True
    assert result.action == "open_onboarding"
    assert not runtime_home.exists()
    assert not database_path().exists()


def test_workspace_validation_requires_absolute_path(runtime_home: Path) -> None:
    result = validate_workspace("relative/courses")

    assert result.valid is False
    assert result.message == "Use an absolute workspace path."


def test_doctor_reports_corrupted_database_as_runtime_error(runtime_home: Path) -> None:
    runtime_home.mkdir(parents=True)
    database_path().write_text("this is not sqlite", encoding="utf-8")

    result = build_doctor_result()

    assert result.status == "runtime_error"
    assert result.onboarding_required is False
    assert result.action == "inspect_runtime"


def test_onboarding_persists_workspace_and_makes_doctor_ready(
    runtime_home: Path, tmp_path: Path
) -> None:
    app = create_app(session_token="test-session", web_dir=tmp_path / "missing-web")
    workspace = tmp_path / "Learning" / "courses"

    with TestClient(app) as client:
        bootstrap = client.get("/bootstrap/test-session", follow_redirects=False)
        assert bootstrap.status_code == 303

        defaults = client.get("/api/v1/onboarding/defaults")
        assert defaults.status_code == 200

        validation = client.post(
            "/api/v1/onboarding/validate-workspace",
            json={"path": str(workspace)},
        )
        assert validation.status_code == 200
        assert validation.json()["will_create"] is True

        completion = client.post(
            "/api/v1/onboarding/complete",
            json={
                "workspace_path": str(workspace),
                "workspace_name": "My learning ledger",
                "language": "en",
                "processing_mode": "local_only",
                "reduced_motion": False,
                "review_intervals": [1, 3, 7, 14, 28],
                "initial_source_hint": "https://example.com/lesson",
            },
        )
        assert completion.status_code == 200
        assert completion.json()["workspace"]["name"] == "My learning ledger"

        status = client.get("/api/v1/status")
        assert status.status_code == 200
        assert status.json()["status"] == "ready"

    assert workspace.is_dir()
    assert database_path().is_file()
    assert build_doctor_result().status == "ready"


def test_api_rejects_requests_without_local_session(runtime_home: Path, tmp_path: Path) -> None:
    app = create_app(session_token="test-session", web_dir=tmp_path / "missing-web")

    with TestClient(app) as client:
        response = client.get("/api/v1/status")

    assert response.status_code == 401


def test_health_identifies_the_local_application(runtime_home: Path, tmp_path: Path) -> None:
    app = create_app(session_token="test-session", web_dir=tmp_path / "missing-web")

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "schema_version": "health-v1",
        "application": "mastery-ledger",
    }


def test_built_frontend_is_served_after_bootstrap(runtime_home: Path) -> None:
    app = create_app(session_token="test-session")

    with TestClient(app) as client:
        response = client.get("/bootstrap/test-session")

    assert response.status_code == 200
    assert "Mastery Ledger" in response.text
    assert "<div id=\"root\"></div>" in response.text


def test_doctor_cli_emits_one_json_object(runtime_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["doctor", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["schema_version"] == "doctor-v1"
    assert payload["status"] == "onboarding_required"
    assert captured.err == ""


def test_dashboard_discovers_ready_exams_and_review_queue(
    runtime_home: Path, tmp_path: Path
) -> None:
    app = create_app(session_token="test-session", web_dir=tmp_path / "missing-web")
    workspace = tmp_path / "Learning"

    with TestClient(app) as client:
        client.get("/bootstrap/test-session", follow_redirects=False)
        completion = client.post(
            "/api/v1/onboarding/complete",
            json={
                "workspace_path": str(workspace),
                "workspace_name": "Dashboard workspace",
                "language": "en",
                "processing_mode": "local_only",
                "reduced_motion": False,
                "review_intervals": [1, 3, 7, 14],
                "initial_source_hint": None,
            },
        )
        assert completion.status_code == 200

        course = workspace / "courses" / "course-one"
        (course / "questions").mkdir(parents=True)
        (course / "progress").mkdir()
        (course / "source").mkdir()
        (course / "exams" / "EXAM-READY").mkdir(parents=True)
        (course / "exams" / "EXAM-DRAFT").mkdir()
        (course / "course.yaml").write_text(
            "course_id: COURSE-ONE\ntitle: Clinical Foundations\nupdated_at: '2026-07-20T10:00:00Z'\n",
            encoding="utf-8",
        )
        (course / "questions" / "question-bank.json").write_text(
            json.dumps({"questions": [{"question_id": "Q-1"}, {"question_id": "Q-2"}]}),
            encoding="utf-8",
        )
        (course / "progress" / "review-queue.json").write_text(
            json.dumps(
                {
                    "questions": [
                        {"question_id": "Q-1", "stage_index": 0, "next_due_at": "2020-01-01T00:00:00Z"},
                        {"question_id": "Q-2", "stage_index": 2, "next_due_at": "2999-01-01T00:00:00Z"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        (course / "source" / "source-manifest.yaml").write_text(
            "sources:\n  - source_id: SRC-1\n    processing_status: ready\n  - source_id: SRC-2\n    processing_status: pending\n",
            encoding="utf-8",
        )
        (course / "exams" / "EXAM-READY" / "exam.json").write_text(
            json.dumps(
                {
                    "exam_id": "EXAM-READY",
                    "course_id": "COURSE-ONE",
                    "title": "Clinical Foundations Mock Exam",
                    "status": "ready",
                    "question_count": 40,
                    "estimated_minutes": 60,
                    "concepts": ["diagnosis", "treatment"],
                    "created_at": "2026-07-20T12:00:00Z",
                    "source_status": "verified",
                }
            ),
            encoding="utf-8",
        )
        (course / "exams" / "EXAM-DRAFT" / "exam.json").write_text(
            json.dumps({"exam_id": "EXAM-DRAFT", "status": "draft", "questions": []}),
            encoding="utf-8",
        )

        response = client.get("/api/v1/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "dashboard-v1"
    assert payload["workspace"]["name"] == "Dashboard workspace"
    assert payload["due_now"] == 1
    assert [exam["exam_id"] for exam in payload["ready_exams"]] == ["EXAM-READY"]
    assert payload["ready_exams"][0]["source_status"] == "verified"
    assert payload["recent_courses"][0] == {
        "course_id": "COURSE-ONE",
        "title": "Clinical Foundations",
        "question_count": 2,
        "ready_exam_count": 1,
        "due_count": 1,
        "source_count": 2,
        "source_ready_count": 1,
        "updated_at": "2026-07-20T10:00:00Z",
    }
    assert [stage["interval_days"] for stage in payload["ownership_curve"]] == [1, 3, 7, 14]
    assert [stage["question_count"] for stage in payload["ownership_curve"]] == [1, 0, 1, 0]


def test_dashboard_requires_completed_onboarding(runtime_home: Path, tmp_path: Path) -> None:
    app = create_app(session_token="test-session", web_dir=tmp_path / "missing-web")

    with TestClient(app) as client:
        client.get("/bootstrap/test-session", follow_redirects=False)
        response = client.get("/api/v1/dashboard")

    assert response.status_code == 409
    assert response.json()["detail"] == "Complete onboarding before opening the workspace dashboard."
