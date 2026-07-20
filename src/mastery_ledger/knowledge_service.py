from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mastery_ledger.dashboard import _course_roots, _manifest, _read_json
from mastery_ledger.models import (
    ActivityEvent,
    EvidenceActivityResult,
    EvidenceItem,
    KnowledgeWikiResult,
    WikiConcept,
    WikiCourse,
    WikiRelationship,
    WikiSourceReference,
    WorkspaceState,
)
from mastery_ledger.source_service import load_source_manifest

MAX_MARKDOWN_CHARS = 250_000
MAX_EVENTS_PER_COURSE = 2_000
MAX_EVIDENCE_FILES = 1_000


def _records(payload: dict[str, Any] | None, *keys: str) -> list[dict[str, Any]]:
    if not payload:
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _course_identity(course_root: Path) -> tuple[str, str]:
    manifest = _manifest(course_root) or {}
    course_id = str(manifest.get("course_id") or manifest.get("study_id") or course_root.name)
    title = str(manifest.get("title") or manifest.get("name") or course_root.name.replace("-", " ").title())
    return course_id, title


def _safe_http(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _safe_page(course_root: Path, relative: object) -> tuple[str | None, str | None]:
    if not isinstance(relative, str) or not relative.strip():
        return None, None
    normalized = relative.strip().replace("\\", "/")
    path = (course_root / normalized).resolve(strict=False)
    try:
        path.relative_to(course_root.resolve(strict=False))
    except ValueError:
        return None, None
    if path.suffix.casefold() != ".md" or not path.is_file() or path.is_symlink():
        return None, None
    try:
        content = path.read_text(encoding="utf-8")[:MAX_MARKDOWN_CHARS]
    except (OSError, UnicodeError):
        return None, None
    return normalized, content


def _fallback_page(course_root: Path, concept_id: str) -> tuple[str | None, str | None]:
    safe_id = re.sub(r"[^A-Za-z0-9._-]", "-", concept_id)
    for relative in (f"wiki/pages/{safe_id}.md", f"wiki/{safe_id}.md"):
        path, content = _safe_page(course_root, relative)
        if path:
            return path, content
    return None, None


def _summary_from_markdown(content: str | None) -> str | None:
    if not content:
        return None
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", content):
        cleaned = re.sub(r"^---.*?---$", "", block, flags=re.DOTALL).strip()
        cleaned = re.sub(r"^#+\s+", "", cleaned)
        cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
        cleaned = cleaned.replace("**", "").replace("__", "").replace("`", "")
        if cleaned and not cleaned.startswith(("- ", "* ", ">")):
            paragraphs.append(" ".join(cleaned.split()))
        if paragraphs:
            break
    return paragraphs[0][:700] if paragraphs else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, (str, int)) and str(item).strip()]


def _bounded_score(value: object) -> float:
    try:
        parsed = float(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return min(1, max(0, parsed))


def _nonnegative_count(value: object) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, parsed)


def _source_references(
    raw: object, source_index: dict[str, dict[str, Any]]
) -> list[WikiSourceReference]:
    if not isinstance(raw, list):
        return []
    references: list[WikiSourceReference] = []
    for item in raw:
        if isinstance(item, (str, int)):
            item = {"source_id": str(item), "locator": {"label": "Source record"}}
        if not isinstance(item, dict) or not item.get("source_id"):
            continue
        source_id = str(item["source_id"])
        source = source_index.get(source_id, {})
        locator = item.get("locator")
        label = str(locator.get("label")) if isinstance(locator, dict) and locator.get("label") else "Source record"
        strength = str(item.get("support_strength") or "contextual")
        if strength not in {"direct", "partial", "contextual"}:
            strength = "contextual"
        references.append(
            WikiSourceReference(
                source_id=source_id,
                title=str(source.get("title") or source_id),
                locator_label=label,
                support_strength=strength,
                href=_safe_http(item.get("href")) or _safe_http(source.get("original_location")),
            )
        )
    return references


