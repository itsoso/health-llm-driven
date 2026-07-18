"""
Personal Outcome 服务

回答一个问题：因为这个系统，我过去 X 个月 / 年里发生了什么可测量的变化？

不同于日/周维度的看板，这里聚焦"长期时间序列 + 干预事件锚点"：
- 时间序列按 week/month 聚合，最长支持 2 年
- 事件锚点来源：补剂开始日期、体检日期、血压初始记录等
- 每个事件可以计算"前后 N 天指标变化"（给 UI 展示 tooltip 用）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from statistics import stdev
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.daily_health import GarminData
from app.models.weight import WeightRecord
from app.models.blood_pressure import BloodPressureRecord
from app.models.medical_exam import MedicalExam

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

GRANULARITIES = {"week", "month"}


def _resolve_range(range_key: str) -> Optional[date]:
    """根据 range_key 计算起始日期。None 代表不限制（all）。"""
    today = date.today()
    if range_key == "6m":
        return today - timedelta(days=180)
    if range_key == "1y":
        return today - timedelta(days=365)
    if range_key == "2y":
        return today - timedelta(days=730)
    return None  # all


def _bucket_key(d: date, granularity: str) -> str:
    """将日期映射到 week/month 桶字符串（用作键和前端 X 轴 label）。"""
    if granularity == "week":
        # ISO 周：YYYY-Www
        iso_year, iso_week, _ = d.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    # month
    return f"{d.year}-{d.month:02d}"


def _bucket_anchor_date(key: str, granularity: str) -> date:
    """桶字符串 → 代表日期（方便前端排序 + 计算）。"""
    if granularity == "week":
        year, week = key.split("-W")
        # ISO 周的周一
        return date.fromisocalendar(int(year), int(week), 1)
    year, month = key.split("-")
    return date(int(year), int(month), 1)


def _avg(values: List[Optional[float]]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 2)


def _std(values: List[Optional[float]]) -> Optional[float]:
    """Sample standard deviation; fewer than two readings cannot estimate noise."""
    clean = [float(value) for value in values if value is not None]
    if len(clean) < 2:
        return None
    return round(stdev(clean), 3)


def _pooled_std(parts: List[tuple[Optional[float], int]]) -> Optional[float]:
    """Pool within-window variation without treating a level shift as noise."""
    usable = [(sd, count) for sd, count in parts if sd is not None and count >= 2]
    degrees_of_freedom = sum(count - 1 for _, count in usable)
    if not usable or degrees_of_freedom <= 0:
        return None
    variance = sum((count - 1) * float(sd) ** 2 for sd, count in usable)
    return round((variance / degrees_of_freedom) ** 0.5, 3)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class TimelinePoint:
    bucket: str  # 例如 "2025-03" 或 "2025-W12"
    date: str  # ISO 日期，代表这个桶的锚点日（方便前端排序）
    hrv: Optional[float] = None
    rhr: Optional[float] = None
    sleep_score: Optional[float] = None
    deep_sleep_min: Optional[float] = None
    body_battery_high: Optional[float] = None
    steps: Optional[float] = None
    weight_kg: Optional[float] = None
    systolic: Optional[float] = None
    diastolic: Optional[float] = None
    samples: int = 0  # 这个桶内覆盖的原始天数（用于判断数据稀疏度）


@dataclass
class TimelineEvent:
    id: str  # 类型 + 原始ID，唯一键
    kind: str  # supplement_start / medical_exam / first_bp / milestone
    date: str
    title: str
    detail: Optional[str] = None
    color: Optional[str] = None  # 前端用的 tag 色


# ---------------------------------------------------------------------------
# 主服务
# ---------------------------------------------------------------------------


class PersonalOutcomeService:
    """聚合用户长期健康时间序列 + 干预事件。"""

    # 每种 kind 的默认颜色（和前端 Tailwind 无关，纯 RGB）
    EVENT_COLOR = {
        "supplement_start": "#F59E0B",  # 琥珀色：开始吃某个补剂
        "medical_exam": "#3B82F6",  # 蓝色：体检
        "first_bp": "#EF4444",  # 红色：首次血压记录
        "milestone": "#10B981",  # 绿色：里程碑
    }

    def get_timeline(
        self,
        db: Session,
        user_id: int,
        range_key: str = "2y",
        granularity: str = "month",
    ) -> Dict[str, Any]:
        """
        返回完整 timeline：
        {
            "range": "2y",
            "granularity": "month",
            "start_date": "...",
            "end_date": "...",
            "points": [TimelinePoint, ...],
            "events": [TimelineEvent, ...],
            "summary": { 关键整体指标，用于页头显示 },
        }
        """
        if granularity not in GRANULARITIES:
            granularity = "month"

        start_date = _resolve_range(range_key)
        end_date = date.today()

        points = self._build_points(db, user_id, start_date, end_date, granularity)
        events = self._build_events(db, user_id, start_date, end_date)
        summary = self._build_summary(db, user_id, start_date, end_date, points)

        return {
            "range": range_key,
            "granularity": granularity,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat(),
            "points": [asdict(p) for p in points],
            "events": [asdict(e) for e in events],
            "summary": summary,
        }

    # ------------------------------------------------------------------
    # 时间序列聚合
    # ------------------------------------------------------------------

    def _build_points(
        self,
        db: Session,
        user_id: int,
        start_date: Optional[date],
        end_date: date,
        granularity: str,
    ) -> List[TimelinePoint]:
        """从 garmin_data + weight + bp 聚合成桶序列。"""

        # ---- Garmin (多源按日合并 → 每天一行,防同一天多设备重复计入桶均值) ----
        from app.services.garmin_daily_merged import merged_daily_rows
        garmin_rows = merged_daily_rows(
            db, user_id, since=start_date, until=end_date, ascending=True,
        )

        buckets: Dict[str, Dict[str, List[Any]]] = {}

        def _ensure(key: str):
            if key not in buckets:
                buckets[key] = {
                    "hrv": [],
                    "rhr": [],
                    "sleep_score": [],
                    "deep_sleep_min": [],
                    "body_battery_high": [],
                    "steps": [],
                    "weight_kg": [],
                    "systolic": [],
                    "diastolic": [],
                    "dates": set(),
                }
            return buckets[key]

        for g in garmin_rows:
            key = _bucket_key(g.record_date, granularity)
            b = _ensure(key)
            b["dates"].add(g.record_date)
            if g.hrv is not None:
                b["hrv"].append(g.hrv)
            if g.resting_heart_rate is not None:
                b["rhr"].append(g.resting_heart_rate)
            if g.sleep_score is not None:
                b["sleep_score"].append(g.sleep_score)
            if g.deep_sleep_duration is not None:
                b["deep_sleep_min"].append(g.deep_sleep_duration)
            if g.body_battery_most_charged is not None:
                b["body_battery_high"].append(g.body_battery_most_charged)
            if g.steps is not None:
                b["steps"].append(g.steps)

        # ---- Weight ----
        weight_q = db.query(WeightRecord).filter(WeightRecord.user_id == user_id)
        if start_date:
            weight_q = weight_q.filter(WeightRecord.record_date >= start_date)
        weight_q = weight_q.filter(WeightRecord.record_date <= end_date)
        for w in weight_q.all():
            if w.weight is None:
                continue
            key = _bucket_key(w.record_date, granularity)
            b = _ensure(key)
            b["weight_kg"].append(w.weight)
            b["dates"].add(w.record_date)

        # ---- Blood Pressure ----
        bp_q = db.query(BloodPressureRecord).filter(
            BloodPressureRecord.user_id == user_id
        )
        if start_date:
            bp_q = bp_q.filter(BloodPressureRecord.record_date >= start_date)
        bp_q = bp_q.filter(BloodPressureRecord.record_date <= end_date)
        for bp in bp_q.all():
            key = _bucket_key(bp.record_date, granularity)
            b = _ensure(key)
            if bp.systolic is not None:
                b["systolic"].append(bp.systolic)
            if bp.diastolic is not None:
                b["diastolic"].append(bp.diastolic)
            b["dates"].add(bp.record_date)

        # ---- 组装按时间排序的 TimelinePoint ----
        points: List[TimelinePoint] = []
        for key in sorted(buckets.keys(), key=lambda k: _bucket_anchor_date(k, granularity)):
            b = buckets[key]
            anchor = _bucket_anchor_date(key, granularity)
            points.append(
                TimelinePoint(
                    bucket=key,
                    date=anchor.isoformat(),
                    hrv=_avg(b["hrv"]),
                    rhr=_avg(b["rhr"]),
                    sleep_score=_avg(b["sleep_score"]),
                    deep_sleep_min=_avg(b["deep_sleep_min"]),
                    body_battery_high=_avg(b["body_battery_high"]),
                    steps=_avg(b["steps"]),
                    weight_kg=_avg(b["weight_kg"]),
                    systolic=_avg(b["systolic"]),
                    diastolic=_avg(b["diastolic"]),
                    samples=len(b["dates"]),
                )
            )
        return points

    # ------------------------------------------------------------------
    # 事件锚点
    # ------------------------------------------------------------------

    def _build_events(
        self,
        db: Session,
        user_id: int,
        start_date: Optional[date],
        end_date: date,
    ) -> List[TimelineEvent]:
        """从补剂定义 + 体检 + 血压首次记录里推导事件锚点。"""
        events: List[TimelineEvent] = []

        # ---- 1. 补剂开始事件（以 supplement_definitions.created_at 作为"开始服用"锚点）----
        try:
            from app.models.supplement import SupplementDefinition  # type: ignore
        except Exception:
            SupplementDefinition = None  # noqa: N806

        if SupplementDefinition is not None:
            sup_q = db.query(SupplementDefinition).filter(
                SupplementDefinition.user_id == user_id
            )
            for sup in sup_q.all():
                if not getattr(sup, "created_at", None):
                    continue
                event_date = sup.created_at.date() if hasattr(sup.created_at, "date") else sup.created_at
                if start_date and event_date < start_date:
                    continue
                if event_date > end_date:
                    continue
                events.append(
                    TimelineEvent(
                        id=f"sup-{sup.id}",
                        kind="supplement_start",
                        date=event_date.isoformat(),
                        title=f"开始：{sup.name}",
                        detail=getattr(sup, "dosage", None) or None,
                        color=self.EVENT_COLOR["supplement_start"],
                    )
                )

        # ---- 2. 体检事件 ----
        exam_q = db.query(MedicalExam).filter(MedicalExam.user_id == user_id)
        for exam in exam_q.all():
            if not exam.exam_date:
                continue
            if start_date and exam.exam_date < start_date:
                continue
            if exam.exam_date > end_date:
                continue
            events.append(
                TimelineEvent(
                    id=f"exam-{exam.id}",
                    kind="medical_exam",
                    date=exam.exam_date.isoformat(),
                    title="体检",
                    detail=(exam.overall_assessment or exam.exam_type or None),
                    color=self.EVENT_COLOR["medical_exam"],
                )
            )

        # ---- 3. 数据起点里程碑（让最早的那一天有锚点）----
        earliest_garmin = (
            db.query(func.min(GarminData.record_date))
            .filter(GarminData.user_id == user_id)
            .scalar()
        )
        if earliest_garmin and (not start_date or earliest_garmin >= start_date):
            events.append(
                TimelineEvent(
                    id="milestone-garmin-start",
                    kind="milestone",
                    date=earliest_garmin.isoformat(),
                    title="开始记录数据",
                    detail="Garmin 首次同步",
                    color=self.EVENT_COLOR["milestone"],
                )
            )

        # ---- 4. 按时间排序 ----
        events.sort(key=lambda e: e.date)
        return events

    # ------------------------------------------------------------------
    # 页头摘要（show the story in one glance）
    # ------------------------------------------------------------------

    def _build_summary(
        self,
        db: Session,
        user_id: int,
        start_date: Optional[date],
        end_date: date,
        points: List[TimelinePoint],
    ) -> Dict[str, Any]:
        """
        生成页头 4 个数字 + 一段简短文案。

        比较逻辑：取时间序列第一条 vs 最后一条（非空），计算差值。
        """

        def _first_last(attr: str):
            first = next((getattr(p, attr) for p in points if getattr(p, attr) is not None), None)
            last = next(
                (getattr(p, attr) for p in reversed(points) if getattr(p, attr) is not None),
                None,
            )
            return first, last

        def _delta(first, last):
            if first is None or last is None:
                return None
            return round(last - first, 2)

        hrv_first, hrv_last = _first_last("hrv")
        rhr_first, rhr_last = _first_last("rhr")
        weight_first, weight_last = _first_last("weight_kg")
        sleep_first, sleep_last = _first_last("sleep_score")

        total_days = 0
        if start_date:
            total_days = (end_date - start_date).days
        else:
            earliest = (
                db.query(func.min(GarminData.record_date))
                .filter(GarminData.user_id == user_id)
                .scalar()
            )
            if earliest:
                total_days = (end_date - earliest).days

        # distinct: 多源下同一天有多行,按 distinct 日期计覆盖天数,否则虚高
        covered_days = (
            db.query(func.count(func.distinct(GarminData.record_date)))
            .filter(GarminData.user_id == user_id)
            .scalar()
            or 0
        )

        return {
            "total_days": total_days,
            "covered_days": covered_days,
            "metrics": {
                "hrv": {
                    "first": hrv_first,
                    "last": hrv_last,
                    "delta": _delta(hrv_first, hrv_last),
                    "unit": "ms",
                    "desirable": "up",
                },
                "rhr": {
                    "first": rhr_first,
                    "last": rhr_last,
                    "delta": _delta(rhr_first, rhr_last),
                    "unit": "bpm",
                    "desirable": "down",
                },
                "weight": {
                    "first": weight_first,
                    "last": weight_last,
                    "delta": _delta(weight_first, weight_last),
                    "unit": "kg",
                    "desirable": "flat",
                },
                "sleep_score": {
                    "first": sleep_first,
                    "last": sleep_last,
                    "delta": _delta(sleep_first, sleep_last),
                    "unit": "分",
                    "desirable": "up",
                },
            },
        }

    # ------------------------------------------------------------------
    # 单个事件前后对比（用于点击事件锚点弹出 tooltip）
    # ------------------------------------------------------------------

    def get_event_impact(
        self,
        db: Session,
        user_id: int,
        event_id: str,
        window_days: int = 30,
    ) -> Dict[str, Any]:
        """
        返回某个事件前后 window_days 的关键指标均值对比。
        仅支持 sup-* / exam-* / milestone-* 三种 id。
        """
        prefix, _, raw_id = event_id.partition("-")
        event_date: Optional[date] = None
        title = event_id
        detail: Optional[str] = None

        if prefix == "sup":
            try:
                from app.models.supplement import SupplementDefinition  # type: ignore
                sup = (
                    db.query(SupplementDefinition)
                    .filter(
                        SupplementDefinition.id == int(raw_id),
                        SupplementDefinition.user_id == user_id,
                    )
                    .first()
                )
                if sup and sup.created_at:
                    event_date = (
                        sup.created_at.date()
                        if hasattr(sup.created_at, "date")
                        else sup.created_at
                    )
                    title = f"开始：{sup.name}"
                    detail = getattr(sup, "dosage", None)
            except Exception as exc:  # noqa: BLE001
                logger.warning("event_impact sup lookup failed: %s", exc)
        elif prefix == "exam":
            exam = (
                db.query(MedicalExam)
                .filter(
                    MedicalExam.id == int(raw_id),
                    MedicalExam.user_id == user_id,
                )
                .first()
            )
            if exam:
                event_date = exam.exam_date
                title = "体检"
                detail = exam.overall_assessment or exam.exam_type
        elif prefix == "milestone" and raw_id == "garmin-start":
            event_date = (
                db.query(func.min(GarminData.record_date))
                .filter(GarminData.user_id == user_id)
                .scalar()
            )
            title = "开始记录数据"
            detail = "Garmin 首次同步"

        if not event_date:
            return {"error": "event_not_found"}

        baseline_start = event_date - timedelta(days=window_days * 2)
        baseline_end = event_date - timedelta(days=window_days + 1)
        before_start = event_date - timedelta(days=window_days)
        before_end = event_date - timedelta(days=1)
        after_start = event_date
        after_end = event_date + timedelta(days=window_days)

        metric_columns = (
            ("hrv", "hrv"),
            ("rhr", "resting_heart_rate"),
            ("sleep_score", "sleep_score"),
            ("deep_sleep_min", "deep_sleep_duration"),
            ("steps", "steps"),
        )

        def _window_stats(start: date, end: date) -> Dict[str, Any]:
            # 多源按日合并；均值保留旧 UI 合约，样本数按指标另行返回给证据层。
            from app.services.garmin_daily_merged import merged_daily_rows
            rows = merged_daily_rows(db, user_id, since=start, until=end)
            means: Dict[str, Optional[float]] = {"samples": len(rows)}
            counts: Dict[str, int] = {}
            deviations: Dict[str, Optional[float]] = {}
            for key, column in metric_columns:
                values = [getattr(row, column) for row in rows]
                means[key] = _avg(values)
                counts[key] = len([value for value in values if value is not None])
                deviations[key] = _std(values)
            return {"means": means, "counts": counts, "deviations": deviations}

        baseline_stats = _window_stats(baseline_start, baseline_end)
        before_stats = _window_stats(before_start, before_end)
        after_stats = _window_stats(after_start, after_end)
        noise = {
            key: _pooled_std([
                (baseline_stats["deviations"][key], baseline_stats["counts"][key]),
                (before_stats["deviations"][key], before_stats["counts"][key]),
                (after_stats["deviations"][key], after_stats["counts"][key]),
            ])
            for key, _ in metric_columns
        }

        return {
            "event_id": event_id,
            "title": title,
            "detail": detail,
            "event_date": event_date.isoformat(),
            "window_days": window_days,
            "baseline": baseline_stats["means"],
            "before": before_stats["means"],
            "after": after_stats["means"],
            "metric_samples": {
                "baseline": baseline_stats["counts"],
                "before": before_stats["counts"],
                "after": after_stats["counts"],
            },
            "noise": noise,
        }
