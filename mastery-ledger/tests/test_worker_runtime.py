from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from test_publication_pipeline import prepare_assessment_inputs


ROOT = Path(__file__).resolve().parents[1]


def run_script(name: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def prepare_provided_course(parent: Path, source_count: int = 5) -> Path:
    run_script("init_study.py", "Capacity Course", "--mode", "provided-material-only", "--studies-dir", str(parent))
    course = parent / "capacity-course"
    study_path = course / "study.yaml"
    study = yaml.safe_load(study_path.read_text(encoding="utf-8"))
    study["workflow_state"] = "CORPUS_MAPPED"
    study["learning_contract"] = {
        "status": "approved",
        "approved_at": "2026-07-21T00:00:00Z",
        "goal": "Learn from the supplied material",
        "accepted_branches": ["core"],
        "excluded": [],
        "source_limit": source_count,
        "research_workers": 0,
    }
    study_path.write_text(yaml.safe_dump(study, sort_keys=False), encoding="utf-8")
    for index in range(1, source_count + 1):
        source_id = f"SRC-{index:03d}"
        path = course / "records" / "source" / f"{source_id}.md"
        path.write_text(f"# {source_id}\n\nSubstantive source content with a stable section locator.\n", encoding="utf-8")
        run_script(
            "register_source.py", str(course), "--source-id", source_id, "--title", source_id,
            "--location", f"https://example.invalid/{source_id}", "--knowledge-path", f"records/source/{source_id}.md",
        )
    run_script("create_provided_evidence_plan.py", str(course), "--authorized")
    plan = yaml.safe_load((course / ".work" / "orchestration" / "run-plan.yaml").read_text(encoding="utf-8"))
    for task in plan["task_graph"]:
        if task["role"] == "source-extractor":
            run_script("compile_worker_context.py", str(course), task["task_id"], "--json")
    return course


def write_valid_extractor_return(course: Path, task_id: str) -> None:
    plan_path = course / ".work" / "orchestration" / "run-plan.yaml"
    plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    task = next(item for item in plan["task_graph"] if item["task_id"] == task_id)
    source_id = task_id.removeprefix("TASK-EXTRACT-")
    output = {
        "schema_version": "evidence-packet-v1",
        "source_ref_schema": "source-ref-v1",
        "report_id": f"REPORT-{task_id}",
        "task_id": task_id,
        "worker_role": "source-extractor",
        "scope": {"included": ["core"], "excluded": []},
        "sources_used": [source_id],
        "claims": [],
        "contradictions": [],
        "unresolved_questions": [],
        "suggested_concepts": [],
        "scope_drift": [],
        "quality_notes": [],
    }
    output_path = course / task["output_path"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    (course / task["event_path"]).write_text(json.dumps({
        "schema_version": "action-event-v1",
        "event_id": f"EVT-{task_id}",
        "timestamp": "2026-07-21T00:00:00Z",
        "run_id": task["run_id"],
        "task_id": task_id,
        "action": "source-extractor.completed",
        "actor": "source-extractor",
        "status": "complete",
        "summary": "Submitted the bounded source packet.",
        "artifacts": [task["output_path"]],
    }, separators=(",", ":")) + "\n", encoding="utf-8")
    completion_path = course / task["completion_path"]
    completion = json.loads((course / task["completion_template_path"]).read_text(encoding="utf-8"))
    completion["summary"] = "Submitted the bounded source packet."
    completion["completed_at"] = "2026-07-21T00:00:00Z"
    completion_path.write_text(json.dumps(completion, indent=2) + "\n", encoding="utf-8")


def test_capacity_queue_uses_three_normal_slots_and_preserves_the_fourth() -> None:
    with tempfile.TemporaryDirectory() as directory:
        course = prepare_provided_course(Path(directory))
        status = json.loads(run_script("manage_worker_runtime.py", "status", str(course)).stdout)
        assert status["hard_agent_limit"] == 4
        assert status["normal_active_limit"] == 3
        assert status["reserve_slots"] == 1
        assert len(status["dispatch_task_ids"]) == 3

        for index, task_id in enumerate(status["dispatch_task_ids"], 1):
            reserved = json.loads(run_script("manage_worker_runtime.py", "reserve", str(course), task_id).stdout)
            run_script(
                "manage_worker_runtime.py", "attach", str(course), task_id,
                "--reservation-id", reserved["reservation_id"], "--agent-id", f"agent-{index}",
            )

        saturated = json.loads(run_script("manage_worker_runtime.py", "status", str(course)).stdout)
        assert saturated["active_count"] == 3
        assert saturated["available_normal_slots"] == 0
        assert saturated["dispatch_task_ids"] == []


def test_capacity_rejection_releases_reservation_without_unverified_publication() -> None:
    with tempfile.TemporaryDirectory() as directory:
        course = prepare_provided_course(Path(directory), source_count=1)
        status = json.loads(run_script("manage_worker_runtime.py", "status", str(course)).stdout)
        task_id = status["dispatch_task_ids"][0]
        reserved = json.loads(run_script("manage_worker_runtime.py", "reserve", str(course), task_id).stdout)
        released = json.loads(run_script(
            "manage_worker_runtime.py", "release", str(course), task_id,
            "--reservation-id", reserved["reservation_id"], "--reason", "agent thread limit reached",
        ).stdout)
        assert released["status"] == "queued"
        assert released["publication_status_changed"] is False
        study = yaml.safe_load((course / "study.yaml").read_text(encoding="utf-8"))
        assert study["publication_status"] != "DRAFT_UNVERIFIED"
        resumed = json.loads(run_script("manage_worker_runtime.py", "status", str(course)).stdout)
        assert resumed["dispatch_task_ids"] == [task_id]


def test_managed_worker_must_return_then_route_and_close_before_refill() -> None:
    with tempfile.TemporaryDirectory() as directory:
        course = prepare_provided_course(Path(directory), source_count=2)
        status = json.loads(run_script("manage_worker_runtime.py", "status", str(course)).stdout)
        task_id = status["dispatch_task_ids"][0]
        reservation = json.loads(run_script("manage_worker_runtime.py", "reserve", str(course), task_id).stdout)
        run_script(
            "manage_worker_runtime.py", "attach", str(course), task_id,
            "--reservation-id", reservation["reservation_id"], "--agent-id", "extractor-1",
        )
        write_valid_extractor_return(course, task_id)

        premature = run_script("route_worker_completion.py", str(course), task_id, check=False)
        assert premature.returncode == 2
        assert "must be marked returned" in premature.stderr

        run_script("manage_worker_runtime.py", "returned", str(course), task_id)
        routed = json.loads(run_script("route_worker_completion.py", str(course), task_id).stdout)
        assert routed["status"] == "accepted"
        awaiting_close = json.loads(run_script("manage_worker_runtime.py", "status", str(course)).stdout)
        assert awaiting_close["dispatch_task_ids"] == []
        assert awaiting_close["close_required_task_ids"] == [task_id]

        closed = json.loads(run_script(
            "manage_worker_runtime.py", "confirm-close", str(course), task_id,
            "--reason", "Accepted completion routed and agent closed.",
        ).stdout)
        assert closed["status"] == "closed"
        refilled = json.loads(run_script("manage_worker_runtime.py", "status", str(course)).stdout)
        assert refilled["active_count"] == 0
        assert len(refilled["dispatch_task_ids"]) == 1


def test_stalled_reviewer_gets_one_fresh_worker_then_becomes_unverified() -> None:
    with tempfile.TemporaryDirectory() as directory:
        parent = Path(directory)
        run_script("init_study.py", "Review Course", "--mode", "provided-material-only", "--studies-dir", str(parent))
        course = parent / "review-course"
        prepare_assessment_inputs(course)
        run_script("create_assessment_plan.py", str(course), "--authorized")
        task_id = "TASK-ASSESSMENT-VALIDATE"
        run_script("compile_worker_context.py", str(course), task_id, "--json")

        first = json.loads(run_script("manage_worker_runtime.py", "reserve", str(course), task_id).stdout)
        run_script(
            "manage_worker_runtime.py", "attach", str(course), task_id,
            "--reservation-id", first["reservation_id"], "--agent-id", "reviewer-1",
        )
        for _ in range(5):
            silence = json.loads(run_script("manage_worker_runtime.py", "silent-poll", str(course), task_id).stdout)
        assert silence["status"] == "stall_suspected"
        retry = json.loads(run_script(
            "manage_worker_runtime.py", "confirm-close", str(course), task_id, "--reason", "Reviewer made no observable progress after probe.",
        ).stdout)
        assert retry["status"] == "queued_retry"
        assert retry["restart_allowed"] is True

        second = json.loads(run_script("manage_worker_runtime.py", "reserve", str(course), task_id).stdout)
        run_script(
            "manage_worker_runtime.py", "attach", str(course), task_id,
            "--reservation-id", second["reservation_id"], "--agent-id", "reviewer-2",
        )
        for _ in range(5):
            run_script("manage_worker_runtime.py", "silent-poll", str(course), task_id)
        exhausted = run_script(
            "manage_worker_runtime.py", "confirm-close", str(course), task_id, "--reason", "Replacement reviewer also stalled.", check=False,
        )
        assert exhausted.returncode == 3
        payload = json.loads(exhausted.stdout)
        assert payload["status"] == "retry_exhausted"
        assert payload["publication_status"] == "DRAFT_UNVERIFIED"
        study = yaml.safe_load((course / "study.yaml").read_text(encoding="utf-8"))
        assert study["workflow_state"] == "EVIDENCE_APPROVED"
        assert study["publication_status"] == "DRAFT_UNVERIFIED"
