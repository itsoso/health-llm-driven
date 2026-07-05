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

from app.services.health_query_dimensions import normalize_health_query_args
from app.services.intake_intent_classifier import classify_intake_intent

# 北京时区 (UTC+8) — 用户活动以中国本地日期为准
BEIJING_TZ = timezone(timedelta(hours=8))

logger = logging.getLogger(__name__)


def _flatten_text(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_text(item) for item in value if item is not None)
    if value is None:
        return ""
    return str(value).strip()


def _looks_like_diet_management_intent(value: Any) -> bool:
    """LLM 有时把“删除/误删这餐”当成 diet.food_items, 写库前硬拦截."""
    return classify_intake_intent(_flatten_text(value)).kind == "diet_management"


def _looks_like_non_diet_intake(value: Any) -> bool:
    """药物/补剂摄入不能落成 DietRecord, 写库前硬拦截."""
    return classify_intake_intent(_flatten_text(value)).kind in {"medication", "supplement"}


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
        "amount": (10, 5000, None),            # ml; missing amount must stay visible
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
            _metric(rtype, field, "non_numeric", action="rejected")
            data.pop(field, None)
            continue
        if num < low or num > high:
            # 极端值: 移除 (让 API 层报"必填"比写入垃圾值好)
            msg = (f"[tool_validator] {rtype}.{field}={num} 超界 [{low},{high}], "
                   f"移除 — LLM 可能幻觉")
            warnings.append(msg)
            logger.warning(msg)
            _metric(rtype, field, "out_of_range", action="rejected")
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
                _metric(rtype, "medication_id", "ownership_mismatch", action="rejected")
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
                _metric(rtype, "profile_id", "ownership_mismatch", action="rejected")
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
        "water": ["amount"],
        "weight": ["weight"],
        "blood_pressure": ["systolic", "diastolic"],
        "exercise": ["exercise_type"],
        "medication": [],  # medication_id 或 medication_name 二选一, 由 API 层判
        "illness": ["name"],
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

    if rtype == "illness" and "name" not in data and data.get("illness_name"):
        data["name"] = data["illness_name"]

    # 1. 日期守门 (record_date 通用)
    _validate_date(rtype, data, warnings, today)

    # 2. 数值范围
    _validate_numeric(rtype, data, warnings)

    # 3. 引用 ID 存在性 + 越权
    _validate_reference_id(rtype, data, warnings, db, user_id)

    # 4. 饮食记录的管理意图硬阻断:
    # "我刚才不小心删除了/删除这一餐/撤销这顿" 是 health_manage 语义,
    # 绝不能被上下文带偏写成一条 0 kcal 晚餐。
    if rtype == "diet" and _looks_like_diet_management_intent(data.get("food_items")):
        msg = "[tool_validator] diet.food_items 疑似删除/撤销已有饮食记录, 阻止作为新饮食写入"
        warnings.append(msg)
        logger.warning("%s: %r", msg, data.get("food_items"))
        _metric(rtype, "food_items", "management_intent", action="rejected")
        error = (
            "Error: 用户是在删除/撤销/恢复已有饮食记录, 不能调用 health_record 新增 diet。"
            "请改用 health_manage(record_type='diet', operation='list') 查候选记录; "
            "若已有 record_id 再调用 health_manage(..., operation='delete' 或 update)。"
        )
        if warnings:
            logger.info(f"[tool_validator] {rtype} 守门触发 {len(warnings)} 条")
        return {
            "data": data,
            "warnings": warnings,
            "error": error,
        }

    # 5. 药物/补剂摄入硬阻断:
    # "刚吃了替普瑞酮/奥美拉唑20mg" 是 medication 语义,
    # 绝不能被"吃了"这个词带偏写成饮食。
    if rtype == "diet" and _looks_like_non_diet_intake(data.get("food_items")):
        msg = "[tool_validator] diet.food_items 疑似药物/补剂摄入, 阻止作为新饮食写入"
        warnings.append(msg)
        logger.warning("%s: %r", msg, data.get("food_items"))
        _metric(rtype, "food_items", "non_diet_intake", action="rejected")
        error = (
            "Error: diet.food_items 疑似药物/补剂摄入, 不能作为饮食记录写入。"
            "请改用 health_record(record_type='medication', data={...}); "
            "如果是保健品/补剂, 请用 record_type='supplement'。"
        )
        if warnings:
            logger.info(f"[tool_validator] {rtype} 守门触发 {len(warnings)} 条")
        return {
            "data": data,
            "warnings": warnings,
            "error": error,
        }

    # 6. 必填检查 (返回 error)
    error = _validate_required(rtype, data, warnings)

    if warnings:
        logger.info(f"[tool_validator] {rtype} 守门触发 {len(warnings)} 条")
    return {
        "data": data,
        "warnings": warnings,
        "error": error,
    }


