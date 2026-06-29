r"""GenUI line_chart 构建器 — 确定性查真实日级序列, 聚合分桶, 拼 `reva-ui` block.

数据来源 (与 mobile `indicator-history` 同一日级源, 见 `mobile/services/trends.ts`
的 `fetchGarminMetricTrend`):
  - GarminData 日行 (`backend/app/models/daily_health.py`):
      hrv / resting_heart_rate / stress_level / total_sleep_duration
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
    "weight": _MetricSpec(
        key="weight", title="体重趋势", unit="kg", source="scale",
        garmin_field=None, warn_direction="high_is_warn",
    ),
}

# range → 天数
_RANGE_DAYS: Dict[str, int] = {"1m": 30, "3m": 90, "6m": 180}

# 数据点 (有值的日子) 少于此数 → 数据不足
MIN_POINTS = 3
# 非空桶少于此数 → 数据不足 (一条线至少 2 个桶才有"趋势")
MIN_BUCKETS = 2


# ---------------------------------------------------------------------------
# 确定性图表意图检测 (纯正则, 无 LLM)
# ---------------------------------------------------------------------------

_CHART_VERB = re.compile(r"(绘制|画|展示|看一?下|看看|show|plot|draw)", re.IGNORECASE)
_CHART_NOUN = re.compile(r"(曲线|趋势|走势|图表|图|变化|chart|trend|graph)", re.IGNORECASE)

# metric 关键词 → metric key (顺序敏感: 更具体的在前)
_METRIC_KEYWORDS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(hrv|心率变异|心律变异)", re.IGNORECASE), "hrv"),
    (re.compile(r"(静息心率|静息心跳|resting\s*hr|rhr)", re.IGNORECASE), "resting_hr"),
    (re.compile(r"(压力|stress)", re.IGNORECASE), "stress"),
    (re.compile(r"(睡眠时长|睡眠时间|睡眠|sleep)", re.IGNORECASE), "sleep"),
    (re.compile(r"(体重|weight)", re.IGNORECASE), "weight"),
]

# range 提示
_RANGE_HINTS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(半年|6\s*个?月|六个月|6m|180\s*天|6\s*months?)", re.IGNORECASE), "6m"),
    (re.compile(r"(近三月|三个月|3\s*个?月|3m|90\s*天|一个季度|季度|3\s*months?)", re.IGNORECASE), "3m"),
    (re.compile(r"(一个月|1\s*个?月|近一月|最近一月|30\s*天|1m|这个月|本月|1\s*month|last\s*month)", re.IGNORECASE), "1m"),
]


def detect_chart_request(query: str) -> Optional[Tuple[str, str]]:
    """确定性检测图表意图。

    命中条件: (绘制/画/展示/看/show/plot) + (曲线/趋势/图/chart) + 已知 metric 关键词。
    返回 (metric_key, range)；未命中返回 None。range 默认 "6m"。
    """
    if not query:
        return None
    if not (_CHART_VERB.search(query) and _CHART_NOUN.search(query)):
        return None

    metric: Optional[str] = None
    for pat, key in _METRIC_KEYWORDS:
        if pat.search(query):
            metric = key
            break
    if metric is None:
        return None

    rng = "6m"
    for pat, r in _RANGE_HINTS:
        if pat.search(query):
            rng = r
            break

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


# ---------------------------------------------------------------------------
# 纯计算核心 (无 DB, 无 LLM) — 可直接单测
# ---------------------------------------------------------------------------


def compute_chart(
    points: List[Tuple[date, float]],
    metric: str,
    rng: str,
) -> Optional[dict]:
    """把日级 (date, value) 序列聚合成分桶均值, 拼成 reva-ui line_chart dict。

    - 6m / 3m → 月度桶 (mean); 1m → 周桶 (mean)。空桶 points 填 null。
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

    use_week = rng == "1m"
    key_fn = _bucket_key_week if use_week else _bucket_key_month
    label_fn = _bucket_label_week if use_week else _bucket_label_month

    # 确定桶的全集 (按数据真实跨度), 升序
    sorted_pts = sorted(points, key=lambda p: p[0])
    start_d = sorted_pts[0][0]
    end_d = sorted_pts[-1][0]

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

    x_labels: List[str] = []
    bucket_means: List[Optional[float]] = []
    for k in bucket_order:
        x_labels.append(label_fn(k))
        vals = buckets[k]
        bucket_means.append(round(mean(vals), 1) if vals else None)

    non_null = [(lbl, val) for lbl, val in zip(x_labels, bucket_means) if val is not None]
    if len(non_null) < MIN_BUCKETS:
        return None

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

    grain = "周度均值" if use_week else "月度均值"
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


def build_line_chart(
    db: Session, user_id: int, metric: str, range: str = "6m"
) -> Optional[dict]:
    """构建 reva-ui line_chart block (真数据)。

    metric 不在 allowlist / range 非法 / 数据不足 → None (调用方显"数据不足")。
    返回的 dict 即 §3.2 契约;数值全部来自 DB。
    """
    spec = SUPPORTED_METRICS.get(metric)
    if spec is None:
        return None
    days = _RANGE_DAYS.get(range)
    if days is None:
        return None

    points = _fetch_daily_points(db, user_id, spec, days)
    return compute_chart(points, metric, range)


# ---------------------------------------------------------------------------
# 渲染 fenced block
# ---------------------------------------------------------------------------


def render_reva_ui_block(block: dict) -> str:
    """把 block dict 渲染成 ```reva-ui fenced 文本 (嵌进 assistant 消息)。"""
    payload = json.dumps(block, ensure_ascii=False, separators=(",", ":"))
    return f"```reva-ui\n{payload}\n```"
