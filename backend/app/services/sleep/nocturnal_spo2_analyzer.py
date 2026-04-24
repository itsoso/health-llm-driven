"""Nocturnal SpO2 Root-Cause Analyzer (P1b)。

从数据库读当晚 SpO2/HR/Respiration/SleepStage 时序，识别氧降事件，
写入 nocturnal_spo2_events 表，并返回 ODI / events 给上层 API。

事件定义（沿用临床 ODI 口径）:
    - SpO2 相对基线下降 ≥ DROP_THRESHOLD_PCT 百分点（默认 4）
    - 连续下降持续 ≥ DURATION_MIN_SEC 秒（默认 10）
    - 事件起点记为"跌破基线那一分钟"
    - 事件终点记为"恢复到基线 -2 百分点以内"

基线计算：前 5 分钟的滚动均值（足够平滑个体差异，同时足够响应夜间整体下降）。

此服务只做事件检测 + 特征抽取；行为关联规则在 correlation_rules.py。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, time
from typing import Dict, List, Optional, Tuple
import logging

from sqlalchemy.orm import Session

from app.models.daily_health import (
    SpO2Sample, HeartRateSample, SleepLevelInterval,
)
from app.models.garmin_timeseries import RespirationSample
from app.models.nocturnal_spo2_event import NocturnalSpO2Event

logger = logging.getLogger(__name__)


# ----- 算法配置 -----
DROP_THRESHOLD_PCT = 4.0          # 氧降阈值（百分点）
DURATION_MIN_SEC = 10             # 最短持续秒
BASELINE_WINDOW_MIN = 5           # 基线滚动窗口（分钟）
RECOVERY_MARGIN_PCT = 2.0         # 恢复到基线 - margin 以内则视为事件结束
MIN_SAMPLES_FOR_BASELINE = 3      # 基线至少需要几个样本


@dataclass
class DetectedEvent:
    start_ts: datetime
    end_ts: datetime
    duration_seconds: int
    min_spo2: float
    baseline_spo2: float
    drop_magnitude: float
    concurrent_hr_delta: Optional[float] = None
    concurrent_respiration_rate: Optional[float] = None
    sleep_stage: Optional[str] = None


@dataclass
class NightAnalysis:
    night_date: date
    odi: float                     # 每小时事件数
    events_count: int
    min_spo2: Optional[float]
    avg_spo2: Optional[float]
    total_sleep_minutes: int
    events: List[DetectedEvent] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 算法：氧降事件检测
# ---------------------------------------------------------------------------

def _detect_events(
    samples: List[Tuple[datetime, float]],
    drop_pct: float = DROP_THRESHOLD_PCT,
    min_duration_sec: int = DURATION_MIN_SEC,
    baseline_window_min: int = BASELINE_WINDOW_MIN,
) -> List[DetectedEvent]:
    """
    扫描 (ts, spo2) 序列识别氧降事件。

    不要求 samples 按固定秒间隔（Garmin 有时 1 分钟、有时不等间隔），
    但要求按时间升序。
    """
    if len(samples) < MIN_SAMPLES_FOR_BASELINE:
        return []
    samples = sorted(samples, key=lambda s: s[0])

    events: List[DetectedEvent] = []
    in_event = False
    event_start_idx = 0
    event_start_ts: Optional[datetime] = None
    event_baseline: float = 0.0
    event_min_spo2: float = 100.0

    for i, (ts, spo2) in enumerate(samples):
        # 动态基线：当前点之前 baseline_window_min 分钟内的中位数
        window_start = ts - timedelta(minutes=baseline_window_min)
        baseline_vals = [
            s for (t, s) in samples[max(0, i - 30):i] if t >= window_start and s is not None
        ]
        if len(baseline_vals) < MIN_SAMPLES_FOR_BASELINE:
            continue
        baseline_vals.sort()
        baseline = baseline_vals[len(baseline_vals) // 2]  # 中位数

        diff = baseline - spo2  # 正数 = 下降

        if not in_event:
            if diff >= drop_pct:
                in_event = True
                event_start_idx = i
                event_start_ts = ts
                event_baseline = baseline
                event_min_spo2 = spo2
        else:
            # 更新事件内最低值
            event_min_spo2 = min(event_min_spo2, spo2)
            # 恢复条件：回到 baseline - RECOVERY_MARGIN 以内
            if (event_baseline - spo2) <= RECOVERY_MARGIN_PCT:
                # 事件结束
                end_ts = ts
                duration = int((end_ts - event_start_ts).total_seconds())
                if duration >= min_duration_sec:
                    events.append(DetectedEvent(
                        start_ts=event_start_ts,
                        end_ts=end_ts,
                        duration_seconds=duration,
                        min_spo2=event_min_spo2,
                        baseline_spo2=event_baseline,
                        drop_magnitude=event_baseline - event_min_spo2,
                    ))
                in_event = False
                event_min_spo2 = 100.0

    # 收尾：夜结束时还在事件中
    if in_event and event_start_ts:
        end_ts = samples[-1][0]
        duration = int((end_ts - event_start_ts).total_seconds())
        if duration >= min_duration_sec:
            events.append(DetectedEvent(
                start_ts=event_start_ts,
                end_ts=end_ts,
                duration_seconds=duration,
                min_spo2=event_min_spo2,
                baseline_spo2=event_baseline,
                drop_magnitude=event_baseline - event_min_spo2,
            ))

    return events


# ---------------------------------------------------------------------------
# 数据读取 + 事件富化
# ---------------------------------------------------------------------------

def _load_spo2_samples(db: Session, user_id: int, d: date) -> List[Tuple[datetime, float]]:
    rows = db.query(SpO2Sample).filter(
        SpO2Sample.user_id == user_id,
        SpO2Sample.record_date == d,
    ).order_by(SpO2Sample.sample_time).all()
    out: List[Tuple[datetime, float]] = []
    for r in rows:
        if r.epoch_ms:
            ts = datetime.fromtimestamp(r.epoch_ms / 1000)
        else:
            ts = datetime.combine(d, r.sample_time)
        if r.spo2_value is not None and 50 <= r.spo2_value <= 100:
            out.append((ts, float(r.spo2_value)))
    return out


def _load_hr_by_time(db: Session, user_id: int, d: date) -> List[Tuple[time, int]]:
    rows = db.query(HeartRateSample).filter(
        HeartRateSample.user_id == user_id,
        HeartRateSample.record_date == d,
    ).all()
    return [(r.sample_time, r.heart_rate) for r in rows if r.heart_rate]


def _load_respiration_by_time(db: Session, user_id: int, d: date) -> List[Tuple[time, float]]:
    rows = db.query(RespirationSample).filter(
        RespirationSample.user_id == user_id,
        RespirationSample.record_date == d,
    ).all()
    return [(r.sample_time, r.respiration_rate) for r in rows if r.respiration_rate]


def _load_sleep_stages(db: Session, user_id: int, d: date) -> List[Tuple[int, int, str]]:
    """Return [(start_ms, end_ms, level), ...] — include prior-day rows (cross-midnight)."""
    rows = db.query(SleepLevelInterval).filter(
        SleepLevelInterval.user_id == user_id,
        SleepLevelInterval.record_date.in_([d, d - timedelta(days=1)]),
    ).all()
    return [(r.start_epoch_ms, r.end_epoch_ms, r.activity_level) for r in rows]


def _stage_at(stages: List[Tuple[int, int, str]], ts: datetime) -> Optional[str]:
    ts_ms = int(ts.timestamp() * 1000)
    for s, e, lvl in stages:
        if s <= ts_ms <= e:
            return lvl
    return None


def _nearest_hr(samples: List[Tuple[time, int]], ts: datetime) -> Optional[int]:
    if not samples:
        return None
    target = ts.time()
    target_sec = target.hour * 3600 + target.minute * 60
    best: Optional[Tuple[int, int]] = None
    for t, hr in samples:
        t_sec = t.hour * 3600 + t.minute * 60
        dist = abs(t_sec - target_sec)
        if best is None or dist < best[0]:
            best = (dist, hr)
    if best and best[0] <= 900:  # 15 min tolerance
        return best[1]
    return None


def _avg_in_window(samples: List[Tuple[time, float]], start: datetime, end: datetime) -> Optional[float]:
    if not samples:
        return None
    start_sec = start.hour * 3600 + start.minute * 60
    end_sec = end.hour * 3600 + end.minute * 60
    values: List[float] = []
    for t, v in samples:
        t_sec = t.hour * 3600 + t.minute * 60
        if start_sec <= t_sec <= end_sec:
            values.append(v)
    if not values:
        return None
    return sum(values) / len(values)


# ---------------------------------------------------------------------------
# 公开入口
# ---------------------------------------------------------------------------

def analyze_night(db: Session, user_id: int, night_date: date) -> NightAnalysis:
    """对某一夜执行分析，写事件表，返回聚合结果。"""
    samples = _load_spo2_samples(db, user_id, night_date)
    if not samples:
        return NightAnalysis(
            night_date=night_date,
            odi=0.0,
            events_count=0,
            min_spo2=None,
            avg_spo2=None,
            total_sleep_minutes=0,
            events=[],
        )

    spo2_values = [s for _, s in samples]
    min_spo2 = min(spo2_values)
    avg_spo2 = sum(spo2_values) / len(spo2_values)

    # 真实睡眠时长优先从 GarminData.total_sleep_duration 拿（临床口径）
    # fallback 用样本跨度
    from app.models.daily_health import GarminData
    gd = db.query(GarminData).filter(
        GarminData.user_id == user_id,
        GarminData.record_date == night_date,
    ).first()
    if gd and gd.total_sleep_duration and gd.total_sleep_duration >= 60:
        total_minutes = int(gd.total_sleep_duration)
    else:
        total_minutes = int((samples[-1][0] - samples[0][0]).total_seconds() / 60)

    # 少于 1 小时的"夜"不算数（数据不完整 → ODI 没意义）
    if total_minutes < 60:
        return NightAnalysis(
            night_date=night_date,
            odi=0.0,
            events_count=0,
            min_spo2=min_spo2,
            avg_spo2=round(avg_spo2, 1),
            total_sleep_minutes=total_minutes,
            events=[],
        )
    sleep_hours = total_minutes / 60.0

    raw_events = _detect_events(samples)

    # 富化：每个事件加 HR delta / 呼吸 / 睡眠分期
    hr_samples = _load_hr_by_time(db, user_id, night_date)
    resp_samples = _load_respiration_by_time(db, user_id, night_date)
    stages = _load_sleep_stages(db, user_id, night_date)

    # HR 基线：整夜平均
    hr_values = [hr for _, hr in hr_samples]
    hr_baseline = sum(hr_values) / len(hr_values) if hr_values else None

    enriched: List[DetectedEvent] = []
    for ev in raw_events:
        # HR delta
        mid_ts = ev.start_ts + (ev.end_ts - ev.start_ts) / 2
        hr_at = _nearest_hr(hr_samples, mid_ts)
        hr_delta = (hr_at - hr_baseline) if (hr_at is not None and hr_baseline) else None

        # 呼吸平均
        resp_avg = _avg_in_window(resp_samples, ev.start_ts, ev.end_ts)

        # 睡眠阶段（起点）
        stage = _stage_at(stages, ev.start_ts)

        enriched.append(DetectedEvent(
            start_ts=ev.start_ts,
            end_ts=ev.end_ts,
            duration_seconds=ev.duration_seconds,
            min_spo2=ev.min_spo2,
            baseline_spo2=ev.baseline_spo2,
            drop_magnitude=ev.drop_magnitude,
            concurrent_hr_delta=hr_delta,
            concurrent_respiration_rate=resp_avg,
            sleep_stage=stage,
        ))

    # 写表（幂等：先删当夜再插）
    db.query(NocturnalSpO2Event).filter(
        NocturnalSpO2Event.user_id == user_id,
        NocturnalSpO2Event.night_date == night_date,
    ).delete()

    to_save = [
        NocturnalSpO2Event(
            user_id=user_id,
            night_date=night_date,
            start_ts=ev.start_ts,
            end_ts=ev.end_ts,
            duration_seconds=ev.duration_seconds,
            min_spo2=ev.min_spo2,
            baseline_spo2=ev.baseline_spo2,
            drop_magnitude=ev.drop_magnitude,
            concurrent_hr_delta=ev.concurrent_hr_delta,
            concurrent_respiration_rate=ev.concurrent_respiration_rate,
            sleep_stage=ev.sleep_stage,
        )
        for ev in enriched
    ]
    if to_save:
        db.bulk_save_objects(to_save)
    db.commit()

    odi = len(enriched) / sleep_hours

    return NightAnalysis(
        night_date=night_date,
        odi=round(odi, 2),
        events_count=len(enriched),
        min_spo2=min_spo2,
        avg_spo2=round(avg_spo2, 1),
        total_sleep_minutes=total_minutes,
        events=enriched,
    )


def analyze_period(db: Session, user_id: int, start: date, end: date) -> List[NightAnalysis]:
    """对一段时间内每一夜分析；返回每夜 NightAnalysis。"""
    out: List[NightAnalysis] = []
    d = start
    while d <= end:
        try:
            out.append(analyze_night(db, user_id, d))
        except Exception as e:
            logger.warning(f"[nocturnal_analyzer] {d} 分析失败: {e}")
        d += timedelta(days=1)
    return out