# ═══════════════════════════════════════════════════════════════
# 统一入口 validate_tool_call — 所有 6 个工具的总守门
# ═══════════════════════════════════════════════════════════════

# 工具枚举白名单 (与 tool_schema_registry.HEALTH_TOOLS 对齐, 测试会比对一致性)
_QUERY_DIMENSIONS = {
    "comprehensive", "sleep", "heart_rate", "hrv", "activity",
    "spo2", "spo2_sleep_correlation", "weight", "blood_pressure",
    "supplements", "water", "diet", "exercise", "workout", "manual_exercise",
    "body_battery", "stress",
    "medical_exam", "genetic", "genetic_cognitive", "genetic_personality",
    "genetic_comprehensive", "medication",
}
_ANALYSIS_TYPES = {
    "comprehensive", "sleep_insight", "heart_rate_insight",
    "recovery_status", "risk_factors", "trend",
    "supplement_effectiveness", "orchestrator",
}
_ENV_CHECK_TYPES = {"weather", "air_quality", "outdoor_suitability"}
_PLAN_ACTIONS = {"generate_weekly", "complete_item", "save_to_card"}
_MANAGE_RECORD_TYPES = {
    "diet", "water", "weight", "waist", "blood_pressure",
    "sleep", "mood", "excretion", "exercise", "illness", "symptom",
    "medication", "medication_log", "supplement", "supplement_definition", "reminder",
}
_MANAGE_OPERATIONS = {"list", "update", "delete"}
_CARD_TYPES = {"plan", "insight", "recommendation"}
_TARGET_WEEKS = {"current", "next"}

_INDICATOR_ALLOWED_DIMS = {"medical_exam", "genetic"}


def _metric(tool: str, field: str, reason: str, *, action: str = "coerced") -> None:
    """结构化 metric 日志 — Sentry 接入后可直接聚合 (STRATEGY 第七节项 2).

    action='coerced': 字段被纠正到合法值 (enum 替换 / 日期回写今天)
    action='rejected': 字段被整个丢弃 (数值超界 / 非数值 / 越权 ID)
    """
    logger.info("metric: tool_validator_%s tool=%s field=%s reason=%s",
                action, tool, field, reason)


def _coerce_enum(
    tool: str, args: Dict[str, Any], field: str,
    allowed: set, default: Optional[str], warnings: list,
) -> None:
    """枚举越界 → coerce 到 default. default=None 表示越界则 pop."""
    v = args.get(field)
    if v is None or v in allowed:
        return
    msg = f"[tool_validator] {tool}.{field}={v!r} 不在白名单, 修正为 {default!r}"
    warnings.append(msg)
    logger.warning(msg)
    _metric(tool, field, "enum_out_of_range")
    if default is None:
        args.pop(field, None)
    else:
        args[field] = default


def _coerce_int_range(
    tool: str, args: Dict[str, Any], field: str,
    low: int, high: int, default: int, warnings: list,
) -> None:
    """整数越界 → coerce 到 default."""
    if field not in args:
        return
    try:
        v = int(args[field])
    except (TypeError, ValueError):
        msg = f"[tool_validator] {tool}.{field}={args[field]!r} 非整数, 修正为 {default}"
        warnings.append(msg)
        logger.warning(msg)
        _metric(tool, field, "not_integer")
        args[field] = default
        return
    if v < low or v > high:
        msg = f"[tool_validator] {tool}.{field}={v} 超界 [{low},{high}], 修正为 {default}"
        warnings.append(msg)
        logger.warning(msg)
        _metric(tool, field, "out_of_range")
        args[field] = default
    else:
        args[field] = v


