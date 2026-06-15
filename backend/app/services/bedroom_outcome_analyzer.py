"""卧室环境 × 睡眠结果关联分析 (设计文档 §9 BedroomOutcomeAnalyzer · Phase 4 Outcome Proof).

职责 (纯读, 确定性): 把**卧室环境快照** (BedroomEnvironmentSnapshot 的 co2/温度/湿度)
与**次日睡眠结果** (GarminData 的 sleep_score / deep_sleep_duration / awake_duration)
按夜聚合对齐, 输出:
  1. correlate_env_sleep —— 分组对比 (高 CO2 夜 vs 低 CO2 夜的深睡/评分均值), N 不足诚实返回.
  2. bedroom_intervention_effect —— 把"低 CO2 环境"当作 N-of-1 干预, 复用 Phase 1
     effect_estimator.estimate_from_deltas 估计环境干预对睡眠指标的效应后验.

隐私 (设计文档 §11, 硬约束): 居住状态 / 睡眠环境数据**不进通用 LLM**. 本模块产出
**绝不**被 twin_to_prompt_blob 引用, 也不在本 PR 注入任何 LLM 上下文 —— 只供确定性
service 和将来的 UI/API. 有隐私守门测试 (test_bedroom_outcome_analyzer.py).

降级 (对齐 effect_estimator/bedroom_environment_service 风格): DB / 数学异常 →
rollback + log, 返回"数据不足"/空, **不抛**崩调用方.

夜聚合定义: 一"睡眠夜"以**起床日期 D** 为键. 该夜的环境 = [D-1 18:00, D 12:00) 窗口内
卧室快照的聚合 (CO2 取 max + 均值, 温湿度取均值); 睡眠结果 = GarminData(record_date=D).
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 夜窗口: 起床日 D 的睡眠夜环境取 [D-1 NIGHT_START, D NIGHT_END).
NIGHT_START_HOUR = 18   # 前一日 18:00
NIGHT_END_HOUR = 12     # 当日 12:00

# CO2 分组阈值 (设计文档 §6.1): >HIGH 视为"高 CO2 夜", <LOW 视为"低 CO2 夜".
CO2_HIGH_PPM = 1200.0
CO2_LOW_PPM = 900.0

# 分组对比最少夜数 (每组). 不足 → 诚实返回"数据不足".
MIN_NIGHTS_PER_GROUP = 3

# 支持的睡眠指标: code -> (GarminData 属性, 期望方向, 单位).
#   direction: up(升为好, 深睡/评分越多越好) / down(降为好, 觉醒越少越好).
SLEEP_METRICS: Dict[str, Tuple[str, str, str]] = {
    "sleep_deep_minutes": ("deep_sleep_duration", "up", "min"),
    "sleep_score": ("sleep_score", "up", "分"),
    "sleep_awake_minutes": ("awake_duration", "down", "min"),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sleep_night_key(captured_at: datetime) -> date:
    """把一条卧室快照归到它所属的"睡眠夜"键 (= 起床日期 D).

    [D-1 18:00, D 12:00) → 键 D. 18:00 之后的读数属于次日的睡眠夜.
    """
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    local = captured_at  # 统一按 UTC 归夜 (快照 captured_at 已 tz-aware)
    if local.hour >= NIGHT_START_HOUR:
        return (local + timedelta(days=1)).date()
    return local.date()


def _aggregate_nights(
    db: Session, user_id: int, room_id: str, days: int
) -> Dict[date, Dict[str, float]]:
    """按睡眠夜聚合卧室环境. 返回 {wake_date: {co2_max, co2_mean, temp_mean, humidity_mean}}.

    DB 异常向上抛 (由调用方降级)。
    """
    from app.models.bedroom_environment import BedroomEnvironmentSnapshot

    since = _now() - timedelta(days=days + 1)  # +1 覆盖窗口跨夜的前一日
    rows = (
        db.query(BedroomEnvironmentSnapshot)
        .filter(
            BedroomEnvironmentSnapshot.user_id == user_id,
            BedroomEnvironmentSnapshot.room_id == room_id,
            BedroomEnvironmentSnapshot.captured_at >= since,
        )
        .all()
    )

    buckets: Dict[date, Dict[str, List[float]]] = {}
    for r in rows:
        if r.captured_at is None:
            continue
        key = _sleep_night_key(r.captured_at)
        b = buckets.setdefault(key, {"co2": [], "temp": [], "humidity": []})
        if r.co2_ppm is not None:
            b["co2"].append(float(r.co2_ppm))
        if r.temperature_c is not None:
            b["temp"].append(float(r.temperature_c))
        if r.humidity_percent is not None:
            b["humidity"].append(float(r.humidity_percent))

    out: Dict[date, Dict[str, float]] = {}
    for key, b in buckets.items():
        agg: Dict[str, float] = {}
        if b["co2"]:
            agg["co2_max"] = max(b["co2"])
            agg["co2_mean"] = statistics.fmean(b["co2"])
        if b["temp"]:
            agg["temp_mean"] = statistics.fmean(b["temp"])
        if b["humidity"]:
            agg["humidity_mean"] = statistics.fmean(b["humidity"])
        if agg:
            out[key] = agg
    return out


def _sleep_by_date(
    db: Session, user_id: int, days: int
) -> Dict[date, Dict[str, float]]:
    """按 record_date 取睡眠指标. 返回 {date: {metric_code: value}}. DB 异常向上抛。"""
    from app.models.daily_health import GarminData

    since_date = (_now() - timedelta(days=days + 1)).date()
    rows = (
        db.query(GarminData)
        .filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= since_date,
        )
        .all()
    )
    out: Dict[date, Dict[str, float]] = {}
    for r in rows:
        metrics: Dict[str, float] = {}
        for code, (attr, _dir, _unit) in SLEEP_METRICS.items():
            val = getattr(r, attr, None)
            if val is not None:
                metrics[code] = float(val)
        if metrics:
            out[r.record_date] = metrics
    return out


def _paired_nights(
    env: Dict[date, Dict[str, float]], sleep: Dict[date, Dict[str, float]]
) -> List[Tuple[date, Dict[str, float], Dict[str, float]]]:
    """对齐有环境且有睡眠结果的夜, 按日期升序。"""
    keys = sorted(set(env) & set(sleep))
    return [(k, env[k], sleep[k]) for k in keys]


def _insufficient(reason: str, **extra: Any) -> Dict[str, Any]:
    out = {"status": "insufficient_data", "reason": reason}
    out.update(extra)
    return out


# ─────────────────────────── 1. 分组关联 ───────────────────────────

def correlate_env_sleep(
    db: Session, user_id: int, days: int = 14, room_id: str = "bedroom"
) -> Dict[str, Any]:
    """高 CO2 夜 vs 低 CO2 夜的睡眠指标分组对比。

    N 不足 (任一组 < MIN_NIGHTS_PER_GROUP) → status=insufficient_data, 诚实返回.
    降级: DB/数学异常 → rollback + log, 返回 insufficient_data, 不抛.
    """
    try:
        env = _aggregate_nights(db, user_id, room_id, days)
        sleep = _sleep_by_date(db, user_id, days)
    except Exception:  # noqa: BLE001 — 分析器不崩调用方
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.exception("[BedroomOutcome] correlate load failed user=%s", user_id)
        return _insufficient("load_failed")

    paired = _paired_nights(env, sleep)
    if len(paired) < 2 * MIN_NIGHTS_PER_GROUP:
        return _insufficient(
            "not_enough_paired_nights", paired_nights=len(paired)
        )

    high_grp = [s for (_d, e, s) in paired if e.get("co2_max", 0) > CO2_HIGH_PPM]
    low_grp = [s for (_d, e, s) in paired if e.get("co2_max", 9e9) < CO2_LOW_PPM]

    if len(high_grp) < MIN_NIGHTS_PER_GROUP or len(low_grp) < MIN_NIGHTS_PER_GROUP:
        return _insufficient(
            "groups_too_small",
            paired_nights=len(paired),
            high_co2_nights=len(high_grp),
            low_co2_nights=len(low_grp),
        )

    metrics_out: Dict[str, Any] = {}
    for code, (_attr, direction, unit) in SLEEP_METRICS.items():
        high_vals = [g[code] for g in high_grp if code in g]
        low_vals = [g[code] for g in low_grp if code in g]
        if len(high_vals) < MIN_NIGHTS_PER_GROUP or len(low_vals) < MIN_NIGHTS_PER_GROUP:
            continue
        high_mean = statistics.fmean(high_vals)
        low_mean = statistics.fmean(low_vals)
        # diff = 低CO2 - 高CO2 (低CO2 = 更好的环境). up 指标 diff>0 = 环境帮助.
        diff = low_mean - high_mean
        metrics_out[code] = {
            "direction": direction,
            "unit": unit,
            "low_co2_mean": round(low_mean, 1),
            "high_co2_mean": round(high_mean, 1),
            "diff_low_minus_high": round(diff, 1),
            "n_low": len(low_vals),
            "n_high": len(high_vals),
        }

    if not metrics_out:
        return _insufficient(
            "no_metric_with_enough_coverage",
            paired_nights=len(paired),
            high_co2_nights=len(high_grp),
            low_co2_nights=len(low_grp),
        )

    return {
        "status": "ok",
        "window_days": days,
        "paired_nights": len(paired),
        "co2_high_threshold": CO2_HIGH_PPM,
        "co2_low_threshold": CO2_LOW_PPM,
        "high_co2_nights": len(high_grp),
        "low_co2_nights": len(low_grp),
        "metrics": metrics_out,
    }


# ───────────────────── 2. 接 Phase 1 干预效应估计 ─────────────────────

def bedroom_intervention_effect(
    db: Session,
    user_id: int,
    metric_code: str = "sleep_deep_minutes",
    days: int = 28,
    room_id: str = "bedroom",
) -> Dict[str, Any]:
    """把"低 CO2 卧室环境"当作 N-of-1 干预, 估计它对某睡眠指标的效应后验。

    复用 Phase 1 effect_estimator.estimate_from_deltas (纯函数):
      - baseline = 高 CO2 夜 (>CO2_HIGH_PPM) 该指标均值 (= "未干预"参照).
      - 每个低 CO2 夜 (<CO2_LOW_PPM) 贡献一个 delta = (该夜指标 - baseline) —— 即
        "进入低 CO2 环境后相对未干预参照的改变量"的一次观测.
      - 无低 CO2 夜 / 无 baseline 参照 → 降级返回纯先验 (N=0, 宽 CI, "尚未验证").

    降级: DB/数学异常 → rollback + log, 仍返回一个先验估计 (estimate_from_deltas
    对空序列返回先验), 不抛.
    """
    spec = SLEEP_METRICS.get(metric_code)
    direction = spec[1] if spec else "up"
    unit = spec[2] if spec else None

    from app.services.effect_estimator import estimate_from_deltas

    try:
        env = _aggregate_nights(db, user_id, room_id, days)
        sleep = _sleep_by_date(db, user_id, days)
    except Exception:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.exception(
            "[BedroomOutcome] intervention_effect load failed user=%s metric=%s",
            user_id, metric_code,
        )
        env, sleep = {}, {}

    paired = _paired_nights(env, sleep)

    baseline_vals: List[float] = []
    treated_vals: List[float] = []
    for _d, e, s in paired:
        if metric_code not in s:
            continue
        co2_max = e.get("co2_max")
        if co2_max is None:
            continue
        if co2_max > CO2_HIGH_PPM:
            baseline_vals.append(s[metric_code])
        elif co2_max < CO2_LOW_PPM:
            treated_vals.append(s[metric_code])

    deltas: List[float] = []
    baseline_mean: Optional[float] = None
    if baseline_vals and treated_vals:
        baseline_mean = statistics.fmean(baseline_vals)
        deltas = [v - baseline_mean for v in treated_vals]
    # 无 baseline 或无 treated 夜 → deltas 空 → estimate_from_deltas 返回纯先验.

    est = estimate_from_deltas(
        metric_code,
        deltas,
        direction=direction,
        cycle_type="bedroom_co2",
        unit=unit,
    )
    out = est.to_dict()
    out["intervention"] = "low_co2_bedroom_environment"
    out["n_baseline_nights"] = len(baseline_vals)
    out["n_treated_nights"] = len(treated_vals)
    out["baseline_mean"] = round(baseline_mean, 1) if baseline_mean is not None else None
    return out
