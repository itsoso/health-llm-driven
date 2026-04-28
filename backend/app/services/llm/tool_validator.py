"""
LLM Tool Call 守门 — 所有 health_record / record_type=X 的参数过这一层.

为什么需要这层:
  GPT-4o-mini 等 LLM 在 tool_call 阶段经常给出:
    - 离谱的日期 (2023-10-09 当今天)
    - 越界数值 (体重 720kg, BP 32/200)
    - 不存在的 medication_id (用户根本没添加过)
    - 不属于该用户的 profile_id (越权)

  setdefault('record_date', today) 这种"补全式"防御不够,
  必须主动覆盖 LLM 给的"看起来像但其实错"的值.

设计原则:
  1. fail-soft: 守门触发只 log + coerce, 不报错
     (LLM 听到"参数错"会重试, 反而更慢, 不如直接修正)
  2. log warning + Sentry breadcrumb: 让所有触发都可观测
     线上看到大量某类 coercion → 说明 LLM prompt 该改
  3. 白名单, 不黑名单: 只把"已知合理范围"放进来,
     未知字段一律放行 (兼容 schema 演进)

入口: validate_health_record(rtype, data, db, user_id) -> dict
返回: 修正过的 data (不抛异常)
"""
from __future__ import annotations

import logging
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, Optional

# 北京时区 (UTC+8) — 用户活动以中国本地日期为准
BEIJING_TZ = timezone(timedelta(hours=8))

logger = logging.getLogger(__name__)


# ─────────────────────── 数值范围白名单 ──────────────────────
# (low, high, default_if_missing)
# default_if_missing=None 表示该字段必填, 缺了不补
NUMERIC_RANGES: Dict[str, Dict[str, tuple]] = {
    "weight": {
        "weight": (20.0, 300.0, None),         # kg
    },
    "blood_pressure": {
        "systolic": (60, 250, None),           # mmHg
        "diastolic": (30, 150, None),
    },
    "water": {
        "amount": (10, 5000, 250),             # ml
    },
    "diet": {
        "calories": (0, 10000, None),          # kcal — None 不强制
        "protein": (0, 500, None),
        "carbs": (0, 2000, None),
        "fat": (0, 500, None),
        "alcohol_units": (0, 50, None),
    },
    "exercise": {
        "duration": (1, 720, None),            # 分钟
        "distance": (0.0, 200.0, None),        # km
        "calories_burned": (0, 5000, None),
    },
    "rhinitis": {
        "sneezing": (0, 200, 0),
        "congestion": (0, 10, 0),
        "runny_nose": (0, 200, 0),
    },
    "mood": {
        "score": (1, 10, None),
    },
    "illness": {
        "severity": (1, 10, None),
    },
    "symptom": {
        "overall_severity": (0, 10, None),
    },
}


def _validate_numeric(rtype: str, data: Dict[str, Any], warnings: list) -> None:
    """对 NUMERIC_RANGES[rtype] 中所有字段做范围裁剪."""
    spec = NUMERIC_RANGES.get(rtype, {})
    for field, (low, high, default) in spec.items():
        v = data.get(field)
        if v is None:
            if default is not None:
                data[field] = default
            continue
        try:
            num = float(v)
        except (TypeError, ValueError):
            msg = f"[tool_validator] {rtype}.{field}={v!r} 非数值, 移除"
            warnings.append(msg)
            logger.warning(msg)
            data.pop(field, None)
            continue
        if num < low or num > high:
            # 极端值: 移除 (让 API 层报"必填"比写入垃圾值好)
            msg = (f"[tool_validator] {rtype}.{field}={num} 超界 [{low},{high}], "
                   f"移除 — LLM 可能幻觉")
            warnings.append(msg)
            logger.warning(msg)
            data.pop(field, None)