def _validate_query(
    args: Dict[str, Any], warnings: list, db, user_id: Optional[int],
) -> Optional[str]:
    normalized = normalize_health_query_args(args)
    args.clear()
    args.update(normalized)
    _coerce_enum("health_query", args, "dimension", _QUERY_DIMENSIONS, "comprehensive", warnings)
    _coerce_int_range("health_query", args, "days", 1, 365, 7, warnings)
    _coerce_int_range("health_query", args, "uploaded_days", 1, 365, 1, warnings)
    # indicator 只在 medical_exam / genetic 有意义, 其余 dim silent drop
    if args.get("indicator") and args.get("dimension") not in _INDICATOR_ALLOWED_DIMS:
        _metric("health_query", "indicator", "irrelevant_to_dim")
        args.pop("indicator", None)
    # indicator 长度兜底 (防止超长字串)
    if isinstance(args.get("indicator"), str) and len(args["indicator"]) > 64:
        args["indicator"] = args["indicator"][:64]
        warnings.append("[tool_validator] health_query.indicator 截断到 64 字符")
    if not args.get("dimension"):
        args["dimension"] = "comprehensive"  # 必填, required 检查
    return None


def _validate_analysis(
    args: Dict[str, Any], warnings: list, db, user_id: Optional[int],
) -> Optional[str]:
    _coerce_enum("health_analysis", args, "analysis_type", _ANALYSIS_TYPES,
                 "comprehensive", warnings)
    _coerce_int_range("health_analysis", args, "days", 1, 365, 7, warnings)
    # orchestrator 必填 question
    if args.get("analysis_type") == "orchestrator" and not args.get("question"):
        return "Error: analysis_type=orchestrator 必须提供 question 字段 (用户具体问题)."
    # question 长度截断
    if isinstance(args.get("question"), str) and len(args["question"]) > 2000:
        args["question"] = args["question"][:2000]
        warnings.append("[tool_validator] health_analysis.question 截断到 2000 字符")
    return None


def _validate_environment(
    args: Dict[str, Any], warnings: list, db, user_id: Optional[int],
) -> Optional[str]:
    _coerce_enum("environment_check", args, "check_type", _ENV_CHECK_TYPES,
                 "weather", warnings)
    return None


def _validate_supplement_guide(
    args: Dict[str, Any], warnings: list, db, user_id: Optional[int],
) -> Optional[str]:
    """无参工具. 额外字段 silent strip, 不 warn (LLM 乱塞不是错误)."""
    extra = [k for k in list(args.keys())]
    for k in extra:
        args.pop(k, None)
    return None


def _validate_manage_plan(
    args: Dict[str, Any], warnings: list, db, user_id: Optional[int],
) -> Optional[str]:
    action = args.get("action")
    if action not in _PLAN_ACTIONS:
        return f"Error: manage_plan.action 必须是 {sorted(_PLAN_ACTIONS)} 之一, 收到 {action!r}."

    data = args.get("data") or {}
    if not isinstance(data, dict):
        args["data"] = data = {}

    if action == "generate_weekly":
        _coerce_enum("manage_plan", data, "target_week", _TARGET_WEEKS, "current", warnings)

    elif action == "complete_item":
        plan_id = data.get("plan_id")
        item_id = data.get("item_id")
        if plan_id is None or item_id is None:
            return "Error: manage_plan.complete_item 需要 data.plan_id 和 data.item_id."
        # 越权检查: WeeklyPlan 属于该用户 + PlanItem 属于该 plan
        if db is not None and user_id is not None:
            try:
                from app.models.smart_plan import WeeklyPlan, PlanItem
                plan_ok = db.query(WeeklyPlan.id).filter(
                    WeeklyPlan.id == plan_id, WeeklyPlan.user_id == user_id,
                ).first()
                if not plan_ok:
                    msg = (f"[tool_validator] manage_plan plan_id={plan_id} "
                           f"不存在或不属于 user={user_id} — LLM 编造 ID")
                    warnings.append(msg)
                    logger.warning(msg)
                    _metric("manage_plan", "plan_id", "cross_user_access")
                    return f"Error: plan_id={plan_id} 不存在或不属于当前用户."
                item_ok = db.query(PlanItem.id).filter(
                    PlanItem.id == item_id, PlanItem.plan_id == plan_id,
                ).first()
                if not item_ok:
                    msg = (f"[tool_validator] manage_plan item_id={item_id} "
                           f"不属于 plan_id={plan_id}")
                    warnings.append(msg)
                    logger.warning(msg)
                    _metric("manage_plan", "item_id", "cross_plan_access")
                    return f"Error: item_id={item_id} 不属于 plan_id={plan_id}."
            except Exception as e:
                logger.warning(f"[tool_validator] manage_plan 越权校验失败 (跳过): {e}")

    elif action == "save_to_card":
        _coerce_enum("manage_plan", data, "card_type", _CARD_TYPES, "insight", warnings)
        for field, max_len in (("title", 200), ("content", 10000)):
            v = data.get(field)
            if isinstance(v, str) and len(v) > max_len:
                data[field] = v[:max_len]
                warnings.append(f"[tool_validator] manage_plan.{field} 截断到 {max_len} 字符")
                _metric("manage_plan", field, "truncated")

    return None


