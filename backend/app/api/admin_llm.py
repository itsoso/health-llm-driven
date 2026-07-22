"""
GET  /api/v1/admin/llm/status   — 当前活跃 provider + 配置概况
POST /api/v1/admin/llm/switch   — 临时切换 (内存) provider, 不改 .env
POST /api/v1/admin/llm/ping     — 测当前 provider 延迟 + 中文 tool calling

Karpathy "autonomy slider" 思想: 让管理员能 A/B 切多 LLM 后端验证体验.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from app.api.admin import get_admin_user
from app.api.deps import get_db
from app.config import settings
from app.models.llm_usage import LlmUsageLog
from app.models.user import User
from app.services.llm.usage_tracker import estimate_usage_cost
from app.services.llm.tokenplan_cost import (
    QWEN37_MAX_PROMO_END_UTC,
    estimate_tokenplan_cost,
    tokenplan_cny_rate_table,
    tokenplan_payg_cny_rate_table,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/llm", tags=["admin"])


def _safe_int(value) -> int:
    return int(value or 0)


def _safe_float(value, digits: int = 4) -> float:
    return round(float(value or 0.0), digits)


def _cost_cny_from_usd(value: float) -> float:
    return float(value or 0.0) * float(getattr(settings, "llm_cost_usd_to_cny", 7.2) or 0.0)


def _success_rate(success_calls: int, calls: int) -> Optional[float]:
    if calls <= 0:
        return None
    return round(success_calls / calls, 4)


def _tokenplan_model_names() -> list[str]:
    """TokenPlan 兼容 OpenAI 协议,历史日志里 provider 可能仍是 openai.

    Admin 成本看板用模型名兜底归类,保证旧日志不会从 698/月套餐账本里漏掉.
    """
    names = {settings.tokenplan_model, *tokenplan_cny_rate_table().keys()}
    try:
        from app.services.llm.model_registry import MODELS

        names.update(m.model for m in MODELS if m.provider == "tokenplan")
    except Exception:
        logger.debug("[admin.llm.usage] model registry unavailable", exc_info=True)
    return sorted(str(name).strip().lower() for name in names if str(name).strip())


def _tokenplan_condition(tokenplan_models: list[str]):
    clauses = [func.lower(LlmUsageLog.provider) == "tokenplan"]
    if tokenplan_models:
        clauses.append(func.lower(LlmUsageLog.model).in_(tokenplan_models))
    return or_(*clauses)


def _usage_cost_sql_expr():
    """SQL-side fallback so Admin rollups can estimate older rows with cost_usd=0."""
    model = func.lower(LlmUsageLog.model)
    provider = func.lower(LlmUsageLog.provider)
    input_rate = case(
        (model == "gpt-4o-mini", 0.15),
        (model == "gpt-4o", 2.50),
        (model == "gpt-4-turbo", 10.00),
        (model == "qwen3.7-plus", 0.40),
        (model == "qwen3.7-max", 1.20),
        (model == "qwen3.6-plus", 0.40),
        (model == "qwen3.6-flash", 0.05),
        (model == "qwen-vl-max", 1.50),
        (model == "deepseek-v4-pro", 0.75),
        (model == "deepseek-v4-flash", 0.10),
        (model == "deepseek-v3.2", 0.30),
        (model == "kimi-k2.7-code", 0.80),
        (model.like("kimi%"), 0.50),
        (model == "glm-5.1", 0.25),
        (model.like("glm%"), 0.30),
        (model == "minimax-m2.5", 0.80),
        (model.like("qwen%flash%"), 0.05),
        (model.like("qwen%max%"), 1.20),
        (model.like("qwen%pro%"), 1.20),
        (model.like("qwen%"), 0.40),
        (model.like("deepseek%flash%"), 0.10),
        (model.like("deepseek%pro%"), 0.75),
        (model.like("deepseek%"), 0.30),
        (model.like("gpt-%"), 0.50),
        (provider == "langbridge-proxy", 2.00),
        (provider.in_(("tokenplan", "openai", "openai-proxy")), 0.50),
        else_=0.0,
    )
    output_rate = case(
        (model == "gpt-4o-mini", 0.60),
        (model == "gpt-4o", 10.00),
        (model == "gpt-4-turbo", 30.00),
        (model == "qwen3.7-plus", 1.20),
        (model == "qwen3.7-max", 3.60),
        (model == "qwen3.6-plus", 1.20),
        (model == "qwen3.6-flash", 0.20),
        (model == "qwen-vl-max", 4.50),
        (model == "deepseek-v4-pro", 2.40),
        (model == "deepseek-v4-flash", 0.30),
        (model == "deepseek-v3.2", 0.90),
        (model == "kimi-k2.7-code", 2.40),
        (model.like("kimi%"), 1.50),
        (model == "glm-5.1", 0.75),
        (model.like("glm%"), 0.90),
        (model == "minimax-m2.5", 2.40),
        (model.like("qwen%flash%"), 0.20),
        (model.like("qwen%max%"), 3.60),
        (model.like("qwen%pro%"), 3.60),
        (model.like("qwen%"), 1.20),
        (model.like("deepseek%flash%"), 0.30),
        (model.like("deepseek%pro%"), 2.40),
        (model.like("deepseek%"), 0.90),
        (model.like("gpt-%"), 1.50),
        (provider == "langbridge-proxy", 6.00),
        (provider.in_(("tokenplan", "openai", "openai-proxy")), 1.50),
        else_=0.0,
    )
    estimated = (
        func.coalesce(LlmUsageLog.prompt_tokens, 0) * input_rate
        + func.coalesce(LlmUsageLog.completion_tokens, 0) * output_rate
    ) / 1_000_000.0
    return case((LlmUsageLog.cost_usd > 0, LlmUsageLog.cost_usd), else_=estimated)


def _tokenplan_cost_sql_expr(tokenplan_condition):
    """按公开 TokenPlan 规则估算历史日志的 Credits、容量成本和按量价。"""
    model = func.lower(LlmUsageLog.model)
    prompt = func.coalesce(LlmUsageLog.prompt_tokens, 0)
    completion = func.coalesce(LlmUsageLog.completion_tokens, 0)
    cached_raw = func.coalesce(LlmUsageLog.cached_tokens, 0)
    cached = case(
        (cached_raw < 0, 0),
        (cached_raw > prompt, prompt),
        else_=cached_raw,
    )

    def price_exprs(rate_table):
        input_whens = []
        output_whens = []
        for model_name, tiers in rate_table.items():
            for index, (limit, input_rate, output_rate) in enumerate(tiers):
                condition = model == model_name
                if index < len(tiers) - 1:
                    condition = and_(condition, prompt <= limit)
                input_whens.append((condition, input_rate))
                output_whens.append((condition, output_rate))
        return case(*input_whens, else_=0.0), case(*output_whens, else_=0.0)

    credit_input_rate, credit_output_rate = price_exprs(tokenplan_cny_rate_table())
    payg_input_rate, payg_output_rate = price_exprs(tokenplan_payg_cny_rate_table())
    cache_supported = or_(
        cached == 0,
        and_(
            model == "qwen3.7-max",
            LlmUsageLog.created_at <= QWEN37_MAX_PROMO_END_UTC,
        ),
    )
    cache_multiplier = case(
        (
            and_(
                cached > 0,
                model == "qwen3.7-max",
                LlmUsageLog.created_at <= QWEN37_MAX_PROMO_END_UTC,
            ),
            0.2,
        ),
        else_=1.0,
    )
    credit_basis_cny = (
        (prompt - cached) * credit_input_rate
        + cached * credit_input_rate * cache_multiplier
        + completion * credit_output_rate
    ) / 1_000_000.0
    payg_base_cny = (
        (prompt - cached) * payg_input_rate
        + cached * payg_input_rate * cache_multiplier
        + completion * payg_output_rate
    ) / 1_000_000.0
    promo_multiplier = case(
        (
            and_(
                model == "qwen3.7-max",
                LlmUsageLog.created_at <= QWEN37_MAX_PROMO_END_UTC,
            ),
            0.5,
        ),
        else_=1.0,
    )
    payg_multiplier = case(
        (
            and_(
                model == "qwen3.7-max",
                LlmUsageLog.created_at <= QWEN37_MAX_PROMO_END_UTC,
            ),
            0.5,
        ),
        else_=1.0,
    )
    payg_cny = payg_base_cny * payg_multiplier
    credits_per_cny = float(getattr(settings, "tokenplan_credits_per_cny", 100.0) or 0.0)
    monthly_fee = float(getattr(settings, "tokenplan_monthly_budget_cny", 698.0) or 0.0)
    monthly_credits = int(getattr(settings, "tokenplan_monthly_credits", 100_000) or 0)
    credits = case(
        (
            and_(tokenplan_condition, cache_supported),
            credit_basis_cny * credits_per_cny * promo_multiplier,
        ),
        else_=0.0,
    )
    capacity_cost = credits * monthly_fee / monthly_credits if monthly_credits > 0 else credits * 0
    tokenplan_payg = case(
        (and_(tokenplan_condition, cache_supported), payg_cny),
        else_=0.0,
    )
    # 新账本优先使用写入时的估算;旧行才走上面的 SQL 价格表回退。
    persisted_credits = func.coalesce(LlmUsageLog.tokenplan_credits_estimate, credits)
    persisted_capacity = func.coalesce(LlmUsageLog.tokenplan_cost_cny, capacity_cost)
    persisted_payg = func.coalesce(LlmUsageLog.tokenplan_payg_value_cny, tokenplan_payg)
    return persisted_credits, persisted_capacity, persisted_payg, cache_supported


def _provider_family_expr(tokenplan_models: list[str]):
    whens = [(func.lower(LlmUsageLog.provider) == "tokenplan", "tokenplan")]
    if tokenplan_models:
        whens.append((func.lower(LlmUsageLog.model).in_(tokenplan_models), "tokenplan"))
    return case(*whens, else_=LlmUsageLog.provider)


def _usage_filters(since: datetime, until: datetime, user_id: Optional[int] = None):
    filters = [LlmUsageLog.created_at >= since, LlmUsageLog.created_at <= until]
    if user_id is not None:
        filters.append(LlmUsageLog.user_id == user_id)
    return filters


def _month_start_utc(now: datetime) -> datetime:
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)


def _quota_ratio(used: float, limit: float) -> Optional[float]:
    if limit <= 0:
        return None
    return round(float(used or 0) / float(limit), 4)


def _budget_guard(
    *,
    monthly_token_quota: int,
    tokens_used_month: int,
    now: datetime,
) -> dict:
    if monthly_token_quota <= 0:
        return {
            "monthly_token_quota": 0,
            "tokens_used_month": tokens_used_month,
            "quota_utilization_pct": None,
            "projected_month_tokens": None,
            "projected_quota_utilization_pct": None,
            "level": "unknown",
            "recommended_runtime_policy": "observe",
            "suggested_actions": ["配置 TOKENPLAN_MONTHLY_TOKEN_QUOTA 后启用 50/80/95% 额度预警"],
        }

    month_start = _month_start_utc(now)
    elapsed_days = max((now - month_start).total_seconds() / 86400, 1 / 24)
    projected = int(round(tokens_used_month / elapsed_days * 30))
    used_pct = tokens_used_month / monthly_token_quota
    projected_pct = projected / monthly_token_quota
    pressure = max(used_pct, projected_pct)
    if pressure >= 0.95:
        level = "critical"
        policy = "degrade"
        actions = [
            "自动优先备用模型或快速模型,避免继续触发 429",
            "降低深思轮次和长上下文回填",
            "检查阿里云百炼 TokenPlan 套餐余量或升级额度",
        ]
    elif pressure >= 0.8:
        level = "warn"
        policy = "conserve"
        actions = [
            "默认使用快速/均衡模型处理低风险对话",
            "限制重复图表和长历史上下文",
            "关注近 24 小时 Top 用户和 Top caller",
        ]
    elif pressure >= 0.5:
        level = "watch"
        policy = "observe"
        actions = ["关注本月消耗趋势,暂不影响用户体验"]
    else:
        level = "ok"
        policy = "normal"
        actions = ["额度压力正常"]
    return {
        "monthly_token_quota": monthly_token_quota,
        "tokens_used_month": tokens_used_month,
        "quota_utilization_pct": round(used_pct, 4),
        "projected_month_tokens": projected,
        "projected_quota_utilization_pct": round(projected_pct, 4),
        "level": level,
        "recommended_runtime_policy": policy,
        "suggested_actions": actions,
    }


def _rollup_row(row, *, tokenplan_tokens_total: int, monthly_budget_cny: float) -> dict:
    calls = _safe_int(row.calls)
    success_calls = _safe_int(row.success_calls)
    failed_calls = max(0, calls - success_calls)
    tokenplan_tokens = _safe_int(row.tokenplan_tokens)
    allocated = (
        monthly_budget_cny * tokenplan_tokens / tokenplan_tokens_total
        if tokenplan_tokens_total > 0
        else 0.0
    )
    effective = (
        allocated * 1000 / tokenplan_tokens
        if tokenplan_tokens > 0
        else None
    )
    cost_usd = _safe_float(row.cost_usd, 6)
    tokenplan_calls = _safe_int(row.tokenplan_calls)
    tokenplan_priced_calls = _safe_int(row.tokenplan_priced_calls)
    tokenplan_unpriced_calls = _safe_int(row.tokenplan_unpriced_calls)
    has_plan_price = tokenplan_priced_calls > 0
    tokenplan_credits = _safe_float(row.tokenplan_credits_estimate, 4) if has_plan_price else None
    tokenplan_capacity_cost = _safe_float(row.tokenplan_capacity_cost_cny, 4) if has_plan_price else None
    tokenplan_payg_value = _safe_float(row.tokenplan_payg_value_cny, 4) if has_plan_price else None
    return {
        "calls": calls,
        "success_calls": success_calls,
        "failed_calls": failed_calls,
        "success_rate": _success_rate(success_calls, calls),
        "prompt_tokens": _safe_int(row.prompt_tokens),
        "completion_tokens": _safe_int(row.completion_tokens),
        "total_tokens": _safe_int(row.total_tokens),
        "tokenplan_calls": tokenplan_calls,
        "tokenplan_priced_calls": tokenplan_priced_calls,
        "tokenplan_unpriced_calls": tokenplan_unpriced_calls,
        "tokenplan_tokens": tokenplan_tokens,
        "cost_usd": cost_usd,
        "cost_cny_estimate": round(_cost_cny_from_usd(cost_usd), 4),
        "tokenplan_credits_estimate": tokenplan_credits,
        "tokenplan_capacity_cost_cny": tokenplan_capacity_cost,
        "tokenplan_payg_value_cny": tokenplan_payg_value,
        "cost_savings_vs_payg_cny": round(max(0.0, tokenplan_payg_value - tokenplan_capacity_cost), 4)
        if has_plan_price else None,
        "tokenplan_cost_estimated": has_plan_price,
        "tokenplan_cost_coverage_complete": tokenplan_unpriced_calls == 0,
        "allocated_plan_cost_cny": round(allocated, 2),
        "effective_cny_per_1k_tokens": round(effective, 4) if effective is not None else None,
        "avg_latency_ms": _safe_int(row.avg_latency_ms),
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
    }


def _usage_aggregates(tokenplan_condition):
    success_expr = case((LlmUsageLog.success == 1, 1), else_=0)
    tokenplan_call_expr = case((tokenplan_condition, 1), else_=0)
    _, _, _, cache_supported = _tokenplan_cost_sql_expr(tokenplan_condition)
    priced_condition = and_(
        tokenplan_condition,
        or_(
            LlmUsageLog.tokenplan_cost_cny.isnot(None),
            func.lower(LlmUsageLog.model).in_(list(tokenplan_cny_rate_table().keys())),
        ),
        cache_supported,
    )
    tokenplan_priced_call_expr = case((priced_condition, 1), else_=0)
    tokenplan_unpriced_call_expr = case(
        (and_(tokenplan_condition, ~priced_condition), 1),
        else_=0,
    )
    tokenplan_token_expr = case((tokenplan_condition, LlmUsageLog.total_tokens), else_=0)
    cost_expr = _usage_cost_sql_expr()
    tokenplan_credits_expr, tokenplan_capacity_expr, tokenplan_payg_expr, _ = _tokenplan_cost_sql_expr(
        tokenplan_condition
    )
    return [
        func.count(LlmUsageLog.id).label("calls"),
        func.coalesce(func.sum(success_expr), 0).label("success_calls"),
        func.coalesce(func.sum(LlmUsageLog.prompt_tokens), 0).label("prompt_tokens"),
        func.coalesce(func.sum(LlmUsageLog.completion_tokens), 0).label("completion_tokens"),
        func.coalesce(func.sum(LlmUsageLog.total_tokens), 0).label("total_tokens"),
        func.coalesce(func.sum(tokenplan_call_expr), 0).label("tokenplan_calls"),
        func.coalesce(func.sum(tokenplan_priced_call_expr), 0).label("tokenplan_priced_calls"),
        func.coalesce(func.sum(tokenplan_unpriced_call_expr), 0).label("tokenplan_unpriced_calls"),
        func.coalesce(func.sum(tokenplan_token_expr), 0).label("tokenplan_tokens"),
        func.coalesce(func.sum(cost_expr), 0.0).label("cost_usd"),
        func.coalesce(func.sum(tokenplan_credits_expr), 0.0).label("tokenplan_credits_estimate"),
        func.coalesce(func.sum(tokenplan_capacity_expr), 0.0).label("tokenplan_capacity_cost_cny"),
        func.coalesce(func.sum(tokenplan_payg_expr), 0.0).label("tokenplan_payg_value_cny"),
        func.coalesce(func.avg(LlmUsageLog.latency_ms), 0).label("avg_latency_ms"),
        func.max(LlmUsageLog.created_at).label("last_seen_at"),
    ]


def _usage_log_payload(row: LlmUsageLog, user: User | None = None) -> dict:
    if float(row.cost_usd or 0.0) > 0:
        cost_usd = float(row.cost_usd or 0.0)
        cost_cny = _cost_cny_from_usd(cost_usd)
        cost_estimated = True
        cost_source = "logged_estimate"
    else:
        estimate = estimate_usage_cost(
            row.provider,
            row.model,
            _safe_int(row.prompt_tokens),
            _safe_int(row.completion_tokens),
        )
        cost_usd = estimate.cost_usd
        cost_cny = estimate.cost_cny
        cost_estimated = estimate.estimated
        cost_source = estimate.source
    provider_for_plan = (
        "tokenplan"
        if str(row.provider or "").lower() == "tokenplan"
        or str(row.model or "").lower() in _tokenplan_model_names()
        else row.provider
    )
    # 新行优先读取写入时的套餐估算,保证历史账本不受未来价格表改动影响。
    # 旧行没有这些列值时再按当时记录的模型/token 回退重算。
    persisted_plan_cost = row.tokenplan_cost_cny
    if persisted_plan_cost is not None:
        plan_estimate = None
    else:
        plan_estimate = estimate_tokenplan_cost(
            provider=provider_for_plan,
            model=row.model,
            prompt_tokens=_safe_int(row.prompt_tokens),
            completion_tokens=_safe_int(row.completion_tokens),
            cached_tokens=_safe_int(row.cached_tokens),
            at=row.created_at,
        )
    plan_credits = row.tokenplan_credits_estimate if persisted_plan_cost is not None else (
        plan_estimate.credits if plan_estimate else None
    )
    plan_cost_cny = persisted_plan_cost if persisted_plan_cost is not None else (
        plan_estimate.cost_cny if plan_estimate else None
    )
    plan_payg_cny = row.tokenplan_payg_value_cny if persisted_plan_cost is not None else (
        plan_estimate.payg_value_cny if plan_estimate else None
    )
    plan_estimated = bool(row.tokenplan_cost_estimated) if persisted_plan_cost is not None else bool(plan_estimate)
    plan_source = row.tokenplan_cost_source if persisted_plan_cost is not None else (
        plan_estimate.source if plan_estimate else None
    )
    return {
        "id": row.id,
        "provider": row.provider,
        "model": row.model,
        "caller": row.caller,
        "user_id": row.user_id,
        "run_id": row.run_id,
        "name": getattr(user, "name", None) if user else None,
        "email": getattr(user, "email", None) if user else None,
        "username": getattr(user, "username", None) if user else None,
        "prompt_tokens": _safe_int(row.prompt_tokens),
        "completion_tokens": _safe_int(row.completion_tokens),
        "total_tokens": _safe_int(row.total_tokens),
        "cost_usd": round(cost_usd, 8),
        "cost_cny": round(cost_cny, 6),
        "cost_estimated": cost_estimated,
        "cost_source": cost_source,
        "tokenplan_credits_estimate": round(plan_credits, 4) if plan_credits is not None else None,
        "tokenplan_capacity_cost_cny": round(plan_cost_cny, 6) if plan_cost_cny is not None else None,
        "tokenplan_cost_cny": round(plan_cost_cny, 6) if plan_cost_cny is not None else None,
        "tokenplan_payg_value_cny": round(plan_payg_cny, 6) if plan_payg_cny is not None else None,
        "tokenplan_cost_estimated": plan_estimated,
        "tokenplan_cost_source": plan_source,
        "tokenplan_monthly_fee_cny": row.tokenplan_monthly_fee_cny if persisted_plan_cost is not None else (
            plan_estimate.monthly_fee_cny if plan_estimate else None
        ),
        "tokenplan_monthly_credits": row.tokenplan_monthly_credits if persisted_plan_cost is not None else (
            plan_estimate.monthly_credits if plan_estimate else None
        ),
        "latency_ms": row.latency_ms,
        "success": bool(row.success),
        "error_class": row.error_class,
        "error_type": row.error_type,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "recovery_action": row.recovery_action,
        "recovery_model": row.recovery_model,
        "created_at": row.created_at.isoformat(),
    }


def _percentile(values: list[int], percentile: float) -> Optional[int]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return int(round(ordered[lower] * (1 - weight) + ordered[upper] * weight))


class LLMStatusResponse(BaseModel):
    active_provider: str
    available_providers: list[str]
    current_model: str
    base_url_preview: str
    has_api_key: bool


@router.get("/usage-dashboard", summary="Admin LLM Token/套餐成本总览")
def usage_dashboard(
    days: int = Query(30, ge=1, le=120),
    user_id: Optional[int] = Query(None, ge=1),
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """管理员视角的 LLM 使用账本.

    - 全局/单用户 token、调用数、成功率、延迟。
    - TokenPlan 公开规则估算 Credits，再按 698/100000 折算人民币容量成本。
    - 兼容历史日志: provider=openai 但 model 属于 TokenPlan 注册模型时,仍归入 TokenPlan。
    """
    until = datetime.now(timezone.utc)
    since = until - timedelta(days=days)
    tokenplan_models = _tokenplan_model_names()
    is_tokenplan = _tokenplan_condition(tokenplan_models)
    provider_family = _provider_family_expr(tokenplan_models)
    filters = _usage_filters(since, until, user_id)
    global_filters = _usage_filters(since, until)
    monthly_budget_cny = float(getattr(settings, "tokenplan_monthly_budget_cny", 698.0) or 0.0)
    monthly_credits = int(getattr(settings, "tokenplan_monthly_credits", 100_000) or 0)
    monthly_token_quota = int(getattr(settings, "tokenplan_monthly_token_quota", 0) or 0)
    user_monthly_token_quota = int(
        getattr(settings, "tokenplan_user_monthly_token_quota", 0) or 0
    )
    user_daily_call_quota = int(
        getattr(settings, "tokenplan_user_daily_call_quota", 0) or 0
    )
    user_monthly_credit_quota = float(
        getattr(settings, "tokenplan_user_monthly_credit_quota", 0) or 0
    )
    month_start = _month_start_utc(until)
    day_start = until.replace(hour=0, minute=0, second=0, microsecond=0)
    dispatched_call = or_(
        LlmUsageLog.error_class.is_(None),
        LlmUsageLog.error_class != "local_budget_policy",
    )

    tokenplan_tokens_total = _safe_int(
        db.query(func.coalesce(func.sum(case((is_tokenplan, LlmUsageLog.total_tokens), else_=0)), 0))
        .filter(*global_filters)
        .scalar()
    )
    tokenplan_tokens_month = _safe_int(
        db.query(func.coalesce(func.sum(case((is_tokenplan, LlmUsageLog.total_tokens), else_=0)), 0))
        .filter(*_usage_filters(_month_start_utc(until), until))
        .scalar()
    )

    user_policy_rows = (
        db.query(
            LlmUsageLog.user_id.label("user_id"),
            func.coalesce(
                func.sum(
                    case(
                        (and_(is_tokenplan, dispatched_call), LlmUsageLog.total_tokens),
                        else_=0,
                    )
                ),
                0,
            ).label("monthly_tokens"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(is_tokenplan, dispatched_call),
                            func.coalesce(LlmUsageLog.tokenplan_credits_estimate, 0.0),
                        ),
                        else_=0.0,
                    )
                ),
                0.0,
            ).label("monthly_credits"),
            func.count(
                case(
                    (
                        and_(is_tokenplan, dispatched_call, LlmUsageLog.created_at >= day_start),
                        1,
                    )
                )
            ).label("daily_calls"),
            func.count(
                case(
                    (LlmUsageLog.error_code == "llm_budget_exceeded", 1)
                )
            ).label("rejections_month"),
        )
        .filter(
            LlmUsageLog.created_at >= month_start,
            LlmUsageLog.user_id.isnot(None),
        )
        .group_by(LlmUsageLog.user_id)
        .all()
    )
    user_policy_usage = {row.user_id: row for row in user_policy_rows}
    rejection_reason_rows = (
        db.query(
            LlmUsageLog.user_id.label("user_id"),
            LlmUsageLog.error_type.label("reason"),
            func.count(LlmUsageLog.id).label("count"),
        )
        .filter(
            LlmUsageLog.created_at >= month_start,
            LlmUsageLog.error_code == "llm_budget_exceeded",
            LlmUsageLog.user_id.isnot(None),
        )
        .group_by(LlmUsageLog.user_id, LlmUsageLog.error_type)
        .all()
    )
    rejection_reasons: dict[int, dict[str, int]] = {}
    for row in rejection_reason_rows:
        rejection_reasons.setdefault(int(row.user_id), {})[
            row.reason or "unknown"
        ] = int(row.count or 0)

    overall_row = db.query(*_usage_aggregates(is_tokenplan)).filter(*filters).one()
    overall = _rollup_row(
        overall_row,
        tokenplan_tokens_total=tokenplan_tokens_total,
        monthly_budget_cny=monthly_budget_cny,
    )

    by_user_rows = (
        db.query(
            LlmUsageLog.user_id.label("user_id"),
            User.name.label("name"),
            User.email.label("email"),
            User.username.label("username"),
            User.is_admin.label("is_admin"),
            *_usage_aggregates(is_tokenplan),
        )
        .outerjoin(User, User.id == LlmUsageLog.user_id)
        .filter(*filters)
        .group_by(
            LlmUsageLog.user_id,
            User.name,
            User.email,
            User.username,
            User.is_admin,
        )
        .order_by(func.coalesce(func.sum(LlmUsageLog.total_tokens), 0).desc())
        .limit(100)
        .all()
    )
    by_user = []
    for row in by_user_rows:
        policy_usage = user_policy_usage.get(row.user_id)
        monthly_tokens_used = _safe_int(
            getattr(policy_usage, "monthly_tokens", 0)
        )
        monthly_credits_used = _safe_float(
            getattr(policy_usage, "monthly_credits", 0.0), 4
        )
        daily_calls_used = _safe_int(getattr(policy_usage, "daily_calls", 0))
        rejections_month = _safe_int(
            getattr(policy_usage, "rejections_month", 0)
        )
        is_admin_user = bool(row.is_admin)
        item = _rollup_row(
            row,
            tokenplan_tokens_total=tokenplan_tokens_total,
            monthly_budget_cny=monthly_budget_cny,
        )
        item.update({
            "user_id": row.user_id,
            "name": row.name,
            "email": row.email,
            "username": row.username,
            "is_admin": is_admin_user,
            "share_pct": round(item["tokenplan_tokens"] / tokenplan_tokens_total, 4)
            if tokenplan_tokens_total > 0 else 0.0,
            "quota_policy": {
                "mode": "admin_exempt" if is_admin_user else "enforced",
                "admin_bypass": is_admin_user,
                "monthly_token_limit": user_monthly_token_quota,
                "monthly_tokens_used": monthly_tokens_used,
                "monthly_token_utilization": None
                if is_admin_user
                else _quota_ratio(monthly_tokens_used, user_monthly_token_quota),
                "daily_call_limit": user_daily_call_quota,
                "daily_calls_used": daily_calls_used,
                "daily_call_utilization": None
                if is_admin_user
                else _quota_ratio(daily_calls_used, user_daily_call_quota),
                "monthly_credit_limit": user_monthly_credit_quota,
                "monthly_credits_used": monthly_credits_used,
                "monthly_credit_utilization": None
                if is_admin_user
                else _quota_ratio(monthly_credits_used, user_monthly_credit_quota),
                "rejections_month": rejections_month,
                "rejection_reasons": rejection_reasons.get(row.user_id, {}),
            },
        })
        by_user.append(item)

    by_provider_rows = (
        db.query(
            provider_family.label("provider"),
            *_usage_aggregates(is_tokenplan),
        )
        .filter(*filters)
        .group_by(provider_family)
        .order_by(func.coalesce(func.sum(LlmUsageLog.total_tokens), 0).desc())
        .all()
    )
    by_provider = []
    for row in by_provider_rows:
        item = _rollup_row(
            row,
            tokenplan_tokens_total=tokenplan_tokens_total,
            monthly_budget_cny=monthly_budget_cny,
        )
        item["provider"] = row.provider or "unknown"
        by_provider.append(item)

    by_model_rows = (
        db.query(
            provider_family.label("provider"),
            LlmUsageLog.model.label("model"),
            *_usage_aggregates(is_tokenplan),
        )
        .filter(*filters)
        .group_by(provider_family, LlmUsageLog.model)
        .order_by(func.coalesce(func.sum(LlmUsageLog.total_tokens), 0).desc())
        .limit(100)
        .all()
    )
    by_model = []
    for row in by_model_rows:
        item = _rollup_row(
            row,
            tokenplan_tokens_total=tokenplan_tokens_total,
            monthly_budget_cny=monthly_budget_cny,
        )
        item.update({"provider": row.provider or "unknown", "model": row.model or "unknown"})
        by_model.append(item)

    by_caller_rows = (
        db.query(
            LlmUsageLog.caller.label("caller"),
            func.max(provider_family).label("provider"),
            *_usage_aggregates(is_tokenplan),
        )
        .filter(*filters)
        .group_by(LlmUsageLog.caller)
        .order_by(func.coalesce(func.sum(LlmUsageLog.total_tokens), 0).desc())
        .limit(100)
        .all()
    )
    by_caller = []
    for row in by_caller_rows:
        item = _rollup_row(
            row,
            tokenplan_tokens_total=tokenplan_tokens_total,
            monthly_budget_cny=monthly_budget_cny,
        )
        item.update({"caller": row.caller or "unknown", "provider": row.provider or "unknown"})
        by_caller.append(item)

    day_expr = func.date(LlmUsageLog.created_at)
    by_day_rows = (
        db.query(
            day_expr.label("day"),
            *_usage_aggregates(is_tokenplan),
        )
        .filter(*filters)
        .group_by(day_expr)
        .order_by(day_expr.asc())
        .all()
    )
    by_day = []
    for row in by_day_rows:
        item = _rollup_row(
            row,
            tokenplan_tokens_total=tokenplan_tokens_total,
            monthly_budget_cny=monthly_budget_cny,
        )
        item["day"] = str(row.day)
        by_day.append(item)

    return {
        "window": {
            "days": days,
            "since": since.isoformat(),
            "until": until.isoformat(),
            "user_id": user_id,
        },
        "plan": {
            "name": getattr(settings, "tokenplan_plan_name", "TokenPlan 698/月"),
            "currency": "CNY",
            "monthly_budget_cny": round(monthly_budget_cny, 2),
            "monthly_credits": monthly_credits,
            "capacity_cny_per_credit": round(monthly_budget_cny / monthly_credits, 6)
            if monthly_credits > 0 else None,
            "allocation_basis": "逐次 Credits 估算 × 月费 / 月 Credits；控制台用量明细为最终真值",
            "tokenplan_model_names": tokenplan_models,
            "legacy_provider_note": "历史 openai provider + TokenPlan 模型名的日志会自动归入 TokenPlan",
            "provider_usage_source": "阿里云控制台为套餐余量最终真值；本地账本仅用于 Reva 用量和策略监控",
            "local_user_policy": {
                "admin_bypass": True,
                "monthly_token_limit": user_monthly_token_quota,
                "daily_call_limit": user_daily_call_quota,
                "monthly_credit_limit": user_monthly_credit_quota,
                "rejections_month": sum(
                    int(row.rejections_month or 0) for row in user_policy_rows
                ),
            },
            "quota_guard": _budget_guard(
                monthly_token_quota=monthly_token_quota,
                tokens_used_month=tokenplan_tokens_month,
                now=until,
            ),
        },
        "overall": overall,
        "by_user": by_user,
        "by_provider": by_provider,
        "by_model": by_model,
        "by_caller": by_caller,
        "by_day": by_day,
    }


@router.get("/performance-stats", summary="LLM 性能聚合 (p50/p95 + 成功率 + 成本)")
def performance_stats(
    days: int = 7,
    group_by: str = "model",
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """按 model/provider/caller 聚合 llm_usage_logs, 返回 p50/p95/p99/avg/
    success_rate/total_tokens/cost. 来自 2026-05-13 用户诉求 (积累性能优化).

    group_by: model / provider / caller (默认 model)
    days: 时间窗口 (默认 7 天)
    """

    if group_by not in ("model", "provider", "caller"):
        raise HTTPException(400, detail="group_by 必须是 model / provider / caller")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    tokenplan_models = _tokenplan_model_names()
    label_expr = {
        "model": LlmUsageLog.model,
        "provider": _provider_family_expr(tokenplan_models),
        "caller": LlmUsageLog.caller,
    }[group_by]

    rows = (
        db.query(
            label_expr.label("label"),
            LlmUsageLog.latency_ms,
            LlmUsageLog.success,
            LlmUsageLog.total_tokens,
            _usage_cost_sql_expr().label("cost_usd"),
        )
        .filter(LlmUsageLog.created_at >= cutoff, LlmUsageLog.latency_ms.isnot(None))
        .all()
    )

    buckets: dict[str, dict] = {}
    for row in rows:
        label = row.label or "unknown"
        bucket = buckets.setdefault(
            label,
            {"latencies": [], "success": 0, "total_tokens": 0, "cost_usd": 0.0},
        )
        bucket["latencies"].append(int(row.latency_ms or 0))
        bucket["success"] += 1 if int(row.success or 0) == 1 else 0
        bucket["total_tokens"] += int(row.total_tokens or 0)
        bucket["cost_usd"] += float(row.cost_usd or 0.0)

    stats = []
    for label, bucket in buckets.items():
        latencies = bucket["latencies"]
        n = len(latencies)
        avg_ms = int(round(sum(latencies) / n)) if n else None
        stats.append({
            "label": label,
            "n": n,
            "avg_ms": avg_ms,
            "p50_ms": _percentile(latencies, 0.5),
            "p95_ms": _percentile(latencies, 0.95),
            "p99_ms": _percentile(latencies, 0.99),
            "success_rate": round(bucket["success"] / n, 4) if n else None,
            "total_tokens": bucket["total_tokens"],
            "cost_usd": round(bucket["cost_usd"], 4),
        })
    stats.sort(key=lambda r: r["n"], reverse=True)

    return {
        "window": {"days": days, "since": cutoff.isoformat()},
        "group_by": group_by,
        "stats": stats,
    }


@router.get("/performance-failures", summary="最近 LLM 失败样本")
def performance_failures(
    days: int = 7,
    limit: int = 30,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    from datetime import datetime, timedelta, timezone
    from app.models.llm_usage import LlmUsageLog

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(LlmUsageLog)
        .filter(LlmUsageLog.success == 0, LlmUsageLog.created_at >= cutoff)
        .order_by(LlmUsageLog.created_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    return {
        "window": {"days": days, "since": cutoff.isoformat()},
        "failures": [
            {
                "id": r.id,
                "provider": r.provider,
                "model": r.model,
                "caller": r.caller,
                "user_id": r.user_id,
                "run_id": r.run_id,
                "latency_ms": r.latency_ms,
                "error_class": r.error_class,
                "error_type": r.error_type,
                "error_code": r.error_code,
                "error_message": r.error_message,
                "recovery_action": r.recovery_action,
                "recovery_model": r.recovery_model,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }


@router.get("/recent-calls", summary="最近 LLM 调用明细")
def recent_calls(
    days: int = Query(7, ge=1, le=120),
    limit: int = Query(50, ge=1, le=200),
    user_id: Optional[int] = Query(None, ge=1),
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """按时间倒序返回逐次 LLM 调用账本,用于定位用户、调用方、模型和失败原因."""
    until = datetime.now(timezone.utc)
    since = until - timedelta(days=days)
    rows = (
        db.query(LlmUsageLog, User)
        .outerjoin(User, User.id == LlmUsageLog.user_id)
        .filter(*_usage_filters(since, until, user_id))
        .order_by(LlmUsageLog.created_at.desc(), LlmUsageLog.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "window": {
            "days": days,
            "since": since.isoformat(),
            "until": until.isoformat(),
            "user_id": user_id,
        },
        "calls": [_usage_log_payload(row, user) for row, user in rows],
    }


@router.get("/runs/{run_id}", summary="单次回复 LLM 调用 trace")
def run_detail(
    run_id: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """按 run_id 串起一次 Agent 回复里的所有 LLM 调用."""
    rows = (
        db.query(LlmUsageLog, User)
        .outerjoin(User, User.id == LlmUsageLog.user_id)
        .filter(LlmUsageLog.run_id == run_id)
        .order_by(LlmUsageLog.created_at.asc(), LlmUsageLog.id.asc())
        .all()
    )
    if not rows:
        raise HTTPException(404, "run_id 不存在")
    calls = [_usage_log_payload(row, user) for row, user in rows]
    return {
        "run_id": run_id,
        "summary": {
            "calls": len(calls),
            "failed_calls": sum(1 for call in calls if not call["success"]),
            "prompt_tokens": sum(call["prompt_tokens"] for call in calls),
            "completion_tokens": sum(call["completion_tokens"] for call in calls),
            "total_tokens": sum(call["total_tokens"] for call in calls),
            "cost_usd": round(sum(float(call["cost_usd"] or 0.0) for call in calls), 8),
            "cost_cny": round(sum(float(call.get("cost_cny") or 0.0) for call in calls), 6),
            "cost_estimated": any(bool(call.get("cost_estimated")) for call in calls),
            "latency_ms": sum(int(call["latency_ms"] or 0) for call in calls),
        },
        "calls": calls,
    }


@router.get("/status", response_model=LLMStatusResponse)
def llm_status(
    admin: User = Depends(get_admin_user),
):
    """看现在用的是哪家 LLM."""
    from app.services.llm.factory import get_llm_provider, _provider_instance

    provider = get_llm_provider()
    provider_type = settings.llm_provider

    # 模型 + base_url 按 provider 取
    if provider_type == "openai":
        model = settings.openai_model
        base = settings.openai_base_url or "https://api.openai.com/v1"
        has_key = bool(settings.openai_api_key)
    elif provider_type == "tokenplan":
        model = settings.tokenplan_model
        base = settings.tokenplan_base_url
        has_key = bool(settings.tokenplan_api_key)
    elif provider_type == "ollama":
        model = settings.ollama_model
        base = settings.ollama_base_url
        has_key = True  # 本地无需 key
    else:
        model = "unknown"
        base = ""
        has_key = False

    available = ["openai", "ollama"]
    if settings.tokenplan_api_key:
        available.append("tokenplan")

    return LLMStatusResponse(
        active_provider=provider_type,
        available_providers=available,
        current_model=model,
        base_url_preview=base[:80] if base else "",
        has_api_key=has_key,
    )


class LLMSwitchRequest(BaseModel):
    provider: str  # openai | ollama | tokenplan


@router.post("/switch")
def llm_switch(
    req: LLMSwitchRequest,
    admin: User = Depends(get_admin_user),
):
    """
    临时切换 LLM provider (改进程内 settings + 重置 factory 单例).
    重启进程后会回退到 .env 的 LLM_PROVIDER.

    生产场景永久切换请改 .env + 重启服务.
    """
    valid = {"openai", "ollama", "tokenplan"}
    if req.provider not in valid:
        raise HTTPException(400, f"不支持的 provider: {req.provider}, 可选 {sorted(valid)}")

    # tokenplan 必须有 key
    if req.provider == "tokenplan" and not settings.tokenplan_api_key:
        raise HTTPException(400, "tokenplan 切换前需先配置 TOKENPLAN_API_KEY")

    old = settings.llm_provider
    settings.llm_provider = req.provider

    # 重置 factory 单例, 下次 get_llm_provider() 重新创建
    from app.services.llm.factory import reset_llm_provider
    reset_llm_provider()

    logger.warning(
        f"[admin.llm.switch] user={admin.id} {old} → {req.provider} (内存级, 重启失效)"
    )
    return {
        "ok": True,
        "from": old,
        "to": req.provider,
        "note": "进程内切换. 永久切换请改 .env 并重启服务",
    }


class LLMPingResponse(BaseModel):
    ok: bool
    provider: str
    model: str
    latency_ms: int
    sample_reply: str
    error: Optional[str] = None


@router.post("/ping", response_model=LLMPingResponse)
async def llm_ping(
    admin: User = Depends(get_admin_user),
):
    """
    测当前 provider 延迟 + 中文回复. 给管理员 A/B 用.
    """
    from app.services.llm.factory import get_llm_provider

    provider = get_llm_provider()
    provider_type = settings.llm_provider
    model = ""
    if provider_type == "openai":
        model = settings.openai_model
    elif provider_type == "tokenplan":
        model = settings.tokenplan_model
    elif provider_type == "ollama":
        model = settings.ollama_model

    t0 = time.time()
    try:
        raw = await provider.chat(
            messages=[
                {"role": "system", "content": "你是健康助理. 用 ≤30 字回答."},
                {"role": "user", "content": "我今天 HRV 比平时低 12, 怎么办?"},
            ],
            max_tokens=120,
            temperature=0.3,
        )
        if isinstance(raw, dict):
            raw = raw.get("content", "") or ""
        latency = int((time.time() - t0) * 1000)
        return LLMPingResponse(
            ok=True,
            provider=provider_type,
            model=model,
            latency_ms=latency,
            sample_reply=(raw or "")[:200],
        )
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        logger.warning(f"[admin.llm.ping] failed: {e}")
        return LLMPingResponse(
            ok=False,
            provider=provider_type,
            model=model,
            latency_ms=latency,
            sample_reply="",
            error=str(e)[:200],
        )


# ───── 多模型管理: list / select / latency snapshot ─────


class ModelInfo(BaseModel):
    id: str
    label: str
    provider: str
    model: str
    speed_tier: str
    note: str = ""
    capabilities: list[str] = Field(default_factory=list)
    chat_selectable: bool = True
    supports_streaming: bool = True  # False = 整段生成 (无 SSE)
    available: bool       # env 是否齐全
    is_active: bool       # 当前选中的


class ModelListResponse(BaseModel):
    active_id: Optional[str]   # None = 走 settings 默认
    fallback_provider: str     # active 缺失时落到哪个 provider
    fallback_model: str
    models: list[ModelInfo]


@router.get("/models", response_model=ModelListResponse)
def list_available_models(admin: User = Depends(get_admin_user)):
    """列出所有注册的模型 + 可用性 + 当前选中."""
    from app.services.llm.model_registry import MODELS, get_active_model_id, list_models
    available_ids = {m.id for m in list_models(only_available=True, include_non_chat=True)}
    active = get_active_model_id()

    out = []
    for m in MODELS:
        out.append(ModelInfo(
            id=m.id,
            label=m.label,
            provider=m.provider,
            model=m.model,
            speed_tier=m.speed_tier,
            note=m.note,
            capabilities=list(m.capabilities),
            chat_selectable=m.chat_selectable,
            supports_streaming=m.supports_streaming,
            available=m.id in available_ids,
            is_active=(active == m.id),
        ))

    # fallback
    fp = settings.llm_provider
    if fp == "openai":
        fm = settings.openai_model
    elif fp == "tokenplan":
        fm = settings.tokenplan_model
    else:
        fm = "?"

    return ModelListResponse(
        active_id=active,
        fallback_provider=fp,
        fallback_model=fm,
        models=out,
    )


class SelectModelRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: Optional[str]   # None / 空 = 恢复默认


@router.post("/select-model")
def select_model(req: SelectModelRequest, admin: User = Depends(get_admin_user)):
    """切换活跃模型. 进程内, 重启失效."""
    from app.services.llm.model_registry import get_model, set_active_model_id
    from app.services.llm.factory import reset_llm_provider

    if not req.model_id:
        set_active_model_id(None)
        reset_llm_provider()
        logger.warning(f"[admin.llm.select-model] user={admin.id} 恢复默认")
        return {"ok": True, "active_id": None, "note": "恢复默认 provider"}

    entry = get_model(req.model_id)
    if not entry:
        raise HTTPException(404, f"未注册的 model: {req.model_id}")
    if not entry.chat_selectable:
        raise HTTPException(400, f"模型 {req.model_id} 是非聊天模型,不能设为全局 chat provider")

    # 验 env 齐全
    from app.services.llm.model_registry import _env_present
    missing = [e for e in entry.requires_env if not _env_present(e, settings)]
    if missing:
        raise HTTPException(400, f"模型 {req.model_id} 需要的 env 缺失: {missing}")

    set_active_model_id(req.model_id)
    reset_llm_provider()
    logger.warning(f"[admin.llm.select-model] user={admin.id} 选中 {req.model_id}")
    return {"ok": True, "active_id": req.model_id, "label": entry.label}


class BenchmarkResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    label: str
    runs: int
    latency_ms: list[int]
    avg_ms: float
    ok: bool
    sample_reply: str


@router.post("/benchmark/{model_id}", response_model=BenchmarkResponse)
async def benchmark_model(
    model_id: str,
    runs: int = 3,
    admin: User = Depends(get_admin_user),
):
    """跑指定模型 N 次, 测延迟. 用于对比. 不切换活跃 model."""
    from app.services.llm.model_registry import get_model
    from app.services.llm.factory import _create_from_entry
    entry = get_model(model_id)
    if not entry:
        raise HTTPException(404, f"未注册: {model_id}")

    try:
        provider = _create_from_entry(entry)
    except Exception as e:
        raise HTTPException(400, f"创建 provider 失败: {e}")

    latencies = []
    sample = ""
    ok = True
    for _ in range(max(1, min(runs, 5))):
        t0 = time.time()
        try:
            reply = await provider.chat(
                messages=[{"role": "user", "content": "用一句话回答: 现在是早晨还是下午"}],
                max_tokens=40,
            )
            text = reply if isinstance(reply, str) else reply.get("content", "")
            sample = text[:40]
        except Exception as e:
            sample = f"ERR: {type(e).__name__}: {str(e)[:60]}"
            ok = False
        latencies.append(int((time.time() - t0) * 1000))

    avg = sum(latencies) / len(latencies)
    return BenchmarkResponse(
        model_id=model_id, label=entry.label, runs=len(latencies),
        latency_ms=latencies, avg_ms=round(avg, 1), ok=ok, sample_reply=sample,
    )
