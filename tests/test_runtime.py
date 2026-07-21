from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mastery_ledger.app import create_app
from mastery_ledger import cli
from mastery_ledger.cli import main
from mastery_ledger.config import database_path, runtime_signature
from mastery_ledger.database import initialize_database
from mastery_ledger.models import FolderPickerResult
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


def test_doctor_enforces_the_supported_skill_version_range(runtime_home: Path) -> None:
    compatible = build_doctor_result("0.1.0")
    incompatible = build_doctor_result("1.0.0")
    malformed = build_doctor_result("current")

    assert compatible.status == "onboarding_required"
    assert compatible.skill_compatible is True
    assert compatible.skill_version == "0.1.0"
    assert compatible.compatible_skill_range == ">=0.1.0,<0.2.0"
    for result in (incompatible, malformed):
        assert result.status == "incompatible"
        assert result.skill_compatible is False
        assert result.action == "update_application_or_skill"
        assert result.onboarding_required is False


def test_workspace_validation_requires_absolute_path(runtime_home: Path) -> None:
    result = validate_workspace("relative/courses")

    assert result.valid is False
    assert result.message == "Use an absolute workspace path."


def test_database_migration_removes_legacy_ingestion_jobs(runtime_home: Path) -> None:
    target = database_path()
    target.parent.mkdir(parents=True)
    with sqlite3.connect(target) as connection:
        connection.execute(
            "CREATE TABLE jobs (job_id TEXT PRIMARY KEY, kind TEXT, state TEXT, payload_json TEXT, created_at TEXT, updated_at TEXT)"
        )
        connection.execute(
            "INSERT INTO jobs VALUES ('JOB-OLD', 'source_ingestion', 'queued', '{}', 'old', 'old')"
        )

    initialize_database(target)

    with sqlite3.connect(target) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        schema_version = connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
    assert "jobs" not in tables
    assert schema_version == ("2",)


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
                "reduced_motion": False,
                "review_intervals": [1, 3, 7, 14, 28],
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


def test_workspace_repair_preserves_settings_and_native_picker_is_explicit(
    runtime_home: Path, tmp_path: Path
) -> None:
    selected = tmp_path / "ReconnectedWorkspace"
    app = create_app(
        session_token="repair-session",
        web_dir=tmp_path / "missing-web",
        folder_picker=lambda initial: FolderPickerResult(status="selected", path=str(selected)),
    )
    original = tmp_path / "OriginalWorkspace"
    with TestClient(app) as client:
        client.get("/bootstrap/repair-session", follow_redirects=False)
        completed = client.post(
            "/api/v1/onboarding/complete",
            json={
                "workspace_path": str(original),
                "workspace_name": "Original ledger",
                "language": "fr",
                "reduced_motion": True,
                "review_intervals": [2, 5, 11],
            },
        )
        workspace_id = completed.json()["workspace"]["workspace_id"]
        original.rmdir()

        unavailable = client.get("/api/v1/status").json()
        assert unavailable["status"] == "workspace_unavailable"
        assert unavailable["action"] == "repair_workspace"

        picked = client.post(
            "/api/v1/system/pick-folder",
            json={"initial_path": str(original)},
        )
        assert picked.status_code == 200
        assert picked.json()["path"] == str(selected)

        repaired = client.post(
            "/api/v1/workspaces/repair",
            json={"workspace_path": str(selected), "workspace_name": "Reconnected ledger"},
        )
        assert repaired.status_code == 200
        assert repaired.json()["workspace"]["workspace_id"] == workspace_id
        assert repaired.json()["workspace"]["name"] == "Reconnected ledger"
        assert selected.is_dir()
        assert client.get("/api/v1/status").json()["status"] == "ready"
        settings = client.get("/api/v1/settings").json()
        assert settings["language"] == "fr"
        assert settings["review_curve"]["interval_days"] == [2, 5, 11]


def test_health_identifies_the_local_application(runtime_home: Path, tmp_path: Path) -> None:
    app = create_app(session_token="test-session", web_dir=tmp_path / "missing-web")

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "schema_version": "health-v1",
        "application": "mastery-ledger",
        "runtime_signature": runtime_signature(),
    }


def test_built_frontend_is_served_after_bootstrap(runtime_home: Path) -> None:
    app = create_app(session_token="test-session")

    with TestClient(app) as client:
        response = client.get("/bootstrap/test-session")

    assert response.status_code == 200
    assert "Mastery Ledger" in response.text
    assert "<div id=\"root\"></div>" in response.text