def _validate_health_manage(
    args: Dict[str, Any], warnings: list, db, user_id: Optional[int],
) -> Optional[str]:
    _coerce_enum("health_manage", args, "record_type", _MANAGE_RECORD_TYPES, None, warnings)
    _coerce_enum("health_manage", args, "operation", _MANAGE_OPERATIONS, None, warnings)
    rtype = args.get("record_type")
    operation = args.get("operation")
    if not rtype:
        return f"Error: health_manage.record_type 必须是 {sorted(_MANAGE_RECORD_TYPES)} 之一."
    if not operation:
        return f"Error: health_manage.operation 必须是 {sorted(_MANAGE_OPERATIONS)} 之一."

    if operation in {"update", "delete"}:
        record_id = args.get("record_id")
        if record_id is None:
            return f"Error: health_manage.{operation} 必须提供 record_id. 先 list 查候选记录, 不要编造 ID."
        try:
            record_id_int = int(record_id)
        except (TypeError, ValueError):
            return f"Error: health_manage.record_id 必须是整数, 收到 {record_id!r}."
        if record_id_int <= 0:
            return f"Error: health_manage.record_id 必须为正整数, 收到 {record_id_int}."
        args["record_id"] = record_id_int

    if operation == "update":
        data = args.get("data") or {}
        if not isinstance(data, dict):
            return "Error: health_manage.update 的 data 必须是对象."
        if not data:
            return "Error: health_manage.update 必须提供 data 补丁字段."
        args["data"] = data

    if isinstance(args.get("date"), str) and len(args["date"]) > 10:
        args["date"] = args["date"][:10]
        warnings.append("[tool_validator] health_manage.date 截断到 YYYY-MM-DD")

    return None


# 工具名 → 校验函数分发表
_TOOL_VALIDATORS: Dict[str, Any] = {
    "health_query": _validate_query,
    "health_manage": _validate_health_manage,
    "health_analysis": _validate_analysis,
    "environment_check": _validate_environment,
    "supplement_guide": _validate_supplement_guide,
    "manage_plan": _validate_manage_plan,
}


def validate_tool_call(
    tool_name: str,
    args: Dict[str, Any],
    db=None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    所有 LLM tool_call 的统一守门入口.

    bypass-safe: 任何内部异常都 fall through 为"无 warning 无 error 放行",
    保证 validator 自身崩了也不会让工具调用挂掉 (仿 agents/audit.py 样板).

    返回: {
        'data': 修正后的 args (同一对象, in-place),
        'warnings': List[str],
        'error': Optional[str] — 非空时 agent_executor 应返回给 LLM 让其重试,
    }
    """
    if not isinstance(args, dict):
        return {"data": args, "warnings": [], "error": None}

    try:
        if tool_name == "health_record":
            rtype = args.get("record_type", "")
            data = args.get("data") or {}
            if not isinstance(data, dict):
                data = {}
                args["data"] = data
            v = validate_health_record(rtype, data, db=db, user_id=user_id)
            return {"data": args, "warnings": v["warnings"], "error": v["error"]}

        validator = _TOOL_VALIDATORS.get(tool_name)
        if validator is None:
            return {"data": args, "warnings": [], "error": None}

        warnings: list = []
        error = validator(args, warnings, db, user_id)
        if warnings:
            logger.info(f"[tool_validator] {tool_name} 守门触发 {len(warnings)} 条")
        return {"data": args, "warnings": warnings, "error": error}

    except Exception as e:
        # bypass-safe: validator 自身崩 → 放行, 绝不阻塞工具调用
        logger.exception(f"[tool_validator] {tool_name} validator 自身异常 (跳过): {e}")
        return {"data": args, "warnings": [], "error": None}
