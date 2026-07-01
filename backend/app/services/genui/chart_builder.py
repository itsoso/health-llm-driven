r"""GenUI line_chart 构建器 — 确定性查真实日级序列, 聚合分桶, 拼 `reva-ui` block.

数据来源 (与 mobile `indicator-history` 同一日级源, 见 `mobile/services/trends.ts`
的 `fetchGarminMetricTrend`):
  - GarminData 日行 (`backend/app/models/daily_health.py`):
      hrv / resting_heart_rate / stress_level / total_sleep_duration /
      sleep_score / steps / body_battery_current / spo2_avg
  - WeightRecord 日行 (`backend/app/models/weight.py`): weight / body_fat_percentage
  - BloodPressureRecord 日行 (`backend/app/models/blood_pressure.py`): systolic / diastolic
  - WaistRecord 日行 (`backend/app/models/waist.py`): waist_cm
  - BasicHealthData 日行 (`backend/app/models/basic_health.py`): blood_glucose

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

from app.models.basic_health import BasicHealthData
from app.models.blood_pressure import BloodPressureRecord
from app.models.daily_health import GarminData
from app.models.waist import WaistRecord
from app.models.weight import WeightRecord

LINE_CHART_COMPONENT = "line_chart"
METRIC_LINE_CHART_COMPONENT = "metric_line_chart"
METRIC_LINE_CHART_SCHEMA = "reva.metric_line_chart.v1"
METRIC_EMPTY_STATE_COMPONENT = "metric_empty_state"
METRIC_EMPTY_STATE_SCHEMA = "reva.metric_empty_state.v1"
_CHART_COMPONENTS = {LINE_CHART_COMPONENT, METRIC_LINE_CHART_COMPONENT}

# ---------------------------------------------------------------------------
# Metric allowlist — 受约束目录, 只有这些 metric 允许出图
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _MetricSpec:
    key: str
    title: str
    unit: str
    source: str  # "garmin" | "scale" | "blood_pressure" | "waist" | "basic"
    # 数据源模型行上的字段名；历史字段名沿用 garmin_field 以避免大范围改动。
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
        garmin_field="weight", warn_direction="high_is_warn",
    ),
    "bp_systolic": _MetricSpec(
        key="bp_systolic", title="收缩压趋势", unit="mmHg", source="blood_pressure",
        garmin_field="systolic", warn_direction="high_is_warn",
    ),
    "bp_diastolic": _MetricSpec(
        key="bp_diastolic", title="舒张压趋势", unit="mmHg", source="blood_pressure",
        garmin_field="diastolic", warn_direction="high_is_warn",
    ),
    "waist": _MetricSpec(
        key="waist", title="腰围趋势", unit="cm", source="waist",
        garmin_field="waist_cm", warn_direction="high_is_warn",
    ),
    "body_fat": _MetricSpec(
        key="body_fat", title="体脂率趋势", unit="%", source="scale",
        garmin_field="body_fat_percentage", warn_direction="high_is_warn",
    ),
    "blood_glucose": _MetricSpec(
        key="blood_glucose", title="血糖趋势", unit="mmol/L", source="basic",
        garmin_field="blood_glucose", warn_direction="high_is_warn",
    ),
    "spo2": _MetricSpec(
        key="spo2", title="血氧趋势", unit="%", source="garmin",
        garmin_field="spo2_avg", warn_direction="low_is_warn",
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
    (re.compile(r"(舒张压|低压|diastolic)", re.IGNORECASE), "bp_diastolic"),
    (re.compile(r"(收缩压|高压|血压|blood\s*pressure|systolic)", re.IGNORECASE), "bp_systolic"),
    (re.compile(r"(腰围|waist)", re.IGNORECASE), "waist"),
    (re.compile(r"(体脂率|体脂|body\s*fat)", re.IGNORECASE), "body_fat"),
    (re.compile(r"(空腹血糖|血糖|glucose|blood\s*sugar)", re.IGNORECASE), "blood_glucose"),
    (re.compile(r"(血氧饱和度|血氧|spo2|spO2|氧饱和)", re.IGNORECASE), "spo2"),
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


# 多指标叠加图上限 (避免混叠指标过多导致图表拥挤)
MAX_MULTI_METRICS = 3


def detect_chart_request(query: str) -> Optional[Tuple[str, str]]:
    """确定性检测图表意图 (单指标; 取第一个命中的 metric)。

    命中条件:
    - 主动图表请求: (绘制/画/展示/看/show/plot) + (曲线/趋势/图/chart) + 已知 metric。
    - 省略动词的图表请求: 明确 range + (曲线/趋势/图/chart) + 已知 metric。

    第二类覆盖自然输入如"最近一周睡眠时长曲线 以及评估睡眠", 但仍避免把
    "我最近睡眠怎么样"这类非图表分析请求误判成图。
    返回 (metric_key, range)；未命中返回 None。range 默认 "6m"。

    多指标叠加请求 (如"HRV和心率") 请用 `detect_chart_requests` (复数)。
    本函数仍返回第一个命中的 metric, 保持既有单指标调用方零回归。
    """
    matches = detect_chart_requests(query)
    if not matches:
        return None
    return matches[0]


def detect_chart_requests(query: str) -> List[Tuple[str, str]]:
    """确定性检测图表意图 (多指标; 返回所有命中的 metric, 共享同一 range)。

    命中条件与 `detect_chart_request` 相同 (图表名词 + (动词 或 range 提示) + ≥1 metric)。
    返回 [(metric_key, range), ...]:
    - 保持稳定顺序 (按 _METRIC_KEYWORDS 声明序), 去重 (同 metric 只出一次)。
    - 所有条目共享单次检测出的 range (默认 "6m")。
    - "HRV和心率" → [("hrv", rng), ("resting_hr", rng)]
    - "HRV" → [("hrv", rng)]
    - "心率变异和静息心率" → [("hrv", rng), ("resting_hr", rng)] (dedup 若同 metric)
    - 命中 metric 超过 MAX_MULTI_METRICS 条 → 只取前 MAX_MULTI_METRICS 条 (稳定序)。
    未命中 (无 metric / 非图表意图) → []。
    """
    if not query:
        return []
    has_chart_noun = bool(_CHART_NOUN.search(query))

    metrics: List[str] = []
    seen: set = set()
    for pat, key in _METRIC_KEYWORDS:
        if key in seen:
            continue
        if pat.search(query):
            metrics.append(key)
            seen.add(key)
    if not metrics:
        return []

    rng = "6m"
    has_range_hint = False
    for pat, r in _RANGE_HINTS:
        if pat.search(query):
            rng = r
            has_range_hint = True
            break

    has_chart_verb = bool(_CHART_VERB.search(query))
    if not (has_chart_noun and (has_chart_verb or has_range_hint)):
        return []

    return [(m, rng) for m in metrics[:MAX_MULTI_METRICS]]


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


def _coerce_value(raw: object, transform: Optional[Callable[[float], float]] = None) -> Optional[float]:
    if raw is None or raw == 0:
        return None
    val = float(raw)
    return transform(val) if transform else val


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
            val = _coerce_value(getattr(r, spec.garmin_field, None), spec.transform)
            if val is None:
                continue
            if r.record_date in per_day:
                continue
            per_day[r.record_date] = val
        out = sorted(per_day.items())

    elif spec.source == "scale":
        field_name = spec.garmin_field or "weight"
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
            val = _coerce_value(getattr(r, field_name, None), spec.transform)
            if val is None:
                continue
            if r.record_date in per_day:
                continue
            per_day[r.record_date] = val
        out = sorted(per_day.items())

    elif spec.source == "blood_pressure":
        rows = (
            db.query(BloodPressureRecord)
            .filter(
                BloodPressureRecord.user_id == user_id,
                BloodPressureRecord.record_date >= cutoff,
            )
            .order_by(BloodPressureRecord.record_date.asc())
            .all()
        )
        per_day_values: Dict[date, List[float]] = {}
        for r in rows:
            val = _coerce_value(getattr(r, spec.garmin_field, None), spec.transform)
            if val is None:
                continue
            per_day_values.setdefault(r.record_date, []).append(val)
        out = sorted((d, round(mean(vals), 1)) for d, vals in per_day_values.items() if vals)

    elif spec.source == "waist":
        rows = (
            db.query(WaistRecord)
            .filter(
                WaistRecord.user_id == user_id,
                WaistRecord.record_date >= cutoff,
            )
            .order_by(WaistRecord.record_date.asc(), WaistRecord.id.desc())
            .all()
        )
        per_day = {}
        for r in rows:
            val = _coerce_value(getattr(r, spec.garmin_field, None), spec.transform)
            if val is None:
                continue
            if r.record_date in per_day:
                continue
            per_day[r.record_date] = val
        out = sorted(per_day.items())

    elif spec.source == "basic":
        rows = (
            db.query(BasicHealthData)
            .filter(
                BasicHealthData.user_id == user_id,
                BasicHealthData.record_date >= cutoff,
            )
            .order_by(BasicHealthData.record_date.asc(), BasicHealthData.id.desc())
            .all()
        )
        per_day = {}
        for r in rows:
            val = _coerce_value(getattr(r, spec.garmin_field, None), spec.transform)
            if val is None:
                continue
            if r.record_date in per_day:
                continue
            per_day[r.record_date] = val
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
    if component not in _CHART_COMPONENTS:
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
    if component not in _CHART_COMPONENTS:
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


# 多指标叠加图 series 名里显示单位 (轴无法承载多单位)
def _metric_display_name(spec: _MetricSpec) -> str:
    """指标短名: title 去掉 "趋势" 后缀并 strip (HRV 的 title 是 "HRV 趋势", 带空格)。"""
    return spec.title.removesuffix("趋势").strip()


def _metric_series_name(spec: _MetricSpec) -> str:
    """多指标叠加线名: 指标名 + 单位, 如 "HRV（ms）"、"静息心率（bpm）"。

    无单位 metric (压力/身体电量) 只出名字。名字里带单位是因为叠加图 y 轴混合单位,
    无法给单一轴单位, 只能靠 series 名区分。
    """
    base = _metric_display_name(spec)
    return f"{base}（{spec.unit}）" if spec.unit else base


def build_multi_metric_chart(
    db: Session,
    user_id: int,
    metrics: List[str],
    range: str = "6m",
    *,
    component: str = LINE_CHART_COMPONENT,
) -> Optional[dict]:
    """把多个 metric 叠加进一张 reva-ui line_chart (每 metric 一条 7 日滚动均值线)。

    - 每个 metric 取其"主日级序列"(合并全源, 与单指标 build 的日级取值一致),
      对该序列算 7 日滚动均值 → 一条干净的对比线 (不含原始/多源/30日, 避免拥挤)。
    - x = 各 metric 日级日期并集 (升序), 每条 series.points 对齐等长, 缺日 null。
    - series.role = "value" (渲染端多序列调色板自动上色区分)。
    - unit: metric 单位不同 → "" (渲染端不出单一 y 轴单位); 全同 → 该单位。
    - title = 各 metric 名 join, 如 "HRV × 静息心率 趋势对比"。
    - data_note = 混合单位说明 + 真实天数基数。
    - annotations = [] (混合单位下单条 latest callout 会误导)。
    - 铁律 (R4): 所有数值来自 DB 主日级序列 + 滚动均值, 无 LLM。
    - fail-soft: 某 metric 数据不足 → 略过该 metric 的 series (不伪造);
      可用 metric < 1 → None (调用方 fall through)。
    """
    if component not in _CHART_COMPONENTS:
        return None
    days = _RANGE_DAYS.get(range)
    if days is None:
        return None

    from app.services.genui.chart_rich import _rolling_mean, _ROLL_7D

    # 去重保序 + 只保留 allowlist 内 metric
    ordered: List[str] = []
    seen: set = set()
    for m in metrics:
        if m in seen or m not in SUPPORTED_METRICS:
            continue
        seen.add(m)
        ordered.append(m)
    if not ordered:
        return None

    # 逐 metric 取主日级序列 {date: value}, 数据不足的 metric 略过 (不伪造)
    per_metric: List[Tuple[_MetricSpec, Dict[date, float]]] = []
    for m in ordered:
        spec = SUPPORTED_METRICS[m]
        by_day = dict(_fetch_daily_points(db, user_id, spec, days))
        if len(by_day) < MIN_POINTS:
            continue  # fail-soft: 略过数据不足的 metric
        per_metric.append((spec, by_day))

    if not per_metric:
        return None

    # x = 所有可用 metric 的日级日期并集 (升序)
    all_days: set = set()
    for _spec, by_day in per_metric:
        all_days |= set(by_day.keys())
    axis: List[date] = sorted(all_days)
    x_labels = [_date_label_day(d) for d in axis]

    # 每 metric 一条 7 日滚动均值线, 与 axis 对齐
    series: List[dict] = []
    units: set = set()
    for spec, by_day in per_metric:
        rolled = _rolling_mean(axis, by_day, _ROLL_7D)
        series.append({
            "name": _metric_series_name(spec),
            "role": "value",
            "points": rolled,
        })
        units.add(spec.unit)

    if not series:
        return None

    # 单位: 全同 → 该单位; 混合 → "" (渲染端不出 y 轴单位)
    unit = next(iter(units)) if len(units) == 1 else ""

    titles = [_metric_display_name(spec) for spec, _ in per_metric]
    title = f"{' × '.join(titles)} 趋势对比"

    unit_desc = "、".join(
        f"{_metric_display_name(spec)} 单位 {spec.unit}"
        for spec, _ in per_metric if spec.unit
    )
    total_days = len(all_days)
    if unit and len(units) == 1:
        data_note = f"单位 {unit} · 7 日滚动均值 · 基于 {total_days} 天真实数据"
    elif unit_desc:
        data_note = f"{unit_desc}，单位不同仅供趋势对比 · 7 日滚动均值 · 基于 {total_days} 天真实数据"
    else:
        data_note = f"7 日滚动均值 · 基于 {total_days} 天真实数据"

    block = {
        "v": 1,
        "component": "line_chart",
        "title": title,
        "unit": unit,
        "x": x_labels,
        "series": series,
        "annotations": [],
        # source 留空: 多指标叠加跨多个数据源, 单一 "来源" 标签会误导; 基数走 data_note。
        "source": "",
        "data_note": data_note,
    }
    # 多指标叠加沿用第一个 metric 作 component contract 的 metric 标识 (客户端仅用于分析埋点)
    return _apply_component_contract(block, per_metric[0][0].key, range, component)


def build_empty_state(metric: str, range: str = "6m") -> Optional[dict]:
    """为已识别的图表意图构建受 schema 约束的数据不足卡片。

    这是 GenUI 的 fail-loud 兜底: 不补点、不让 LLM 手画图, 而是明确告诉客户端
    当前缺真实数据, 并给出可执行的数据补齐动作。
    """
    spec = SUPPORTED_METRICS.get(metric)
    if spec is None or range not in _RANGE_DAYS:
        return None

    title_base = spec.title[:-2] if spec.title.endswith("趋势") else spec.title
    return {
        "v": 1,
        "schema": METRIC_EMPTY_STATE_SCHEMA,
        "component": METRIC_EMPTY_STATE_COMPONENT,
        "metric": metric,
        "range": range,
        "title": f"{title_base}数据不足",
        "message": "暂无足够数据，至少需要 3 天真实记录后才能生成趋势图。",
        "suggestions": [
            "同步 HealthKit 或可穿戴设备数据",
            "补录最近几天的关键指标",
            "等新数据进入后再生成趋势",
        ],
        "boundary": "仅用于健康管理参考，不替代诊断或治疗。",
    }


# ---------------------------------------------------------------------------
# 渲染 fenced block
# ---------------------------------------------------------------------------


def render_reva_ui_block(block: dict) -> str:
    """把 block dict 渲染成 ```reva-ui fenced 文本 (嵌进 assistant 消息)。"""
    payload = json.dumps(block, ensure_ascii=False, separators=(",", ":"))
    return f"```reva-ui\n{payload}\n```"


# ---------------------------------------------------------------------------
# 确定性护栏: 剥离 / 占位 LLM 伪造的 reva-ui block
# ---------------------------------------------------------------------------
#
# 铁律 (R4): reva-ui 图表 block **只能**由本模块的确定性短路 (agent
# `_maybe_genui_chart_events` / orchestrator `_maybe_build_genui_chart`) 产出,
# 数值全部来自 DB 查询。LLM 见过历史里的 reva-ui block 会**模仿**这个格式并**编造**
# 数据 (实测: 编出 "多源合并: Apple Watch + Garmin + RingConn")。因此:
#   - 喂给 LLM 的历史里, 助手消息的 reva-ui block 必须换成占位符 (LLM 无从模仿)。
#   - LLM 生成的最终文本落库/下发前, reva-ui block 必须整块剥掉 (防御纵深)。
# 短路自身产出的 block 走的是独立、更早返回的路径, 不经过这两处 → 不受影响。

# 匹配一个 ```reva-ui fenced block。opener 行可带尾随空白; 首选匹配到成对的 ``` 闭合;
# re.DOTALL 让 block 体跨行。闭合 fence 前允许可选换行 (block 体可能不以换行结尾)。
_REVA_UI_CLOSED_RE = re.compile(
    r"```reva-ui[^\n]*\n.*?\n?```",
    re.DOTALL,
)
# 未闭合 (缺尾 ```) 的 opener → 从 opener 一直吃到文本结尾。仅在闭合形全部移除后再跑,
# 避免把一段闭合 block 之后、下一段无关 fence 之前的内容误吞。
_REVA_UI_UNCLOSED_RE = re.compile(
    r"```reva-ui[^\n]*(?:\n.*)?\Z",
    re.DOTALL,
)


