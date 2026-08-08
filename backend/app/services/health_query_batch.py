"""health_query_batch — 声明式批查询计划的确定性执行器 (Slice 1).

LLM 一次产出 JSON plan, 后端确定性执行多条**只读**健康查询 + 聚合, 把多指标
问题从 3-4 轮 LLM 往返压到 1 轮。零代码执行 —— plan 只是声明式结构, 不是可执行
代码 (刻意不偷 Hermes 的 execute_code 任意代码执行, 安全面不可接受)。

设计: docs/plans/2026-07-07-agent-harness-freedom-upgrades.md §Slice 1

分层:
  - 纯函数层 (validate_plan / aggregate_series / compute_compare / execute_batch):
    不碰 DB/HTTP, 由注入的 async ``fetch(dimension, days)`` 取数 → 完全可单测
    (mock 数据面)。
  - 数据面适配层 (build_wearable_series): 复用既有 health_query 数据面 ——
    GarminData + merge_field 多源合并 (与 Twin / read_wearable_daily 同源), 由
    agent_executor 薄接线注入。非数值维度直接复用 _exec_health_query 的紧凑原文。

fail-loud 契约 (与 health_query 跨模型三层防御同款):
  - 未知 dimension / 未知 agg / >6 条子查询 / plan 非法 shape → 返回带合法值清单的
    Error 字符串 (在任何取数之前发生), 模型下一轮自纠。绝不静默跳过某条子查询。
  - 单条子查询数据为空 → 合法结果 (value=null + note), 整体不失败。
  - 单条取数抛异常 → 该条 error 字段显式挂账 (可观测, 非静默) + meta.failed 计数。

只读: 任何写路径禁止, R4 不涉及。工具注册 confirm=none。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Awaitable, Callable, Optional

from app.services.health_query_dimensions import normalize_health_query_args

logger = logging.getLogger(__name__)

MAX_QUERIES = 6
_NUMERIC_AGGS = ("latest", "avg", "min", "max", "trend")
VALID_AGGS = _NUMERIC_AGGS
VALID_COMPARE_OPS = ("diff", "ratio")
BATCH_UNSUPPORTED_DIMENSIONS = frozenset({"illness"})

_EXAMPLE_HINT = (
    ' 示例: {"queries":[{"dimension":"hrv","days":7,"agg":"avg"},'
    '{"dimension":"sleep","days":7,"agg":"trend"}]}。'
)

# 可产出按日数值序列 (可聚合) 的维度 → (GarminData 列名, 单位)。
# 其余 health_query 维度 (diet/medication/genetic/medical_exam/weight/blood_pressure...)
# 无单标量数值序列: agg 会被忽略, 返回原始数据 (value=null + note)。
_SERIES_FIELD: dict[str, tuple[str, str]] = {
    "activity": ("steps", ""),
    "heart_rate": ("resting_heart_rate", "bpm"),
    "hrv": ("hrv", "ms"),
    "sleep": ("sleep_score", ""),
    "body_battery": ("body_battery_current", ""),
    "stress": ("stress_level", ""),
    "spo2": ("spo2_avg", "%"),
}
SERIES_DIMENSIONS: frozenset[str] = frozenset(_SERIES_FIELD)


@dataclass
class BatchFetchResult:
    """数据面取数返回。

    series 时间升序 (oldest→newest); 空表示该窗口无数据。
    aggregatable=False 表示该维度天然无数值序列 (与"窗口恰好为空"区分, 用于给 note)。
    """

    series: list[float] = field(default_factory=list)
    unit: Optional[str] = None
    raw: Optional[str] = None
    note: Optional[str] = None
    error: Optional[str] = None
    aggregatable: bool = False


FetchFn = Callable[[str, int], Awaitable[BatchFetchResult]]


def known_dimensions() -> frozenset[str]:
    """canonical health_query dimension 全集 —— 单一真源 = health_query schema enum。

    lazy import 避免与 tool_schema_registry 潜在循环。找不到时返回空集 (调用方
    仍会 fail-loud, 不会静默放行未知维度)。
    """
    try:
        from app.services.tool_schema_registry import HEALTH_TOOLS
    except Exception:  # noqa: BLE001 — 导入异常不该让批查询整体崩
        return frozenset()
    for tool in HEALTH_TOOLS:
        fn = tool.get("function") or {}
        if fn.get("name") == "health_query":
            props = (fn.get("parameters") or {}).get("properties") or {}
            enum = (props.get("dimension") or {}).get("enum") or []
            return frozenset(str(e) for e in enum) - BATCH_UNSUPPORTED_DIMENSIONS
    return frozenset()


# ── 校验 (fail-loud, 取数之前) ─────────────────────────────────────────────
def validate_plan(
    plan: Any, *, valid_dimensions: frozenset[str]
) -> tuple[Optional[list[dict]], Optional[dict], Optional[str]]:
    """校验并归一 plan。返回 (queries, compare, error)。

    error 非空时 queries/compare 无意义, 调用方直接把 error 串回给 LLM 自纠。
    """
    if not isinstance(plan, dict):
        return None, None, "Error: health_query_batch plan 必须是对象。" + _EXAMPLE_HINT

    queries_raw = plan.get("queries")
    if not isinstance(queries_raw, list) or not queries_raw:
        return None, None, "Error: health_query_batch 需要非空 queries 数组。" + _EXAMPLE_HINT
    if len(queries_raw) > MAX_QUERIES:
        return None, None, (
            f"Error: health_query_batch 最多 {MAX_QUERIES} 条子查询 "
            f"(收到 {len(queries_raw)} 条)。请拆分成多次调用或精简指标。"
        )

    # canonical dims 均为小写 snake; 建 lowercase→canonical 映射兼容模型大小写。
    lc_map = {d.lower(): d for d in valid_dimensions}
    norm_queries: list[dict] = []
    for i, q in enumerate(queries_raw):
        if not isinstance(q, dict):
            return None, None, (
                f"Error: queries[{i}] 必须是对象 {{dimension, days, agg?}}。" + _EXAMPLE_HINT
            )
        normalized = normalize_health_query_args(q)  # 别名归一 + time_range→days
        dim = normalized.get("dimension")
        if not isinstance(dim, str) or not dim.strip():
            return None, None, f"Error: queries[{i}] 缺 dimension 字段。" + _EXAMPLE_HINT
        canonical = lc_map.get(dim.strip().lower())
        if canonical is None:
            return None, None, (
                f"Error: queries[{i}] 未知 dimension '{dim}'。合法值: "
                f"{', '.join(sorted(valid_dimensions))}。请从中选择后重试。"
            )

        agg = q.get("agg")
        if agg is not None:
            if not isinstance(agg, str) or agg.strip().lower() not in _NUMERIC_AGGS:
                return None, None, (
                    f"Error: queries[{i}] 未知 agg '{agg}'。合法值: "
                    f"{', '.join(_NUMERIC_AGGS)} (或省略 agg 返回原始数据)。"
                )
            agg = agg.strip().lower()

        norm_queries.append(
            {"dimension": canonical, "days": _coerce_days(normalized.get("days")), "agg": agg}
        )

    compare = None
    compare_raw = plan.get("compare")
    if compare_raw is not None:
        compare, cerr = _validate_compare(compare_raw, len(norm_queries))
        if cerr:
            return None, None, cerr

    return norm_queries, compare, None


def _validate_compare(compare: Any, n: int) -> tuple[Optional[dict], Optional[str]]:
    if not isinstance(compare, dict):
        return None, "Error: compare 必须是对象 {a:<下标>, b:<下标>, op:'diff'|'ratio'}。"
    ai = _coerce_index(compare.get("a"))
    bi = _coerce_index(compare.get("b"))
    if ai is None or bi is None or not (0 <= ai < n) or not (0 <= bi < n):
        return None, (
            f"Error: compare.a/b 必须是 0..{n - 1} 范围内的子查询下标 "
            f"(收到 a={compare.get('a')!r}, b={compare.get('b')!r})。"
        )
    op = compare.get("op")
    if not isinstance(op, str) or op.strip().lower() not in VALID_COMPARE_OPS:
        return None, (
            f"Error: compare.op 未知 '{op}'。合法值: {', '.join(VALID_COMPARE_OPS)} "
            "(diff=a-b, ratio=a/b)。"
        )
    return {"a": ai, "b": bi, "op": op.strip().lower()}, None


def _coerce_days(v: Any, *, default: int = 7) -> int:
    if v is None:
        return default
    try:
        d = int(v)
    except (TypeError, ValueError):
        return default
    return d if d > 0 else default


def _coerce_index(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ── 聚合 / 对比 (纯数学) ────────────────────────────────────────────────────
def aggregate_series(series: list[float], agg: Optional[str]) -> tuple[Optional[float], Optional[str]]:
    """在数值序列 (时间升序) 上做聚合。返回 (value, note)。

    value=None 表示无标量结果 (agg 省略 / 序列为空 / 趋势点不足)。
    """
    if agg is None:
        return None, None  # 不聚合, 由 raw 承载
    if not series:
        return None, "最近窗口无数据点, 无法聚合"
    if agg == "latest":
        return _round(series[-1]), None
    if agg == "avg":
        return _round(sum(series) / len(series)), None
    if agg == "min":
        return _round(min(series)), None
    if agg == "max":
        return _round(max(series)), None
    if agg == "trend":
        if len(series) < 2:
            return None, "数据点不足 (<2 天), 无法计算趋势"
        return _round(series[-1] - series[0]), None  # 首尾差: 最新 - 最早
    return None, f"未知 agg {agg}"  # 理论不达: validate_plan 已挡


def compute_compare(entries: list[dict], compare: Optional[dict]) -> Optional[dict]:
    """在已算出 value 的 entries 上做 diff/ratio。返回 comparison dict 或 None。"""
    if not compare:
        return None
    a = entries[compare["a"]]
    b = entries[compare["b"]]
    out: dict[str, Any] = {"a": compare["a"], "b": compare["b"], "op": compare["op"]}
    va, vb = a.get("value"), b.get("value")
    if va is None or vb is None:
        out["value"] = None
        out["note"] = "对比失败: 子查询 a 或 b 无标量值 (数据为空或该维度不可聚合)"
        return out
    if compare["op"] == "diff":
        out["value"] = _round(va - vb)
        if a.get("unit"):
            out["unit"] = a["unit"]
    else:  # ratio
        if vb == 0:
            out["value"] = None
            out["note"] = "对比失败: 除数 (子查询 b) 为 0"
        else:
            out["value"] = _round(va / vb)
    return out


def _round(v: float) -> float:
    r = round(float(v), 2)
    return int(r) if r == int(r) else r


def _cap(text: Any, limit: int = 600) -> str:
    t = str(text)
    return t if len(t) <= limit else t[:limit].rstrip() + "…"


# ── 编排 (async; fetch 注入数据面) ─────────────────────────────────────────
async def execute_batch(
    plan: Any, fetch: FetchFn, *, valid_dimensions: Optional[frozenset[str]] = None
) -> str:
    """执行批查询。成功返回紧凑结构化 JSON 字符串; 校验失败返回 Error 字符串。"""
    if valid_dimensions is None:
        valid_dimensions = known_dimensions()

    queries, compare, err = validate_plan(plan, valid_dimensions=valid_dimensions)
    if err:
        return err

    entries: list[dict] = []
    failed = 0
    for q in queries:
        entry: dict[str, Any] = {"dimension": q["dimension"], "days": q["days"], "agg": q["agg"]}
        try:
            fr = await fetch(q["dimension"], q["days"])
        except Exception as e:  # noqa: BLE001 — 数据面抛错 → 显式挂账, 不静默跳过
            logger.warning("[health_query_batch] fetch %s 失败: %s", q["dimension"], e)
            entry["value"] = None
            entry["error"] = f"数据查询失败: {e}"
            failed += 1
            entries.append(entry)
            continue

        if fr.error:
            entry["value"] = None
            entry["error"] = fr.error
            failed += 1
            entries.append(entry)
            continue

        value, note = aggregate_series(fr.series, q["agg"])
        entry["value"] = value
        if fr.unit:
            entry["unit"] = fr.unit
        if fr.series:
            entry["n"] = len(fr.series)

        if value is None and q["agg"] in _NUMERIC_AGGS and not fr.aggregatable:
            note = "该维度不支持数值聚合, 已返回原始数据"
        # 无标量结果 (agg 省略 / 空数据 / 不可聚合) → 带紧凑原文供 LLM 佐证
        if value is None and fr.raw:
            entry["data"] = _cap(fr.raw)
        note = note or fr.note
        if note:
            entry["note"] = note
        entries.append(entry)

    result: dict[str, Any] = {
        "queries": entries,
        "meta": {"executed": len(entries), "failed": failed},
    }
    cmp_out = compute_compare(entries, compare)
    if cmp_out is not None:
        result["compare"] = cmp_out
    return json.dumps(result, ensure_ascii=False, default=str)


# ── 数据面适配: 可穿戴日指标的按日数值序列 (复用 GarminData 多源合并) ──────────
def build_wearable_series(
    db, user_id: Optional[int], dimension: str, days: int
) -> tuple[list[float], str, str]:
    """取某可穿戴维度按日数值序列 (时间升序) + 紧凑原文。

    复用 merge_field (device_source_priority 单一优先级表, 与 Twin /
    read_wearable_daily 同源) —— 一次 GarminData 查询同时产出序列与原文。
    series 时间升序 (oldest→newest): trend/latest 依赖此序。
    """
    field_name, unit = _SERIES_FIELD[dimension]
    if user_id is None:
        return [], unit, "Error: 当前会话无 user_id, 无法查询可穿戴数据"

    from app.models.daily_health import GarminData
    from app.services.multi_source_merger import merge_field

    window = max(int(days), 1)
    since = date.today() - timedelta(days=window)
    try:
        rows = (
            db.query(GarminData)
            .filter(GarminData.user_id == user_id, GarminData.record_date >= since)
            .order_by(GarminData.record_date)
            .all()
        )
    except Exception as e:  # noqa: BLE001 — DB 异常回滚, 不静默吞
        logger.error("[health_query_batch] 查询 GarminData 失败: %s", e)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise

    if not rows:
        return [], unit, f"最近 {window} 天无可穿戴数据 ({dimension})。"

    by_date: dict = {}
    for r in rows:
        by_date.setdefault(r.record_date, []).append(r)

    series: list[float] = []
    lines: list[str] = []
    for d in sorted(by_date):
        v, _src = merge_field(by_date[d], field_name)
        if v is None:
            continue
        try:
            series.append(float(v))
        except (TypeError, ValueError):
            continue
        lines.append(f"{d.isoformat()}: {v}{unit}")

    if not lines:
        return [], unit, f"最近 {window} 天 {dimension} 数据均为空。"
    raw = f"{dimension} 最近 {len(lines)} 天: " + "; ".join(lines)
    return series, unit, raw
