"""Reasoning Explainer — 把 safety alert / specialist finding 的'为什么'拼出来.

只读 DB, 不调 LLM. API 层直接 JSON 返回.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.agent_audit_log import AgentAuditLog
from app.services.hybrid_search import hybrid_retrieve  # 供 monkeypatch 用

logger = logging.getLogger(__name__)

# safety rule category → HealthTwin partition attribute name
_CATEGORY_TO_PARTITION = {
    "vitals": "physiological",
    "labs": "labs",
    "ddi": "medication",
    "dsi": "supplement",
    "pgx": "genetic",
    "training_load": "behavioral",
    "cgm": "cgm",
}


def _load_audit(db: Session, audit_id: int, expected_agent: str, user_id: int) -> AgentAuditLog:
    row = db.query(AgentAuditLog).filter(AgentAuditLog.id == audit_id).first()
    if row is None or row.agent_type != expected_agent:
        raise HTTPException(status_code=404, detail="audit 记录不存在或已过期")
    if row.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权访问该 audit 记录")
    return row


def _twin_evidence_for_category(db: Session, user_id: int, category: str) -> List[Dict[str, Any]]:
    """从 Twin 当前快照抽 category 对应分区的几条关键字段."""
    try:
        from app.twin.builder import build_twin
        twin = build_twin(db, user_id, use_cache=True)
        partition_name = _CATEGORY_TO_PARTITION.get(category, "physiological")
        partition = getattr(twin, partition_name, None)
        if partition is None:
            return []
        raw = partition.model_dump(exclude_none=True) if hasattr(partition, "model_dump") else {}
        out = []
        for k, v in list(raw.items())[:4]:
            if isinstance(v, (int, float, str, bool)):
                out.append({
                    "partition": partition_name,
                    "field": k, "value": v,
                    "source": ",".join(twin.meta.data_sources or []) or "unknown",
                    "freshness_hours": None,
                })
        return out
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[explainer] twin evidence 失败: {e}")
        return []


def _related_facts(db: Session, user_id: int, query: str, k: int = 3) -> List[Dict[str, Any]]:
    try:
        # Reference through the module-level name so tests can monkeypatch it.
        hits = hybrid_retrieve(db, user_id, query, top_k=k)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[explainer] hybrid_retrieve 失败, related_facts=[]: {e}")
        return []
    out = []
    for h in hits:
        if h.source_type != "fact":
            continue
        out.append({
            "id": h.source_id,
            "tier": h.metadata.get("tier", "unknown"),
            "predicate": h.metadata.get("predicate", ""),
            "preview": h.text_preview,
            "confidence": h.metadata.get("confidence"),
        })
    return out


def _confidence_note(twin_evidence: List[Dict], related: List[Dict]) -> str:
    tc = len(twin_evidence)
    rc = len(related)
    if tc == 0 and rc == 0:
        return "数据不足"
    return f"基于 {tc} 条 Twin 字段 + {rc} 条记忆事实"


def explain_safety_alert(
    db: Session, audit_id: int, rule_id: str, user_id: int,
) -> Dict[str, Any]:
    audit = _load_audit(db, audit_id, expected_agent="safety_guardian", user_id=user_id)
    alerts = (audit.result_detail or {}).get("alerts") or []
    alert = next((a for a in alerts if a.get("rule_id") == rule_id), None)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"未找到 rule_id={rule_id} 的 alert")

    category = alert.get("category") or "vitals"
    twin_evidence = _twin_evidence_for_category(db, user_id, category)
    query_text = f"{rule_id} {category} {alert.get('title', '')}"
    related = _related_facts(db, user_id, query_text)

    return {
        "source": "safety",
        "summary": alert.get("title") or rule_id,
        "rule": {
            "name": rule_id,
            "category": category,
            "severity": alert.get("severity"),
            "threshold": alert.get("message"),
        },
        "twin_evidence": twin_evidence,
        "related_facts": related,
        "confidence_note": _confidence_note(twin_evidence, related),
        "generated_at": alert.get("generated_at"),
    }


def explain_specialist_finding(
    db: Session, audit_id: int, specialist: str, user_id: int,
) -> Dict[str, Any]:
    audit = _load_audit(db, audit_id, expected_agent="specialist_batch", user_id=user_id)
    findings = (audit.result_detail or {}).get("findings") or []
    finding = next((f for f in findings if f.get("specialist") == specialist), None)
    if finding is None:
        raise HTTPException(status_code=404, detail=f"未找到 specialist={specialist} 的 finding")

    twin_evidence = _twin_evidence_for_category(db, user_id, category="vitals")
    related = _related_facts(db, user_id, f"{specialist} {finding.get('kind', '')}")

    return {
        "source": "specialist",
        "specialist": specialist,
        "summary": finding.get("summary") or "",
        "kind": finding.get("kind"),
        "data": finding.get("data") or {},
        "twin_evidence": twin_evidence,
        "related_facts": related,
        "confidence_note": _confidence_note(twin_evidence, related),
        "proposed_cards_count": len(finding.get("proposed_cards") or []),
    }
