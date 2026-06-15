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
) -> Optional[int]:
    """记录一次 Safety Guardian 评估。

    Returns:
        新写入 audit_log 行的 id (旁路写入失败时为 None).
        Mobile ExplainSheet 需要这个 id 反查 /reasoning-trace/safety/{id}.
    """
    return _write(
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
    source: Optional[str] = None,
    memory_trace: Optional[Dict[str, Any]] = None,
    output_text: Optional[str] = None,
    perf_breakdown: Optional[Dict[str, Any]] = None,
) -> None:
    """记录一次 Orchestrator 综合调度。

    Args:
        source: 'siri' | 'chat' | 'widget' | None — 调用入口, 用来分析不同入口使用率.
        memory_trace: _inject_memory 返回的 trace dict (4 stage hit/chars/count).
            为 None 时表示该路径没启用 memory 注入 (legacy).
        output_text: LLM 完整输出, 用于启发式判断是否引用了 memory. 不写入 audit
            (省空间), 只用于计算 memory_referenced 布尔字段.
        perf_breakdown: 2026-05-28 — orchestrator 各阶段耗时分解 (intent / specialists
            per-name / llm_ttft / llm_full / twin / total). 用来做"哪一段在拖时间"的
            attribution. 落地到 result_detail['perf'].

    Phase 0.3 (2026-05-04): 加 memory_trace + memory_referenced. 之前 22 次
    orchestrator audit 中无人能判断 memory 是否真被 LLM 引用 — 修复后看板能算
    "memory 引用率 (orchestrator run 中 LLM 真用上 memory 的百分比)".
    """
    detail: Dict[str, Any] = {"used_specialists": used_specialists}
    if source:
        detail["source"] = source

    if memory_trace is not None:
        # 只取 trace 的关键摘要, 避免重复存大段 (memory_injection 已存全量)
        stages = memory_trace.get("stages", {})
        detail["memory"] = {
            "total_chars": memory_trace.get("total_chars_added", 0),
            "stages_ok": [name for name, s in stages.items() if s.get("ok")],
            "stages_failed": [name for name, s in stages.items() if not s.get("ok")],
            "hybrid_count": stages.get("hybrid", {}).get("count", 0),
            "conversation_count": stages.get("conversation", {}).get("count", 0),
        }

    if output_text:
        try:
            from app.services.memory_reference_detector import detect_memory_reference
            detail["memory_referenced"] = detect_memory_reference(output_text)
        except Exception:  # noqa: BLE001
            # detector 永不应抛, 但保险起见旁路
            pass

    if perf_breakdown:
        detail["perf"] = perf_breakdown

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
        result_detail=detail,
    )


def log_cross_review_conflicts(
    db: Session,
    user_id: int,
    conflicts: List[Dict[str, Any]],
    used_specialists: List[str],
) -> None:
    """记录一次 cross-review 检测到的 specialist 矛盾.

    每个 conflict 的字段: specialist_a, specialist_b, severity, description,
    resolution_hint. 全部存到 result_detail.
    """
    if not conflicts:
        return
    hard_count = sum(1 for c in conflicts if c.get("severity") == "hard")
    summary = (
        f"检测到 {len(conflicts)} 个 specialist 矛盾 "
        f"(hard={hard_count}, soft={len(conflicts) - hard_count}); "
        f"涉及 specialist: {', '.join(used_specialists)}"
    )
    _write(
        db,
        user_id=user_id,
        agent_type="cross_review",
        action="detect_conflicts",
        result_summary=summary,
        findings_count=len(conflicts),
        result_detail={"conflicts": conflicts, "used_specialists": used_specialists},
    )


def log_llm_arbitration(
    db: Session,
    user_id: int,
    arbitration: Dict[str, Any],
    conflicts_snapshot: List[Dict[str, Any]],
) -> None:
    """LLM 仲裁裁决 audit. arbitration = ArbitrationResult.to_dict().

    agent_type='llm_arbitrator' — Reasoning Trace UI 会聚合这类 trace.
    """
    try:
        winning = arbitration.get("winning_side", "?")
        conf = arbitration.get("confidence", 0)
        summary = (
            f"LLM 仲裁: {winning} (conf={conf:.2f}), "
            f"处理 {arbitration.get('conflicts_addressed', 0)} 个冲突"
        )
        _write(
            db,
            user_id=user_id,
            agent_type="llm_arbitrator",
            action="arbitrate",
            result_summary=summary,
            findings_count=arbitration.get("conflicts_addressed", 0),
            result_detail={
                "arbitration": arbitration,
                "conflicts": conflicts_snapshot,
            },
        )
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[audit] log_llm_arbitration 失败 (跳过): {e}")