def _collapse_blank_runs(text: str) -> str:
    """把剥离后残留的 3+ 连续换行压回 2 个 (即最多一个空行), 并 strip 首尾空白。"""
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def strip_reva_ui_blocks(text: str) -> str:
    """移除文本里所有 ```reva-ui``` fenced block, 保留其余内容 (其它 fence / 散文原样)。

    - 成对闭合的 block: 整块删除 (支持多个)。
    - 未闭合的 opener (没有闭合 fence): 从 opener 删到文本结尾 —— 半个伪造 block
      也绝不能泄漏给用户。
    - ```json 等其它语言的 fence、普通散文: 原样保留。
    - 清理剥离后残留的多余空行。

    纯函数, 可单测。None / 空串安全返回原值。
    """
    if not text or "reva-ui" not in text:
        return text
    cleaned = _REVA_UI_CLOSED_RE.sub("", text)
    if "```reva-ui" in cleaned:
        # 剩下的一定是未闭合 opener (闭合形已全被上一步吃掉)。
        cleaned = _REVA_UI_UNCLOSED_RE.sub("", cleaned)
    return _collapse_blank_runs(cleaned)


def placeholder_reva_ui_blocks(text: str, placeholder: str = "［图表已展示］") -> str:
    """把文本里的 ```reva-ui``` block 换成短占位符 (而非删除)。

    用于喂给 LLM 的历史: LLM 看到占位符而非真格式, 就无从模仿 reva-ui 结构编数据,
    同时仍知道"上一轮展示过一张图表"的语义。闭合 block 换成占位符; 未闭合 opener
    (历史里极少见) 同样换成占位符。其它内容不动。

    纯函数, 可单测。None / 空串安全返回原值。
    """
    if not text or "reva-ui" not in text:
        return text
    replaced = _REVA_UI_CLOSED_RE.sub(placeholder, text)
    if "```reva-ui" in replaced:
        replaced = _REVA_UI_UNCLOSED_RE.sub(placeholder, replaced)
    return _collapse_blank_runs(replaced)
