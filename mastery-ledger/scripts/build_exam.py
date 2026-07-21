#!/usr/bin/env python3
"""Build an app-compatible exam from validated question-bank items."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from course_paths import PUBLICATION_RECEIPT, SOURCE_MANIFEST
from record_action import append_event
from render_question_bank import render
from source_registry import sha256_file
from validate_evidence import load_source_ids
from validate_study_pack import validate_question_bank, validate_workspace


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "exam"


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    parser.add_argument("--exam-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--question-id", action="append", default=[])
    parser.add_argument("--ready", action="store_true")
    args = parser.parse_args()
    root = args.course_root.resolve()
    bank = json.loads((root / "questions" / "question-bank.json").read_text(encoding="utf-8"))
    (root / "questions" / "question-bank.md").write_text(render(bank), encoding="utf-8")
    questions = bank.get("questions", [])
    selected_ids = set(args.question_id)
    selected = [item for item in questions if not selected_ids or item.get("question_id") in selected_ids]
    if selected_ids and selected_ids != {str(item.get("question_id")) for item in selected}:
        parser.error("One or more requested question IDs were not found.")
    if not selected:
        parser.error("No questions selected.")
    bank_errors, _ = validate_question_bank(bank, source_ids=load_source_ids(root / SOURCE_MANIFEST), concept_ids=set())
    if bank_errors:
        parser.error("Question bank is invalid: " + "; ".join(bank_errors))
    if args.ready and any(item.get("quality_status") != "validated" for item in selected):
        parser.error("Every question must have quality_status=validated before a ready exam is built.")
    exam_id = args.exam_id.strip()
    payload = {
        "schema_version": "exam-v1",
        "exam_id": exam_id,
        "course_id": bank.get("study_id"),
        "title": args.title,
        "status": "ready" if args.ready else "draft",
        "source_status": "verified" if args.ready else "review_needed",
        "question_count": len(selected),
        "estimated_minutes": max(5, round(len(selected) * 1.5)),
        "concept_ids": sorted({str(concept) for item in selected for concept in item.get("concept_ids", [])}),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "questions": selected,
    }
    if args.ready:
        errors, _ = validate_workspace(root, publication=True, require_ready_exam=False)
        if errors:
            print(json.dumps({"status": "fail", "errors": errors, "exam": None}, ensure_ascii=False, indent=2))
            return 1
    path = root / "exams" / slug(exam_id) / "exam.json"
    atomic_json(path, payload)
    artifacts = [path.relative_to(root).as_posix()]
    if args.ready:
        lesson_hashes: dict[str, str] = {}
        for chapter in bank.get("chapters", []):
            if not isinstance(chapter, dict) or not isinstance(chapter.get("lesson_path"), str):
                continue
            lesson = root / chapter["lesson_path"]
            if lesson.is_file() and not lesson.is_symlink():
                lesson_hashes[chapter["lesson_path"]] = sha256_file(lesson)
        receipt_path = root / PUBLICATION_RECEIPT
        atomic_json(receipt_path, {
            "schema_version": "publication-receipt-v1",
            "exam_id": exam_id,
            "exam_path": path.relative_to(root).as_posix(),
            "exam_sha256": sha256_file(path),
            "question_bank_sha256": sha256_file(root / "questions" / "question-bank.json"),
            "source_manifest_sha256": sha256_file(root / SOURCE_MANIFEST),
            "lesson_sha256": lesson_hashes,
            "validated_at": datetime.now(timezone.utc).isoformat(),
        })
        artifacts.append(receipt_path.relative_to(root).as_posix())
    append_event(root, {
        "action": "exam.built", "actor": "main-agent", "status": payload["status"],
        "summary": f"Built {len(selected)}-question exam {exam_id}.",
        "artifacts": artifacts, "decision": payload["status"],
        "justification": "Questions passed the canonical bank validator."
    })
    print(json.dumps({"status": payload["status"], "exam": str(path), "questions": len(selected)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
