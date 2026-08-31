"""确定性查询直出 (延迟优化 Phase-2 rank2).

把 fast-record 路径已证明的「确定性回复 + 跳过合成轮 break」模式扩展到高频
**只读**查询形状。单指标覆盖水 / 体重 / 睡眠 / 步数活动 / 血压；多指标只覆盖
HRV / 睡眠评分 / 步数 / 身体电量 / 压力等低风险标量。若本回合**所有**工具结果
都能被下面的确定性格式化器覆盖, 就直接从**真实 tool result** 渲染人话读数并 break。

诚实 / R4 不变量 (test-enforced):
  1. 读数**只**从真实 tool result 渲染, 绝不编造数字; 缺数据 → 诚实「今天还没有记录」。
  2. 覆盖不全 (任何未覆盖工具 / 未覆盖维度 / 无法解析) → 返回 ``None``, 调用方 fail-open
     回落到合成轮 (宁可慢而对, 不快而错)。
  3. tool result 里带 SafetyGuardian 安全告警后缀 (``⚠️ 安全提示:``) → 返回 ``None``,
     让强模型作答 (安全文本必须进入强模型答案, 不被确定性短路吞掉)。
  4. 只认 ``health_query`` / ``health_query_batch`` 只读工具; 任何写工具或其它工具
     在场 → 返回 ``None`` (查询回合绝不谎报/执行写操作的硬门不受影响)。

血压分级只**引用** tool result 里已由服务端 ``classify_blood_pressure`` (ACC/AHA) 计算好
的 ``category`` 字段, 不新造任何医学判断。
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

from app.services.health_query_dimensions import normalize_health_query_args
from app.utils.number_format import format_display_number

# 与 agent_executor.SAFETY_WARNING_MARKER 同源 (test_query_readouts 里有 drift 断言钉死)。
# 写后安全评估把 SafetyGuardian 的告警以这个前缀追加进 tool result content。
_SAFETY_WARNING_MARKER = "\n\n⚠️ 安全提示:"

# 只覆盖确定性健康只读工具。写工具 / knowledge_search / orchestrator 等在场 → 不短路。
_COVERED_QUERY_TOOLS = frozenset({"health_query", "health_query_batch"})

_BATCH_DIMENSION_LABELS = {
    "activity": ("步数", "步"),
    "hrv": ("HRV", "ms"),
    "sleep": ("睡眠评分", "分"),
    "body_battery": ("身体电量", ""),
    "stress": ("压力", ""),
}
_BATCH_AGG_LABELS = {
    "latest": "最新值",
    "avg": "平均值",
    "min": "最低值",
    "max": "最高值",
}

# Zero-LLM planning is intentionally narrower than result formatting.  These
# dimensions are scalar, read-only wearable facts that can be requested without
# making a medical interpretation.  Ordering is recovered from match positions
# so the answer follows the user's wording.
_PREPLANNED_DIMENSION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "hrv",
        re.compile(r"(?<![a-z0-9])hrv(?![a-z0-9])|心率变异(?:性)?", re.IGNORECASE),
    ),
    ("sleep", re.compile(r"睡眠(?:评分|分数|数据)?")),
    (
        "activity",
        re.compile(r"步数|(?<![a-z0-9])steps?(?![a-z0-9])|走了多少步", re.IGNORECASE),
    ),
    (
        "body_battery",
        re.compile(
            r"(?<![a-z0-9])body\s*battery(?![a-z0-9])|身体电量|体能电量|身体能量",
            re.IGNORECASE,
        ),
    ),
    ("stress", re.compile(r"压力(?:数据|水平|值)?")),
)
_PREPLANNED_QUERY_ACTION_RE = re.compile(
    r"查|查询|看(?:看|下|一下)?|显示|列出|数据|读数|指标"
)
_PREPLANNED_INTERPRETATION_RE = re.compile(
    r"分析|建议|为什么|原因|怎么办|怎么改善|评估|风险|正常吗|好不好|怎么样|"
    r"诊断|治疗|用药|解读|意味着什么"
)
_PREPLANNED_RESTRICTION_RE = re.compile(
    r"不要|别查|无需|不用|禁止|停止|取消|能不能|能否|可不可以|可以吗|"
    r"是否(?:能|可以|支持)|(?:你)?能(?:查|查询)|支持(?:查|查询)"
)
_PREPLANNED_UNSUPPORTED_METRIC_RE = re.compile(
    r"血氧|(?<![a-z0-9])spo2(?![a-z0-9])|心率(?!变异)|血压|体重|饮水|喝水|"
    r"补剂|药物|用药|基因|化验|症状|疾病|血糖|(?<![a-z0-9])cgm(?![a-z0-9])|"
    r"体温|呼吸|月经",
    re.IGNORECASE,
)
_PREPLANNED_UNSUPPORTED_TIME_RE = re.compile(
    r"昨天|前天|昨晚|小时|分钟|去年|前年|今年|半年|年内|上个月|上月|本月|"
    r"这个月|半个月|历史|全部|所有|\d{4}[-年/]\d{1,2}"
)
_PREPLANNED_UNSUPPORTED_AGG_RE = re.compile(r"总和|合计|累计|中位数|百分位")


def _preplanned_query_days(message: str) -> Optional[int]:
    """Return a bounded explicit/default window; unsupported windows fail open."""
    explicit_days = re.search(r"(?:最近|近|过去)?\s*(\d{1,3})\s*天", message)
    if explicit_days:
        days = int(explicit_days.group(1))
    else:
        period = re.search(
            r"(?:最近|近|过去)?\s*(\d{1,2}|一|二|两|三|四|五|六|七|八|九|十)"
            r"\s*(周|个?月)",
            message,
        )
        if period:
            count_token = period.group(1)
            count = (
                int(count_token)
                if count_token.isdigit()
                else {
                    "一": 1,
                    "二": 2,
                    "两": 2,
                    "三": 3,
                    "四": 4,
                    "五": 5,
                    "六": 6,
                    "七": 7,
                    "八": 8,
                    "九": 9,
                    "十": 10,
                }[count_token]
            )
            days = count * (7 if period.group(2) == "周" else 30)
        elif re.search(r"这周|本周", message):
            days = 7
        else:
            days = 7
    return days if 1 <= days <= 90 else None


def preplanned_batch_query_args(message: str) -> Optional[Dict[str, Any]]:
    """Plan an exact low-risk multi-metric read without an LLM decision round.

    This parser is an allowlist, not a general intent recognizer.  Ambiguous,
    interpretive, unsupported, or single-metric wording returns ``None`` so the
    existing model/tool path remains responsible for the turn.
    """
    text = str(message or "").strip()
    if (
        not text
        or not _PREPLANNED_QUERY_ACTION_RE.search(text)
        or _PREPLANNED_INTERPRETATION_RE.search(text)
        or _PREPLANNED_RESTRICTION_RE.search(text)
        or _PREPLANNED_UNSUPPORTED_METRIC_RE.search(text)
        or _PREPLANNED_UNSUPPORTED_TIME_RE.search(text)
        or _PREPLANNED_UNSUPPORTED_AGG_RE.search(text)
    ):
        return None

    matches: list[tuple[int, str]] = []
    for dimension, pattern in _PREPLANNED_DIMENSION_PATTERNS:
        match = pattern.search(text)
        if match:
            matches.append((match.start(), dimension))
    matches.sort()
    if not 2 <= len(matches) <= 5:
        return None

    days = _preplanned_query_days(text)
    if days is None:
        return None
    if re.search(r"趋势|变化", text):
        agg = "trend"
    elif re.search(r"最新|当前|现在", text):
        agg = "latest"
    elif re.search(r"最高|最大", text):
        agg = "max"
    elif re.search(r"最低|最小", text):
        agg = "min"
    else:
        agg = "avg"

    return {
        "queries": [
            {"dimension": dimension, "days": days, "agg": agg}
            for _, dimension in matches
        ]
    }


# ── 数值 / 解析小工具 ────────────────────────────────────────────────────
def _as_int(value: Any) -> Optional[int]:
    """尽力把值转成 int (ml / 分钟 / 步数都是整数)。转不动 → None。"""
    if isinstance(value, bool):  # bool 是 int 子类, 显式排除
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        m = re.search(r"-?\d+", value)
        if m:
            return int(m.group())
    return None


def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        m = re.search(r"-?\d+(?:\.\d+)?", value)
        if m:
            return float(m.group())
    return None


def _fmt_num(value: Any) -> str:
    """去掉浮点尾部 .0 (75.0 → 75, 75.5 → 75.5)。"""
    f = _as_float(value)
    if f is None:
        return str(value)
    if f == int(f):
        return str(int(f))
    return f"{f:.1f}"


def _fmt_duration(minutes: Optional[int]) -> Optional[str]:
    if minutes is None or minutes < 0:
        return None
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}小时{m}分钟"
    if h:
        return f"{h}小时"
    return f"{m}分钟"


def _parse_json_result(content: str) -> Any:
    """把 tool result content 解析成 JSON 值; 只返回**完整合法**的 JSON, 绝不返回半截。

    - ``Error`` 前缀 / 空 → None (调用方 fail-open)。
    - 严格 json.loads 优先。
    - 失败时从首个 ``[``/``{`` 起 raw_decode: 救 ``_api_get`` 给合法数组加的
      "...(仅显示前10条)" 尾注 (raw_decode 只吃合法前缀, 被字符截断到半个 token 时
      raw_decode 也会失败 → None, 绝不返回残缺数值)。
    """
    s = (content or "").strip()
    if not s or s.startswith("Error"):
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (s.find("["), s.find("{")) if i != -1]
    if starts:
        try:
            value, _ = json.JSONDecoder().raw_decode(s[min(starts):])
            return value
        except json.JSONDecodeError:
            return None
    return None


# ── 各维度格式化器: (content: str) -> Optional[str] ──────────────────────
# 返回值语义: 人话读数字符串 = 覆盖成功 (含诚实「还没有记录」); None = 不覆盖 → fall-open。

def _format_water(content: str) -> Optional[str]:
    """今日饮水 total + 目标 (DailyWaterSummary JSON)。"""
    payload = _parse_json_result(content)
    if not isinstance(payload, dict):
        return None
    records = payload.get("records")
    total = _as_int(payload.get("total_amount"))
    # total 字段缺失时从 records 求和 (与服务端同口径; 求和读的是真实记录, 非编造)。
    if total is None and isinstance(records, list):
        total = sum(
            (_as_int(r.get("amount")) or 0)
            for r in records
            if isinstance(r, dict)
        )
    if total is None:
        return None
    count = _as_int(payload.get("records_count"))
    has_records = bool(records) if isinstance(records, list) else (count or 0) > 0
    if not has_records or total <= 0:
        return "今天还没有喝水记录哦,记得及时补水。"
    target = _as_int(payload.get("target_amount")) or 2000
    line = f"今日饮水 {total}ml,目标 {target}ml"
    progress = _as_float(payload.get("progress_percentage"))
    if progress is not None:
        line += f"(完成 {_fmt_num(progress)}%)"
    return line + "。"


def _format_weight(content: str) -> Optional[str]:
    """最新体重 + 较上次 (List[WeightRecordResponse], record_date DESC)。"""
    payload = _parse_json_result(content)
    if not isinstance(payload, list):
        return None
    records = [r for r in payload if isinstance(r, dict) and r.get("weight") is not None]
    if not records:
        return "还没有体重记录,记录一次就能看到变化趋势。"
    latest = records[0]
    w = _as_float(latest.get("weight"))
    if w is None:
        return None
    line = f"最新体重 {_fmt_num(w)}kg"
    d = latest.get("record_date")
    if d:
        line += f"({d})"
    if len(records) >= 2:
        prev = _as_float(records[1].get("weight"))
        if prev is not None:
            delta = w - prev
            if abs(delta) < 0.05:
                line += ",与上次持平"
            else:
                line += f",较上次{'上升' if delta > 0 else '下降'} {abs(delta):.1f}kg"
    return line + "。"


def _format_blood_pressure(content: str) -> Optional[str]:
    """最新血压 + 分级 label (List[BloodPressureRecordResponse], record_date DESC)。

    分级只引用 tool result 里服务端算好的 ``category`` (ACC/AHA), 不新造医学判断。
    """
    payload = _parse_json_result(content)
    if not isinstance(payload, list):
        return None
    records = [
        r for r in payload
        if isinstance(r, dict) and r.get("systolic") is not None and r.get("diastolic") is not None
    ]
    if not records:
        return "还没有血压记录。"
    latest = records[0]
    sys = _as_int(latest.get("systolic"))
    dia = _as_int(latest.get("diastolic"))
    if sys is None or dia is None:
        return None
    from app.utils.blood_pressure_classify import is_severe_blood_pressure_record

    if any(is_severe_blood_pressure_record(record) for record in records):
        return None
    line = f"最新血压 {sys}/{dia} mmHg"
    pulse = _as_int(latest.get("pulse"))
    if pulse:
        line += f",脉搏 {pulse}次/分"
    category = latest.get("category")
    if isinstance(category, str) and category.strip():
        line += f"(分级:{category.strip()})"
    d = latest.get("record_date")
    if d:
        line += f",记录于 {d}"
    return line + "。"


def _format_sleep(content: str) -> Optional[str]:
    """昨晚睡眠时长 / 深睡 (analyze_sleep_quality dict, 取 daily_data 里最近一晚)。"""
    payload = _parse_json_result(content)
    if not isinstance(payload, dict):
        return None
    if payload.get("status") == "no_data":
        return "还没有足够的睡眠数据(可能设备未同步)。"
    daily = payload.get("daily_data")
    if not isinstance(daily, list) or not daily:
        return None
    nights = [d for d in daily if isinstance(d, dict) and d.get("date")]
    if not nights:
        return None
    latest = max(nights, key=lambda d: str(d.get("date")))
    total_min = _as_int(latest.get("total_sleep_duration"))
    dur = _fmt_duration(total_min)
    if dur is None:
        return None
    line = f"{latest.get('date')} 睡了 {dur}"
    deep_min = _as_int(latest.get("deep_sleep_duration"))
    deep = _fmt_duration(deep_min)
    if deep is not None:
        line += f",其中深睡 {deep}"
    score = _as_int(latest.get("sleep_score"))
    if score is not None:
        line += f",睡眠评分 {score}"
    days_analyzed = _as_int(payload.get("days_analyzed")) or 0
    avg_hours = _as_float(payload.get("average_sleep_duration_hours"))
    if days_analyzed > 1 and avg_hours is not None:
        line += f"(最近 {days_analyzed} 晚平均 {_fmt_num(avg_hours)} 小时)"
    return line + "。"


# read_wearable_daily 的确定性文本行: "- 2026-07-11: 步数 8500, 静息心率 55bpm, ..."
_ACTIVITY_LINE_RE = re.compile(r"^-\s*(\d{4}-\d{2}-\d{2})\s*:\s*(.+)$", re.MULTILINE)
_STEPS_RE = re.compile(r"步数\s*(\d+)")
_ACTIVE_MIN_RE = re.compile(r"活动分钟\s*(\d+)")
_CALORIES_RE = re.compile(r"总消耗\s*(\d+)")


def _format_activity(content: str) -> Optional[str]:
    """今日步数 / 活动 (read_wearable_daily 确定性文本, 取最近一天)。

    活动维度经 canonical_read 返回**文本**(非 JSON), 用锚定到自家固定输出格式的
    正则抽最近一天的步数; 抽不到 → None (fail-open, 绝不猜数)。
    """
    s = (content or "").strip()
    if not s or s.startswith("Error"):
        return None
    if s.startswith("未找到可穿戴"):
        return "还没有可穿戴设备(Garmin/Apple Watch 等)的活动数据(可能设备未同步)。"
    m = _ACTIVITY_LINE_RE.search(s)  # 首个 "- 日期:" 行 = 最近一天 (输出按日期倒序)
    if not m:
        return None
    day, rest = m.group(1), m.group(2)
    steps_m = _STEPS_RE.search(rest)
    if not steps_m:
        return None
    line = f"{day} 步数 {int(steps_m.group(1))}步"
    active_m = _ACTIVE_MIN_RE.search(rest)
    if active_m:
        line += f",活动 {int(active_m.group(1))}分钟"
    cal_m = _CALORIES_RE.search(rest)
    if cal_m:
        line += f",消耗 {int(cal_m.group(1))}kcal"
    return line + "。"


def _format_batch(args: Dict[str, Any], content: str) -> Optional[str]:
    """Render a fully successful low-risk scalar batch without interpretation."""
    payload = _parse_json_result(content)
    if not isinstance(payload, dict) or args.get("compare") is not None:
        return None
    if payload.get("compare") is not None:
        return None
    planned = args.get("queries")
    entries = payload.get("queries")
    meta = payload.get("meta")
    if (
        not isinstance(planned, list)
        or not planned
        or not isinstance(entries, list)
        or len(entries) != len(planned)
        or not isinstance(meta, dict)
        or meta.get("executed") != len(entries)
        or meta.get("failed") != 0
    ):
        return None

    readouts: List[str] = []
    for raw_plan, entry in zip(planned, entries):
        if not isinstance(raw_plan, dict) or not isinstance(entry, dict):
            return None
        normalized = normalize_health_query_args(raw_plan)
        dimension = normalized.get("dimension")
        label_and_unit = _BATCH_DIMENSION_LABELS.get(dimension)
        if label_and_unit is None or entry.get("dimension") != dimension:
            return None
        try:
            planned_days = int(normalized.get("days") or 7)
            result_days = int(entry.get("days"))
        except (TypeError, ValueError):
            return None
        agg = raw_plan.get("agg")
        if (
            planned_days <= 0
            or result_days != planned_days
            or entry.get("agg") != agg
            or agg not in {*_BATCH_AGG_LABELS, "trend"}
            or entry.get("error")
            or entry.get("note")
        ):
            return None
        value = entry.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        count = entry.get("n")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            return None

        label, default_unit = label_and_unit
        unit = str(entry.get("unit") or default_unit).strip()
        rendered = format_display_number(abs(value) if agg == "trend" else value)
        value_with_unit = f"{rendered} {unit}".strip()
        prefix = f"近{result_days}天 {label}"
        if agg == "trend":
            if value > 0:
                text = f"{prefix} 较窗口起点上升 {value_with_unit}。"
            elif value < 0:
                text = f"{prefix} 较窗口起点下降 {value_with_unit}。"
            else:
                text = f"{prefix} 与窗口起点持平。"
        else:
            text = f"{prefix} {_BATCH_AGG_LABELS[agg]} {value_with_unit}。"
        readouts.append(text)
    return "\n\n".join(readouts) or None


_FORMATTERS: Dict[str, Callable[[str], Optional[str]]] = {
    "water": _format_water,
    "weight": _format_weight,
    "blood_pressure": _format_blood_pressure,
    "sleep": _format_sleep,
    "activity": _format_activity,
}

COVERED_DIMENSIONS = frozenset(_FORMATTERS)


def _collect_tool_results(messages: List[Dict[str, Any]]) -> Dict[str, str]:
    """tool_call_id → tool result content。"""
    out: Dict[str, str] = {}
    for m in messages:
        if m.get("role") == "tool":
            tcid = m.get("tool_call_id")
            if tcid:
                out[str(tcid)] = str(m.get("content") or "")
    return out


def _collect_tool_calls(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []
    for m in messages:
        if m.get("role") == "assistant":
            for tc in (m.get("tool_calls") or []):
                if isinstance(tc, dict):
                    calls.append(tc)
    return calls


def deterministic_query_reply(messages: List[Dict[str, Any]]) -> Optional[str]:
    """本回合能否用确定性读数直出? 能 → 返回人话读数; 不能 → None (fall-open 到合成)。

    只有当本回合执行过的**每一个**工具都是受支持的只读查询且其维度被格式化器覆盖、
    每个结果都成功渲染、且**没有**任何安全告警后缀时, 才返回非空读数。任一条件不满足
    → None, 让调用方回落强模型合成轮 (fail-open)。
    """
    if not messages:
        return None
    # History may contain writes or unsupported queries from older turns.  Only
    # tool calls after the latest user message belong to the reply currently
    # being finalized; including older calls would unnecessarily disable the
    # fast path (or mix stale facts into the answer).
    last_user_idx = next(
        (
            idx
            for idx in range(len(messages) - 1, -1, -1)
            if messages[idx].get("role") == "user"
        ),
        -1,
    )
    turn_messages = messages[last_user_idx + 1:] if last_user_idx >= 0 else messages
    # 不变量 3: 任一 tool result 带安全告警后缀 → 绝不短路 (安全文本须进强模型答案)。
    for m in turn_messages:
        if m.get("role") == "tool" and _SAFETY_WARNING_MARKER in str(m.get("content") or ""):
            return None

    calls = _collect_tool_calls(turn_messages)
    if not calls:
        return None
    results_by_id = _collect_tool_results(turn_messages)

    readouts: List[str] = []
    for tc in calls:
        fn = tc.get("function") or {}
        name = fn.get("name")
        if name not in _COVERED_QUERY_TOOLS:
            return None  # 不变量 4: 非只读查询工具在场 → 不短路
        raw_args = fn.get("arguments")
        try:
            args = (
                json.loads(raw_args) if isinstance(raw_args, str)
                else dict(raw_args or {})
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        if not isinstance(args, dict):
            return None
        content = results_by_id.get(str(tc.get("id")))
        if content is None:
            return None  # 找不到对应结果 (配对不上) → 保守 fall-open
        if name == "health_query_batch":
            readout = _format_batch(args, content)
            if not readout:
                return None
            readouts.append(readout)
            continue
        dim = normalize_health_query_args(args).get("dimension")
        formatter = _FORMATTERS.get(dim)
        if formatter is None:
            return None  # 未覆盖维度 → fall-open
        readout = formatter(content)
        if not readout:
            return None  # 无法确定性渲染 → fall-open
        readouts.append(readout)

    # 去重保序 (同一维度被查两次时不重复行)。
    deduped: List[str] = []
    for r in readouts:
        if r not in deduped:
            deduped.append(r)
    reply = "\n\n".join(deduped).strip()
    return reply or None
