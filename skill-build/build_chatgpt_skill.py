"""Validate and emit the single-file Mastery Ledger ChatGPT skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path, PurePosixPath
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = Path(__file__).with_name("chatgpt-single-file-build.json")
FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
FORBIDDEN_DEPENDENCIES = {
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
REQUIRED_CONTRACTS = {
    "DRAFT_UNVERIFIED",
    "mastery-ledger-course-bundle-v1",
    "course-layout-v2",
    "exactly one top-level folder",
    "questions/question-bank.json",
    "exams/PRACTICE-001/exam.json",
    "practice_ready",
    "mastery_eligible",
    "progress/learner-progress.json",
    "records/source-manifest.yaml",
    "records/evidence/approved-claims.json",
    "records/evidence/validation/artifact-hashes.json",
    "records/logs/events.jsonl",
    "same-agent-recheck",
    "source-ref-v1",
    "Never use aliases such as `start_line`, `end_line`",
    "permit no keys except those shown for its kind",
    "Validate **every locator occurrence**",
    "Reopen each unique passage once",
    "does **not** reuse an entailment judgment",
    "Availability belongs to the unique passage",
    "locator_occurrences_checked",
    "unique_locators_reopened",
    "unsupported_items_removed",
    "unresolved_findings",
    "artifact-hash-manifest-v1",
    "sha256-raw-bytes-v1",
    "sorted-path-tab-sha256-lf-v1",
    "Exclude the manifest and check receipts to prevent cycles",
    "contradiction check",
    "citation check",
    "assessment check",
    "I cannot transcribe or inspect the spoken content of this video",
    "Never ask ChatGPT to transcribe",
}
MAX_SKILL_BYTES = 250 * 1024


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_relative(value: str, field: str) -> Path:
    posix = PurePosixPath(value.replace("\\", "/"))
    if posix.is_absolute() or ".." in posix.parts or not posix.parts:
        raise ValueError(f"{field} must be a non-empty repository-relative path: {value}")
    return Path(*posix.parts)


def load_spec(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != "chatgpt-single-file-build-v1"
    ):
        raise ValueError("Build spec must use schema_version chatgpt-single-file-build-v1")
    required = {"package_name", "package_version", "source_file", "default_output"}
    missing = sorted(required.difference(payload))
    if missing:
        raise ValueError(f"Build spec is missing: {', '.join(missing)}")
    return payload


def validate_skill(source: Path, package_name: str) -> list[str]:
    errors: list[str] = []
    if source.name != "SKILL.md":
        errors.append("The source upload manifest must be named SKILL.md")
        return errors
    if not source.is_file():
        errors.append(f"Source SKILL.md does not exist: {source}")
        return errors
    if source.is_symlink():
        errors.append("The source SKILL.md may not be a symlink")
        return errors
    if source.stat().st_size > MAX_SKILL_BYTES:
        errors.append(f"SKILL.md exceeds {MAX_SKILL_BYTES} bytes")

    try:
        content = source.read_text(encoding="utf-8")
    except UnicodeError:
        errors.append("SKILL.md must be UTF-8")
        return errors

    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        errors.append("SKILL.md must begin with YAML frontmatter")
        return errors
    keys = re.findall(r"(?m)^([a-zA-Z][a-zA-Z0-9_-]*):", match.group(1))
    if keys != ["name", "description"]:
        errors.append(f"Frontmatter must contain only name and description; found {keys}")
    if not re.search(rf"(?m)^name: {re.escape(package_name)}$", match.group(1)):
        errors.append(f"SKILL.md name must be {package_name}")

    body = content[match.end() :]
    for raw_link in MARKDOWN_LINK_PATTERN.findall(body):
        if not raw_link.startswith(("https://", "http://", "mailto:", "#")):
            errors.append(f"Upload SKILL.md contains a companion-file link: {raw_link}")
    lowered = body.lower()
    for term in sorted(FORBIDDEN_DEPENDENCIES):
        if term in lowered:
            errors.append(f"Upload SKILL.md depends on unavailable functionality: {term}")
    for contract in sorted(REQUIRED_CONTRACTS):
        if contract.lower() not in lowered:
            errors.append(f"Upload SKILL.md is missing required contract: {contract}")
    return errors


def build(spec_path: Path, output: Path | None) -> dict[str, Any]:
    spec = load_spec(spec_path)
    source = (REPO_ROOT / safe_relative(str(spec["source_file"]), "source_file")).resolve()
    errors = validate_skill(source, str(spec["package_name"]))
    result: dict[str, Any] = {
        "schema_version": "chatgpt-single-file-build-result-v1",
        "status": "invalid" if errors else "valid",
        "package_name": spec["package_name"],
        "package_version": spec["package_version"],
        "source": str(source),
        "file_count": 1,
        "errors": errors,
    }
    if errors:
        return result

    output_path = output or (REPO_ROOT / safe_relative(str(spec["default_output"]), "default_output"))
    output_path = output_path.resolve()
    if output_path.name != "SKILL.md":
        raise ValueError("ChatGPT upload output must be named SKILL.md")
    if output_path == source:
        raise ValueError("Output SKILL.md must differ from the authoring source")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output_path)
    result.update(
        {
            "output": str(output_path),
            "skill_bytes": output_path.stat().st_size,
            "skill_sha256": sha256_file(output_path),
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the self-contained one-file Mastery Ledger ChatGPT skill."
    )
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC, help="Build specification JSON.")
    parser.add_argument("--output", type=Path, help="Output path, which must end in SKILL.md.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON output.")
    args = parser.parse_args()

    try:
        result = build(args.spec.resolve(), args.output)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema_version": "chatgpt-single-file-build-result-v1",
            "status": "invalid",
            "errors": [str(exc)],
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "valid":
        print(f"Built {result['output']} (one file)")
    else:
        for error in result.get("errors", []):
            print(f"Error: {error}", file=sys.stderr)
    return 0 if result["status"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
