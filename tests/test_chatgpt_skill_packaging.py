from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "mastery-ledger-chatgpt" / "SKILL.md"
BUILDER = ROOT / "skill-build" / "build_chatgpt_skill.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_chatgpt_skill_frontmatter_and_ui_metadata() -> None:
    content = SKILL.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    assert match is not None
    keys = re.findall(r"(?m)^([a-zA-Z][a-zA-Z0-9_-]*):", match.group(1))
    assert keys == ["name", "description"]
    assert re.search(r"(?m)^name: mastery-ledger-chatgpt$", match.group(1))

    metadata = (SKILL.parent / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert 'display_name: "Mastery Ledger for ChatGPT"' in metadata
    assert "$mastery-ledger-chatgpt" in metadata


def test_upload_manifest_is_self_contained() -> None:
    content = SKILL.read_text(encoding="utf-8")
    body = content.split("---\n", 2)[2]
    local_links = [
        raw
        for raw in re.findall(r"\[[^\]]+\]\(([^)]+)\)", body)
        if not raw.startswith(("https://", "http://", "mailto:", "#"))
    ]
    assert local_links == []

    lowered = body.lower()
    forbidden = {
        "assets/",
        "download_media.py",
        "faster-whisper",
        "manage_worker_runtime.py",
        "mastery-ledger/skill.md",
        "references/",
        "scripts/",
        "spawn_agent",
        "transcribe_media.py",
        "worker-runtime-contract.md",
        "yt-dlp",
    }
    assert [term for term in forbidden if term in lowered] == []


def test_upload_manifest_contains_essential_embedded_contracts() -> None:
    content = SKILL.read_text(encoding="utf-8")
    for required in (
        "DRAFT_UNVERIFIED",
        "same-agent-recheck",
        "source-ref-v1",
        "Contradiction check",
        "Citation check",
        "Assessment check",
        "I cannot transcribe or inspect the spoken content of this video",
        "Never ask ChatGPT to transcribe",
        "Never offer transcription as a capability",
        "exactly ten multiple-choice questions",
        "no durable course bundle was created",
        "mastery-ledger-course-bundle-v1",
        "course-layout-v2",
        "exactly one top-level folder",
        "questions/question-bank.json",
        "progress/learner-progress.json",
        "records/source-manifest.yaml",
        "records/evidence/approved-claims.json",
        "records/logs/events.jsonl",
        "status: draft",
        "workflow_state: STUDY_PACK_DRAFTED",
    ):
        assert required in content


def test_upload_manifest_stays_within_single_file_context_budget() -> None:
    content = SKILL.read_text(encoding="utf-8")
    assert len(content.encode("utf-8")) < 250 * 1024
    assert len(content.splitlines()) < 500
    assert len(re.findall(r"\b\w+\b", content)) < 5000


def test_builder_emits_only_skill_md(tmp_path: Path) -> None:
    output = tmp_path / "chatgpt-upload" / "SKILL.md"
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--output", str(output), "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "valid"
    assert payload["file_count"] == 1
    assert output.is_file()
    assert list(output.parent.iterdir()) == [output]
    assert output.read_bytes() == SKILL.read_bytes()
    assert payload["skill_sha256"] == sha256(output)


def test_builder_rejects_non_manifest_output_name(tmp_path: Path) -> None:
    output = tmp_path / "mastery-ledger-chatgpt.md"
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--output", str(output), "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "invalid"
    assert "must be named SKILL.md" in payload["errors"][0]
