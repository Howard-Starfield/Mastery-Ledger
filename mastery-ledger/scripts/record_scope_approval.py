#!/usr/bin/env python3
"""Record the learner-visible scope approval used by workflow reconciliation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import yaml

from advance_workflow import atomic_yaml
from record_action import append_event


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course_root", type=Path)
    parser.add_argument("--summary", required=True, help="Concise learner-approved scope")
    parser.add_argument("--source-limit", type=int, required=True)
    parser.add_argument("--research-workers", type=int, required=True)
    parser.add_argument("--accepted-branch", action="append", default=[])
    parser.add_argument("--excluded", action="append", default=[])
    parser.add_argument("--assumed-level", default="beginner")
    args = parser.parse_args()
    if not 1 <= args.source_limit <= 20:
        parser.error("Source limit must be 1-20.")
    if args.research_workers != 0:
        parser.error("research_workers must be 0; new runs use source-specific extractors instead of concept-research workers.")

    root = args.course_root.resolve()
    path = root / "study.yaml"
    study = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(study, dict):
        parser.error("study.yaml must contain a YAML object.")
    mode = str(study.get("mode", ""))
    if mode in {"topic-research", "hybrid"} and args.source_limit > 5:
        parser.error("Verified Course research may retain at most five sources; the default is three.")
    if mode == "hybrid" and args.source_limit < 2:
        parser.error("Anchor-plus-corroboration requires room for at least one anchor and one corroborating source.")

    now = datetime.now(timezone.utc).isoformat()
    study["scope_approval"] = {
        "status": "approved",
        "approved_at": now,
        "summary": args.summary.strip(),
        "source_limit": args.source_limit,
        "research_workers": args.research_workers,
        "accepted_branches": args.accepted_branch,
        "excluded": args.excluded,
    }
    study["learner_goal"] = args.summary.strip()
    study["source_policy"] = mode
    study["learning_contract"] = {
        "status": "approved",
        "approved_at": now,
        "goal": args.summary.strip(),
        "assumed_level": args.assumed_level.strip() or "beginner",
        "accepted_branches": args.accepted_branch,
        "excluded": args.excluded,
        "source_limit": args.source_limit,
        "research_workers": args.research_workers,
        "output_contract": {
            "lesson_schema": "lesson-v1",
            "default_chapter_range": "1-3",
            "standard_lesson_words": "1200-1800",
            "question_tier": "standard",
            "questions_per_chapter": 10,
            "ready_exam_required": True,
        },
    }
    study.setdefault("workflow_target", "LEARNING_ACTIVE")
    study["updated_at"] = now
    atomic_yaml(path, study)
    append_event(root, {
        "action": "scope.approved",
        "actor": "main-agent",
        "status": "complete",
        "summary": "Recorded the learner-approved scope, source limit, and worker budget.",
        "artifacts": ["study.yaml"],
        "decision": "approved",
        "justification": args.summary.strip(),
    })
    print(yaml.safe_dump({"status": "complete", "scope_approval": study["scope_approval"]}, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
