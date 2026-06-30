r"""GenUI 富日级图表纯计算核心 (无 DB, 无 LLM)。

`compute_chart_rich` 把日级多源 (Garmin / Apple Watch) 序列拼成一个"富"reva-ui
line_chart dict: 每日点 + 7/30 日滚动均值 + 多源分线 + latest annotation。

铁律 (R4): 所有数值来自入参 {date: value} (上游 DB 真查) + 纯数学 (滚动均值)。
LLM 不参与 —— `grep -n "llm\|LLM\|_call_llm" chart_rich.py` 无命中。

从 `chart_builder.py` 拆出以守复杂度预算 (单文件 ≤500 行)。依赖方向单向:
本模块 → chart_builder 的纯常量/规格 (SUPPORTED_METRICS / MIN_POINTS), chart_builder
反向只在函数内 lazy-import `compute_chart_rich`, 无模块级环。
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import mean
from typing import Dict, List, Optional

from app.services.genui.chart_builder import SUPPORTED_METRICS, MIN_POINTS

# 滚动均值窗口 (日历天). 标准 trailing window。
_ROLL_7D = 7
_ROLL_30D = 30

# Apple Watch 在 GarminData.data_source 上的标签 (见 device_source_priority.py)
_APPLE_WATCH_SOURCE = "apple-watch"


def _date_label(d: date) -> str:
    """日级 x 轴标签 (ISO 短日期, 月-日). 渲染端把刻度抽稀到 ≤8 个。"""
    return f"{d.month:02d}-{d.day:02d}"


def _align_series(
    axis: List[date], by_day: Dict[date, float]
) -> List[Optional[float]]:
    """把 {date: value} 对齐到日级 axis, 缺日填 None。长度 == len(axis)。"""
    return [by_day.get(d) for d in axis]


def _rolling_mean(
    axis: List[date], primary_by_day: Dict[date, float], window_days: int
) -> List[Optional[float]]:
    """trailing 日历窗口滚动均值, 与 axis 等长。

    对 axis 上第 i 天 (日期 d_i), 取 [d_i-(window-1), d_i] 内 primary 已有的非空值求均值;
    窗口内无任何值 → None。窗口按"日历天"而非"数据点个数"——缺数据的日子不占窗位,
    但也不被插值, 完全由真实落值决定 (确定性, 无 LLM, 无补点)。
    """
    out: List[Optional[float]] = []
    for d_i in axis:
        lo = d_i - timedelta(days=window_days - 1)
        vals = [v for dd, v in primary_by_day.items() if lo <= dd <= d_i]
        out.append(round(mean(vals), 1) if vals else None)
    return out


def compute_chart_rich(
    garmin_by_day: Dict[date, float],
    apple_by_day: Dict[date, float],
    metric: str,
    rng: str,
) -> Optional[dict]:
    """把日级多源序列拼成"富"reva-ui line_chart dict (每日点 + 7/30 日滚动均值 + 多源分线)。

    入参均为 {date: value} (值已 transform 到展示单位)。两源可各自有/无数据。
    - x = 数据真实跨度内的每日日期标签 (升序), 每条 series.points 等长, 缺日填 null。
    - series (≤5, 每条带 role):
        Garmin 夜间 HRV     role=raw     (garmin 源日级原始)
        Apple Watch HRV     role=device  (仅当有 apple-watch 源数据)
        7日滚动均值          role=avg_7d  (对 primary 合并日级求滚动均值)
        30日滚动均值         role=avg_30d
      primary (滚动均值的底) = 逐日取"按 device_source_priority 该 metric 的优先源",
      garmin 缺值时回落 apple-watch (与 twin builder 合并语义一致), 但两源仍各自单列。
    - annotations: 单条 latest (最新有值日 + 值 + 源), 事实陈述, 无 LLM。
    - 数据点过少 (合并后 < MIN_POINTS) → None (调用方显"数据不足")。
    """
    spec = SUPPORTED_METRICS.get(metric)
    if spec is None:
        return None

    # primary: 逐日取优先源值 (priority_for(metric) 决定 garmin/apple 谁先)。
    # 这里只有两源参与 (garmin + apple-watch), 用其优先顺序逐日挑。
    from app.services.device_source_priority import priority_for

    prio = priority_for(spec.garmin_field or metric)
    garmin_first = prio.index("garmin") <= prio.index(_APPLE_WATCH_SOURCE) \
        if (_APPLE_WATCH_SOURCE in prio and "garmin" in prio) else True

    all_days = set(garmin_by_day) | set(apple_by_day)
    if len(all_days) < MIN_POINTS:
        return None

    primary_by_day: Dict[date, float] = {}
    for d in all_days:
        if garmin_first:
            primary_by_day[d] = garmin_by_day.get(d, apple_by_day.get(d))  # type: ignore[assignment]
        else:
            primary_by_day[d] = apple_by_day.get(d, garmin_by_day.get(d))  # type: ignore[assignment]

    start_d = min(all_days)
    end_d = max(all_days)
    axis: List[date] = []
    cur = start_d
    while cur <= end_d:
        axis.append(cur)
        cur += timedelta(days=1)

    x_labels = [_date_label(d) for d in axis]

    display_title = spec.title.removesuffix("趋势")
    series: List[dict] = [
        {
            "name": "Garmin 夜间 HRV" if metric == "hrv" else f"Garmin {display_title}",
            "role": "raw",
            "points": _align_series(axis, garmin_by_day),
        }
    ]
    # Apple Watch 分线: 仅当确有 apple-watch 源数据 (不伪造)。
    if apple_by_day:
        series.append({
            "name": "Apple Watch HRV" if metric == "hrv" else f"Apple Watch {display_title}",
            "role": "device",
            "points": _align_series(axis, apple_by_day),
        })
    series.append({
        "name": "7日滚动均值",
        "role": "avg_7d",
        "points": _rolling_mean(axis, primary_by_day, _ROLL_7D),
    })
    series.append({
        "name": "30日滚动均值",
        "role": "avg_30d",
        "points": _rolling_mean(axis, primary_by_day, _ROLL_30D),
    })

    # latest annotation: 最新有值日 (primary), 标注值 + 源 (事实)。
    latest_day = end_d  # all_days 的 max 必有 primary 值
    latest_val = primary_by_day[latest_day]
    if garmin_first:
        latest_src = "Garmin" if latest_day in garmin_by_day else "Apple Watch"
    else:
        latest_src = "Apple Watch" if latest_day in apple_by_day else "Garmin"
    unit_sfx = f" {spec.unit}" if spec.unit else ""
    annotations: List[dict] = [{
        "x": _date_label(latest_day),
        "label": f"最新 {latest_val}{unit_sfx} · {latest_src}",
        "kind": "latest",
    }]

    g_days = len(garmin_by_day)
    a_days = len(apple_by_day)
    total_days = len(all_days)
    src_note = f"Garmin {g_days}d"
    if a_days:
        src_note += f" + Apple Watch {a_days}d"
    block = {
        "v": 1,
        "component": "line_chart",
        "title": spec.title,
        "unit": spec.unit,
        "x": x_labels,
        "series": series,
        "annotations": annotations,
        "source": spec.source,
        "data_note": f"基于 {total_days} 天真实数据 · 每日 · {src_note}",
    }
    return block
