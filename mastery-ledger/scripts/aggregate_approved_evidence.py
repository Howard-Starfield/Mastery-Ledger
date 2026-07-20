#!/usr/bin/env python3
"""Aggregate claims from reports explicitly approved by the main agent."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def parse_simple_yaml(path: Path) -> dict[str, Any]:
    """Parse the top-level scalar fields needed from review YAML.

    Full YAML parsing is intentionally avoided so the script remains standard-
    library only. JSON review files are also supported and preferred for
    programmatic pipelines.
    """
    result: dict[str, Any] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*?)\s*$", line)
        if not match:
            continue
        key, raw = match.groups()
        raw = raw.strip().strip('"\'')
        if raw in {"null", "~", ""}:
            value: Any = None
        elif raw.lower() in {"true", "false"}:
            value = raw.lower() == "true"
        else:
            value = raw
        result[key] = value
    return result


def load_records(directory: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*")):
        if path.suffix.lower() == ".json":
            records.append(json.loads(path.read_text(encoding="utf-8")))
        elif path.suffix.lower() in {".yaml", ".yml"}:
            records.append(parse_simple_yaml(path))
    return records


def aggregate(
    reports: dict[str, dict[str, Any]],
    reviews: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    approval_by_report: dict[str, dict[str, Any]] = {}
    for review in reviews:
        report_id = str(review.get("report_id", "")).strip()
        if not report_id:
            errors.append("Review missing report_id")
            continue
        if review.get("decision") == "approved" and review.get("approved_by") == "main-agent":
            approval_by_report[report_id] = review

    merged: list[dict[str, Any]] = []
    seen_claim_ids: set[str] = set()
    for report_id in sorted(approval_by_report):
        report = reports.get(report_id)
        if report is None:
            errors.append(f"Approved review references missing report: {report_id}")
            continue
        claims = report.get("claims", [])
        if not isinstance(claims, list):
            errors.append(f"Report {report_id} has non-list claims")
            continue
        for claim in claims:
            if not isinstance(claim, dict):
                errors.append(f"Report {report_id} contains non-object claim")
                continue
            claim_id = str(claim.get("claim_id", "")).strip()
            if not claim_id:
                errors.append(f"Report {report_id} contains claim without claim_id")
                continue
            if claim_id in seen_claim_ids:
                errors.append(f"Duplicate approved claim_id: {claim_id}")
                continue
            seen_claim_ids.add(claim_id)
            merged.append(claim)
    return merged, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, required=True)
    parser.add_argument("--reviews-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.reports_dir.is_dir():
        parser.error(f"Reports directory does not exist: {args.reports_dir}")
    if not args.reviews_dir.is_dir():
        parser.error(f"Reviews directory does not exist: {args.reviews_dir}")

    report_list = load_records(args.reports_dir)
    reports = {str(record.get("report_id")): record for record in report_list if record.get("report_id")}
    reviews = load_records(args.reviews_dir)
    merged, errors = aggregate(reports, reviews)
    if errors:
        print(json.dumps({"status": "fail", "errors": errors}, ensure_ascii=False, indent=2))
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": "1.0", "claims": merged}
    temp_path = args.output.with_suffix(args.output.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(args.output)
    print(json.dumps({"status": "pass", "claims": len(merged), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
