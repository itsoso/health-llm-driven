r"""GenUI line_chart 构建器 — 确定性查真实日级序列, 聚合分桶, 拼 `reva-ui` block.

数据来源 (与 mobile `indicator-history` 同一日级源, 见 `mobile/services/trends.ts`
的 `fetchGarminMetricTrend`):
  - GarminData 日行 (`backend/app/models/daily_health.py`):
      hrv / resting_heart_rate / stress_level / total_sleep_duration /
      sleep_score / steps / body_battery_current
  - WeightRecord 日行 (`backend/app/models/weight.py`): weight

铁律 (R4): 本模块所有数值均来自上述 DB 表的真实行。LLM 不参与数据路径 —
请用 `grep -n "llm\|LLM\|_call_llm" chart_builder.py` 自证 (无命中)。LLM 仅在
orchestrator synthesis 阶段写 block 之外的叙事。

设计:
  - DB I/O (`_fetch_daily_points`) 与纯计算 (`compute_chart`) 分离, 便于纯单测。
  - 数据点过少 (< MIN_POINTS) → build_line_chart 返回 None, 调用方显"数据不足"。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean
from typing import Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.daily_health import GarminData
from app.models.weight import WeightRecord

LINE_CHART_COMPONENT = "line_chart"
METRIC_LINE_CHART_COMPONENT = "metric_line_chart"
METRIC_LINE_CHART_SCHEMA = "reva.metric_line_chart.v1"
_SUPPORTED_COMPONENTS = {LINE_CHART_COMPONENT, METRIC_LINE_CHART_COMPONENT}

# ---------------------------------------------------------------------------
# Metric allowlist — 受约束目录, 只有这些 metric 允许出图
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _MetricSpec:
    key: str
    title: str
    unit: str
    source: str  # "garmin" | "scale"
    # GarminData 行上的字段名, 或 None 表示走 WeightRecord
    garmin_field: Optional[str]
    # 把原始单位转成展示单位 (例如睡眠 分钟→小时)
    transform: Optional[Callable[[float], float]] = None
    # annotation 方向: "low_is_warn" 最低桶标 warn; "high_is_warn" 最高桶标 warn
    warn_direction: str = "low_is_warn"


def _sleep_min_to_hours(v: float) -> float:
    return round(v / 60.0, 1)


SUPPORTED_METRICS: Dict[str, _MetricSpec] = {
    "hrv": _MetricSpec(
        key="hrv", title="HRV 趋势", unit="ms", source="garmin",
        garmin_field="hrv", warn_direction="low_is_warn",
    ),
    "resting_hr": _MetricSpec(
        key="resting_hr", title="静息心率趋势", unit="bpm", source="garmin",
        garmin_field="resting_heart_rate", warn_direction="high_is_warn",
    ),
    "stress": _MetricSpec(
        key="stress", title="压力趋势", unit="", source="garmin",
        garmin_field="stress_level", warn_direction="high_is_warn",
    ),
    "sleep": _MetricSpec(
        key="sleep", title="睡眠时长趋势", unit="h", source="garmin",
        garmin_field="total_sleep_duration", transform=_sleep_min_to_hours,
        warn_direction="low_is_warn",
    ),
    "sleep_score": _MetricSpec(
        key="sleep_score", title="睡眠评分趋势", unit="分", source="garmin",
        garmin_field="sleep_score", warn_direction="low_is_warn",
    ),
    "steps": _MetricSpec(
        key="steps", title="步数趋势", unit="步", source="garmin",
        garmin_field="steps", warn_direction="low_is_warn",
    ),
    "body_battery": _MetricSpec(
        key="body_battery", title="身体电量趋势", unit="", source="garmin",
        garmin_field="body_battery_current", warn_direction="low_is_warn",
    ),
    "weight": _MetricSpec(
        key="weight", title="体重趋势", unit="kg", source="scale",
        garmin_field=None, warn_direction="high_is_warn",
    ),
}

# range → 天数
_RANGE_DAYS: Dict[str, int] = {"7d": 7, "2w": 14, "1m": 30, "3m": 90, "6m": 180}

# 数据点 (有值的日子) 少于此数 → 数据不足
MIN_POINTS = 3
# 非空桶少于此数 → 数据不足 (一条线至少 2 个桶才有"趋势")
MIN_BUCKETS = 2

# ---------------------------------------------------------------------------
# 富日级路径 (rich daily) — 仅对下列 metric 出"每日点 + 滚动均值 + 多源分线"图。
# 纯计算核心在 `chart_rich.compute_chart_rich`; 本文件只管路由 + DB I/O。
# 其余 metric 仍走原月/周分桶 compute_chart, 行为零变化 (back-compat)。
# ---------------------------------------------------------------------------

# 走富日级路径的 metric (其余 metric 保持月/周分桶不变)
_RICH_METRICS = frozenset({"hrv", "resting_hr"})

# Apple Watch 在 GarminData.data_source 上的标签 (见 device_source_priority.py)
_APPLE_WATCH_SOURCE = "apple-watch"


# ---------------------------------------------------------------------------
# 确定性图表意图检测 (纯正则, 无 LLM)
# ---------------------------------------------------------------------------

_CHART_VERB = re.compile(r"(绘制|画|展示|看一?下|看看|show|plot|draw)", re.IGNORECASE)
_CHART_NOUN = re.compile(r"(曲线|趋势|走势|图表|图|变化|chart|trend|graph)", re.IGNORECASE)

# metric 关键词 → metric key (顺序敏感: 更具体的在前)
_METRIC_KEYWORDS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(睡眠评分|睡眠分|sleep\s*score)", re.IGNORECASE), "sleep_score"),
    (re.compile(r"(hrv|心率变异|心律变异)", re.IGNORECASE), "hrv"),
    (re.compile(r"(静息心率|静息心跳|resting\s*hr|rhr)", re.IGNORECASE), "resting_hr"),
    (re.compile(r"(心率|心跳|heart\s*rate|heart\s*beat)", re.IGNORECASE), "resting_hr"),
    (re.compile(r"(身体电量|体力电量|body\s*battery|电量)", re.IGNORECASE), "body_battery"),
    (re.compile(r"(步数|步行|steps?)", re.IGNORECASE), "steps"),
    (re.compile(r"(压力|stress)", re.IGNORECASE), "stress"),
    (re.compile(r"(睡眠时长|睡眠时间|睡眠|sleep)", re.IGNORECASE), "sleep"),
    (re.compile(r"(体重|weight)", re.IGNORECASE), "weight"),
]

# range 提示
_RANGE_HINTS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(最近两周|近两周|两周|两个?星期|两星期|2\s*周|14\s*天|十四天|半个月|2\s*weeks?|two\s*weeks?)", re.IGNORECASE), "2w"),
    (re.compile(r"(最近一周|近一周|一周|7\s*天|七天|7d|1w|last\s*week|one\s*week)", re.IGNORECASE), "7d"),
    (re.compile(r"(半年|6\s*个?月|六个月|6m|180\s*天|6\s*months?)", re.IGNORECASE), "6m"),
    (re.compile(r"(近三月|三个月|3\s*个?月|3m|90\s*天|一个季度|季度|3\s*months?)", re.IGNORECASE), "3m"),
    (re.compile(r"(一个月|1\s*个?月|近一月|最近一月|30\s*天|1m|这个月|本月|1\s*month|last\s*month)", re.IGNORECASE), "1m"),
]


def detect_chart_request(query: str) -> Optional[Tuple[str, str]]:
    """确定性检测图表意图。

    命中条件:
    - 主动图表请求: (绘制/画/展示/看/show/plot) + (曲线/趋势/图/chart) + 已知 metric。
    - 省略动词的图表请求: 明确 range + (曲线/趋势/图/chart) + 已知 metric。

    第二类覆盖自然输入如"最近一周睡眠时长曲线 以及评估睡眠", 但仍避免把
    "我最近睡眠怎么样"这类非图表分析请求误判成图。
    返回 (metric_key, range)；未命中返回 None。range 默认 "6m"。
    """
    if not query:
        return None
    has_chart_noun = bool(_CHART_NOUN.search(query))

    metric: Optional[str] = None
    for pat, key in _METRIC_KEYWORDS:
        if pat.search(query):
            metric = key
            break
    if metric is None:
        return None

    rng = "6m"
    has_range_hint = False
    for pat, r in _RANGE_HINTS:
        if pat.search(query):
            rng = r
            has_range_hint = True
            break

    has_chart_verb = bool(_CHART_VERB.search(query))
    if not (has_chart_noun and (has_chart_verb or has_range_hint)):
        return None

    return (metric, rng)


# ---------------------------------------------------------------------------
# 分桶策略
# ---------------------------------------------------------------------------

_MONTH_NAMES = ["", "1月", "2月", "3月", "4月", "5月", "6月",
                "7月", "8月", "9月", "10月", "11月", "12月"]


def _bucket_key_month(d: date) -> Tuple[int, int]:
    return (d.year, d.month)


def _bucket_label_month(key: Tuple[int, int]) -> str:
    return _MONTH_NAMES[key[1]]


def _bucket_key_week(d: date) -> Tuple[int, int]:
    iso = d.isocalendar()
    return (iso[0], iso[1])  # (iso_year, iso_week)


def _bucket_label_week(key: Tuple[int, int]) -> str:
    return f"W{key[1]}"


def _date_label_day(d: date) -> str:
    return f"{d.month}/{d.day}"


# ---------------------------------------------------------------------------
# 纯计算核心 (无 DB, 无 LLM) — 可直接单测
# ---------------------------------------------------------------------------


def compute_chart(
    points: List[Tuple[date, float]],
    metric: str,
    rng: str,
) -> Optional[dict]:
    """把日级 (date, value) 序列聚合成分桶均值, 拼成 reva-ui line_chart dict。

    - 6m / 3m → 月度桶 (mean); 1m → 周桶 (mean); 7d → 日级值。
      空桶 points 填 null。
    - 数据点或非空桶过少 → None (调用方显"数据不足")。
    - annotation 由数据确定 (最低/最高桶), 文案为事实陈述, 无 LLM。

    points 必须是 (date, raw_value) — raw_value 已是 transform 之后的展示值由调用方决定;
    本函数对 value 不做单位换算 (换算在 _fetch 层做, 保持本函数纯粹分桶)。
    """
    spec = SUPPORTED_METRICS.get(metric)
    if spec is None:
        return None
    if len(points) < MIN_POINTS:
        return None

    # 确定桶的全集 (按数据真实跨度), 升序
    sorted_pts = sorted(points, key=lambda p: p[0])
    start_d = sorted_pts[0][0]
    end_d = sorted_pts[-1][0]

    if rng == "7d":
        by_day = {d: v for d, v in sorted_pts}
        x_labels: List[str] = []
        day_points: List[Optional[float]] = []
        cur = start_d
        while cur <= end_d:
            x_labels.append(_date_label_day(cur))
            day_points.append(by_day.get(cur))
            cur += timedelta(days=1)
        non_null = [(lbl, val) for lbl, val in zip(x_labels, day_points) if val is not None]
        if len(non_null) < MIN_BUCKETS:
            return None
        bucket_means = day_points
        grain = "每日值"
    else:
        use_week = rng == "1m"
        key_fn = _bucket_key_week if use_week else _bucket_key_month
        label_fn = _bucket_label_week if use_week else _bucket_label_month

        # 枚举 start..end 的所有桶 key (保证空桶也出 null, x 轴连续)
        bucket_order: List[Tuple[int, int]] = []
        seen = set()
        cur = start_d
        while cur <= end_d:
            k = key_fn(cur)
            if k not in seen:
                seen.add(k)
                bucket_order.append(k)
            cur += timedelta(days=1)

        # 聚合
        buckets: Dict[Tuple[int, int], List[float]] = {k: [] for k in bucket_order}
        for d, v in sorted_pts:
            k = key_fn(d)
            if k in buckets:
                buckets[k].append(v)

        x_labels = []
        bucket_means = []
        for k in bucket_order:
            x_labels.append(label_fn(k))
            vals = buckets[k]
            bucket_means.append(round(mean(vals), 1) if vals else None)

        non_null = [(lbl, val) for lbl, val in zip(x_labels, bucket_means) if val is not None]
        if len(non_null) < MIN_BUCKETS:
            return None

        grain = "周度均值" if use_week else "月度均值"

    # annotations: 标出最低 / 最高桶 (事实, 非 LLM)
    annotations: List[dict] = []
    lo_lbl, lo_val = min(non_null, key=lambda t: t[1])
    hi_lbl, hi_val = max(non_null, key=lambda t: t[1])
    if lo_lbl != hi_lbl:
        if spec.warn_direction == "low_is_warn":
            annotations.append({"x": lo_lbl, "label": f"最低 {lo_val}{spec.unit}", "kind": "warn"})
            annotations.append({"x": hi_lbl, "label": f"最高 {hi_val}{spec.unit}", "kind": "good"})
        else:  # high_is_warn
            annotations.append({"x": hi_lbl, "label": f"最高 {hi_val}{spec.unit}", "kind": "warn"})
            annotations.append({"x": lo_lbl, "label": f"最低 {lo_val}{spec.unit}", "kind": "good"})

    block = {
        "v": 1,
        "component": "line_chart",
        "title": spec.title,
        "unit": spec.unit,
        "x": x_labels,
        "series": [{"name": f"{grain}", "points": bucket_means}],
        "annotations": annotations,
        "source": spec.source,
        "data_note": f"基于 {len(points)} 天真实数据",
    }
    return block


# ---------------------------------------------------------------------------
# DB I/O 层
# ---------------------------------------------------------------------------


def _fetch_daily_points(
    db: Session, user_id: int, spec: _MetricSpec, days: int
) -> List[Tuple[date, float]]:
    """查真实日级 (date, value) 序列。0/None 视为缺值跳过。"""
    cutoff = date.today() - timedelta(days=days)
    out: List[Tuple[date, float]] = []

    if spec.source == "garmin":
        rows = (
            db.query(GarminData)
            .filter(
                GarminData.user_id == user_id,
                GarminData.record_date >= cutoff,
            )
            .order_by(GarminData.record_date.asc())
            .all()
        )
        # 同日多源 (apple-watch/garmin/ringconn) 取该日第一条非空值, 防重复计入桶
        per_day: Dict[date, float] = {}
        for r in rows:
            raw = getattr(r, spec.garmin_field, None)
            if raw is None or raw == 0:
                continue
            if r.record_date in per_day:
                continue
            val = spec.transform(float(raw)) if spec.transform else float(raw)
            per_day[r.record_date] = val
        out = sorted(per_day.items())

    elif spec.source == "scale":
        rows = (
            db.query(WeightRecord)
            .filter(
                WeightRecord.user_id == user_id,
                WeightRecord.record_date >= cutoff,
            )
            .order_by(WeightRecord.record_date.asc())
            .all()
        )
        per_day = {}
        for r in rows:
            if r.weight is None or r.weight == 0:
                continue
            if r.record_date in per_day:
                continue
            per_day[r.record_date] = float(r.weight)
        out = sorted(per_day.items())

    return out


def _fetch_daily_by_source(
    db: Session, user_id: int, spec: _MetricSpec, days: int
) -> Dict[str, Dict[date, float]]:
    """查真实日级值, 按 data_source 分组: {"garmin": {date: v}, "apple-watch": {...}}。

    富日级路径专用。同源同日多行取第一条非空 (唯一约束 (user,date,source) 下通常仅一行)。
    0/None 视为缺值跳过。Apple Watch 行 = data_source == "apple-watch"; 其余源 (garmin/
    ringconn/oura/...) 当前合并归入 "garmin" 主线 (本图只双源分线: Garmin 主线 + Apple Watch)。
    """
    cutoff = date.today() - timedelta(days=days)
    garmin: Dict[date, float] = {}
    apple: Dict[date, float] = {}

    rows = (
        db.query(GarminData)
        .filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= cutoff,
        )
        .order_by(GarminData.record_date.asc())
        .all()
    )
    for r in rows:
        raw = getattr(r, spec.garmin_field, None)
        if raw is None or raw == 0:
            continue
        val = spec.transform(float(raw)) if spec.transform else float(raw)
        src = getattr(r, "data_source", None) or "garmin"
        target = apple if src == _APPLE_WATCH_SOURCE else garmin
        if r.record_date not in target:  # 同源同日取首条非空
            target[r.record_date] = val

    return {"garmin": garmin, _APPLE_WATCH_SOURCE: apple}


def _apply_component_contract(
    block: Optional[dict], metric: str, rng: str, component: str
) -> Optional[dict]:
    """把内部图表 block 包装成客户端协商的 GenUI 组件形态。"""
    if block is None:
        return None
    if component not in _SUPPORTED_COMPONENTS:
        return None

    out = dict(block)
    out["component"] = component
    if component == METRIC_LINE_CHART_COMPONENT:
        out["schema"] = METRIC_LINE_CHART_SCHEMA
        out["metric"] = metric
        out["range"] = rng
    return out


def build_line_chart(
    db: Session,
    user_id: int,
    metric: str,
    range: str = "6m",
    *,
    component: str = LINE_CHART_COMPONENT,
) -> Optional[dict]:
    """构建 reva-ui line_chart / metric_line_chart block (真数据)。

    metric 不在 allowlist / range 非法 / 数据不足 → None (调用方显"数据不足")。
    返回的 dict 即 GenUI 契约;数值全部来自 DB。

    路由: HRV / 静息心率 (_RICH_METRICS) → compute_chart_rich (每日点 + 7/30 日滚动
    均值 + Garmin/Apple Watch 多源分线 + latest annotation); 其余 metric → compute_chart
    (月/周分桶, 行为零变化, back-compat)。
    """
    spec = SUPPORTED_METRICS.get(metric)
    if spec is None:
        return None
    if component not in _SUPPORTED_COMPONENTS:
        return None
    days = _RANGE_DAYS.get(range)
    if days is None:
        return None

    # 富日级路径仅适用于 garmin 源 metric (有 data_source 分线意义)。
    if metric in _RICH_METRICS and spec.source == "garmin":
        from app.services.genui.chart_rich import compute_chart_rich
        by_source = _fetch_daily_by_source(db, user_id, spec, days)
        block = compute_chart_rich(
            by_source["garmin"], by_source[_APPLE_WATCH_SOURCE], metric, range
        )
        return _apply_component_contract(block, metric, range, component)

    points = _fetch_daily_points(db, user_id, spec, days)
    block = compute_chart(points, metric, range)
    return _apply_component_contract(block, metric, range, component)


# ---------------------------------------------------------------------------
# 渲染 fenced block
# ---------------------------------------------------------------------------


def render_reva_ui_block(block: dict) -> str:
    """把 block dict 渲染成 ```reva-ui fenced 文本 (嵌进 assistant 消息)。"""
    payload = json.dumps(block, ensure_ascii=False, separators=(",", ":"))
    return f"```reva-ui\n{payload}\n```"
