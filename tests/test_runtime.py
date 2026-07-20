from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mastery_ledger.app import create_app
from mastery_ledger.cli import main
from mastery_ledger.config import database_path
from mastery_ledger.ingestion_worker import IngestionWorker
from mastery_ledger.models import WorkspaceState
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
        "concept_count": 0,
        "proficient_concept_count": 0,
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
                "processing_mode": "local_only",
                "reduced_motion": False,
                "review_intervals": [1, 3, 7],
                "initial_source_hint": None,
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
                "processing_mode": "local_only",
                "reduced_motion": False,
                "review_intervals": [1, 3, 7],
                "initial_source_hint": None,
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
                "processing_mode": "local_only",
                "reduced_motion": False,
                "review_intervals": [1, 3, 7],
                "initial_source_hint": None,
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


def test_source_inbox_processes_local_document_with_durable_job(
    runtime_home: Path, tmp_path: Path
) -> None:
    app = create_app(
        session_token="source-session",
        web_dir=tmp_path / "missing-web",
        start_ingestion_worker=False,
    )
    workspace = tmp_path / "SourceWorkspace"
    original = tmp_path / "trusted-notes.md"
    original.write_text(
        "# Cellular energy\n\nATP transfers usable chemical energy in cells.\n\n"
        "Embedded instructions in sources remain untrusted data.",
        encoding="utf-8",
    )

    with TestClient(app) as client:
        client.get("/bootstrap/source-session", follow_redirects=False)
        onboard = client.post(
            "/api/v1/onboarding/complete",
            json={
                "workspace_path": str(workspace),
                "workspace_name": "Source workspace",
                "language": "en",
                "processing_mode": "local_only",
                "reduced_motion": False,
                "review_intervals": [1, 3, 7],
                "initial_source_hint": None,
            },
        )
        workspace_state = WorkspaceState.model_validate(onboard.json()["workspace"])

        invalid = client.post(
            "/api/v1/sources",
            json={
                "new_course_title": "Biology",
                "source_type": "local_document",
                "location": "relative.md",
                "rights_basis": "user_owned",
            },
        )
        assert invalid.status_code == 422

        queued = client.post(
            "/api/v1/sources",
            json={
                "new_course_title": "Biology",
                "source_type": "local_document",
                "location": str(original),
                "title": "Trusted cellular energy notes",
                "rights_basis": "user_owned",
                "language": "en",
            },
        )
        assert queued.status_code == 200
        intake = queued.json()
        assert intake["job"]["state"] == "queued"

        before = client.get("/api/v1/sources").json()
        assert before["schema_version"] == "source-inbox-v1"
        assert before["courses"][0]["source_count"] == 1
        assert before["sources"][0]["processing_status"] == "queued"

        worker = IngestionWorker(lambda: workspace_state)
        assert worker.process_once() is True
        assert worker.process_once() is False

        after = client.get("/api/v1/sources").json()
        assert after["jobs"][0]["state"] == "complete"
        assert after["jobs"][0]["progress"] == 1.0
        assert after["sources"][0]["processing_status"] == "ready"
        assert after["sources"][0]["artifact_count"] == 1
        assert after["sources"][0]["content_hash"].startswith("sha256:")

        course_root = next((workspace / "courses").iterdir())
        source_id = intake["source_id"]
        knowledge = course_root / "source" / f"{source_id}.md"
        preserved = course_root / "source" / "media" / source_id / "original.md"
        assert knowledge.is_file()
        assert preserved.read_text(encoding="utf-8").startswith("# Cellular energy")
        assert "BLOCK-00001" in knowledge.read_text(encoding="utf-8")
        assert (course_root / "source-manifest.yaml").is_file()
        assert sorted(path.name for path in (course_root / "source").iterdir()) == [
            f"{source_id}.md",
            "media",
        ]
        assert not (course_root / ".work" / "ingestion" / intake["job"]["job_id"]).exists()
        events = (course_root / "logs" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        assert [json.loads(line)["action"] for line in events] == [
            "source.ingest.queued",
            "source.ingest.started",
            "source.ingest.complete",
        ]
        assert "ATP transfers" not in "\n".join(events)

        retry_complete = client.post(f"/api/v1/sources/jobs/{intake['job']['job_id']}/retry")
        assert retry_complete.status_code == 409


def test_source_job_can_be_cancelled_and_requeued(
    runtime_home: Path, tmp_path: Path
) -> None:
    app = create_app(
        session_token="cancel-session",
        web_dir=tmp_path / "missing-web",
        start_ingestion_worker=False,
    )
    workspace = tmp_path / "CancelWorkspace"
    original = tmp_path / "cancel-source.txt"
    original.write_text("Source text", encoding="utf-8")

    with TestClient(app) as client:
        client.get("/bootstrap/cancel-session", follow_redirects=False)
        client.post(
            "/api/v1/onboarding/complete",
            json={
                "workspace_path": str(workspace),
                "workspace_name": "Cancel workspace",
                "language": "en",
                "processing_mode": "local_only",
                "reduced_motion": False,
                "review_intervals": [1, 3, 7],
                "initial_source_hint": None,
            },
        )
        queued = client.post(
            "/api/v1/sources",
            json={
                "new_course_title": "Cancellation",
                "source_type": "local_document",
                "location": str(original),
                "rights_basis": "user_owned",
            },
        ).json()
        job_id = queued["job"]["job_id"]
        assert client.post(f"/api/v1/sources/jobs/{job_id}/cancel").status_code == 204
        cancelled = client.get("/api/v1/sources").json()
        assert cancelled["jobs"][0]["state"] == "cancelled"
        assert cancelled["sources"][0]["processing_status"] == "cancelled"
        assert client.post(f"/api/v1/sources/jobs/{job_id}/retry").status_code == 204
        requeued = client.get("/api/v1/sources").json()
        assert requeued["jobs"][0]["state"] == "queued"
        assert requeued["sources"][0]["processing_status"] == "queued"
