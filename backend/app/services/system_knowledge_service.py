"""DB-backed system knowledge lookup for LLM Wiki v2 Phase 0."""

from __future__ import annotations

import ast
import operator
import re
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.system_knowledge import KBDocument, KBEdge


CLAIM_BOUNDARY = "仅用于健康管理和风险沟通，不替代医生诊断、治疗或用药决策。"

_IN_RE = re.compile(r"^(?P<path>twin\.[A-Za-z0-9_.-]+)\s+in\s+(?P<values>\[.*\])$")
_EQ_RE = re.compile(r"^(?P<path>twin\.[A-Za-z0-9_.-]+)\s*(==|=)\s*(?P<value>.+)$")
_COMPARE_RE = re.compile(
    r"^(?P<path>twin\.[A-Za-z0-9_.-]+)\s*(?P<op>>=|<=|>|<)\s*(?P<value>-?\d+(?:\.\d+)?)$"
)
_NULL_RE = re.compile(r"^(?P<path>twin\.[A-Za-z0-9_.-]+)\s+is\s+(?P<negation>not\s+)?null$")
_GENE_MESSAGE_PATTERNS = {
    "MTHFR": re.compile(r"\bMTHFR\b(?:[-\s_]*(?P<mthfr>CC|CT|TT))?", re.IGNORECASE),
    "APOE": re.compile(r"\bAPOE\b(?:[-\s_]*(?P<apoe>E[234]/E[234]|E[234]E[234]))?", re.IGNORECASE),
    "FTO": re.compile(r"\bFTO\b", re.IGNORECASE),
    "ACTN3": re.compile(r"\bACTN3\b", re.IGNORECASE),
    "ALDH2": re.compile(r"\bALDH2\b(?:[-\s_]*(?P<aldh2>GA|AA|GG|\*1/\*2|\*2/\*2))?", re.IGNORECASE),
}


def serialize_document(document: KBDocument, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "doc_id": document.doc_id,
        "doc_type": document.doc_type,
        "entity_type": document.entity_type,
        "entity_id": document.entity_id,
        "title": document.title,
        "summary": document.summary,
        "body": document.body,
        "confidence": document.confidence,
        "evidence_level": document.evidence_level,
        "applies_when": document.applies_when or [],
        "recommends_lookup": document.recommends_lookup or [],
        "sources": document.sources or [],
        "last_confirmed": document.last_confirmed.isoformat() if document.last_confirmed else None,
        "decay_rate": document.decay_rate,
        "is_archived": document.is_archived,
        "metadata": document.metadata_json or {},
    }
    if extra:
        payload.update(extra)
    return payload


def get_entity_bundle(db: Session, entity_type: str, entity_id: str) -> dict[str, Any] | None:
    entity = (
        db.query(KBDocument)
        .filter(
            KBDocument.doc_type == "entity",
            KBDocument.entity_type == entity_type,
            KBDocument.entity_id == entity_id,
            KBDocument.is_archived.is_(False),
        )
        .first()
    )
    if entity is None:
        return None

    edges = (
        db.query(KBEdge)
        .filter(or_(KBEdge.src_doc_id == entity.doc_id, KBEdge.dst_doc_id == entity.doc_id))
        .all()
    )
    related_ids = {
        edge.dst_doc_id if edge.src_doc_id == entity.doc_id else edge.src_doc_id
        for edge in edges
    }
    linked_claims = []
    if related_ids:
        linked_claims = (
            db.query(KBDocument)
            .filter(
                KBDocument.doc_id.in_(related_ids),
                KBDocument.doc_type == "claim",
                KBDocument.is_archived.is_(False),
            )
            .order_by(KBDocument.confidence.desc().nullslast(), KBDocument.doc_id.asc())
            .all()
        )

    return {
        "entity": serialize_document(entity),
        "linked_claims": [serialize_document(claim) for claim in linked_claims],
        "edges": [
            {
                "edge_id": edge.edge_id,
                "src_doc_id": edge.src_doc_id,
                "dst_doc_id": edge.dst_doc_id,
                "relation": edge.relation,
                "confidence": edge.confidence,
                "source_claim_id": edge.source_claim_id,
            }
            for edge in edges
        ],
        "claim_boundary": CLAIM_BOUNDARY,
    }


