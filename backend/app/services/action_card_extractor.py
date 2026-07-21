"""
ActionCard trust-loop field extractor.

`POST /action-cards/from-message` 让用户从 AI 对话固化卡片, 但用户/前端不会手填
metric_key / target_value / verification_days, 这些字段空着 → outcome_grader
查询条件 (check_back_date IS NOT NULL) 过滤掉 → 卡片永远进不了信任循环.

本模块用 best-effort LLM 抽取, 失败不阻断 (只是该卡退化成"不进信任循环"的状态).

设计要点:
- 同步函数, 失败返回 None 各字段, 调用方决定要不要落到 ActionCard.
- 严格白名单 metric_key (复用 outcome_grader 已支持的 keys), LLM 输出非白名单的丢弃.
- verification_days 默认 7, 限制 1-30 (避免 LLM 给 365 这种离谱值).
- LLM 失败 (网络/JSON) → 返回全 None, 不抛异常.

测试覆盖见 tests/test_action_card_extractor.py.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# 与 backend/app/api/action_card.py ALLOWED_METRIC_KEYS 保持一致.
# 复制而非 import 因为本模块要保持轻量, 不引入 API 层依赖.
_ALLOWED_METRIC_KEYS = {
    "sleep_score", "hrv", "rhr", "weight", "bp", "spo2_odi", "custom",
    "alt", "ast", "ggt", "alp", "creatinine", "uric_acid", "urea",
    "hba1c", "tsh", "ft3", "ft4", "vitamin_d", "b12", "ferritin",
    "crp", "esr", "wbc", "rbc", "hgb", "plt", "lp_a", "apo_b",
    "ldl", "hdl", "tc", "tg", "fasting_glucose", "blood_glucose",
    "systolic_bp", "diastolic_bp", "bmi", "body_fat",
    "phenotypic_age", "biological_age", "vo2max", "fitness_age",
}


@dataclass
class ExtractedFields:
    """LLM 抽取结果. 任意字段可为 None — 调用方根据是否有 metric_key 决定走信任循环."""
    metric_key: Optional[str] = None
    baseline_value: Optional[str] = None
    target_value: Optional[str] = None
    verification_days: Optional[int] = None


_SYSTEM_PROMPT = """\
你是健康卡片字段抽取器. 输入是 AI 给用户的健康建议 (markdown), 输出 JSON.

抽取以下字段 (能抽到才填, 抽不到留 null):
- metric_key: 该建议要追踪验证的指标 key, 必须是白名单之一:
  sleep_score / hrv / rhr / weight / spo2_odi / hba1c / ldl / hdl / tc / tg /
  fasting_glucose / blood_glucose / systolic_bp / diastolic_bp / bmi / body_fat /
  alt / ast / ggt / alp / creatinine / uric_acid / urea / vitamin_d / b12 /
  ferritin / crp / esr / wbc / rbc / hgb / plt / lp_a / apo_b / tsh / ft3 / ft4 /
  phenotypic_age / biological_age (抗衰: 生物年龄/身体年龄/表型年龄) /
  custom (作为兜底, 但优先选其它具体 key)
  如果建议是泛泛的"多喝水/早睡" 没有可验证指标 → null.
- baseline_value: 当前起点值 (如 "82kg", "48", "5.7%"), 抽不到 → null.
- target_value: 目标/预测值 (如 ">90", "<35", "70-72kg", "回归基线 ±10%"), 抽不到 → null.
- verification_days: 多少天后回看验证 (整数, 1-30). 默认 7. 文本里说"一周后"=7, "两周"=14, "一个月"=30.

只输出 JSON, 不要 markdown 包裹, 不要解释.
"""

_USER_TEMPLATE = """\
卡片标题: {title}

卡片内容:
{content}

输出 JSON, 不要其它文字."""


def _validate_and_clean(raw: dict) -> ExtractedFields:
    """从 LLM 原始输出做白名单校验 + 类型转换. 不合规字段一律置 None."""
    out = ExtractedFields()

    metric = raw.get("metric_key")
    if isinstance(metric, str) and metric.strip() in _ALLOWED_METRIC_KEYS:
        out.metric_key = metric.strip()

    baseline = raw.get("baseline_value")
    if isinstance(baseline, (str, int, float)) and str(baseline).strip():
        s = str(baseline).strip()
        if len(s) <= 100:  # 与 DB column 长度对齐
            out.baseline_value = s

    target = raw.get("target_value")
    if isinstance(target, (str, int, float)) and str(target).strip():
        s = str(target).strip()
        if len(s) <= 100:
            out.target_value = s

    vdays = raw.get("verification_days")
    try:
        if vdays is not None:
            n = int(vdays)
            if 1 <= n <= 30:
                out.verification_days = n
    except (TypeError, ValueError):
        pass

    return out


def _strip_codeblock(text: str) -> str:
    """LLM 习惯包 markdown 代码块, 去掉."""
    s = text.strip()
    if s.startswith("```"):
        # 去掉首行 ```json 或 ```
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    return s


def extract_from_content(
    content: str,
    title: str = "",
    *,
    user_id: Optional[int] = None,
) -> ExtractedFields:
    """
    Best-effort 抽取信任循环字段. 任何失败都返回全 None 的 ExtractedFields, 不抛.

    调用方典型用法:
        ext = extract_from_content(content, title)
        if ext.metric_key:
            check_back = now + timedelta(days=ext.verification_days or 7)
            card = ActionCard(..., metric_key=ext.metric_key,
                              target_value=ext.target_value, check_back_date=check_back)
        else:
            # 没抽到指标 → 退化为不进信任循环的普通卡 (与原有行为一致)
            card = ActionCard(...)
    """
    if not content or not content.strip():
        return ExtractedFields()

    try:
        from app.config import settings
        from app.services.llm.factory import create_provider_for_extraction
        from app.services.llm.usage_tracker import set_caller
        from app.utils.async_helpers import run_async

        set_caller("action_card.extract_fields", user_id=user_id)
        # Batch-1 token-perf: 纯抽取, 降档 flash; 创建失败 fail-soft 回退默认 provider。
        provider = create_provider_for_extraction(settings.action_card_extract_model_id)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _USER_TEMPLATE.format(
                title=(title or "")[:200],
                content=content[:2000],  # 限制 token, 卡片正文一般不长
            )},
        ]
        result = run_async(provider.chat(
            messages=messages,
            temperature=0.0,  # 抽取任务确定性优先
            max_tokens=200,
        ))

        cleaned = _strip_codeblock(result)
        try:
            raw = json.loads(cleaned)
        except (json.JSONDecodeError, TypeError) as e:
            logger.info(
                "[action_card.extract] LLM 输出不是 JSON, 跳过 error_type=%s response_len=%s",
                type(e).__name__,
                len(cleaned),
            )
            return ExtractedFields()

        if not isinstance(raw, dict):
            return ExtractedFields()

        return _validate_and_clean(raw)
    except Exception as e:  # noqa: BLE001 - 旁路, 任何失败都吞
        logger.info(
            "[action_card.extract] LLM 抽取失败 (旁路, 卡片仍创建) error_type=%s",
            type(e).__name__,
        )
        return ExtractedFields()
