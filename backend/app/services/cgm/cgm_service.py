"""
CGM 高层服务。

职责：
- ingest_reading(): 单条读数写入（幂等，通过 raw_id）
- ingest_batch(): 批量写入（来自 adapter）
- get_latest_reading(): 最近一次读数（用于 Twin）
- get_range_summary(): 时段统计（均值 / SD / TIR）
- get_24h_summary(): 24 小时关键指标（均值 / 标准差 / TIR 70-180）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

from app.models.cgm_reading import CgmReading

logger = logging.getLogger(__name__)


# 临床参考值（美式单位 mg/dL）
GLUCOSE_LOW = 70
GLUCOSE_HIGH = 180  # TIR (Time In Range) 上限
GLUCOSE_SEVERE_LOW = 54
GLUCOSE_SEVERE_HIGH = 250


@dataclass
class GlucoseSummary:
    """CGM 时段摘要。"""

    start: datetime
    end: datetime
    count: int
    mean_mg_dl: Optional[float]
    std_mg_dl: Optional[float]
    cv_pct: Optional[float]         # 变异系数 (std/mean × 100)
    gmi: Optional[float]            # Glucose Management Indicator (近似 A1C)
    tir_pct: Optional[float]        # Time In Range 70-180
    time_below_pct: Optional[float]  # < 70
    time_above_pct: Optional[float]  # > 180
    severe_low_count: int           # < 54 次数
    severe_high_count: int          # > 250 次数
    latest_mg_dl: Optional[float]
    latest_trend_arrow: Optional[str]
    latest_measured_at: Optional[datetime] = None  # 最新读数时间(供急性规则判新鲜度)


class CgmService:
    """CGM 服务类。"""

    def get_latest_reading(self, db: Session, user_id: int) -> Optional[CgmReading]:
        return (
            db.query(CgmReading)
            .filter(CgmReading.user_id == user_id)
            .order_by(desc(CgmReading.measured_at))
            .first()
        )

    def get_24h_summary(self, db: Session, user_id: int) -> GlucoseSummary:
        """最近 24 小时摘要。"""
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=24)
        return self.get_range_summary(db, user_id, start, end)

    def get_range_summary(
        self,
        db: Session,
        user_id: int,
        start: datetime,
        end: datetime,
    ) -> GlucoseSummary:
        rows = (
            db.query(CgmReading)
            .filter(
                and_(
                    CgmReading.user_id == user_id,
                    CgmReading.measured_at >= start,
                    CgmReading.measured_at <= end,
                )
            )
            .order_by(CgmReading.measured_at)
            .all()
        )

        latest = (
            db.query(CgmReading)
            .filter(CgmReading.user_id == user_id)
            .order_by(desc(CgmReading.measured_at))
            .first()
        )

        if not rows:
            return GlucoseSummary(
                start=start,
                end=end,
                count=0,
                mean_mg_dl=None,
                std_mg_dl=None,
                cv_pct=None,
                gmi=None,
                tir_pct=None,
                time_below_pct=None,
                time_above_pct=None,
                severe_low_count=0,
                severe_high_count=0,
                latest_mg_dl=latest.glucose_mg_dl if latest else None,
                latest_trend_arrow=latest.trend_arrow if latest else None,
            )

        values = [r.glucose_mg_dl for r in rows if r.glucose_mg_dl is not None]
        n = len(values)

        mean = sum(values) / n if n > 0 else None
        variance = sum((v - mean) ** 2 for v in values) / n if (mean is not None and n > 0) else None
        std = variance**0.5 if variance is not None else None
        cv = (std / mean * 100) if (std is not None and mean) else None

        # GMI (Glucose Management Indicator) 近似：
        # GMI% = 3.31 + 0.02392 × mean_glucose_mg_dl
        gmi = round(3.31 + 0.02392 * mean, 2) if mean is not None else None

        tir = sum(1 for v in values if GLUCOSE_LOW <= v <= GLUCOSE_HIGH) / n * 100 if n else None
        below = sum(1 for v in values if v < GLUCOSE_LOW) / n * 100 if n else None
        above = sum(1 for v in values if v > GLUCOSE_HIGH) / n * 100 if n else None

        severe_low = sum(1 for v in values if v < GLUCOSE_SEVERE_LOW)
        severe_high = sum(1 for v in values if v > GLUCOSE_SEVERE_HIGH)

        return GlucoseSummary(
            start=start,
            end=end,
            count=n,
            mean_mg_dl=round(mean, 1) if mean is not None else None,
            std_mg_dl=round(std, 1) if std is not None else None,
            cv_pct=round(cv, 1) if cv is not None else None,
            gmi=gmi,
            tir_pct=round(tir, 1) if tir is not None else None,
            time_below_pct=round(below, 1) if below is not None else None,
            time_above_pct=round(above, 1) if above is not None else None,
            severe_low_count=severe_low,
            severe_high_count=severe_high,
            latest_mg_dl=latest.glucose_mg_dl if latest else None,
            latest_trend_arrow=latest.trend_arrow if latest else None,
            latest_measured_at=latest.measured_at if latest else None,
        )

    def ingest_reading(
        self,
        db: Session,
        user_id: int,
        measured_at: datetime,
        glucose_mg_dl: float,
        source: str = "manual",
        trend_arrow: Optional[str] = None,
        trend_rate: Optional[float] = None,
        device_serial: Optional[str] = None,
        raw_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> CgmReading:
        """写入一条读数，幂等（依赖 raw_id + user_id 唯一索引）。"""
        if raw_id:
            existing = (
                db.query(CgmReading)
                .filter(
                    and_(
                        CgmReading.user_id == user_id,
                        CgmReading.raw_id == raw_id,
                    )
                )
                .first()
            )
            if existing:
                return existing

        reading = CgmReading(
            user_id=user_id,
            measured_at=measured_at,
            glucose_mg_dl=glucose_mg_dl,
            trend_arrow=trend_arrow,
            trend_rate=trend_rate,
            source=source,
            device_serial=device_serial,
            raw_id=raw_id,
            notes=notes,
        )
        db.add(reading)
        db.commit()
        db.refresh(reading)
        return reading

    def ingest_batch(
        self,
        db: Session,
        user_id: int,
        readings: List[Any],
    ) -> Dict[str, int]:
        """
        批量写入。入参可以是 CgmReadingDTO 或 dict。

        返回 {"inserted": N, "duplicates": N}.
        """
        inserted = 0
        duplicates = 0
        for r in readings:
            measured_at = getattr(r, "measured_at", None) or r.get("measured_at")
            glucose = getattr(r, "glucose_mg_dl", None) or r.get("glucose_mg_dl")
            raw_id = getattr(r, "raw_id", None) or r.get("raw_id") if isinstance(r, dict) else getattr(r, "raw_id", None)
            source = getattr(r, "source", None) or (r.get("source") if isinstance(r, dict) else None) or "manual"

            if not measured_at or glucose is None:
                continue

            # 幂等检查
            if raw_id:
                exists = (
                    db.query(CgmReading.id)
                    .filter(and_(CgmReading.user_id == user_id, CgmReading.raw_id == raw_id))
                    .first()
                )
                if exists:
                    duplicates += 1
                    continue

            reading = CgmReading(
                user_id=user_id,
                measured_at=measured_at,
                glucose_mg_dl=float(glucose),
                trend_arrow=getattr(r, "trend_arrow", None) if not isinstance(r, dict) else r.get("trend_arrow"),
                trend_rate=getattr(r, "trend_rate", None) if not isinstance(r, dict) else r.get("trend_rate"),
                source=source,
                device_serial=getattr(r, "device_serial", None) if not isinstance(r, dict) else r.get("device_serial"),
                raw_id=raw_id,
            )
            db.add(reading)
            inserted += 1

        if inserted:
            db.commit()

        return {"inserted": inserted, "duplicates": duplicates}
