"""TokenPlan Credits 与人民币容量成本估算。

阿里云响应目前只返回 Token，不返回逐次 Credits。这里用公开的人民币按量
单价估算 Credits，再按套餐 `月费 / 月 Credits` 转为用户可读的人民币金额。
所有结果均为估算；控制台用量明细仍是真值。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class TokenPlanCostEstimate:
    credits: float
    cost_cny: float
    payg_value_cny: float
    monthly_fee_cny: float
    monthly_credits: int
    estimated: bool
    source: str


# 华北 2（北京）公开原价：人民币 / 1M tokens。TokenPlan 官方示例显示
# Credits 与原价近似按 100 Credits / ¥1 换算，活动再单独作用于 Credits。
# value: 按单次 prompt token 上限升序排列的 (上限, 输入价, 输出价)。
_CREDIT_BASIS_CNY_RATES: Dict[str, Tuple[Tuple[int, float, float], ...]] = {
    "qwen3.7-max": ((1_000_000, 12.0, 36.0),),
    "qwen3.7-plus": ((256_000, 2.0, 8.0), (1_000_000, 6.0, 24.0)),
    "qwen3.6-plus": ((256_000, 2.0, 12.0), (1_000_000, 8.0, 48.0)),
    "qwen3.6-flash": ((256_000, 1.2, 7.2), (1_000_000, 4.8, 28.8)),
    "deepseek-v4-pro": ((1_000_000, 12.0, 24.0),),
    "deepseek-v4-flash": ((1_000_000, 1.0, 2.0),),
    "deepseek-v3.2": ((1_000_000, 2.0, 3.0),),
    "kimi-k2.7-code": ((1_000_000, 6.5, 27.0),),
    "kimi-k2.6": ((1_000_000, 6.5, 27.0),),
    "kimi-k2.5": ((1_000_000, 4.0, 21.0),),
    "glm-5.2": ((1_000_000, 8.0, 28.0),),
    "glm-5.1": ((32_000, 6.0, 24.0), (200_000, 8.0, 28.0)),
    "glm-5": ((32_000, 4.0, 18.0), (198_000, 6.0, 22.0)),
    "minimax-m2.5": ((1_000_000, 2.1, 8.4),),
}

# 当前公开按量活动价，仅用于“如果按量付费”的人民币对照。TokenPlan Credits
# 的活动规则与按量活动规则彼此独立，不能把折扣叠乘。
_PAYG_CNY_RATES: Dict[str, Tuple[Tuple[int, float, float], ...]] = {
    **_CREDIT_BASIS_CNY_RATES,
    "qwen3.7-plus": ((256_000, 1.6, 6.4), (1_000_000, 4.8, 19.2)),
}

QWEN37_MAX_PROMO_END_UTC = datetime(2026, 7, 22, 15, 59, 59, tzinfo=timezone.utc)


def tokenplan_public_cny_rate_table() -> Dict[str, Tuple[Tuple[int, float, float], ...]]:
    """返回 Credits 估算使用的公开原价表副本。"""
    return dict(_CREDIT_BASIS_CNY_RATES)


def tokenplan_cny_rate_table() -> Dict[str, Tuple[Tuple[int, float, float], ...]]:
    """返回含环境覆盖的 Credits 估算价格表。"""
    table = tokenplan_public_cny_rate_table()
    for model, (input_rate, output_rate) in _pricing_overrides().items():
        table[model] = ((2_147_483_647, input_rate, output_rate),)
    return table


def tokenplan_payg_cny_rate_table() -> Dict[str, Tuple[Tuple[int, float, float], ...]]:
    """返回含环境覆盖的当前按量活动价表。"""
    table = dict(_PAYG_CNY_RATES)
    for model, (input_rate, output_rate) in _pricing_overrides().items():
        table[model] = ((2_147_483_647, input_rate, output_rate),)
    return table


def _normalize(value: str) -> str:
    return str(value or "").strip().lower()


def _pricing_overrides() -> Dict[str, Tuple[float, float]]:
    try:
        from app.config import settings

        raw = getattr(settings, "tokenplan_model_pricing_cny_json", None)
    except Exception:
        raw = None
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    result: Dict[str, Tuple[float, float]] = {}
    for key, value in payload.items():
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            continue
        try:
            input_rate, output_rate = float(value[0]), float(value[1])
        except (TypeError, ValueError):
            continue
        if input_rate >= 0 and output_rate >= 0:
            result[_normalize(key)] = (input_rate, output_rate)
    return result


def _rates_for(
    table: Dict[str, Tuple[Tuple[int, float, float], ...]],
    model: str,
    prompt_tokens: int,
    source_prefix: str,
) -> Optional[Tuple[float, float, str]]:
    model_key = _normalize(model)
    override = _pricing_overrides().get(model_key)
    if override is not None:
        return override[0], override[1], f"env_cny_rate:{model_key}"

    tiers = table.get(model_key)
    if not tiers:
        return None
    count = max(0, int(prompt_tokens or 0))
    for limit, input_rate, output_rate in tiers:
        if count <= limit:
            return input_rate, output_rate, f"{source_prefix}:{model_key}:le_{limit}"
    limit, input_rate, output_rate = tiers[-1]
    return input_rate, output_rate, f"{source_prefix}:{model_key}:gt_{limit}"


def tokenplan_cny_rates(model: str, prompt_tokens: int) -> Optional[Tuple[float, float, str]]:
    """返回 Credits 估算使用的输入/输出原价及来源。"""
    return _rates_for(
        tokenplan_cny_rate_table(),
        model,
        prompt_tokens,
        "public_credit_basis_cny_rate",
    )


def tokenplan_payg_cny_rates(model: str, prompt_tokens: int) -> Optional[Tuple[float, float, str]]:
    """返回当前按量活动价及来源。"""
    return _rates_for(
        tokenplan_payg_cny_rate_table(),
        model,
        prompt_tokens,
        "public_payg_cny_rate",
    )


def _credit_multiplier(model: str, at: Optional[datetime]) -> Tuple[float, str]:
    """TokenPlan 明示活动折扣；到期后自动恢复，避免永久硬编码促销价。"""
    model_key = _normalize(model)
    instant = at or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    # 官方活动截止 2026-07-22 23:59 (UTC+8)。
    if model_key == "qwen3.7-max" and instant <= QWEN37_MAX_PROMO_END_UTC:
        return 0.5, "promo_credits_half_until_2026-07-22"
    return 1.0, "standard"


def _payg_multiplier(model: str, at: Optional[datetime]) -> Tuple[float, str]:
    """当前公开按量活动折扣；已知截止日期的活动到期后自动恢复。"""
    model_key = _normalize(model)
    instant = at or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    if model_key == "qwen3.7-max" and instant <= QWEN37_MAX_PROMO_END_UTC:
        return 0.5, "promo_payg_half_until_2026-07-22"
    return 1.0, "standard"


def tokenplan_implicit_cache_multiplier(
    model: str,
    *,
    cached_tokens: int,
    at: Optional[datetime] = None,
) -> Optional[float]:
    """返回 TokenPlan 隐式缓存命中的输入价格系数。

    当前套餐文档只明确 qwen3.7-max 在限时活动期间支持隐式缓存。调用方
    没有创建显式 cache_control，因此其他模型出现 cached_tokens 时不能可靠
    判断账单口径，返回 None 让上层显示“无法估算”。
    """
    if cached_tokens <= 0:
        return 1.0
    instant = at or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    if _normalize(model) == "qwen3.7-max" and instant <= QWEN37_MAX_PROMO_END_UTC:
        return 0.2
    return None


def estimate_tokenplan_cost(
    *,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: Optional[int] = None,
    at: Optional[datetime] = None,
) -> Optional[TokenPlanCostEstimate]:
    """估算单次 TokenPlan Credits 和人民币容量成本。

    `prompt_tokens` 按 OpenAI/DashScope 语义包含缓存命中 Token。系统未创建
    显式缓存，故只按 TokenPlan 已明确支持的隐式缓存口径计算。非 TokenPlan
    provider、无公开价格或缓存计费口径不明确时返回 None。
    """
    if _normalize(provider) != "tokenplan":
        return None
    credit_rates = tokenplan_cny_rates(model, prompt_tokens)
    payg_rates = tokenplan_payg_cny_rates(model, prompt_tokens)
    if credit_rates is None or payg_rates is None:
        return None

    try:
        from app.config import settings

        monthly_fee = float(getattr(settings, "tokenplan_monthly_budget_cny", 698.0) or 0.0)
        monthly_credits = int(getattr(settings, "tokenplan_monthly_credits", 100_000) or 0)
        credits_per_cny = float(getattr(settings, "tokenplan_credits_per_cny", 100.0) or 0.0)
    except Exception:
        monthly_fee, monthly_credits, credits_per_cny = 698.0, 100_000, 100.0
    if monthly_fee <= 0 or monthly_credits <= 0 or credits_per_cny <= 0:
        return None

    credit_input_rate, credit_output_rate, credit_source = credit_rates
    payg_input_rate, payg_output_rate, payg_source = payg_rates
    prompt = max(0, int(prompt_tokens or 0))
    completion = max(0, int(completion_tokens or 0))
    cached = min(prompt, max(0, int(cached_tokens or 0)))
    uncached = prompt - cached
    cache_multiplier = tokenplan_implicit_cache_multiplier(
        model,
        cached_tokens=cached,
        at=at,
    )
    if cache_multiplier is None:
        return None
    credit_basis_cny = (
        uncached * credit_input_rate
        + cached * credit_input_rate * cache_multiplier
        + completion * credit_output_rate
    ) / 1_000_000
    payg_base_cny = (
        uncached * payg_input_rate
        + cached * payg_input_rate * cache_multiplier
        + completion * payg_output_rate
    ) / 1_000_000
    payg_multiplier, payg_multiplier_source = _payg_multiplier(model, at)
    payg_value_cny = payg_base_cny * payg_multiplier
    multiplier, multiplier_source = _credit_multiplier(model, at)
    credits = credit_basis_cny * credits_per_cny * multiplier
    cost_cny = credits * monthly_fee / monthly_credits
    return TokenPlanCostEstimate(
        credits=credits,
        cost_cny=cost_cny,
        payg_value_cny=payg_value_cny,
        monthly_fee_cny=monthly_fee,
        monthly_credits=monthly_credits,
        estimated=True,
        source=(
            f"{credit_source}:{payg_source}:implicit_cache_{cache_multiplier}:"
            f"{multiplier_source}:{payg_multiplier_source}"
        ),
    )