def lookup_for_twin(db: Session, twin: dict[str, Any]) -> dict[str, Any]:
    entity_keys = _extract_entity_keys(twin)
    entities = []
    if entity_keys:
        entity_filters = [
            (KBDocument.entity_type == entity_type) & (KBDocument.entity_id == entity_id)
            for entity_type, entity_id in sorted(entity_keys)
        ]
        entities = (
            db.query(KBDocument)
            .filter(
                KBDocument.doc_type == "entity",
                KBDocument.is_archived.is_(False),
                or_(*entity_filters),
            )
            .order_by(KBDocument.entity_type.asc(), KBDocument.entity_id.asc())
            .all()
        )

    matched_claims = []
    claims = (
        db.query(KBDocument)
        .filter(KBDocument.doc_type == "claim", KBDocument.is_archived.is_(False))
        .order_by(KBDocument.confidence.desc().nullslast(), KBDocument.doc_id.asc())
        .all()
    )
    for claim in claims:
        conditions = claim.applies_when or []
        matched_conditions = [condition for condition in conditions if evaluate_condition(condition, twin)]
        if matched_conditions:
            matched_claims.append(serialize_document(claim, {"matched_conditions": matched_conditions}))

    return {
        "entities": [serialize_document(entity) for entity in entities],
        "claims": matched_claims,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def format_system_knowledge_for_prompt(
    db: Session,
    twin: dict[str, Any],
    max_claims: int = 6,
    max_chars: int = 1500,
) -> str:
    """Render a bounded system-KB block for Agent prompts."""

    result = lookup_for_twin(db, twin)
    claims = result["claims"][:max_claims]
    if not claims:
        return ""

    lines = ["## 系统知识库相关条目"]
    for claim in claims:
        sources = ", ".join(claim.get("sources") or [])
        confidence = claim.get("confidence")
        confidence_text = f"{confidence:.2f}" if isinstance(confidence, float) else "n/a"
        line = (
            f"- {claim.get('title') or claim.get('doc_id')} "
            f"[{claim.get('evidence_level') or '?'} conf={confidence_text}] "
            f"({claim.get('doc_id')})"
        )
        summary = claim.get("summary")
        if summary:
            line += f": {summary}"
        if sources:
            line += f" 来源: {sources}"
        lines.append(line)
    lines.append(f"边界: {CLAIM_BOUNDARY}")

    rendered = "\n".join(lines)
    if len(rendered) <= max_chars:
        return rendered
    return rendered[: max_chars - 3].rstrip() + "..."


def build_evidence_card_for_message(db: Session, message: str) -> dict[str, Any] | None:
    """Build a mobile evidence card for explicit gene questions.

    This is intentionally conservative for Phase 0: it only extracts clear gene
    mentions and a few common genotype spellings, then reuses structured
    `lookup_for_twin` instead of free-form embedding matches.
    """

    twin = _twin_from_message(message)
    if not twin.get("genetics"):
        return None

    result = lookup_for_twin(db, twin)
    if not result["entities"] or not result["claims"]:
        return None

    return {
        "type": "system_knowledge_evidence",
        "data": {
            "entity": result["entities"][0],
            "claims": result["claims"][:3],
            "claim_boundary": result["claim_boundary"],
        },
    }


def evaluate_condition(condition: str, twin: dict[str, Any]) -> bool:
    expression = condition.strip()
    null_match = _NULL_RE.match(expression)
    if null_match:
        value = _value_at_path(twin, null_match.group("path"))
        is_null = value is None
        return not is_null if null_match.group("negation") else is_null

    in_match = _IN_RE.match(expression)
    if in_match:
        value = _value_at_path(twin, in_match.group("path"))
        try:
            candidates = ast.literal_eval(in_match.group("values"))
        except (SyntaxError, ValueError):
            return False
        return value in candidates

    eq_match = _EQ_RE.match(expression)
    if eq_match:
        value = _value_at_path(twin, eq_match.group("path"))
        expected = _parse_literal(eq_match.group("value"))
        return value == expected

    compare_match = _COMPARE_RE.match(expression)
    if compare_match:
        value = _value_at_path(twin, compare_match.group("path"))
        if value is None:
            return False
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return False
        expected = float(compare_match.group("value"))
        op = {
            ">=": operator.ge,
            "<=": operator.le,
            ">": operator.gt,
            "<": operator.lt,
        }[compare_match.group("op")]
        return op(numeric_value, expected)

    return False


def _parse_literal(raw: str) -> Any:
    normalized = raw.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    if normalized in {"null", "none"}:
        return None
    try:
        return ast.literal_eval(raw.strip())
    except (SyntaxError, ValueError):
        return raw.strip().strip("\"'")


def _value_at_path(twin: dict[str, Any], path: str) -> Any:
    parts = path.split(".")
    if parts and parts[0] == "twin":
        parts = parts[1:]
    current: Any = twin
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current


def _extract_entity_keys(twin: dict[str, Any]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    genetics = twin.get("genetics") if isinstance(twin.get("genetics"), dict) else {}
    gene_prefixes = {
        "MTHFR_C677T": "MTHFR",
        "MTHFR": "MTHFR",
        "APOE": "APOE",
        "FTO": "FTO",
        "ACTN3": "ACTN3",
        "ALDH2": "ALDH2",
    }
    for field, entity_id in gene_prefixes.items():
        if genetics.get(field) is not None:
            keys.add(("gene", entity_id))

    labs = twin.get("labs") if isinstance(twin.get("labs"), dict) else {}
    if labs.get("homocysteine_umol_l") is not None or labs.get("Hcy") is not None:
        keys.add(("biomarker", "Hcy"))
    if labs.get("ldl_c_mmol_l") is not None or labs.get("LDL-C") is not None:
        keys.add(("biomarker", "LDL-C"))
    if labs.get("hba1c_percent") is not None or labs.get("HbA1c") is not None:
        keys.add(("biomarker", "HbA1c"))
    if labs.get("triglycerides_mmol_l") is not None or labs.get("TG") is not None:
        keys.add(("biomarker", "TG"))
    if labs.get("systolic_bp") is not None or labs.get("diastolic_bp") is not None:
        keys.add(("biomarker", "BP"))
    if labs.get("uric_acid_umol_l") is not None or labs.get("UA") is not None:
        keys.add(("biomarker", "uric-acid"))

    goals = twin.get("goals") if isinstance(twin.get("goals"), dict) else {}
    if _value_at_path({"goals": goals}, "twin.goals.weight_loss.active") is True:
        keys.add(("condition", "metabolic-health"))
        keys.add(("intervention", "weight-waist-tracking"))
    if _value_at_path({"goals": goals}, "twin.goals.metabolic_health.active") is True:
        keys.add(("condition", "metabolic-health"))
    if _value_at_path({"goals": goals}, "twin.goals.sleep.active") is True:
        keys.add(("condition", "sleep-recovery"))

    return keys


def _twin_from_message(message: str) -> dict[str, Any]:
    genetics: dict[str, Any] = {}
    for gene, pattern in _GENE_MESSAGE_PATTERNS.items():
        match = pattern.search(message or "")
        if not match:
            continue
        if gene == "MTHFR":
            genetics["MTHFR_C677T"] = (match.group("mthfr") or "TT").upper()
        elif gene == "APOE":
            genotype = match.group("apoe")
            if genotype:
                genotype = genotype.upper().replace("E", "E", 1)
                if "/" not in genotype and len(genotype) == 4:
                    genotype = f"{genotype[:2]}/{genotype[2:]}"
                genetics["APOE"] = genotype
            else:
                genetics["APOE"] = "E3/E4"
        elif gene == "ALDH2":
            genetics["ALDH2"] = (match.group("aldh2") or "GA").upper()
        else:
            genetics[gene] = "present"
    return {"genetics": genetics, "labs": {}}
