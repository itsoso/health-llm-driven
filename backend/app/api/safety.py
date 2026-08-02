"""
Safety Guardian API 端点。

- GET  /api/v1/safety/me            返回全部安全告警报告
- GET  /api/v1/safety/rules         列出所有已注册的规则
- POST /api/v1/safety/explain       对单条告警请求 LLM 个性化解读
"""

import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.safety_guardian import evaluate_safety
from app.agents.safety_guardian.cache import safety_report_cache_key
from app.agents.safety_guardian.engine import registry
from app.api.deps import get_current_user_required
from app.api.knowledge import _ensure_legacy_knowledge_runtime_enabled
from app.database import get_db
from app.models.user import User
from app.twin.builder import build_twin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/safety", tags=["safety"])


# ─────────────────────────── Schemas ────────────────────────────


class ExplainRequest(BaseModel):
    rule_id: str
    data_citation: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


class ExplainResponse(BaseModel):
    rule_id: str
    explanation: str
    generated_at: datetime
    cached: bool


@router.get("/me")
def get_my_safety_report(
    severity_min: int = Query(2, ge=0, le=4, description="只返回 >= 此严重度的告警 (默认 2=MEDIUM, 过滤 INFO/LOW 噪声)"),
    limit: int = Query(8, ge=1, le=50, description="最多返回 N 条告警 (按 severity 降序). 剩余进 summary.truncated_count"),
    dedup_by_rule: bool = Query(True, description="同 rule_id 只保留最高 severity 那条 (防 DDI 多药对刷屏)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """
    当前用户的安全告警报告。

    **默认降噪**: severity >= MEDIUM, 最多 8 条, 同规则去重. 前端如需全量可传
    `?severity_min=0&limit=50&dedup_by_rule=false`.

    返回结构：
      {
        user_id, generated_at,
        alerts: [{rule_id, category, severity, title, message, action, ...}],
        summary: {total, critical, high, medium, rules_evaluated,
                  truncated_count, dedup_count},
        timing: {twin_build_ms, evaluate_ms}
      }
    """
    # Safety report 缓存（5min，Twin 更新时会 invalidate）
    # 缓存 key 含参数, 避免不同过滤条件错缓存
    _safety_cache_key = safety_report_cache_key(
        current_user.id,
        severity_min=severity_min,
        limit=limit,
        dedup_by_rule=dedup_by_rule,
    )
    try:
        from app.utils.redis_cache import RedisCache
        _cached_safety = RedisCache.get(_safety_cache_key)
        if _cached_safety:
            _cached_safety["_cached"] = True
            return _cached_safety
    except Exception as e:
        # 缓存读失败 → 走重算(正确降级),但记一笔便于发现 Redis 长期不可用
        logger.warning("[safety] cache read failed, recomputing: %s", e)

    twin = build_twin(db, current_user.id)
    report = evaluate_safety(twin)

    # 审计日志（旁路，失败不影响响应）
    # result_detail 存入本次所有 alerts 的结构化快照, 让后续
    # /reasoning-trace/safety/{audit_id}?rule_id=... 可以反查单条 alert 详情.
    audit_id: Optional[int] = None
    try:
        from app.agents.audit import log_safety_evaluation

        alerts_snapshot = [
            {
                "rule_id": a.rule_id,
                "category": a.category,
                "severity": int(a.severity),
                "title": a.title,
                "message": a.message,
                "action": a.action,
                "data_citation": a.data_citation,
                "generated_at": a.generated_at.isoformat(),
            }
            for a in report.alerts
        ]

        audit_id = log_safety_evaluation(
            db=db,
            user_id=current_user.id,
            alerts_count=len(report.alerts),
            result_summary=f"{report.critical_count}crit/{report.high_count}high/{report.medium_count}med",
            twin_build_ms=report.twin_build_ms,
            evaluate_ms=report.evaluate_ms,
            twin_sources=twin.meta.data_sources,
            result_detail={"alerts": alerts_snapshot},
        )
    except Exception:
        pass

    # 过滤用户已忽略/已知的告警
    try:
        from app.models.dismissed_alert import DismissedAlert

        dismissed_ids = {
            d.rule_id
            for d in db.query(DismissedAlert.rule_id)
            .filter(DismissedAlert.user_id == current_user.id)
            .all()
        }
        if dismissed_ids:
            dismissed_alerts = [a for a in report.alerts if a.rule_id in dismissed_ids]
            report.alerts = [a for a in report.alerts if a.rule_id not in dismissed_ids]
    except Exception:
        dismissed_ids = set()
        dismissed_alerts = []

    # WSCLA 生命周期 surface: 把活跃告警写入 action_cards (旁路, 失败不影响响应).
    # 幂等 upsert 策略见 action_card_surface.py.
    try:
        from app.services.action_card_surface import surface_safety_alerts
        from app.agents.safety_guardian.rules.training_load import ACWR_RULE_IDS

        surface_safety_alerts(
            db,
            current_user.id,
            report.alerts,
            reconcile_rule_ids=ACWR_RULE_IDS,
        )
    except Exception as e:
        logger.warning(
            "[safety] action-card surface/reconcile failed for user=%s: %s",
            current_user.id,
            e,
        )

    # Severity 门槛
    if severity_min > 0:
        report.alerts = [a for a in report.alerts if int(a.severity) >= severity_min]

    # Dedup by rule_id (同规则触发多次保留最高 severity)
    dedup_count = 0
    if dedup_by_rule and report.alerts:
        by_rule: Dict[str, Any] = {}
        for a in report.alerts:
            existing = by_rule.get(a.rule_id)
            if existing is None or int(a.severity) > int(existing.severity):
                by_rule[a.rule_id] = a
        dedup_count = len(report.alerts) - len(by_rule)
        # 按 severity 降序 + 生成时间降序
        report.alerts = sorted(by_rule.values(), key=lambda a: (-int(a.severity), -a.generated_at.timestamp()))

    # Top N 限制
    total_after_filter = len(report.alerts)
    truncated_count = max(0, total_after_filter - limit)
    if truncated_count > 0:
        report.alerts = report.alerts[:limit]

    result = report.model_dump_for_api()
    result["dismissed_count"] = len(dismissed_ids)
    result["summary"]["truncated_count"] = truncated_count
    result["summary"]["dedup_count"] = dedup_count
    # Task 3: 回传 audit_id, Mobile ExplainSheet 用它反查 reasoning-trace.
    # 旁路 audit 写失败时为 None, 客户端需容忍.
    result["audit_id"] = audit_id

    # 写缓存（5min TTL, 和 Twin 缓存对齐）
    try:
        from app.utils.redis_cache import RedisCache
        RedisCache.set(_safety_cache_key, result, ttl=300)
    except Exception:
        pass

    return result


@router.post("/dismiss")
def dismiss_alert(
    rule_id: str = Query(...),
    reason: str = Query("known", description="known / resolved / false_positive"),
    note: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """忽略/标记已知某条告警。下次 /safety/me 不再返回该 rule_id。"""
    from app.models.dismissed_alert import DismissedAlert

    existing = db.query(DismissedAlert).filter(
        DismissedAlert.user_id == current_user.id,
        DismissedAlert.rule_id == rule_id,
    ).first()
    if existing:
        return {"message": "已忽略", "rule_id": rule_id}

    d = DismissedAlert(user_id=current_user.id, rule_id=rule_id, reason=reason, note=note)
    db.add(d)
    db.commit()
    return {"message": "已忽略", "rule_id": rule_id, "reason": reason}


@router.delete("/dismiss")
def restore_alert(
    rule_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """恢复之前忽略的告警。"""
    from app.models.dismissed_alert import DismissedAlert

    d = db.query(DismissedAlert).filter(
        DismissedAlert.user_id == current_user.id,
        DismissedAlert.rule_id == rule_id,
    ).first()
    if d:
        db.delete(d)
        db.commit()
    return {"message": "已恢复", "rule_id": rule_id}


@router.get("/dismissed")
def list_dismissed(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """列出所有已忽略的告警。"""
    from app.models.dismissed_alert import DismissedAlert

    items = db.query(DismissedAlert).filter(DismissedAlert.user_id == current_user.id).all()
    return [
        {"rule_id": d.rule_id, "reason": d.reason, "note": d.note, "dismissed_at": d.dismissed_at.isoformat() if d.dismissed_at else None}
        for d in items
    ]


@router.post("/knowledge/index")
def build_knowledge_index(
    force: bool = Query(False),
    current_user: User = Depends(get_current_user_required),
    _legacy_runtime: None = Depends(
        _ensure_legacy_knowledge_runtime_enabled
    ),
):
    """触发知识库索引构建（得到 wiki → ChromaDB）。"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="只有管理员可以重建旧知识索引",
        )

    try:
        from app.agents.knowledge_librarian.indexer import build_index

        result = build_index(force=force)
        return result
    except Exception as e:
        return {"error": str(e)}


@router.get("/rules")
def list_rules(
    current_user: User = Depends(get_current_user_required),
):
    """列出所有已注册的 Safety 规则 —— 透明度用。"""
    return {
        "total": registry.count(),
        "rules": [name for name, _ in registry.all_rules()],
    }


@router.get("/audit")
def get_audit_logs(
    limit: int = Query(20, ge=1, le=100),
    agent_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """查看 agent 审计日志：系统为什么告诉我这个。"""
    try:
        from sqlalchemy import desc

        from app.models.agent_audit_log import AgentAuditLog

        q = db.query(AgentAuditLog).filter(AgentAuditLog.user_id == current_user.id)
        if agent_type:
            q = q.filter(AgentAuditLog.agent_type == agent_type)
        logs = q.order_by(desc(AgentAuditLog.created_at)).limit(limit).all()
        return [
            {
                "id": log.id,
                "agent_type": log.agent_type,
                "action": log.action,
                "query": log.query,
                "result_summary": log.result_summary,
                "alerts_count": log.alerts_count,
                "findings_count": log.findings_count,
                "twin_build_ms": log.twin_build_ms,
                "evaluate_ms": log.evaluate_ms,
                "total_ms": log.total_ms,
                "twin_sources": log.twin_sources,
                "intent_categories": log.intent_categories,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
    except Exception as e:
        return {"error": str(e), "logs": []}


# ─────────────────────────── LLM 解释端点 ────────────────────────


_EXPLAIN_CACHE: Dict[str, tuple[float, str]] = {}
_EXPLAIN_TTL = 60 * 60  # 1 hour


def _cache_key(user_id: int, rule_id: str, data_citation: Optional[Dict[str, Any]]) -> str:
    payload = json.dumps(
        {"u": user_id, "r": rule_id, "d": data_citation or {}},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:20]


@router.post("/explain", response_model=ExplainResponse)
async def explain_alert(
    req: ExplainRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    from app.services.llm.usage_tracker import set_caller
    set_caller("safety.explain", user_id=current_user.id)
    """
    对某条安全告警请求 LLM 个性化解读。

    输入：rule_id + 可选的 data_citation（用户直接从前端回传，避免再建 Twin）
    输出：基于用户当前健康上下文的白话解读 + 具体建议

    策略：
    - 1 小时进程内缓存（按 user_id + rule_id + data_citation 哈希）
    - 调用默认 LLM provider，短 prompt，temperature=0.3 求稳定
    - 失败不抛，返回规则自身的 message 作为降级
    """
    cache_key = _cache_key(current_user.id, req.rule_id, req.data_citation)
    now = time.time()
    cached = _EXPLAIN_CACHE.get(cache_key)
    if cached and now - cached[0] < _EXPLAIN_TTL:
        return ExplainResponse(
            rule_id=req.rule_id,
            explanation=cached[1],
            generated_at=datetime.now(UTC),
            cached=True,
        )

    # 构建用户上下文（轻量，只读 Twin 摘要文本）
    try:
        from app.twin.builder import build_twin as _build_twin
        from app.twin.formatter import twin_to_prompt_blob

        twin = _build_twin(db, current_user.id)
        twin_context = twin_to_prompt_blob(twin)
    except Exception as e:
        logger.warning(f"[safety.explain] twin 构建失败: {e}")
        twin_context = ""

    system_prompt = (
        "你是健康助理的安全顾问。用户的安全监控系统检出了一条告警，"
        "请你基于用户的当下健康状态给出"
        "个性化、具体、可执行的中文解读，不少于 100 字、不超过 300 字。\n\n"
        "原则：\n"
        "1. 不重复告警本身的字面话，要结合用户真实数据解释为什么这个告警对 TA 重要\n"
        "2. 给出 2-3 个具体的下一步行动（时间/频率/剂量要具体）\n"
        "3. 若涉及药物/剂量调整，明确说需要和医生确认\n"
        "4. 不要医学免责声明废话，直入主题\n"
    )

    user_prompt = (
        f"【告警 rule_id】{req.rule_id}\n"
        f"【告警原文】{req.message or '(未提供)'}\n"
        f"【触发数据】{json.dumps(req.data_citation or {}, ensure_ascii=False, default=str)}\n\n"
        f"【用户当前健康快照】\n{twin_context or '(数据暂缺)'}\n\n"
        "请给出个性化解读和具体行动。"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # 先尝试默认 provider，失败则回退到 TokenPlan。
    async def _try_provider(provider_type: Optional[str]) -> Optional[str]:
        try:
            from app.services.llm import get_llm_provider
            from app.services.llm.factory import create_llm_provider

            provider = (
                create_llm_provider(provider_type)
                if provider_type
                else get_llm_provider()
            )
            result = await provider.chat(
                messages=messages,
                temperature=0.3,
                max_tokens=600,
            )
            if isinstance(result, dict):
                text = result.get("content") or result.get("message") or ""
            else:
                text = str(result or "")
            text = text.strip()
            return text if text else None
        except Exception as inner:
            logger.warning(
                f"[safety.explain] provider={provider_type or 'default'} 失败: "
                f"{str(inner)[:200]}"
            )
            return None

    explanation = await _try_provider(None)  # 默认 provider
    if not explanation:
        explanation = await _try_provider("tokenplan")  # fallback

    if explanation:
        _EXPLAIN_CACHE[cache_key] = (now, explanation)
        return ExplainResponse(
            rule_id=req.rule_id,
            explanation=explanation,
            generated_at=datetime.now(UTC),
            cached=False,
        )

    # 两个 provider 都失败 → 降级
    fallback = (
        (req.message or "") + "\n\n[个性化解读服务暂时不可用（LLM 服务超限），请稍后重试]"
    ).strip()
    return ExplainResponse(
        rule_id=req.rule_id,
        explanation=fallback,
        generated_at=datetime.now(UTC),
        cached=False,
    )