def test_repair_bootstrap_establishes_session_and_routes_to_application(
    runtime_home: Path, tmp_path: Path
) -> None:
    app = create_app(session_token="repair-session", web_dir=tmp_path / "missing-web")

    with TestClient(app) as client:
        response = client.get("/bootstrap/repair-session/repair", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"
        assert client.get("/api/v1/status").status_code == 200


def test_doctor_cli_emits_one_json_object(runtime_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["doctor", "--json", "--skill-version", "0.1.0"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["schema_version"] == "doctor-v2"
    assert payload["capabilities"] == {
        "exam_player": "ready",
        "learner_state": "ready",
        "review_scheduler": "ready",
    }
    assert payload["status"] == "onboarding_required"
    assert payload["skill_version"] == "0.1.0"
    assert captured.err == ""


def test_repair_cli_uses_fixed_workspace_repair_launcher(
    runtime_home: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli,
        "launch_workspace_repair",
        lambda *, open_browser: {
            "schema_version": "workspace-repair-launch-v1",
            "status": "launched",
            "opened": open_browser,
            "pid": 123,
            "url": "http://127.0.0.1:8765/",
        },
    )

    assert main(["repair", "--open", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "workspace-repair-launch-v1"
    assert payload["opened"] is True


def test_launcher_reuses_server_with_matching_runtime(
    runtime_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = {
        "schema_version": "server-state-v1",
        "port": 8765,
        "pid": 123,
        "session_token": "existing-token",
    }
    stopped: list[dict[str, object]] = []
    spawned: list[tuple[int, str]] = []
    monkeypatch.setattr(cli, "_read_server_state", lambda: existing)
    monkeypatch.setattr(cli, "runtime_signature", lambda: "current-build")
    monkeypatch.setattr(
        cli,
        "_server_is_healthy",
        lambda port, expected_signature=None: port == 8765
        and expected_signature in {None, "current-build"},
    )
    monkeypatch.setattr(cli, "_stop_server", stopped.append)
    monkeypatch.setattr(cli, "_spawn_server", lambda port, token: spawned.append((port, token)))

    result = cli.launch_onboarding(open_browser=False)

    assert result["status"] == "already_running"
    assert stopped == []
    assert spawned == []


def test_launcher_replaces_server_with_stale_runtime(
    runtime_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = {
        "schema_version": "server-state-v1",
        "port": 8765,
        "pid": 123,
        "session_token": "old-token",
    }
    stopped: list[dict[str, object]] = []
    written: list[dict[str, object]] = []

    class SpawnedProcess:
        pid = 456

    monkeypatch.setattr(cli, "_read_server_state", lambda: existing)
    monkeypatch.setattr(cli, "runtime_signature", lambda: "current-build")
    monkeypatch.setattr(
        cli,
        "_server_is_healthy",
        lambda port, expected_signature=None: port == 8765 and expected_signature is None,
    )
    monkeypatch.setattr(cli, "_stop_server", stopped.append)
    monkeypatch.setattr(cli, "_free_loopback_port", lambda: 9876)
    monkeypatch.setattr(cli.secrets, "token_urlsafe", lambda _: "new-token")
    monkeypatch.setattr(cli, "_spawn_server", lambda port, token: SpawnedProcess())
    monkeypatch.setattr(cli, "_write_server_state", written.append)
    monkeypatch.setattr(cli, "_wait_for_server", lambda port, signature: True)

    result = cli.launch_onboarding(open_browser=False)

    assert result["status"] == "launched"
    assert stopped == [existing]
    assert written == [{
        "schema_version": "server-state-v1",
        "port": 9876,
        "pid": 456,
        "session_token": "new-token",
        "runtime_signature": "current-build",
    }]


def test_stop_cli_stops_registered_application_and_removes_state(
    runtime_home: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {
        "schema_version": "server-state-v1",
        "port": 8765,
        "pid": 123,
        "session_token": "session-token",
    }
    health_checks = iter([True, False])
    stopped: list[dict[str, object]] = []
    monkeypatch.setattr(cli, "_read_server_state", lambda: state)
    monkeypatch.setattr(cli, "_server_is_healthy", lambda port, expected_signature=None: next(health_checks))
    monkeypatch.setattr(cli, "_stop_server", stopped.append)
    runtime_home.mkdir(parents=True)
    (runtime_home / "server.json").write_text("{}", encoding="utf-8")

    assert main(["stop", "--json"]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "schema_version": "application-stop-v1",
        "status": "stopped",
    }
    assert stopped == [state]
    assert not (runtime_home / "server.json").exists()


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
                "reduced_motion": False,
                "review_intervals": [1, 3, 7, 14],
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
        "concept_count": 0,
        "proficient_concept_count": 0,
        "updated_at": "2026-07-20T10:00:00Z",
    }
    assert [stage["interval_days"] for stage in payload["ownership_curve"]] == [1, 3, 7, 14]
    assert [stage["question_count"] for stage in payload["ownership_curve"]] == [1, 0, 1, 0]


def test_study_library_exposes_validated_lessons_without_frontmatter_and_preserves_html(
    runtime_home: Path, tmp_path: Path
) -> None:
    app = create_app(session_token="study-session", web_dir=tmp_path / "missing-web")
    workspace = tmp_path / "StudyWorkspace"

    with TestClient(app) as client:
        client.get("/bootstrap/study-session", follow_redirects=False)
        completion = client.post(
            "/api/v1/onboarding/complete",
            json={
                "workspace_path": str(workspace),
                "workspace_name": "Study workspace",
                "language": "en",
                "reduced_motion": False,
                "review_intervals": [1, 3, 7],
            },
        )
        assert completion.status_code == 200

        published = workspace / "published-course"
        (published / "lessons").mkdir(parents=True)
        (published / "questions").mkdir()
        (published / "study.yaml").write_text(
            "study_id: COURSE-STUDY\ntitle: Systems Thinking\nworkflow_state: LEARNING_ACTIVE\nupdated_at: '2026-07-20T12:00:00Z'\n",
            encoding="utf-8",
        )
        lesson_body = (
            "# Feedback loops\n\n"
            "A feedback loop returns part of a system's output as a later input. "
            "Reinforcing loops amplify change, while balancing loops resist it.\n\n"
            "<aside class=\"worked-example\"><strong>Worked example</strong>: "
            "A thermostat compares measured temperature with its target.</aside>\n\n"
            "<script>window.parent.document.body.dataset.compromised = 'true'</script>\n"
        )
        lesson_content = (
            "---\n"
            "schema_version: lesson-v1\n"
            "chapter_id: CH-001\n"
            "title: Feedback loops\n"
            "status: validated\n"
            "---\n\n"
            + lesson_body
        )
        (published / "lessons" / "CH-001.md").write_text(lesson_content, encoding="utf-8")
        (published / "questions" / "question-bank.json").write_text(
            json.dumps(
                {
                    "schema_version": "question-bank-v2",
                    "chapters": [
                        {
                            "chapter_id": "CH-001",
                            "title": "Feedback loops",
                            "class": "core",
                            "lesson_path": "lessons/CH-001.md",
                        }
                    ],
                    "questions": [],
                }
            ),
            encoding="utf-8",
        )

        draft = workspace / "draft-course"
        (draft / "lessons").mkdir(parents=True)
        (draft / "questions").mkdir()
        (draft / "study.yaml").write_text(
            "study_id: COURSE-DRAFT\ntitle: Draft course\nworkflow_state: STUDY_PACK_DRAFTED\n",
            encoding="utf-8",
        )
        draft_body = "# Validated lesson\n\n" + "This lesson is readable while its exam awaits validation. " * 20
        (draft / "lessons" / "CH-DRAFT.md").write_text(
            "---\n"
            "schema_version: lesson-v1\n"
            "chapter_id: CH-DRAFT\n"
            "title: Validated lesson\n"
            "status: validated\n"
            "---\n\n"
            + draft_body,
            encoding="utf-8",
        )
        (draft / "questions" / "question-bank.json").write_text(
            json.dumps(
                {
                    "schema_version": "question-bank-v2",
                    "chapters": [
                        {
                            "chapter_id": "CH-DRAFT",
                            "title": "Draft",
                            "class": "core",
                            "lesson_path": "lessons/CH-DRAFT.md",
                        }
                    ],
                    "questions": [],
                }
            ),
            encoding="utf-8",
        )

        unsafe = workspace / "unsafe-course"
        (unsafe / "lessons").mkdir(parents=True)
        (unsafe / "questions").mkdir()
        (unsafe / "study.yaml").write_text(
            "study_id: COURSE-UNSAFE\ntitle: Unsafe course\nworkflow_state: LEARNING_ACTIVE\n",
            encoding="utf-8",
        )
        (unsafe / "secret.md").write_text("# Secret\n\n" + "Outside lesson root. " * 20, encoding="utf-8")
        (unsafe / "questions" / "question-bank.json").write_text(
            json.dumps(
                {
                    "schema_version": "question-bank-v2",
                    "chapters": [
                        {
                            "chapter_id": "CH-UNSAFE",
                            "title": "Unsafe",
                            "class": "core",
                            "lesson_path": "lessons/../secret.md",
                        }
                    ],
                    "questions": [],
                }
            ),
            encoding="utf-8",
        )

        library = client.get("/api/v1/study")
        assert library.status_code == 200
        payload = library.json()
        assert payload["schema_version"] == "study-library-v1"
        assert [course["course_id"] for course in payload["courses"]] == ["COURSE-STUDY", "COURSE-DRAFT"]
        assert payload["courses"][0]["chapters"][0]["lesson_path"] == "lessons/CH-001.md"
        assert any("CH-UNSAFE" in warning for warning in payload["warnings"])

        lesson = client.get("/api/v1/study/COURSE-STUDY/chapters/CH-001")
        assert lesson.status_code == 200
        assert lesson.json()["content"] == lesson_body
        assert "schema_version: lesson-v1" not in lesson.json()["content"]
        assert "<aside" in lesson.json()["content"]
        assert "<script>" in lesson.json()["content"]
        assert lesson.json()["word_count"] > 20
        draft_lesson = client.get("/api/v1/study/COURSE-DRAFT/chapters/CH-DRAFT")
        assert draft_lesson.status_code == 200
        assert draft_lesson.json()["content"] == draft_body


def test_dashboard_requires_completed_onboarding(runtime_home: Path, tmp_path: Path) -> None:
    app = create_app(session_token="test-session", web_dir=tmp_path / "missing-web")

    with TestClient(app) as client:
        client.get("/bootstrap/test-session", follow_redirects=False)
        response = client.get("/api/v1/dashboard")

    assert response.status_code == 409
    assert response.json()["detail"] == "Complete onboarding before opening the workspace dashboard."


def test_focused_exam_locks_answers_and_gates_explanations(
    runtime_home: Path, tmp_path: Path
) -> None:
    app = create_app(session_token="test-session", web_dir=tmp_path / "missing-web")
    workspace = tmp_path / "ExamWorkspace"

    with TestClient(app) as client:
        client.get("/bootstrap/test-session", follow_redirects=False)
        client.post(
            "/api/v1/onboarding/complete",
            json={
                "workspace_path": str(workspace),
                "workspace_name": "Exam workspace",
                "language": "en",
                "reduced_motion": False,
                "review_intervals": [1, 3, 7],
            },
        )

        course = workspace / "courses" / "medicine"
        exam_root = course / "exams" / "EXAM-FOCUSED"
        source_root = course / "source"
        progress_root = course / "progress"
        exam_root.mkdir(parents=True)
        source_root.mkdir()
        progress_root.mkdir()
        (course / "course.yaml").write_text(
            "course_id: COURSE-MED\ntitle: Medicine Foundations\n",
            encoding="utf-8",
        )
        (source_root / "source-manifest.yaml").write_text(
            "sources:\n  - source_id: SRC-001\n    title: Clinical guide\n    processing_status: ready\n",
            encoding="utf-8",
        )
        (progress_root / "review-queue.json").write_text(
            json.dumps(
                {
                    "questions": [
                        {
                            "question_id": "Q-001",
                            "stage_index": 2,
                            "interval_days": 7,
                            "next_due_at": "2020-01-01T00:00:00Z",
                            "due_success_count": 2,
                            "lapse_count": 0,
                            "early_practice_count": 0,
                        },
                        {
                            "question_id": "Q-003",
                            "stage_index": 1,
                            "interval_days": 3,
                            "next_due_at": "2020-01-01T00:00:00Z",
                            "due_success_count": 4,
                            "lapse_count": 0,
                            "early_practice_count": 0,
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        source_ref = {
            "source_id": "SRC-001",
            "locator": {"kind": "section", "value": "2", "label": "Section 2"},
            "supports": ["correct_answer", "explanation"],
            "support_strength": "direct",
            "href": "https://example.com/guide#section-2",
        }
        (exam_root / "exam.json").write_text(
            json.dumps(
                {
                    "exam_id": "EXAM-FOCUSED",
                    "course_id": "COURSE-MED",
                    "title": "Focused Medicine Mock",
                    "status": "ready",
                    "estimated_minutes": 10,
                    "questions": [
                        {
                            "question_id": "Q-001",
                            "prompt": "Which option is supported?",
                            "options": [
                                {"option_id": "A", "text": "Unsupported option"},
                                {"option_id": "B", "text": "Supported option"},
                            ],
                            "correct_option_id": "B",
                            "correct_explanation": "Option B matches the clinical guide.",
                            "source_refs": [source_ref],
                            "concept_ids": ["diagnosis"],
                        },
                        {
                            "question_id": "Q-002",
                            "prompt": "Choose the second supported option.",
                            "options": [
                                {"option_id": "A", "text": "First option"},
                                {"option_id": "B", "text": "Second option"},
                            ],
                            "correct_option_id": "A",
                            "correct_explanation": "Option A is supported.",
                            "source_refs": [source_ref],
                        },
                        {
                            "question_id": "Q-003",
                            "prompt": "Choose the due-review answer.",
                            "options": [
                                {"option_id": "A", "text": "First review option"},
                                {"option_id": "B", "text": "Second review option"},
                            ],
                            "correct_option_id": "B",
                            "correct_explanation": "Option B is supported for this review.",
                            "source_refs": [source_ref],
                            "version": 2,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        generated_exam = (exam_root / "exam.json").read_bytes()
        generated_source_manifest = (source_root / "source-manifest.yaml").read_bytes()

        start = client.post("/api/v1/exams/COURSE-MED/EXAM-FOCUSED/attempts")
        assert start.status_code == 200
        start_payload = start.json()
        serialized_start = json.dumps(start_payload)
        assert "correct_option_id" not in serialized_start
        assert "correct_explanation" not in serialized_start
        assert "source_count" in serialized_start
        assert start_payload["resumed"] is False
        assert start_payload["answers"] == []
        attempt_id = start_payload["attempt_id"]
        attempt_path = course / "attempts" / f"{attempt_id}.json"
        persisted_start = json.loads(attempt_path.read_text(encoding="utf-8"))
        assert persisted_start["status"] == "in_progress"
        assert persisted_start["responses"] == []
        assert "correct_option_id" not in json.dumps(persisted_start)

        wrong = client.post(
            f"/api/v1/exams/COURSE-MED/EXAM-FOCUSED/attempts/{attempt_id}/questions/Q-001",
            json={"option_id": "A"},
        )
        assert wrong.status_code == 200
        assert wrong.json()["status"] == "incorrect"
        assert wrong.json()["explanation"] is None
        assert wrong.json()["sources"] == []

        persisted_wrong = json.loads(attempt_path.read_text(encoding="utf-8"))
        assert len(persisted_wrong["responses"]) == 1
        assert persisted_wrong["responses"][0]["question_id"] == "Q-001"
        assert persisted_wrong["responses"][0]["selected_option_id"] == "A"
        assert persisted_wrong["responses"][0]["status"] == "incorrect"
        assert persisted_wrong["responses"][0]["submitted_at"]

        dashboard_before_restart = client.get("/api/v1/dashboard").json()
        assert dashboard_before_restart["ready_exams"][0]["resume_available"] is True

        retry = client.post(
            f"/api/v1/exams/COURSE-MED/EXAM-FOCUSED/attempts/{attempt_id}/questions/Q-001",
            json={"option_id": "B"},
        )
        assert retry.status_code == 409

        restarted_app = create_app(
            session_token="restart-session", web_dir=tmp_path / "missing-web"
        )
        with TestClient(restarted_app) as restarted_client:
            restarted_client.get("/bootstrap/restart-session", follow_redirects=False)
            resumed = restarted_client.post(
                "/api/v1/exams/COURSE-MED/EXAM-FOCUSED/attempts"
            )
            assert resumed.status_code == 200
            assert resumed.json()["attempt_id"] == attempt_id
            assert resumed.json()["resumed"] is True
            assert resumed.json()["answers"][0]["status"] == "incorrect"
            assert resumed.json()["answers"][0]["explanation"] is None

            correct = restarted_client.post(
                f"/api/v1/exams/COURSE-MED/EXAM-FOCUSED/attempts/{attempt_id}/questions/Q-002",
                json={"option_id": "A"},
            )
            assert correct.status_code == 200
            assert correct.json()["status"] == "correct"
            assert correct.json()["explanation"] == "Option A is supported."
            assert correct.json()["sources"][0] == {
                "source_id": "SRC-001",
                "title": "Clinical guide",
                "locator_label": "Section 2",
                "support_strength": "direct",
                "href": "https://example.com/guide#section-2",
            }

            due_correct = restarted_client.post(
                f"/api/v1/exams/COURSE-MED/EXAM-FOCUSED/attempts/{attempt_id}/questions/Q-003",
                json={"option_id": "B"},
            )
            assert due_correct.status_code == 200
            assert due_correct.json()["status"] == "correct"

            finish = restarted_client.post(
                f"/api/v1/exams/COURSE-MED/EXAM-FOCUSED/attempts/{attempt_id}/finish"
            )
            repeated_finish = restarted_client.post(
                f"/api/v1/exams/COURSE-MED/EXAM-FOCUSED/attempts/{attempt_id}/finish"
            )
            assert repeated_finish.status_code == 200
            assert repeated_finish.json() == finish.json()
            dashboard_after_finish = restarted_client.get("/api/v1/dashboard").json()
            assert dashboard_after_finish["ready_exams"][0]["resume_available"] is False

    assert finish.status_code == 200
    completion = finish.json()
    assert completion["correct_count"] == 2
    assert completion["incorrect_count"] == 1
    assert completion["unanswered_count"] == 0
    assert completion["score_percent"] == 66.7
    assert completion["questions"][0]["correct_option_id"] == "B"
    assert completion["questions"][0]["sources"][0]["source_id"] == "SRC-001"

    persisted_completion = json.loads(attempt_path.read_text(encoding="utf-8"))
    assert persisted_completion["status"] == "complete"
    assert persisted_completion["result"]["score_percent"] == 66.7

    review_queue = json.loads(
        (progress_root / "review-queue.json").read_text(encoding="utf-8")
    )
    assert review_queue["schema_version"] == "review-queue-v1"
    assert review_queue["curve_intervals"] == [1, 3, 7]
    assert review_queue["applied_attempt_ids"] == [attempt_id]
    records = {item["question_id"]: item for item in review_queue["questions"]}
    assert records["Q-001"]["stage_index"] == 0
    assert records["Q-001"]["interval_days"] == 1
    assert records["Q-001"]["lapse_count"] == 1
    assert records["Q-001"]["last_attempt_id"] == attempt_id
    assert records["Q-002"]["stage_index"] == 0
    assert records["Q-002"]["interval_days"] == 1
    assert records["Q-002"]["early_practice_count"] == 1
    assert records["Q-003"]["question_version"] == 2
    assert records["Q-003"]["stage_index"] == 2
    assert records["Q-003"]["interval_days"] == 7
    assert records["Q-003"]["due_success_count"] == 5
    assert (exam_root / "exam.json").read_bytes() == generated_exam
    assert (source_root / "source-manifest.yaml").read_bytes() == generated_source_manifest


def test_due_review_advances_curve_and_updates_concept_progress(
    runtime_home: Path, tmp_path: Path
) -> None:
    app = create_app(session_token="review-session", web_dir=tmp_path / "missing-web")
    workspace = tmp_path / "ReviewWorkspace"

    with TestClient(app) as client:
        client.get("/bootstrap/review-session", follow_redirects=False)
        client.post(
            "/api/v1/onboarding/complete",
            json={
                "workspace_path": str(workspace),
                "workspace_name": "Review workspace",
                "language": "en",
                "reduced_motion": False,
                "review_intervals": [1, 3, 7],
            },
        )
        course = workspace / "courses" / "biology"
        questions_root = course / "questions"
        source_root = course / "source"
        progress_root = course / "progress"
        questions_root.mkdir(parents=True)
        source_root.mkdir()
        progress_root.mkdir()
        (course / "course.yaml").write_text(
            "course_id: COURSE-BIO\ntitle: Biology\n",
            encoding="utf-8",
        )
        (source_root / "source-manifest.yaml").write_text(
            "sources:\n  - source_id: SRC-BIO\n    title: Biology text\n    processing_status: ready\n",
            encoding="utf-8",
        )
        source_ref = {
            "source_id": "SRC-BIO",
            "locator": {"kind": "section", "value": "4", "label": "Section 4"},
            "supports": ["correct_answer", "explanation"],
            "support_strength": "direct",
        }
        (questions_root / "question-bank.json").write_text(
            json.dumps(
                {
                    "questions": [
                        {
                            "question_id": "Q-BIO-1",
                            "version": 3,
                            "concept_ids": ["cellular-respiration"],
                            "prompt": "Which molecule is the primary energy currency of the cell?",
                            "options": [
                                {"option_id": "A", "text": "DNA"},
                                {"option_id": "B", "text": "ATP"},
                            ],
                            "correct_option_id": "B",
                            "correct_explanation": "ATP transfers usable chemical energy.",
                            "source_refs": [source_ref],
                            "difficulty": 2,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (progress_root / "review-queue.json").write_text(
            json.dumps(
                {
                    "questions": [
                        {
                            "question_id": "Q-BIO-1",
                            "question_version": 3,
                            "concept_ids": ["cellular-respiration"],
                            "stage_index": 0,
                            "interval_days": 1,
                            "next_due_at": "2020-01-01T00:00:00Z",
                            "due_success_count": 0,
                            "lapse_count": 0,
                            "early_practice_count": 0,
                            "status": "learning",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (course / "learner-progress.json").write_text(
            json.dumps({"schema_version": "1.0", "study_id": "COURSE-BIO", "concepts": []}),
            encoding="utf-8",
        )

        curve_update = client.put(
            "/api/v1/settings/review-curve",
            json={
                "name": "Biology ownership curve",
                "interval_days": [1, 5, 12],
                "application_policy": "future_advancement",
                "save_mode": "new_version",
                "confirm_recalculate": False,
            },
        )
        assert curve_update.status_code == 200
        assert curve_update.json()["review_curve"]["version"] == 2
        migrated_queue = json.loads(
            (progress_root / "review-queue.json").read_text(encoding="utf-8")
        )
        assert migrated_queue["questions"][0]["next_due_at"] == "2020-01-01T00:00:00Z"
        assert migrated_queue["questions"][0]["curve_version"] == 1
        assert migrated_queue["questions"][0]["pending_curve_version"] == 2

        start = client.post("/api/v1/reviews/attempts")
        assert start.status_code == 200
        attempt = start.json()
        assert attempt["exam_id"] == "REVIEW-DUE"
        assert attempt["title"] == "Due review"
        assert [item["question_id"] for item in attempt["questions"]] == ["Q-BIO-1"]
        assert "correct_option_id" not in json.dumps(attempt)

        answer = client.post(
            f"/api/v1/exams/COURSE-BIO/REVIEW-DUE/attempts/{attempt['attempt_id']}/questions/Q-BIO-1",
            json={"option_id": "B"},
        )
        assert answer.status_code == 200
        assert answer.json()["correct"] is True

        finish = client.post(
            f"/api/v1/exams/COURSE-BIO/REVIEW-DUE/attempts/{attempt['attempt_id']}/finish"
        )
        assert finish.status_code == 200
        assert finish.json()["score_percent"] == 100.0

        no_more_due = client.post("/api/v1/reviews/attempts")
        assert no_more_due.status_code == 404
        dashboard = client.get("/api/v1/dashboard").json()
        assert dashboard["recent_courses"][0]["concept_count"] == 1
        assert dashboard["recent_courses"][0]["proficient_concept_count"] == 0

    attempt_payload = json.loads(
        (course / "attempts" / f"{attempt['attempt_id']}.json").read_text(encoding="utf-8")
    )
    assert attempt_payload["attempt_kind"] == "review"
    assert attempt_payload["status"] == "complete"

    queue = json.loads(
        (progress_root / "review-queue.json").read_text(encoding="utf-8")
    )
    queue_record = queue["questions"][0]
    assert queue_record["stage_index"] == 1
    assert queue_record["interval_days"] == 5
    assert queue_record["curve_version"] == 2
    assert queue_record["curve_intervals"] == [1, 5, 12]
    assert "pending_curve_version" not in queue_record
    assert queue_record["due_success_count"] == 1

    learner_progress = json.loads(
        (course / "learner-progress.json").read_text(encoding="utf-8")
    )
    assert not (progress_root / "learner-progress.json").exists()
    assert learner_progress["schema_version"] == "learner-progress-v1"
    assert learner_progress["applied_attempt_ids"] == [attempt["attempt_id"]]
    concept = learner_progress["concepts"][0]
    assert concept["concept_id"] == "cellular-respiration"
    assert concept["attempt_count"] == 1
    assert concept["correct_count"] == 1
    assert concept["proficiency_score"] == 1.0
    assert concept["status"] == "introduced"
    assert concept["next_review_at"] == queue_record["next_due_at"]
    assert concept["evidence"][0]["evaluation_method"] == "deterministic_multiple_choice"


def test_curve_settings_recalculate_and_preserve_versioned_schedules(
    runtime_home: Path, tmp_path: Path
) -> None:
    app = create_app(session_token="settings-session", web_dir=tmp_path / "missing-web")
    workspace = tmp_path / "SettingsWorkspace"

    with TestClient(app) as client:
        client.get("/bootstrap/settings-session", follow_redirects=False)
        onboard = client.post(
            "/api/v1/onboarding/complete",
            json={
                "workspace_path": str(workspace),
                "workspace_name": "Settings workspace",
                "language": "en",
                "reduced_motion": False,
                "review_intervals": [1, 3, 7],
            },
        )
        assert onboard.status_code == 200
        course = workspace / "courses" / "history"
        progress = course / "progress"
        progress.mkdir(parents=True)
        (course / "course.yaml").write_text(
            "course_id: COURSE-HISTORY\ntitle: History\n",
            encoding="utf-8",
        )
        (progress / "review-queue.json").write_text(
            json.dumps(
                {
                    "schema_version": "review-queue-v1",
                    "course_id": "COURSE-HISTORY",
                    "curve_intervals": [1, 3, 7],
                    "questions": [
                        {
                            "question_id": "Q-HISTORY-1",
                            "concept_ids": ["primary-sources"],
                            "stage_index": 1,
                            "interval_days": 3,
                            "scheduled_from_at": "2026-01-01T00:00:00Z",
                            "next_due_at": "2026-01-04T00:00:00Z",
                            "status": "learning",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (progress / "learner-progress.json").write_text(
            json.dumps(
                {
                    "schema_version": "learner-progress-v1",
                    "course_id": "COURSE-HISTORY",
                    "concepts": [
                        {
                            "concept_id": "primary-sources",
                            "next_review_at": "2026-01-04T00:00:00Z",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        settings = client.get("/api/v1/settings")
        assert settings.status_code == 200
        assert settings.json()["review_curve"]["version"] == 1
        assert settings.json()["scheduled_question_count"] == 1

        unconfirmed = client.put(
            "/api/v1/settings/review-curve",
            json={
                "name": "Long history curve",
                "interval_days": [2, 6, 12],
                "application_policy": "recalculate_all",
                "save_mode": "duplicate_profile",
                "confirm_recalculate": False,
            },
        )
        assert unconfirmed.status_code == 422
        assert "Confirm recalculation" in unconfirmed.json()["detail"]

        recalculated = client.put(
            "/api/v1/settings/review-curve",
            json={
                "name": "Long history curve",
                "interval_days": [2, 6, 12],
                "application_policy": "recalculate_all",
                "save_mode": "duplicate_profile",
                "confirm_recalculate": True,
            },
        )
        assert recalculated.status_code == 200
        recalculated_payload = recalculated.json()
        assert recalculated_payload["review_curve"]["version"] == 1
        assert recalculated_payload["review_curve"]["curve_id"] != "CURVE-OWNERSHIP"
        assert recalculated_payload["affected_question_count"] == 1

        queue = json.loads((progress / "review-queue.json").read_text(encoding="utf-8"))
        record = queue["questions"][0]
        assert record["curve_id"] == recalculated_payload["review_curve"]["curve_id"]
        assert record["curve_version"] == 1
        assert record["curve_intervals"] == [2, 6, 12]
        assert record["interval_days"] == 6
        assert record["next_due_at"] == "2026-01-07T00:00:00Z"
        learner_progress = json.loads(
            (progress / "learner-progress.json").read_text(encoding="utf-8")
        )
        assert learner_progress["concepts"][0]["next_review_at"] == "2026-01-07T00:00:00Z"

        new_only = client.put(
            "/api/v1/settings/review-curve",
            json={
                "name": "Long history curve",
                "interval_days": [2, 8, 16],
                "application_policy": "new_questions_only",
                "save_mode": "new_version",
                "confirm_recalculate": False,
            },
        )
        assert new_only.status_code == 200
        assert new_only.json()["review_curve"]["version"] == 2
        preserved = json.loads((progress / "review-queue.json").read_text(encoding="utf-8"))[
            "questions"
        ][0]
        assert preserved["curve_version"] == 1
        assert preserved["curve_intervals"] == [2, 6, 12]
        assert preserved["next_due_at"] == "2026-01-07T00:00:00Z"


def test_application_exposes_no_source_or_course_authoring_routes(
    runtime_home: Path, tmp_path: Path
) -> None:
    app = create_app(
        session_token="exam-only-session",
        web_dir=tmp_path / "missing-web",
    )
    workspace = tmp_path / "ExamOnlyWorkspace"

    with TestClient(app) as client:
        client.get("/bootstrap/exam-only-session", follow_redirects=False)
        onboard = client.post(
            "/api/v1/onboarding/complete",
            json={
                "workspace_path": str(workspace),
                "workspace_name": "Exam only workspace",
                "language": "en",
                "reduced_motion": False,
                "review_intervals": [1, 3, 7],
            },
        )
        assert onboard.status_code == 200

        assert client.get("/api/v1/sources").status_code == 404
        assert client.post("/api/v1/sources", json={}).status_code == 405
        assert client.get("/api/v1/knowledge").status_code == 404
        assert client.get("/api/v1/evidence-activity").status_code == 404

    assert not (workspace / "courses").exists()
