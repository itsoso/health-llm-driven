"""Bridge compiled down-dedao LLM Wiki artifacts into System KB V2 seed files.

This module only imports transformed wiki artifacts. It deliberately avoids
serving long source/course text and skips personal notes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any


ARTIFACT_FILES = ("pages.jsonl", "entities.jsonl", "claims.jsonl", "relations.jsonl")
PRIVATE_MARKERS = ("personal", "private", "私人", "个人")


@dataclass
class DownDedaoBridgeResult:
    source_root: Path
    base_artifact_dir: Path
    pages: list[dict[str, Any]] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    skipped_private: list[str] = field(default_factory=list)
    diff: dict[str, int] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)


def compile_down_dedao_wiki_artifacts(
    source_root: str | Path,
    base_artifact_dir: str | Path,
    now: datetime | None = None,
) -> DownDedaoBridgeResult:
    """Compile reviewed down-dedao LLM Wiki artifacts into System KB seed rows."""
    source_root = Path(source_root).expanduser()
    base_artifact_dir = Path(base_artifact_dir)
    now = now or datetime.now(UTC)
    artifact_root = source_root / "artifacts"

    existing_docs = _load_existing_doc_ids(base_artifact_dir)
    existing_relations = _load_existing_relation_keys(base_artifact_dir)

    result = DownDedaoBridgeResult(source_root=source_root, base_artifact_dir=base_artifact_dir)

    gene_knowledge_path = artifact_root / "gene_knowledge.json"
    if gene_knowledge_path.exists():
        gene_knowledge = _read_json(gene_knowledge_path)
        for entity in _iter_gene_entities(gene_knowledge.get("entities") or {}):
            doc = _entity_to_document(entity, gene_knowledge, now)
            if doc["doc_id"] not in existing_docs:
                result.entities.append(doc)
                existing_docs.add(doc["doc_id"])

        for claim in gene_knowledge.get("claims") or []:
            doc = _claim_to_document(claim, gene_knowledge, now)
            if doc["doc_id"] not in existing_docs:
                result.claims.append(doc)
                existing_docs.add(doc["doc_id"])
            _add_claim_relations(doc, claim, result.relations, existing_relations)

    for page_path in sorted(artifact_root.glob("*.json")):
        if page_path.name in {"manifest.json", "gene_knowledge.json", "gene_drug_rules.json"}:
            continue
        if _is_private_artifact(page_path):
            result.skipped_private.append(page_path.name)
            continue
        page_payload = _read_json(page_path)
        page_doc = _page_to_document(page_payload, now)
        if page_doc["doc_id"] not in existing_docs:
            result.pages.append(page_doc)
            existing_docs.add(page_doc["doc_id"])

    _ensure_relation_endpoint_entities(result, existing_docs, base_artifact_dir, now)

    result.diff = {
        "pages_added": len(result.pages),
        "entities_added": len(result.entities),
        "claims_added": len(result.claims),
        "relations_added": len(result.relations),
        "private_skipped": len(result.skipped_private),
    }
    result.manifest = {
        "compiled_at": now.isoformat(),
        "source_root": str(source_root),
        "pipeline": "down_dedao_llm_wiki_bridge_v1",
        "diff": result.diff,
        "skipped_private": result.skipped_private,
    }
    return result


def write_down_dedao_wiki_artifacts(
    result: DownDedaoBridgeResult,
    output_dir: str | Path,
) -> dict[str, int]:
    """Merge bridge output into JSONL seed files idempotently."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    counts = {
        "pages": _merge_jsonl(output_dir / "pages.jsonl", result.pages, key_fields=("doc_id",)),
        "entities": _merge_jsonl(output_dir / "entities.jsonl", result.entities, key_fields=("doc_id",)),
        "claims": _merge_jsonl(output_dir / "claims.jsonl", result.claims, key_fields=("doc_id",)),
        "relations": _merge_jsonl(
            output_dir / "relations.jsonl",
            result.relations,
            key_fields=("src_doc_id", "dst_doc_id", "relation"),
        ),
    }
    manifest = _read_json(output_dir / "manifest.json") if (output_dir / "manifest.json").exists() else {}
    manifest.setdefault("counts", {})
    manifest["counts"].update(counts)
    manifest["down_dedao_wiki"] = result.manifest
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return counts


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_existing_doc_ids(root: Path) -> set[str]:
    doc_ids: set[str] = set()
    for name in ("pages.jsonl", "entities.jsonl", "claims.jsonl"):
        for row in _read_jsonl(root / name):
            if row.get("doc_id"):
                doc_ids.add(row["doc_id"])
    return doc_ids


def _load_existing_relation_keys(root: Path) -> set[tuple[str, str, str]]:
    return {
        (row.get("src_doc_id"), row.get("dst_doc_id"), row.get("relation"))
        for row in _read_jsonl(root / "relations.jsonl")
        if row.get("src_doc_id") and row.get("dst_doc_id") and row.get("relation")
    }


