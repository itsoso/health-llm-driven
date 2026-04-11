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
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.safety_guardian import evaluate_safety
from app.agents.safety_guardian.engine import registry
from app.api.deps import get_current_user_required
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
    severity_min: int = Query(0, ge=0, le=4, description="只返回 >= 此严重度的告警"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """
    当前用户的安全告警报告。

    返回结构：
      {
        user_id, generated_at,
        alerts: [{rule_id, category, severity, title, message, action, ...}],
        summary: {total, critical, high, medium, rules_evaluated},
        timing: {twin_build_ms, evaluate_ms}
      }
    """
    twin = build_twin(db, current_user.id)
    report = evaluate_safety(twin)

    if severity_min > 0:
        report.alerts = [a for a in report.alerts if int(a.severity) >= severity_min]

    return report.model_dump_for_api()


@router.get("/rules")
def list_rules(
    current_user: User = Depends(get_current_user_required),
):
    """列出所有已注册的 Safety 规则 —— 透明度用。"""
    return {
        "total": registry.count(),
        "rules": [name for name, _ in registry.all_rules()],
    }


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
            generated_at=datetime.utcnow(),
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

    try:
        from app.services.llm import get_llm_provider

        provider = get_llm_provider()
        result = await provider.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=600,
        )

        # 防御：provider 可能返回 dict 形态（tool_calls 场景），我们只要文本
        if isinstance(result, dict):
            explanation = result.get("content") or result.get("message") or str(result)
        else:
            explanation = str(result or "").strip()

        if not explanation:
            raise ValueError("LLM 返回空内容")

        _EXPLAIN_CACHE[cache_key] = (now, explanation)
        return ExplainResponse(
            rule_id=req.rule_id,
            explanation=explanation,
            generated_at=datetime.utcnow(),
            cached=False,
        )
    except Exception as e:
        logger.warning(f"[safety.explain] LLM 调用失败: {e}")
        fallback = (
            (req.message or "") + "\n\n[个性化解读暂不可用，请稍后重试]"
        ).strip()
        return ExplainResponse(
            rule_id=req.rule_id,
            explanation=fallback,
            generated_at=datetime.utcnow(),
            cached=False,
        )