def _contradiction_records(course_root: Path) -> list[dict[str, Any]]:
    return _records(
        _read_json(course_root / "evidence" / "contradictions.json", course_root),
        "contradictions",
        "items",
    )


def knowledge_wiki(workspace: WorkspaceState) -> KnowledgeWikiResult:
    concepts: list[WikiConcept] = []
    relationships: list[WikiRelationship] = []
    courses: list[WikiCourse] = []
    warnings: list[str] = []

    for course_root in _course_roots(Path(workspace.path)):
        course_id, course_title = _course_identity(course_root)
        wiki_payload = _read_json(course_root / "wiki" / "wiki.json", course_root)
        if wiki_payload is None:
            wiki_payload = _read_json(course_root / "wiki" / "index.json", course_root)
        progress_payload = _read_json(course_root / "progress" / "learner-progress.json", course_root)
        if progress_payload is None:
            progress_payload = _read_json(course_root / "learner-progress.json", course_root)
        question_payload = _read_json(course_root / "questions" / "question-bank.json", course_root)
        if question_payload is None:
            question_payload = _read_json(course_root / "question-bank.json", course_root)

        progress_records = _records(progress_payload, "concepts")
        progress = {
            str(item["concept_id"]): item
            for item in progress_records
            if item.get("concept_id") is not None
        }
        raw_concepts = _records(wiki_payload, "concepts", "pages")
        concept_index = {
            str(item["concept_id"]): item
            for item in raw_concepts
            if item.get("concept_id") is not None
        }
        for record in _records(question_payload, "questions"):
            for concept_id in _string_list(record.get("concept_ids")):
                concept_index.setdefault(concept_id, {"concept_id": concept_id})
        for concept_id in progress:
            concept_index.setdefault(concept_id, {"concept_id": concept_id})

        try:
            source_manifest = load_source_manifest(course_root)
        except ValueError:
            source_manifest = {"sources": []}
            warnings.append(f"{course_title}: source manifest could not be read.")
        source_index = {
            str(item["source_id"]): item
            for item in _records(source_manifest, "sources")
            if item.get("source_id") is not None
        }
        contradictions = _contradiction_records(course_root)
        contradiction_counts: dict[str, int] = {}
        for item in contradictions:
            ids = _string_list(item.get("concept_ids"))
            if item.get("concept_id") is not None:
                ids.append(str(item["concept_id"]))
            for concept_id in set(ids):
                contradiction_counts[concept_id] = contradiction_counts.get(concept_id, 0) + 1

        raw_relationships = _records(wiki_payload, "relationships", "edges")
        course_relationships: list[WikiRelationship] = []
        known_ids = set(concept_index)
        for item in raw_relationships:
            from_id = str(item.get("from_concept_id") or item.get("from") or "")
            to_id = str(item.get("to_concept_id") or item.get("to") or "")
            if not from_id or not to_id or from_id not in known_ids or to_id not in known_ids:
                continue
            status = "approved" if str(item.get("status")).casefold() == "approved" else "provisional"
            course_relationships.append(
                WikiRelationship(
                    course_id=course_id,
                    course_title=course_title,
                    from_concept_id=from_id,
                    to_concept_id=to_id,
                    kind=str(item.get("kind") or item.get("relation") or "related_to"),
                    status=status,
                )
            )
        relationships.extend(course_relationships)

        related_by_id: dict[str, list[str]] = {concept_id: [] for concept_id in known_ids}
        prerequisites_by_id: dict[str, list[str]] = {concept_id: [] for concept_id in known_ids}
        for edge in course_relationships:
            related_by_id[edge.from_concept_id].append(edge.to_concept_id)
            related_by_id[edge.to_concept_id].append(edge.from_concept_id)
            if edge.kind == "prerequisite_of":
                prerequisites_by_id[edge.to_concept_id].append(edge.from_concept_id)

        for concept_id, raw in sorted(concept_index.items(), key=lambda pair: pair[0].casefold()):
            learner = progress.get(concept_id, {})
            page_path, page_markdown = _safe_page(course_root, raw.get("page_path"))
            if page_path is None:
                page_path, page_markdown = _fallback_page(course_root, concept_id)
            title = str(raw.get("title") or learner.get("title") or concept_id.replace("-", " ").replace("_", " ").title())
            summary = str(raw.get("summary") or learner.get("summary") or _summary_from_markdown(page_markdown) or "Knowledge record awaiting approved synthesis.")
            explicit_sources = raw.get("source_refs", raw.get("sources", []))
            concepts.append(
                WikiConcept(
                    course_id=course_id,
                    course_title=course_title,
                    concept_id=concept_id,
                    title=title,
                    summary=summary,
                    status=str(learner.get("status") or raw.get("status") or "unseen"),
                    proficiency_score=_bounded_score(learner.get("proficiency_score")),
                    attempt_count=_nonnegative_count(learner.get("attempt_count")),
                    next_review_at=(str(learner["next_review_at"]) if learner.get("next_review_at") else None),
                    tags=_string_list(raw.get("tags")),
                    prerequisites=sorted(set(_string_list(raw.get("prerequisites")) + prerequisites_by_id.get(concept_id, []))),
                    related=sorted(set(_string_list(raw.get("related")) + related_by_id.get(concept_id, []))),
                    sources=_source_references(explicit_sources, source_index),
                    contradiction_count=contradiction_counts.get(concept_id, 0),
                    page_markdown=page_markdown,
                    page_path=page_path,
                )
            )

        courses.append(
            WikiCourse(
                course_id=course_id,
                title=course_title,
                concept_count=len(concept_index),
                relationship_count=len(course_relationships),
                contradiction_count=len(contradictions),
            )
        )

    return KnowledgeWikiResult(
        courses=courses,
        concepts=concepts,
        relationships=relationships,
        warnings=warnings,
    )