def _merge_jsonl(path: Path, rows: list[dict[str, Any]], key_fields: tuple[str, ...]) -> int:
    existing_rows = _read_jsonl(path)
    if not rows:
        return len(existing_rows)

    merged: dict[tuple[Any, ...], dict[str, Any]] = {}
    ordered: list[dict[str, Any]] = []
    for row in existing_rows:
        key = tuple(row.get(field) for field in key_fields)
        merged[key] = row
        ordered.append(row)
    for row in rows:
        key = tuple(row.get(field) for field in key_fields)
        if key in merged:
            for index, existing_row in enumerate(ordered):
                if existing_row is merged[key]:
                    ordered[index] = row
                    break
        else:
            ordered.append(row)
        merged[key] = row
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in ordered),
        encoding="utf-8",
    )
    return len(ordered)


def _ensure_relation_endpoint_entities(
    result: DownDedaoBridgeResult,
    known_doc_ids: set[str],
    artifact_dir: Path,
    now: datetime,
) -> None:
    """Create placeholder entity docs for graph endpoints referenced by relations.

    PostgreSQL enforces FK integrity for kb_edges. Some reviewed wiki claims link
    to actionable entities (for example entity:intervention:caffeine-cutoff)
    before a full entity page exists, so the bridge materializes a minimal,
    reviewed placeholder instead of dropping the relationship.
    """
    relation_rows = _read_jsonl(artifact_dir / "relations.jsonl") + result.relations
    for row in relation_rows:
        for field in ("src_doc_id", "dst_doc_id"):
            doc_id = str(row.get(field) or "")
            if not doc_id.startswith("entity:") or doc_id in known_doc_ids:
                continue
            placeholder = _placeholder_entity_document(doc_id, now)
            if placeholder:
                result.entities.append(placeholder)
                known_doc_ids.add(doc_id)


def _placeholder_entity_document(doc_id: str, now: datetime) -> dict[str, Any] | None:
    parts = doc_id.split(":", 2)
    if len(parts) != 3:
        return None
    _, entity_type, entity_id = parts
    title = entity_id.replace("-", " ")
    summary = (
        f"{title} 是 down-dedao LLM Wiki 关系引用的占位实体，"
        "用于保持系统知识图谱完整；后续需要补充独立证据页。"
    )
    return {
        "doc_id": doc_id,
        "doc_type": "entity",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "title": title,
        "summary": summary,
        "body": summary,
        "confidence": 0.55,
        "evidence_level": "C",
        "sources": ["down-dedao:llm-wiki"],
        "last_confirmed": now.isoformat(),
        "decay_rate": "normal",
        "metadata": {
            "origin": "down-dedao-llm-wiki",
            "placeholder": True,
            "license_scope": "internal_transformed_claims",
            "review_status": "reviewed",
        },
    }


def _iter_gene_entities(groups: dict[str, Any]) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for entity_type, group in groups.items():
        items = group.values() if isinstance(group, dict) else group
        for item in items or []:
            if not isinstance(item, dict):
                continue
            item = {**item, "entity_type": item.get("entity_type") or entity_type}
            entities.append(item)
    return entities


def _entity_to_document(entity: dict[str, Any], source: dict[str, Any], now: datetime) -> dict[str, Any]:
    entity_type = str(entity["entity_type"])
    entity_id = str(entity["entity_id"])
    body = entity.get("body") or entity.get("summary") or entity.get("title") or entity_id
    return {
        "doc_id": f"entity:{entity_type}:{entity_id}",
        "doc_type": "entity",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "title": entity.get("title") or entity_id,
        "summary": _summary_from_body(body),
        "body": _compact_body(body),
        "confidence": _float_or_default(entity.get("confidence"), 0.72),
        "evidence_level": entity.get("evidence_level") or "C",
        "sources": entity.get("sources") or ["down-dedao:llm-wiki"],
        "last_confirmed": _date_to_datetime(entity.get("last_confirmed"), now),
        "decay_rate": entity.get("decay_rate") or "normal",
        "metadata": {
            "origin": "down-dedao-llm-wiki",
            "source_version": source.get("version"),
            "aliases": entity.get("aliases") or [],
            "linked_gene": entity.get("gene"),
            "license_scope": "internal_transformed_claims",
            "review_status": "reviewed",
        },
    }


def _claim_to_document(claim: dict[str, Any], source: dict[str, Any], now: datetime) -> dict[str, Any]:
    claim_id = claim.get("claim_id") or claim.get("doc_id", "").replace("claim:", "")
    body = claim.get("body") or claim.get("summary") or claim.get("title") or claim_id
    return {
        "doc_id": f"claim:{claim_id}",
        "doc_type": "claim",
        "entity_type": claim.get("entity_type"),
        "entity_id": claim.get("entity_id"),
        "title": claim.get("title") or claim_id,
        "summary": claim.get("summary") or _summary_from_body(body),
        "body": _compact_body(body, limit=1600),
        "confidence": _float_or_default(claim.get("confidence"), 0.68),
        "evidence_level": claim.get("evidence_level") or "C",
        "applies_when": claim.get("applies_when") or [],
        "recommends_lookup": claim.get("recommends_lookup") or [],
        "sources": claim.get("sources") or ["down-dedao:llm-wiki"],
        "last_confirmed": _date_to_datetime(claim.get("last_confirmed"), now),
        "decay_rate": claim.get("decay_rate") or "normal",
        "supersedes": claim.get("supersedes") or [],
        "metadata": {
            "origin": "down-dedao-llm-wiki",
            "source_version": source.get("version"),
            "predicate": claim.get("predicate"),
            "drug_rules": claim.get("drug_rules") or {},
            "claim_boundary": "Health management guidance only; not diagnosis, prescription, or treatment.",
            "license_scope": "internal_transformed_claims",
            "review_status": claim.get("review_status") or "reviewed",
            "safety_tags": _claim_safety_tags(claim),
        },
    }


