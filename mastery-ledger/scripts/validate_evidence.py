#!/usr/bin/env python3
"""Validate evidence-packet structure and source references.

This validator enforces integrity only. It does not decide whether a claim is
true or whether a cited passage semantically supports it.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

CLAIM_TYPES = {"source_fact", "interpretation", "inference", "disputed", "outdated", "not_covered"}
SUPPORT_STRENGTH = {"direct", "partial", "contextual"}
SUPPORT_TARGETS = {
    "claim",
    "question_prompt",
    "correct_answer",
    "explanation",
    "distractor",
    "context",
    "counterevidence",
}
LOCATOR_KINDS = {
    "page",
    "page_range",
    "section",
    "paragraph",
    "heading",
    "heading_path",
    "timestamp",
    "timestamp_range",
    "slide",
    "figure",
    "table",
    "line_range",
    "url_fragment",
    "whole_source",
}


def load_source_ids(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        sources = payload.get("sources", payload if isinstance(payload, list) else [])
        return {str(item["source_id"]) for item in sources if isinstance(item, dict) and item.get("source_id")}
    return set(re.findall(r"(?m)^\s*(?:-\s*)?source_id:\s*[\"']?([^\s\"']+)", text))


def validate_source_ref(
    ref: Any,
    valid_source_ids: set[str],
    prefix: str,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(ref, dict):
        return [f"{prefix} must be an object"]

    source_id = str(ref.get("source_id", "")).strip()
    if not source_id:
        errors.append(f"{prefix}.source_id is required")
    elif valid_source_ids and source_id not in valid_source_ids:
        errors.append(f"{prefix}.source_id does not exist: {source_id}")

    item_id = ref.get("item_id")
    if item_id is not None and not str(item_id).strip():
        errors.append(f"{prefix}.item_id must be non-empty when present")

    locator = ref.get("locator")
    if not isinstance(locator, dict):
        errors.append(f"{prefix}.locator must be a source-ref-v1 object")
    else:
        kind = locator.get("kind")
        if kind not in LOCATOR_KINDS:
            errors.append(f"{prefix}.locator.kind must be one of {sorted(LOCATOR_KINDS)}")
        if not str(locator.get("label", "")).strip():
            errors.append(f"{prefix}.locator.label is required")

        if kind in {"section", "paragraph", "heading", "slide", "figure", "table", "url_fragment"}:
            if not str(locator.get("value", "")).strip():
                errors.append(f"{prefix}.locator.value is required for {kind}")
        elif kind == "heading_path":
            path = locator.get("path")
            if not isinstance(path, list) or not path or not all(str(item).strip() for item in path):
                errors.append(f"{prefix}.locator.path must be a non-empty list for heading_path")
        elif kind == "page":
            page = locator.get("page")
            if not isinstance(page, int) or isinstance(page, bool) or page < 1:
                errors.append(f"{prefix}.locator.page must be a positive integer")
        elif kind in {"page_range", "line_range"}:
            start = locator.get("start")
            end = locator.get("end")
            minimum = 1 if kind == "page_range" else 0
            if not isinstance(start, int) or isinstance(start, bool) or start < minimum:
                errors.append(f"{prefix}.locator.start is invalid for {kind}")
            if not isinstance(end, int) or isinstance(end, bool) or not isinstance(start, int) or end < start:
                errors.append(f"{prefix}.locator.end must be greater than or equal to start")
        elif kind == "timestamp":
            start_ms = locator.get("start_ms")
            if not isinstance(start_ms, int) or isinstance(start_ms, bool) or start_ms < 0:
                errors.append(f"{prefix}.locator.start_ms must be a non-negative integer")
        elif kind == "timestamp_range":
            start_ms = locator.get("start_ms")
            end_ms = locator.get("end_ms")
            if not isinstance(start_ms, int) or isinstance(start_ms, bool) or start_ms < 0:
                errors.append(f"{prefix}.locator.start_ms must be a non-negative integer")
            if not isinstance(end_ms, int) or isinstance(end_ms, bool) or not isinstance(start_ms, int) or end_ms <= start_ms:
                errors.append(f"{prefix}.locator.end_ms must be greater than start_ms")

    supports = ref.get("supports")
    if not isinstance(supports, list) or not supports:
        errors.append(f"{prefix}.supports must be a non-empty list")
    else:
        invalid_targets = sorted({str(item) for item in supports if item not in SUPPORT_TARGETS})
        if invalid_targets:
            errors.append(f"{prefix}.supports contains invalid values: {invalid_targets}")

    strength = ref.get("support_strength")
    if strength not in SUPPORT_STRENGTH:
        errors.append(f"{prefix}.support_strength must be one of {sorted(SUPPORT_STRENGTH)}")

    excerpt = ref.get("supporting_excerpt")
    if excerpt is not None and (not isinstance(excerpt, str) or len(excerpt.strip()) > 500):
        errors.append(f"{prefix}.supporting_excerpt must be a string of at most 500 characters")

    href = ref.get("href")
    if href is not None:
        href_text = str(href).strip()
        if not href_text or not (href_text.startswith("https://") or href_text.startswith("http://") or href_text.startswith("/")):
            errors.append(f"{prefix}.href must be an HTTP(S) URL or app-relative path")

    return errors


def validate_packet(packet: dict[str, Any], valid_source_ids: set[str]) -> list[str]:
    errors: list[str] = []
    if packet.get("source_ref_schema") != "source-ref-v1":
        errors.append("source_ref_schema must be source-ref-v1")
    for field in ("report_id", "task_id", "worker_role", "claims"):
        if field not in packet:
            errors.append(f"Missing required field: {field}")
    claims = packet.get("claims")
    if not isinstance(claims, list):
        errors.append("claims must be a list")
        return errors

    seen_claim_ids: set[str] = set()
    for index, claim in enumerate(claims):
        prefix = f"claims[{index}]"
        if not isinstance(claim, dict):
            errors.append(f"{prefix} must be an object")
            continue
        claim_id = claim.get("claim_id")
        if not claim_id:
            errors.append(f"{prefix}.claim_id is required")
        elif claim_id in seen_claim_ids:
            errors.append(f"Duplicate claim_id: {claim_id}")
        else:
            seen_claim_ids.add(str(claim_id))

        if not str(claim.get("claim", "")).strip():
            errors.append(f"{prefix}.claim is required")
        claim_type = claim.get("claim_type")
        if claim_type not in CLAIM_TYPES:
            errors.append(f"{prefix}.claim_type must be one of {sorted(CLAIM_TYPES)}")
        concepts = claim.get("concept_ids")
        if not isinstance(concepts, list) or not concepts or not all(str(item).strip() for item in concepts):
            errors.append(f"{prefix}.concept_ids must be a non-empty list")
        confidence = claim.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            errors.append(f"{prefix}.confidence must be between 0 and 1")

        refs = claim.get("source_refs", [])
        requires_source = claim_type in {"source_fact", "interpretation", "disputed", "outdated"}
        if requires_source and (not isinstance(refs, list) or not refs):
            errors.append(f"{prefix}.source_refs is required for {claim_type}")
            refs = []
        if not isinstance(refs, list):
            errors.append(f"{prefix}.source_refs must be a list")
            refs = []

        for ref_index, ref in enumerate(refs):
            ref_prefix = f"{prefix}.source_refs[{ref_index}]"
            errors.extend(validate_source_ref(ref, valid_source_ids, ref_prefix))

        for list_field in ("assumptions", "limitations", "counterevidence"):
            if list_field in claim and not isinstance(claim[list_field], list):
                errors.append(f"{prefix}.{list_field} must be a list")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--source-manifest", type=Path, required=True)
    args = parser.parse_args()

    if not args.packet.is_file():
        parser.error(f"Evidence packet does not exist: {args.packet}")
    if not args.source_manifest.is_file():
        parser.error(f"Source manifest does not exist: {args.source_manifest}")

    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    source_ids = load_source_ids(args.source_manifest)
    errors = validate_packet(packet, source_ids)
    output = {"status": "pass" if not errors else "fail", "errors": errors, "source_ids": sorted(source_ids)}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
