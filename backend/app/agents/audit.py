"""
Agent 审计日志写入工具。

统一入口，所有 agent/specialist 的审计写入都走这里。
失败不抛异常（审计是旁路，不能影响主流程）。
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def log_safety_evaluation(
    db: Session,
    user_id: int,
    alerts_count: int,
    result_summary: str,
    twin_build_ms: int,
    evaluate_ms: int,
    twin_sources: List[str],
    result_detail: Optional[Dict[str, Any]] = None,
) -> None:
    """记录一次 Safety Guardian 评估。"""
    _write(
        db,
        user_id=user_id,
        agent_type="safety_guardian",
        action="evaluate",
        result_summary=result_summary,
        alerts_count=alerts_count,
        twin_build_ms=twin_build_ms,
        evaluate_ms=evaluate_ms,
        twin_sources=twin_sources,
        result_detail=result_detail,
    )


def log_orchestrator_run(
    db: Session,
    user_id: int,
    query: str,
    intent_categories: List[str],
    used_specialists: List[str],
    findings_count: int,
    twin_build_ms: int,
    total_ms: int,
    result_summary: Optional[str] = None,
) -> None:
    """记录一次 Orchestrator 综合调度。"""
    _write(
        db,
        user_id=user_id,
        agent_type="orchestrator",
        action="run",
        query=query,
        result_summary=result_summary or f"调度 {len(used_specialists)} 个专家",
        findings_count=findings_count,
        twin_build_ms=twin_build_ms,
        total_ms=total_ms,
        twin_sources=None,
        intent_categories=intent_categories,
        result_detail={"used_specialists": used_specialists},
    )


def _write(
    db: Session,
    user_id: int,
    agent_type: str,
    action: str,
    result_summary: str = "",
    query: Optional[str] = None,
    alerts_count: int = 0,
    findings_count: int = 0,
    twin_build_ms: Optional[int] = None,
    evaluate_ms: Optional[int] = None,
    total_ms: Optional[int] = None,
    twin_sources: Optional[List[str]] = None,
    intent_categories: Optional[List[str]] = None,
    result_detail: Optional[Dict[str, Any]] = None,
) -> None:
    """底层写入。失败静默。"""
    try:
        from app.models.agent_audit_log import AgentAuditLog

        log = AgentAuditLog(
            user_id=user_id,
            agent_type=agent_type,
            action=action,
            query=query,
            result_summary=result_summary[:500] if result_summary else None,
            alerts_count=alerts_count,
            findings_count=findings_count,
            twin_build_ms=twin_build_ms,
            evaluate_ms=evaluate_ms,
            total_ms=total_ms,
            twin_sources=twin_sources,
            intent_categories=intent_categories,
            result_detail=result_detail,
        )
        db.add(log)
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[audit] 写入失败（降级）: {e}")
        try:
            db.rollback()
        except Exception:
            pass
