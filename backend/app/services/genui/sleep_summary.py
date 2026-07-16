"""GenUI sleep_summary 构建器 — 确定性把睡眠分析打成结构化 reva-ui 卡片。

汇总卡族第二张(diet 之后),复用移动端 StatusSummary scaffold(壳/观察/进度条)。
数据来自 health_query(sleep) = `analyze_sleep_quality`(daily_data 逐夜 + 均值);observations
由本模块**确定性派生**(只读测得值 + 通用时长/深睡参考,factual、非诊断 —— 守 R4:绝不消费
服务端 `quality_assessment`、绝不自判睡眠好坏)。actions 沿用只读 route.open。

**跨端契约铁律**(diet 上线即坏的教训):块内 `v` 是**整数 1**(移动端 fence parser 校验
v===1),cap token 才用字符串 "genui-sleep-summary-v1";字段名与 mobile SleepSummaryCard 的
parse* 一字对齐(range_label/nights[date,score,duration_h,deep_min]/averages/duration/observations)。
"""
from __future__ import annotations

import json
import math
from typing import Any, Optional

SLEEP_SUMMARY_TYPE = "sleep_summary"
GENUI_SLEEP_SUMMARY_CAP = "genui-sleep-summary-v1"  # 客户端能力位(点亮门控)
_VERSION = 1  # reva-ui 信封版本 = 整数(与 metric_table/charts/diet 同契约)

_DURATION_TARGET_H = 8.0   # 成人睡眠时长通用目标(常识参考,非诊断)
_DURATION_LOW_H = 6.5      # 偏短阈值
_DEEP_MIN_LOW = 60.0       # 深睡偏少参考(分钟,通用)
_MAX_NIGHTS = 7            # 卡片最多列几夜(防刷屏)


def _num(v: Any) -> Optional[float]:
    """→ 有限浮点,否则 None(nan/inf/非数值/负 → None)。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f) or f < 0:
        return None
    return f


def _round(v: Any, nd: int = 1) -> Optional[float]:
    f = _num(v)
    if f is None:
        return None
    return int(round(f)) if nd == 0 else round(f, nd)


def _min_to_h(v: Any) -> Optional[float]:
    """分钟 → 小时(1 位小数)。缺值/非法 → None。"""
    f = _num(v)
    if f is None:
        return None
    return round(f / 60.0, 1)


def _derive_sleep_observations(
    *, avg_score: Optional[float], avg_dur_h: Optional[float], avg_deep_min: Optional[float]
) -> list[dict]:
    """确定性派生关键观察 —— 只读测得值 + 通用参考,factual、severity ∈ normal/caution。

    R4:不消费服务端 quality_assessment、不判医学诊断;只陈述测得值与通用参考的关系。
    只在值 > 0 时出观察(0/缺值多为未采集,不误报"不足")。
    """
    obs: list[dict] = []

    if avg_dur_h and avg_dur_h > 0:
        short = avg_dur_h < _DURATION_LOW_H
        obs.append({
            "severity": "caution" if short else "normal",
            "label": "睡眠偏短" if short else "睡眠时长充足",
            "detail": f"平均 {avg_dur_h:.1f}h,一般建议 7–9h。",
        })

    if avg_deep_min and avg_deep_min > 0:
        low = avg_deep_min < _DEEP_MIN_LOW
        obs.append({
            "severity": "caution" if low else "normal",
            "label": "深睡偏少" if low else "深睡充足",
            "detail": f"平均 {avg_deep_min:.0f} 分钟。",
        })

    if avg_score and avg_score > 0:
        # sleep_score 是设备端评分,只陈述测得均值(不强判好坏,守 R4)。
        obs.append({
            "severity": "normal",
            "label": "睡眠评分",
            "detail": f"近期平均 {avg_score:.0f}(设备评分)。",
        })

    return obs[:4]


def build_sleep_summary(analysis: dict) -> Optional[dict]:
    """analyze_sleep_quality dict → sleep_summary descriptor。无逐夜数据 → None(fail-open)。"""
    if not isinstance(analysis, dict):
        return None
    raw = analysis.get("daily_data")
    if not isinstance(raw, list) or not raw:
        return None

    nights: list[dict] = []
    for d in raw:
        if not isinstance(d, dict):
            continue
        score = _round(d.get("sleep_score"), 0)
        dur_h = _min_to_h(d.get("total_sleep_duration"))
        deep_min = _round(d.get("deep_sleep_duration"), 0)
        if score is None and dur_h is None and deep_min is None:
            continue  # 仅日期无任何指标 → 跳过(绝不落空行)
        nights.append({
            "date": (str(d.get("date") or "").strip() or None),
            "score": score,
            "duration_h": dur_h,
            "deep_min": deep_min,
        })
    if not nights:
        return None
    # 最新的夜在前(倒序 by date 字符串;ISO/MM-DD 皆可比较)。
    nights.sort(key=lambda n: str(n.get("date") or ""), reverse=True)
    nights = nights[:_MAX_NIGHTS]

    avg_score = _round(analysis.get("average_sleep_score"), 0)
    avg_dur_h = _round(analysis.get("average_sleep_duration_hours"))
    avg_deep_min = _round(analysis.get("average_deep_sleep_minutes"), 0)

    data: dict[str, Any] = {
        "range_label": f"近{len(nights)}天" if len(nights) > 1 else "昨晚",
        "nights": nights,
        "averages": {"score": avg_score, "duration_h": avg_dur_h, "deep_min": avg_deep_min},
        "observations": _derive_sleep_observations(
            avg_score=avg_score, avg_dur_h=avg_dur_h, avg_deep_min=avg_deep_min
        ),
    }
    # 睡眠时长进度条:平均时长 → 8h 目标(有均值才给)。
    if avg_dur_h is not None and avg_dur_h > 0:
        data["duration"] = {"current_h": avg_dur_h, "target_h": _DURATION_TARGET_H}

    return {"type": SLEEP_SUMMARY_TYPE, "v": _VERSION, "data": data}


def render_sleep_summary_block(descriptor: dict) -> str:
    """descriptor → ```reva-ui fenced 文本(与 diet/table/chart 同机制)。"""
    payload = json.dumps(descriptor, ensure_ascii=False, separators=(",", ":"))
    return f"```reva-ui\n{payload}\n```"