def _evidence_source_ids(record: dict[str, Any]) -> list[str]:
    result = _string_list(record.get("source_ids"))
    for key in ("source_refs", "sources", "evidence"):
        value = record.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, dict) and item.get("source_id") is not None:
                result.append(str(item["source_id"]))
    return sorted(set(result))


def _locator_labels(record: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for key in ("source_refs", "sources", "evidence"):
        value = record.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            locator = item.get("locator") if isinstance(item, dict) else None
            if isinstance(locator, dict) and locator.get("label"):
                labels.append(str(locator["label"]))
    return labels


def _evidence_item(
    record: dict[str, Any], *, course_id: str, course_title: str, kind: str, path: str, index: int
) -> EvidenceItem:
    item_id = str(record.get("claim_id") or record.get("contradiction_id") or record.get("gap_id") or record.get("id") or f"{Path(path).stem}-{index + 1}")
    summary = str(record.get("claim") or record.get("statement") or record.get("summary") or record.get("description") or record.get("question") or "No summary recorded.")
    title = str(record.get("title") or record.get("label") or item_id.replace("-", " ").title())
    return EvidenceItem(
        item_id=item_id,
        course_id=course_id,
        course_title=course_title,
        kind=kind,  # type: ignore[arg-type]
        status=str(record.get("verification_status") or record.get("status") or record.get("decision") or ("open" if kind in {"contradiction", "gap"} else "approved")),
        title=title,
        summary=summary[:2_000],
        source_ids=_evidence_source_ids(record),
        concept_ids=_string_list(record.get("concept_ids")),
        locator_labels=_locator_labels(record),
        artifact_path=path,
    )


def _read_event_log(course_root: Path, course_id: str, course_title: str) -> tuple[list[ActivityEvent], bool]:
    path = course_root / "logs" / "events.jsonl"
    if not path.is_file() or path.is_symlink():
        return [], False
    events: list[ActivityEvent] = []
    malformed = False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-MAX_EVENTS_PER_COURSE:]
    except (OSError, UnicodeError):
        return [], True
    for index, line in enumerate(lines):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            malformed = True
            continue
        if not isinstance(item, dict):
            malformed = True
            continue
        events.append(
            ActivityEvent(
                event_id=str(item.get("event_id") or f"EVENT-{index + 1}"),
                course_id=course_id,
                course_title=course_title,
                timestamp=str(item.get("timestamp") or ""),
                action=str(item.get("action") or "unknown.action"),
                actor=str(item.get("actor") or "unknown"),
                status=str(item.get("status") or "recorded"),
                summary=str(item.get("summary") or "Observable action recorded.")[:1_000],
                artifacts=_string_list(item.get("artifacts")),
                source_id=str(item["source_id"]) if item.get("source_id") else None,
                job_id=str(item["job_id"]) if item.get("job_id") else None,
                decision=str(item["decision"]) if item.get("decision") else None,
                justification=str(item["justification"])[:1_000] if item.get("justification") else None,
            )
        )
    return events, malformed