def _validate_date(
    rtype: str,
    data: Dict[str, Any],
    warnings: list,
    today: date,
    *,
    field: str = "record_date",
    past_tolerance_days: int = 7,
    future_tolerance_days: int = 1,
) -> None:
    """日期合理性: 离今天太远 → 覆盖为今天."""
    if field not in data:
        return
    raw = data[field]
    try:
        # 兼容 'YYYY-MM-DD' / ISO datetime / date 对象
        if isinstance(raw, date):
            d = raw
        elif isinstance(raw, datetime):
            d = raw.date()
        else:
            s = str(raw).strip()
            # 允许 'YYYY-MM-DDTHH:MM:SS+...' 截首段
            d = datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError) as e:
        msg = f"[tool_validator] {rtype}.{field}={raw!r} 非合法日期, 改为今天 ({e})"
        warnings.append(msg)
        logger.warning(msg)
        data[field] = today.strftime("%Y-%m-%d")
        return

    delta = (today - d).days
    if delta > past_tolerance_days or delta < -future_tolerance_days:
        msg = (f"[tool_validator] {rtype}.{field}={d} 偏离今天 {delta} 天 "
               f"(容忍 -{future_tolerance_days}/+{past_tolerance_days}), "
               f"覆盖为今天 — LLM 日期幻觉")
        warnings.append(msg)
        logger.warning(msg)
        data[field] = today.strftime("%Y-%m-%d")


def _validate_reference_id(
    rtype: str,
    data: Dict[str, Any],
    warnings: list,
    db,
    user_id: int,
) -> None:
    """医疗引用 ID 必须属于该用户 (防越权)."""
    if db is None or user_id is None:
        return  # 测试模式, 不校验

    # 校验 medication_id 是否属于该用户
    if rtype == "medication" and "medication_id" in data:
        try:
            from app.models.medication import Medication
            mid = data["medication_id"]
            exists = db.query(Medication.id).filter(
                Medication.id == mid,
                Medication.user_id == user_id,
            ).first()
            if not exists:
                msg = (f"[tool_validator] medication_id={mid} 不存在或不属于 user={user_id}, "
                       f"移除 — 防越权 / LLM 编造 ID")
                warnings.append(msg)
                logger.warning(msg)
                data.pop("medication_id", None)
        except Exception as e:
            logger.warning(f"[tool_validator] medication_id 校验失败 (跳过): {e}")

    # 校验 profile_id (disease profile)
    if rtype == "symptom" and "profile_id" in data:
        try:
            from app.models.disease_tracking import DiseaseProfile
            pid = data["profile_id"]
            exists = db.query(DiseaseProfile.id).filter(
                DiseaseProfile.id == pid,
                DiseaseProfile.user_id == user_id,
            ).first()
            if not exists:
                msg = (f"[tool_validator] profile_id={pid} 不存在或不属于 user={user_id}, 移除")
                warnings.append(msg)
                logger.warning(msg)
                data.pop("profile_id", None)
        except Exception as e:
            logger.warning(f"[tool_validator] profile_id 校验失败 (跳过): {e}")


def _validate_required(
    rtype: str,
    data: Dict[str, Any],
    warnings: list,
) -> Optional[str]:
    """各 record_type 的必填字段. 返回错误文本 (LLM 看到会重试) 或 None."""
    required: Dict[str, list] = {
        "diet": ["food_items"],
        "weight": ["weight"],
        "blood_pressure": ["systolic", "diastolic"],
        "exercise": ["exercise_type"],
        "medication": [],  # medication_id 或 medication_name 二选一, 由 API 层判
        "illness": ["illness_name"],
    }
    needs = required.get(rtype, [])
    missing = [f for f in needs if not data.get(f)]
    if missing:
        return (f"Error: {rtype} 记录必须包含 {missing}. "
                f"请补充后重新调用 health_record.")
    return None


def validate_health_record(
    rtype: str,
    data: Dict[str, Any],
    db=None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    主入口. 修改 data 原对象 (in-place), 也返回它便于链式.

    返回: {
        'data': 修正后的 data,
        'warnings': List[str] — 触发了哪些守门规则,
        'error': Optional[str] — 必填缺失等不可恢复错误, agent_executor 应返回给 LLM
    }
    """
    warnings: list = []
    today = datetime.now(BEIJING_TZ).date()

    # 1. 日期守门 (record_date 通用)
    _validate_date(rtype, data, warnings, today)

    # 2. 数值范围
    _validate_numeric(rtype, data, warnings)

    # 3. 引用 ID 存在性 + 越权
    _validate_reference_id(rtype, data, warnings, db, user_id)

    # 4. 必填检查 (返回 error)
    error = _validate_required(rtype, data, warnings)

    if warnings:
        logger.info(f"[tool_validator] {rtype} 守门触发 {len(warnings)} 条")
    return {
        "data": data,
        "warnings": warnings,
        "error": error,
    }