def log_specialist_findings(
    db: Session,
    user_id: int,
    findings: List[Dict[str, Any]],
    orchestrator_run_id: Optional[int] = None,
) -> Optional[int]:
    """记录一批 specialist 产出的 findings, 支持 /reasoning-trace/specialist/{audit_id} 反查.

    旁路, 失败不抛. Returns: 新写入的 audit_log.id, 方便调用方回写关联.
    """
    try:
        from app.models.agent_audit_log import AgentAuditLog

        row = AgentAuditLog(
            user_id=user_id,
            agent_type="specialist_batch",
            action="run",
            result_summary=f"产出 {len(findings)} 条 findings",
            findings_count=len(findings),
            result_detail={
                "findings": findings,
                "orchestrator_run_id": orchestrator_run_id,
            },
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[audit] log_specialist_findings 失败 (跳过): {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return None


def log_memory_injection(
    db: Session,
    user_id: int,
    trace: Dict[str, Any],
) -> Optional[int]:
    """记录一次 _inject_memory 的 stage-level 输出 (Memory 注入诊断).

    trace 形如:
      {
        "stages": {
          "conversation": {"ok": True,  "chars": 120, "count": 5, "error": None},
          "case_timeline": {"ok": False, "chars": 0,   "count": 0, "error": None},  # no findings/metric
          "directives":   {"ok": True,  "chars": 80,  "count": 2, "error": None},
          "hybrid":       {"ok": False, "chars": 0,   "count": 0, "error": "redis down"},
        },
        "total_chars_added": 200,
      }

    agent_type='memory_injection' — observability dashboard 按此类聚合.
    旁路, 失败不抛.
    """
    if user_id is None:
        return None
    try:
        stages = trace.get("stages", {})
        ok_count = sum(1 for s in stages.values() if s.get("ok"))
        total_count = len(stages)
        total_chars = trace.get("total_chars_added", 0)
        summary = (
            f"memory inject {ok_count}/{total_count} stage 命中, "
            f"+{total_chars} chars"
        )
        return _write(
            db,
            user_id=user_id,
            agent_type="memory_injection",
            action="inject",
            result_summary=summary,
            findings_count=ok_count,
            result_detail=trace,
        )
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[audit] log_memory_injection 失败 (跳过): {e}")
        return None


def log_proactive_trigger(
    db: Session,
    user_id: int,
    *,
    agent_type: str,
    metric: str,
    kind: str,
    delta: float,
    notable: bool,
    notified: bool,
) -> Optional[int]:
    """泛型主动 Agent 触发埋点(longevity_watch / trajectory_watch 等共用)。

    eval 看板(agent_eval_service)按 agent_type ∈ {*_watch} 聚合 notable/推送率。
    旁路, 失败不抛。
    """
    if user_id is None:
        return None
    try:
        summary = f"{agent_type} {metric} {kind} {delta:+.3f} notable={notable} notified={notified}"
        return _write(
            db,
            user_id=user_id,
            agent_type=agent_type,
            action="proactive_trigger",
            result_summary=summary,
            result_detail={"metric": metric, "kind": kind, "delta": delta,
                           "notable": notable, "notified": notified},
        )
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[audit] log_proactive_trigger 失败 (跳过): {e}")
        return None


def log_longevity_trigger(
    db: Session,
    user_id: int,
    *,
    metric: str,
    kind: str,
    delta_years: float,
    notable: bool,
    notified: bool,
) -> Optional[int]:
    """记录一次抗衰主动 Agent 的生物年龄变化触发 (Phase2 W6 eval)。

    agent_type='longevity_watch' — observability 据此算:
      触发数 / notable 率 / 推送率 (notified) / 后续接受率(由 action_card 侧关联)。
    旁路, 失败不抛。
    """
    if user_id is None:
        return None
    try:
        summary = (
            f"longevity {metric} {kind} {delta_years:+.1f}y "
            f"notable={notable} notified={notified}"
        )
        return _write(
            db,
            user_id=user_id,
            agent_type="longevity_watch",
            action="proactive_trigger",
            result_summary=summary,
            result_detail={
                "metric": metric,
                "kind": kind,
                "delta_years": delta_years,
                "notable": notable,
                "notified": notified,
            },
        )
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[audit] log_longevity_trigger 失败 (跳过): {e}")
        return None


def log_bedroom_event(
    db: Session,
    user_id: int,
    *,
    event_type: str,
    source: str,
    room_id: str = "bedroom",
    reason: Optional[str] = None,
    command_entity_id: Optional[str] = None,
    command_mode: Optional[str] = None,
    manual_override: bool = False,
) -> Optional[int]:
    """记录一次卧室自动化事件摄入 (设计文档 §10/§11: 每条命令/事件写 AuditLog).

    agent_type='bedroom_automation' — Review / 审计可据此追溯"昨夜自动化"。
    旁路, 失败不抛 (返回 None), 不阻断事件落库。返回 audit_log.id 供回填 audit_ref。
    """
    if user_id is None:
        return None
    try:
        summary = f"bedroom {event_type} source={source}"
        if manual_override:
            summary += " manual_override"
        return _write(
            db,
            user_id=user_id,
            agent_type="bedroom_automation",
            action=event_type,
            result_summary=summary,
            result_detail={
                "room_id": room_id,
                "event_type": event_type,
                "source": source,
                "reason": reason,
                "command_entity_id": command_entity_id,
                "command_mode": command_mode,
                "manual_override": manual_override,
            },
        )
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[audit] log_bedroom_event 失败 (跳过): {e}")
        return None


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
) -> Optional[int]:
    """底层写入。失败静默。返回新行 id (失败时 None)。"""
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
        db.refresh(log)
        return log.id
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[audit] 写入失败（降级）: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return None