def evidence_activity(workspace: WorkspaceState) -> EvidenceActivityResult:
    evidence: list[EvidenceItem] = []
    events: list[ActivityEvent] = []
    warnings: list[str] = []
    for course_root in _course_roots(Path(workspace.path)):
        course_id, course_title = _course_identity(course_root)
        evidence_root = course_root / "evidence"
        files = []
        if evidence_root.is_dir() and not evidence_root.is_symlink():
            files = [path for path in sorted(evidence_root.rglob("*.json")) if path.is_file() and not path.is_symlink()][:MAX_EVIDENCE_FILES]
        for path in files:
            payload = _read_json(path, course_root)
            if payload is None:
                warnings.append(f"{course_title}: could not read {path.relative_to(course_root).as_posix()}.")
                continue
            relative = path.relative_to(course_root).as_posix()
            for index, record in enumerate(_records(payload, "contradictions")):
                evidence.append(_evidence_item(record, course_id=course_id, course_title=course_title, kind="contradiction", path=relative, index=index))
            for index, record in enumerate(_records(payload, "gaps", "unresolved_questions")):
                evidence.append(_evidence_item(record, course_id=course_id, course_title=course_title, kind="gap", path=relative, index=index))
            for index, record in enumerate(_records(payload, "claims", "approved_claims")):
                status = str(record.get("verification_status") or record.get("decision") or record.get("status") or "submitted").casefold()
                if status in {"rejected", "unsupported", "excluded"}:
                    kind = "rejected_claim"
                elif status in {"approved", "accepted", "verified"}:
                    kind = "approved_claim"
                else:
                    continue
                evidence.append(_evidence_item(record, course_id=course_id, course_title=course_title, kind=kind, path=relative, index=index))
        course_events, malformed = _read_event_log(course_root, course_id, course_title)
        events.extend(course_events)
        if malformed:
            warnings.append(f"{course_title}: one or more activity lines were unreadable and skipped.")

    deduplicated: dict[tuple[str, str, str], EvidenceItem] = {}
    for item in evidence:
        key = (item.course_id, item.kind, item.item_id)
        existing = deduplicated.get(key)
        score = len(item.source_ids) * 4 + len(item.locator_labels) * 3 + len(item.summary)
        existing_score = (
            len(existing.source_ids) * 4 + len(existing.locator_labels) * 3 + len(existing.summary)
            if existing
            else -1
        )
        if score > existing_score:
            deduplicated[key] = item
    evidence = list(deduplicated.values())
    events.sort(key=lambda item: item.timestamp, reverse=True)
    return EvidenceActivityResult(
        evidence=evidence,
        events=events,
        approved_count=sum(item.kind == "approved_claim" for item in evidence),
        contradiction_count=sum(item.kind == "contradiction" for item in evidence),
        gap_count=sum(item.kind == "gap" for item in evidence),
        rejected_count=sum(item.kind == "rejected_claim" for item in evidence),
        warnings=warnings,
    )