def _page_to_document(payload: dict[str, Any], now: datetime) -> dict[str, Any]:
    page_id = str(payload["id"])
    summary = payload.get("summary") or payload.get("title") or page_id
    confidence = _float_or_default(payload.get("confidence_score"), 0.7)
    return {
        "doc_id": f"page:ak-kbase:{page_id}",
        "doc_type": "article",
        "entity_type": "concept" if page_id.startswith("concepts_") else "article",
        "entity_id": page_id,
        "title": payload.get("title") or page_id,
        "summary": summary,
        "body": summary,
        "confidence": confidence,
        "evidence_level": "B" if confidence >= 0.8 else "C",
        "sources": payload.get("sources_referenced") or [payload.get("source") or "ak-kbase"],
        "last_confirmed": now.isoformat(),
        "decay_rate": "normal",
        "metadata": {
            "origin": "down-dedao-llm-wiki",
            "source_file": payload.get("source_file"),
            "source_version": payload.get("version"),
            "layer": payload.get("layer"),
            "conditions": payload.get("conditions") or [],
            "tags": payload.get("tags") or [],
            "category": payload.get("category"),
            "license_scope": "internal_transformed_claims",
            "review_status": "reviewed",
        },
    }


def _add_claim_relations(
    doc: dict[str, Any],
    raw_claim: dict[str, Any],
    relations: list[dict[str, Any]],
    existing: set[tuple[str, str, str]],
) -> None:
    source_entity = f"entity:{doc['entity_type']}:{doc['entity_id']}"
    _add_relation(relations, existing, source_entity, doc["doc_id"], "has_claim", doc["confidence"], doc["doc_id"])
    for target in doc.get("recommends_lookup") or []:
        if isinstance(target, str) and target.startswith("entity:"):
            _add_relation(relations, existing, doc["doc_id"], target, "recommends", doc["confidence"], doc["doc_id"])
    for target in _drug_rule_entity_targets(raw_claim.get("drug_rules") or {}):
        _add_relation(relations, existing, doc["doc_id"], target, "mentions", doc["confidence"], doc["doc_id"])


def _add_relation(
    relations: list[dict[str, Any]],
    existing: set[tuple[str, str, str]],
    src: str,
    dst: str,
    relation: str,
    confidence: float | None,
    source_claim_id: str,
) -> None:
    key = (src, dst, relation)
    if key in existing:
        return
    existing.add(key)
    relations.append(
        {
            "src_doc_id": src,
            "dst_doc_id": dst,
            "relation": relation,
            "confidence": confidence,
            "source_claim_id": source_claim_id,
            "metadata": {"origin": "down-dedao-llm-wiki"},
        }
    )


def _drug_rule_entity_targets(drug_rules: dict[str, Any]) -> set[str]:
    targets: set[str] = set()
    for key in ("avoid", "monitor", "substitute", "supplement"):
        for item in drug_rules.get(key) or []:
            if not isinstance(item, dict):
                continue
            for field in ("drug", "from", "to", "item"):
                value = item.get(field)
                if value:
                    entity_type = "supplement" if key == "supplement" or field == "item" else "drug"
                    targets.add(f"entity:{entity_type}:{_normalize_entity_id(str(value))}")
    return targets


def _normalize_entity_id(value: str) -> str:
    return value.strip().replace(" ", "-")


def _claim_safety_tags(claim: dict[str, Any]) -> list[str]:
    tags = ["system_kb"]
    if claim.get("drug_rules"):
        tags.append("gene_drug_boundary")
    if claim.get("predicate") in {"contraindicates", "requires_monitoring", "requires_boundary"}:
        tags.append(str(claim["predicate"]))
    return tags


def _summary_from_body(body: str) -> str:
    lines = [line.strip("#- \n\t") for line in str(body).splitlines() if line.strip()]
    lines = [line for line in lines if line and not line.startswith("[[")]
    return (lines[0] if lines else str(body))[:240]


def _compact_body(body: str, limit: int = 1200) -> str:
    text = str(body).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _date_to_datetime(value: Any, fallback: datetime) -> str:
    if not value:
        return fallback.isoformat()
    raw = str(value)
    if "T" in raw:
        return raw
    return f"{raw}T00:00:00+00:00"


def _is_private_artifact(path: Path) -> bool:
    value = path.name.lower()
    return any(marker in value for marker in PRIVATE_MARKERS)
