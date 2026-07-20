#!/usr/bin/env python3
"""Create and update the observable pre-research calibration record."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def path_for(root: Path) -> Path:
    return root.resolve() / "progress" / "calibration.json"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def write(path: Path, payload: dict) -> None:
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
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start")
    start.add_argument("course_root", type=Path)
    start.add_argument("--count", type=int, required=True)
    start.add_argument("--concept-questions", type=int, required=True)
    start.add_argument("--scenario-questions", type=int, required=True)
    start.add_argument("--disposition", choices=["begin", "adjust", "skip"], required=True)
    add = subparsers.add_parser("add")
    add.add_argument("course_root", type=Path)
    add.add_argument("--question-id", required=True)
    add.add_argument("--format", choices=["concept", "scenario"], required=True)
    add.add_argument("--question", required=True)
    add.add_argument("--learner-answer", required=True)
    add.add_argument("--feedback-shown", required=True)
    add.add_argument("--confidence", type=float)
    finish = subparsers.add_parser("finish")
    finish.add_argument("course_root", type=Path)
    finish.add_argument("--branch", action="append", default=[])
    args = parser.parse_args()

    path = path_for(args.course_root)
    if args.command == "start":
        if not 3 <= args.count <= 10 and args.disposition != "skip":
            parser.error("Calibration count must be 3-10 unless skipped.")
        if args.concept_questions + args.scenario_questions != args.count:
            parser.error("Concept and scenario counts must add up to count.")
        payload = {
            "schema_version": "calibration-v1",
            "status": "skipped" if args.disposition == "skip" else "in_progress",
            "disposition": args.disposition,
            "announced_count": args.count,
            "mix": {"concept": args.concept_questions, "scenario": args.scenario_questions},
            "started_at": timestamp(),
            "completed_at": timestamp() if args.disposition == "skip" else None,
            "interactions": [],
            "proposed_branches": [],
        }
    else:
        payload = read(path)
        if payload.get("schema_version") != "calibration-v1":
            parser.error("Start calibration before recording interactions.")
        if args.command == "add":
            if payload.get("status") != "in_progress":
                parser.error("Calibration is not in progress.")
            interactions = payload.setdefault("interactions", [])
            if len(interactions) >= int(payload.get("announced_count", 0)):
                parser.error("The announced calibration count is already complete.")
            confidence = args.confidence
            if confidence is not None and not 0 <= confidence <= 1:
                parser.error("Confidence must be from 0 to 1.")
            interactions.append({
                "question_id": args.question_id,
                "format": args.format,
                "question_shown": args.question,
                "learner_answer": args.learner_answer,
                "feedback_shown": args.feedback_shown,
                "confidence": confidence,
                "recorded_at": timestamp(),
            })
        else:
            if payload.get("status") != "in_progress":
                parser.error("Calibration is not in progress.")
            if len(payload.get("interactions", [])) != int(payload.get("announced_count", 0)):
                parser.error("Record the announced number of interactions before finishing.")
            branches = []
            for raw in args.branch:
                category, separator, title = raw.partition(":")
                if not separator or category not in {
                    "REQUIRED_NOW", "HELPFUL_SOON", "OPTIONAL_DEEP_DIVE", "SEPARATE_STUDY_RECOMMENDED"
                } or not title.strip():
                    parser.error("Each --branch must be CATEGORY:Title using an allowed category.")
                branches.append({"category": category, "title": title.strip(), "accepted": None})
            if len(branches) > 5:
                parser.error("Propose no more than five branches.")
            payload["proposed_branches"] = branches
            payload["status"] = "complete"
            payload["completed_at"] = timestamp()
    write(path, payload)
    print(json.dumps({"status": payload["status"], "path": str(path), "recorded": len(payload["interactions"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
