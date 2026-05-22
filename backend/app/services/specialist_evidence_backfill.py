"""Controlled historical backfill for specialist system-KB evidence metadata."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from app.models.agent_audit_log import AgentAuditLog
from app.models.system_knowledge import KBDocument


_CLAIM_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "claim:c_training_readiness_high_load_boundary",
        ("readiness", "就绪", "状态极佳", "恢复不足"),
        (),
    ),
    (
        "claim:c_acwr_training_load_boundary",
        ("acwr", "急性/慢性", "急性慢性", "训练 负荷", "过载风险", "脱训阶段"),
        (),
    ),
    (
        "claim:c_hydration_progress_boundary",
        ("饮水", "补水", "水 ", "water", "hydration"),
        (),
    ),
    (
        "claim:c_protein_target_training_boundary",
        ("蛋白", "protein"),
        (),
    ),
    (
        "claim:c_allergic_rhinitis_symptom_tracking_boundary",
        ("鼻炎", "喷嚏", "洗鼻", "rhinitis"),
        (),
    ),
)

_DATA_GAP_TOKENS = (
    "data_gap=true",
    "知识库暂无相关内容",
    "需补充",
    "暂无",
    "未识别",
    "数据不足",
)
_DATA_SUMMARY_TOKENS = (
    "紧急告警",
    "一般提示",
    "空腹血糖",
    "ldl",
    "hdl",
    "tg ",
    "6 个月趋势",
    "hrv",
    "静息心率",
    "睡眠评分",
    "体重",
)


def backfill_specialist_evidence_refs(
    db: Session,
    *,
    dry_run: bool = True,
    limit: int | None = None,
) -> dict[str, int | bool]:
    """Backfill historical specialist audit findings with deterministic metadata.

    The function only handles explicit text/data matches and validates claim IDs
    exist before attaching them. Existing evidence refs are left untouched.
    """

    claim_ids = _existing_claim_ids(db)
    query = (
        db.query(AgentAuditLog)
        .filter(AgentAuditLog.agent_type == "specialist_batch", AgentAuditLog.action == "run")
        .order_by(AgentAuditLog.id.asc())
    )
    if limit is not None:
        query = query.limit(limit)

    result: dict[str, int | bool] = {
        "dry_run": dry_run,
        "audit_logs_scanned": 0,
        "audit_logs_updated": 0,
        "findings_scanned": 0,
        "findings_with_refs": 0,
        "findings_not_applicable": 0,
    }

    for row in query.all():
        result["audit_logs_scanned"] = int(result["audit_logs_scanned"]) + 1
        detail = row.result_detail if isinstance(row.result_detail, dict) else {}
        findings = detail.get("findings")
        if not isinstance(findings, list):
            continue

        next_detail = deepcopy(detail)
        next_findings = next_detail.get("findings")
        row_changed = False
        for finding in next_findings:
            if not isinstance(finding, dict):
                continue
            result["findings_scanned"] = int(result["findings_scanned"]) + 1
            patch = _infer_patch_for_finding(finding, claim_ids)
            if patch is None:
                continue
            _apply_patch_to_finding(finding, patch)
            row_changed = True
            if patch["evidence_refs"]:
                result["findings_with_refs"] = int(result["findings_with_refs"]) + 1
            else:
                result["findings_not_applicable"] = int(result["findings_not_applicable"]) + 1

        if row_changed:
            result["audit_logs_updated"] = int(result["audit_logs_updated"]) + 1
            if not dry_run:
                row.result_detail = next_detail

    if dry_run:
        db.rollback()
    else:
        db.commit()
    return result


def _existing_claim_ids(db: Session) -> set[str]:
    return {
        str(doc_id)
        for (doc_id,) in db.query(KBDocument.doc_id)
        .filter(KBDocument.doc_type == "claim")
        .all()
    }


def _infer_patch_for_finding(
    finding: dict[str, Any],
    existing_claim_ids: set[str],
) -> dict[str, Any] | None:
    if _finding_refs(finding):
        return None

    text = _finding_text(finding)
    lowered = text.lower()
    if any(token in lowered for token in _DATA_GAP_TOKENS):
        return _status_patch("data_gap")

    refs: list[str] = []
    for claim_id, positive_tokens, negative_tokens in _CLAIM_RULES:
        if claim_id not in existing_claim_ids:
            continue
        if negative_tokens and any(token in lowered for token in negative_tokens):
            continue
        if any(token in lowered for token in positive_tokens):
            refs.append(claim_id)

    if refs:
        return {
            "evidence_refs": _dedupe_preserve_order(refs),
            "support_status": "supported",
            "unsupported": False,
            "unsupported_reason": None,
        }

    if any(token in lowered for token in _DATA_SUMMARY_TOKENS):
        return _status_patch("data_summary")
    return None


def _status_patch(status: str) -> dict[str, Any]:
    return {
        "evidence_refs": [],
        "support_status": status,
        "unsupported": False,
        "unsupported_reason": None,
    }


def _apply_patch_to_finding(finding: dict[str, Any], patch: dict[str, Any]) -> None:
    refs = list(patch["evidence_refs"])
    finding["evidence_refs"] = refs
    finding["support_status"] = patch["support_status"]
    finding["unsupported"] = patch["unsupported"]
    finding["unsupported_reason"] = patch["unsupported_reason"]

    data = finding.get("data")
    if not isinstance(data, dict):
        data = {}
        finding["data"] = data
    data["evidence_refs"] = refs
    if refs:
        data["system_kb_evidence_refs"] = refs
    data["support_status"] = patch["support_status"]
    data["unsupported"] = patch["unsupported"]
    data["unsupported_reason"] = patch["unsupported_reason"]
    data["evidence_resolution"] = {
        "evidence_refs": refs,
        "support_status": patch["support_status"],
        "unsupported": patch["unsupported"],
        "unsupported_reason": patch["unsupported_reason"],
        "matched_claim_count": len(refs),
        "resolver": "specialist_backfill_v1",
    }

    for item in finding.get("findings") or []:
        if isinstance(item, dict) and not item.get("evidence_refs") and refs:
            item["evidence_refs"] = refs


def _finding_refs(finding: dict[str, Any]) -> list[Any]:
    refs = finding.get("evidence_refs")
    if refs is None and isinstance(finding.get("data"), dict):
        refs = finding["data"].get("evidence_refs")
    if not refs and isinstance(finding.get("data"), dict):
        refs = finding["data"].get("system_kb_evidence_refs")
    return refs if isinstance(refs, list) else []


def _finding_text(finding: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("summary", "title", "message", "recommendation", "category", "specialist"):
        value = finding.get(key)
        if value is not None:
            parts.append(str(value))
    data = finding.get("data")
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (str, int, float, bool)):
                parts.append(f"{key}={value}")
            elif isinstance(value, list):
                parts.extend(str(item) for item in value if isinstance(item, (str, int, float, bool)))
    return " | ".join(parts)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
