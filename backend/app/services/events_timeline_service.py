"""
健康事件流 Timeline 聚合 (产品改进 H).

从多源聚合为 unified TimelineEvent, 按时间倒序.

设计:
  - 每个事件三要素: 时间 / 类型 / 要点
  - 优先 actionable 事件 (告警/运动/体检) 而非日常数据 (饮食/饮水)
  - 每条带 deep_link, 点开跳详情
  - 限制 30 天窗口 + 最多 40 条 (防首页爆)

future: 支持 ?from=<date>&to=<date> 时间范围, 支持更多源 (mood / symptom / reminder 等)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# 后端指标字段名 → 用户可读标签 + 单位. 用于 timeline subtitle 人话化.
_METRIC_LABELS: dict[str, tuple[str, str]] = {
    "spo2_avg": ("血氧平均", "%"),
    "spo2_min": ("血氧最低", "%"),
    "spo2_below_90_pct": ("低氧占比", "%"),
    "resting_heart_rate": ("静息心率", " bpm"),
    "hrv": ("HRV", " ms"),
    "sleep_score": ("睡眠评分", ""),
    "sleep_duration": ("睡眠时长", " h"),
    "stress_level": ("压力", ""),
    "body_battery": ("身体电量", ""),
    "weight": ("体重", " kg"),
    "blood_pressure": ("血压", " mmHg"),
}


def _metric_humanize(metric_name: str) -> tuple[str, str]:
    """metric_name → (label, unit). 未知 metric 原样返回无单位."""
    if metric_name in _METRIC_LABELS:
        return _METRIC_LABELS[metric_name]
    return (metric_name, "")


@dataclass
class TimelineEvent:
    """Timeline 统一事件."""
    id: str                     # '<source>_<pk>' 保证全局唯一
    source: str                 # workout / alert / sleep / medication / exam / journal
    title: str                  # '跑步 2.6km' / '血氧偏低' / ...
    subtitle: Optional[str]     # '18 分钟, 极限心率占比 87%'
    icon: str                   # Ionicons name
    color: str                  # '#FF9500' / 'red' / ...  mobile 直接用
    occurred_at: datetime       # 事件发生时间 (优先于记录时间)
    deep_link: Optional[str]    # 'workout-detail?id=167' 不带前导 /
    severity: Optional[str]     # info / warning / critical (告警专用, 其它 None)


def build_timeline(
    db: Session,
    user_id: int,
    *,
    days: int = 30,
    limit: int = 40,
) -> List[TimelineEvent]:
    """从多源聚合 timeline 事件."""
    events: List[TimelineEvent] = []
    since_dt = datetime.now(timezone.utc) - timedelta(days=days)
    since_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()

    events.extend(_workouts(db, user_id, since_dt))
    events.extend(_alerts(db, user_id, since_date))
    events.extend(_sleep_lows(db, user_id, since_date))
    events.extend(_medications(db, user_id, since_date))
    events.extend(_exams(db, user_id, since_date))

    # 按时间倒序
    events.sort(key=lambda e: e.occurred_at, reverse=True)
    return events[:limit]


def _workouts(db: Session, user_id: int, since: datetime) -> List[TimelineEvent]:
    from app.models.daily_health import WorkoutRecord

    out = []
    try:
        rows = db.query(WorkoutRecord).filter(
            WorkoutRecord.user_id == user_id,
            WorkoutRecord.start_time >= since,
        ).order_by(WorkoutRecord.start_time.desc()).limit(30).all()
        for w in rows:
            km = (w.distance_meters or 0) / 1000
            mins = (w.duration_seconds or 0) // 60
            wtype_zh = _workout_type_zh(w.workout_type or "")
            title = f"{wtype_zh}"
            if km > 0:
                title += f" {km:.1f} 公里"
            sub_bits = []
            if mins:
                sub_bits.append(f"{mins} 分钟")
            if w.avg_heart_rate:
                sub_bits.append(f"均心率 {w.avg_heart_rate}")
            out.append(TimelineEvent(
                id=f"workout_{w.id}",
                source="workout",
                title=title,
                subtitle=" · ".join(sub_bits) if sub_bits else None,
                icon="fitness-outline",
                color="#0A8F8F",
                occurred_at=w.start_time or datetime.combine(w.workout_date or date.today(), datetime.min.time()),
                deep_link=f"workout-detail?id={w.id}",
                severity=None,
            ))
    except Exception as e:
        logger.warning("[timeline] workouts load failed for user=%s: %s", user_id, e)
    return out


def _alerts(db: Session, user_id: int, since: date) -> List[TimelineEvent]:
    from app.models.anomaly_alert import AnomalyAlert

    out = []
    try:
        rows = db.query(AnomalyAlert).filter(
            AnomalyAlert.user_id == user_id,
            AnomalyAlert.detection_date >= since,
        ).order_by(AnomalyAlert.detection_date.desc(), AnomalyAlert.id.desc()).limit(30).all()
        for a in rows:
            color = "#FF3B30" if a.severity == "critical" else ("#FF9500" if a.severity == "warning" else "#8E8E93")
            # deep_link 根据是否有 clarify 模板决定
            from app.services.alert_clarification import get_clarification_opener
            has_clarify = get_clarification_opener(a) is not None
            deep = f"voice-chat?intent=clarify&alert_id={a.id}" if has_clarify else f"trace/anomaly_{a.id}"
            # 把开发者字段名映射成人话 + 加单位
            metric_label, unit = _metric_humanize(a.metric_name)
            sub_val = f"{a.current_value}{unit}" if a.current_value is not None else ""
            subtitle = f"{metric_label} {sub_val}".strip()
            out.append(TimelineEvent(
                id=f"alert_{a.id}",
                source="alert",
                title=a.message[:40],
                subtitle=subtitle or None,
                icon="warning-outline" if a.severity != "critical" else "alert-circle",
                color=color,
                # detection_date 只到天, 给个稳定的 12:00 防排序抖动
                occurred_at=datetime.combine(a.detection_date, datetime.min.time().replace(hour=12)),
                deep_link=deep,
                severity=a.severity,
            ))
    except Exception as e:
        logger.warning("[timeline] alerts load failed for user=%s: %s", user_id, e)
    return out


def _sleep_lows(db: Session, user_id: int, since: date) -> List[TimelineEvent]:
    """只记明显低分 (< 65) 或异常 RHR 的睡眠. 日常睡眠不堆 timeline."""
    from app.models.daily_health import GarminData

    out = []
    try:
        # 多源按日合并 → 每天最多一个睡眠事件 (否则同一天多设备各发一条重复)
        from app.services.garmin_daily_merged import merged_daily_rows
        rows = merged_daily_rows(db, user_id, since=since)
        for g in rows:
            if g.sleep_score is not None and g.sleep_score < 65:
                out.append(TimelineEvent(
                    id=f"sleep_low_{g.record_date.isoformat()}",
                    source="sleep",
                    title=f"睡眠分数 {g.sleep_score}",
                    subtitle=f"{int((g.total_sleep_duration or 0) / 60)}h 偏低" if g.total_sleep_duration else "偏低",
                    icon="moon-outline",
                    color="#FF9500",
                    occurred_at=datetime.combine(g.record_date, datetime.min.time().replace(hour=8)),
                    deep_link=f"sleep",
                    severity=None,
                ))
    except Exception as e:
        logger.warning("[timeline] sleep_lows load failed for user=%s: %s", user_id, e)
    return out


def _medications(db: Session, user_id: int, since: date) -> List[TimelineEvent]:
    """用药项的开始/停用事件."""
    from app.models.medication import Medication

    out = []
    try:
        rows = db.query(Medication).filter(
            Medication.user_id == user_id,
        ).all()
        for m in rows:
            # 开始服药
            if m.start_date and m.start_date >= since:
                out.append(TimelineEvent(
                    id=f"med_start_{m.id}",
                    source="medication",
                    title=f"开始服 {m.name}",
                    subtitle=m.dosage or m.frequency,
                    icon="medkit-outline",
                    color="#AF52DE",
                    occurred_at=datetime.combine(m.start_date, datetime.min.time().replace(hour=9)),
                    deep_link="medications",
                    severity=None,
                ))
            # 停用
            if not m.is_active and m.end_date and m.end_date >= since:
                cancelled_mark = "(已取消)" if m.notes and "user-cancelled" in m.notes else ""
                out.append(TimelineEvent(
                    id=f"med_end_{m.id}",
                    source="medication",
                    title=f"停用 {m.name} {cancelled_mark}".strip(),
                    subtitle=None,
                    icon="pause-circle-outline",
                    color="#8E8E93",
                    occurred_at=datetime.combine(m.end_date, datetime.min.time().replace(hour=9)),
                    deep_link="medications",
                    severity=None,
                ))
    except Exception as e:
        logger.warning("[timeline] medications load failed for user=%s: %s", user_id, e)
    return out


def _exams(db: Session, user_id: int, since: date) -> List[TimelineEvent]:
    from app.models.medical_exam import MedicalExam

    out = []
    try:
        rows = db.query(MedicalExam).filter(
            MedicalExam.user_id == user_id,
            MedicalExam.exam_date >= since,
        ).order_by(MedicalExam.exam_date.desc()).limit(10).all()
        for e in rows:
            out.append(TimelineEvent(
                id=f"exam_{e.id}",
                source="exam",
                title=f"{e.exam_type or '体检'} 报告",
                subtitle=getattr(e, "hospital_name", None),
                icon="document-text-outline",
                color="#5AC8FA",
                occurred_at=datetime.combine(e.exam_date, datetime.min.time().replace(hour=10)),
                deep_link=f"medical-exam-detail?id={e.id}",
                severity=None,
            ))
    except Exception as e:
        logger.warning("[timeline] exams load failed for user=%s: %s", user_id, e)
    return out


def _workout_type_zh(wtype: str) -> str:
    m = {
        "running": "跑步", "cycling": "骑行", "swimming": "游泳",
        "hiit": "HIIT", "strength": "力量训练", "cardio": "有氧",
        "yoga": "瑜伽", "walking": "步行", "hiking": "徒步",
    }
    return m.get(wtype.lower(), wtype or "训练")
