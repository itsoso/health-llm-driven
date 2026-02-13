"""女性健康服务"""
import logging
from datetime import date, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.womens_health import MenstrualCycle, CycleSymptom

logger = logging.getLogger(__name__)


class WomensHealthService:
    """女性健康管理服务"""

    def start_period(self, db: Session, user_id: int, start_date: date,
                     flow_intensity: str = "moderate") -> MenstrualCycle:
        """记录经期开始"""
        logger.info("[WomensHealth] 用户 %d 记录经期开始: %s", user_id, start_date)
        cycle = MenstrualCycle(
            user_id=user_id,
            start_date=start_date,
            flow_intensity=flow_intensity,
        )
        db.add(cycle)
        db.commit()
        db.refresh(cycle)
        return cycle

    def end_period(self, db: Session, user_id: int, cycle_id: int,
                   end_date: date) -> Optional[MenstrualCycle]:
        """记录经期结束"""
        logger.info("[WomensHealth] 用户 %d 结束经期: cycle_id=%d", user_id, cycle_id)
        cycle = db.query(MenstrualCycle).filter(
            MenstrualCycle.id == cycle_id,
            MenstrualCycle.user_id == user_id,
        ).first()
        if not cycle:
            logger.warning("[WomensHealth] 周期记录不存在: cycle_id=%d", cycle_id)
            return None

        cycle.end_date = end_date
        cycle.period_length = (end_date - cycle.start_date).days + 1

        # 尝试计算周期长度（与上一个周期的间隔）
        prev_cycle = db.query(MenstrualCycle).filter(
            MenstrualCycle.user_id == user_id,
            MenstrualCycle.start_date < cycle.start_date,
        ).order_by(desc(MenstrualCycle.start_date)).first()

        if prev_cycle:
            cycle.cycle_length = (cycle.start_date - prev_cycle.start_date).days

        db.commit()
        db.refresh(cycle)
        return cycle

    def get_cycles(self, db: Session, user_id: int, limit: int = 12) -> List[MenstrualCycle]:
        """获取经期周期列表"""
        logger.info("[WomensHealth] 获取用户 %d 周期列表, limit=%d", user_id, limit)
        return db.query(MenstrualCycle).filter(
            MenstrualCycle.user_id == user_id,
        ).order_by(desc(MenstrualCycle.start_date)).limit(limit).all()

    def predict_next_period(self, db: Session, user_id: int) -> Optional[dict]:
        """预测下次经期"""
        logger.info("[WomensHealth] 预测用户 %d 下次经期", user_id)
        cycles = db.query(MenstrualCycle).filter(
            MenstrualCycle.user_id == user_id,
            MenstrualCycle.cycle_length.isnot(None),
        ).order_by(desc(MenstrualCycle.start_date)).limit(6).all()

        if not cycles:
            logger.info("[WomensHealth] 用户 %d 无足够数据进行预测", user_id)
            return None

        avg_cycle = sum(c.cycle_length for c in cycles) / len(cycles)
        avg_period = None
        period_cycles = [c for c in cycles if c.period_length]
        if period_cycles:
            avg_period = sum(c.period_length for c in period_cycles) / len(period_cycles)

        # 找到最近一个周期的开始日期
        latest = db.query(MenstrualCycle).filter(
            MenstrualCycle.user_id == user_id,
        ).order_by(desc(MenstrualCycle.start_date)).first()

        predicted_start = latest.start_date + timedelta(days=round(avg_cycle))
        predicted_end = predicted_start + timedelta(days=round(avg_period) if avg_period else 5)

        return {
            "predicted_start": str(predicted_start),
            "predicted_end": str(predicted_end),
            "avg_cycle_length": round(avg_cycle, 1),
            "avg_period_length": round(avg_period, 1) if avg_period else None,
            "based_on_cycles": len(cycles),
        }

    def log_symptom(self, db: Session, user_id: int, data: dict) -> CycleSymptom:
        """记录症状"""
        logger.info("[WomensHealth] 用户 %d 记录症状: %s", user_id, data.get("symptom_type"))

        # 尝试关联到当前周期
        record_date = date.fromisoformat(data["record_date"]) if isinstance(data["record_date"], str) else data["record_date"]
        current_cycle = db.query(MenstrualCycle).filter(
            MenstrualCycle.user_id == user_id,
            MenstrualCycle.start_date <= record_date,
        ).order_by(desc(MenstrualCycle.start_date)).first()

        symptom = CycleSymptom(
            user_id=user_id,
            cycle_id=current_cycle.id if current_cycle else None,
            record_date=record_date,
            symptom_type=data["symptom_type"],
            severity=data.get("severity", 1),
            notes=data.get("notes"),
        )
        db.add(symptom)
        db.commit()
        db.refresh(symptom)
        return symptom

    def get_cycle_stats(self, db: Session, user_id: int) -> dict:
        """获取周期统计"""
        logger.info("[WomensHealth] 获取用户 %d 周期统计", user_id)
        cycles = db.query(MenstrualCycle).filter(
            MenstrualCycle.user_id == user_id,
        ).all()

        if not cycles:
            return {
                "avg_cycle_length": None,
                "avg_period_length": None,
                "total_cycles": 0,
            }

        cycle_lengths = [c.cycle_length for c in cycles if c.cycle_length]
        period_lengths = [c.period_length for c in cycles if c.period_length]

        return {
            "avg_cycle_length": round(sum(cycle_lengths) / len(cycle_lengths), 1) if cycle_lengths else None,
            "avg_period_length": round(sum(period_lengths) / len(period_lengths), 1) if period_lengths else None,
            "total_cycles": len(cycles),
        }

    def get_calendar(self, db: Session, user_id: int, year: int, month: int) -> dict:
        """获取日历数据 - 返回指定月份的经期日期"""
        logger.info("[WomensHealth] 获取用户 %d 日历: %d-%02d", user_id, year, month)
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)

        # 查找该月涉及的周期
        cycles = db.query(MenstrualCycle).filter(
            MenstrualCycle.user_id == user_id,
            MenstrualCycle.start_date <= month_end,
        ).filter(
            # 周期的结束日期在月初之后，或者没有结束日期但开始在月份范围内
            (MenstrualCycle.end_date >= month_start) |
            ((MenstrualCycle.end_date.is_(None)) & (MenstrualCycle.start_date >= month_start))
        ).all()

        period_days = []
        for cycle in cycles:
            start = max(cycle.start_date, month_start)
            end = min(cycle.end_date or cycle.start_date, month_end)
            current = start
            while current <= end:
                period_days.append(str(current))
                current += timedelta(days=1)

        # 查找该月的症状
        symptoms = db.query(CycleSymptom).filter(
            CycleSymptom.user_id == user_id,
            CycleSymptom.record_date >= month_start,
            CycleSymptom.record_date <= month_end,
        ).all()

        symptom_days = {}
        for s in symptoms:
            day_str = str(s.record_date)
            if day_str not in symptom_days:
                symptom_days[day_str] = []
            symptom_days[day_str].append({
                "type": s.symptom_type,
                "severity": s.severity,
            })

        return {
            "year": year,
            "month": month,
            "period_days": sorted(set(period_days)),
            "symptom_days": symptom_days,
        }

    def get_symptoms(self, db: Session, user_id: int, cycle_id: Optional[int] = None,
                     start_date: Optional[date] = None, end_date: Optional[date] = None) -> List[CycleSymptom]:
        """获取症状列表"""
        query = db.query(CycleSymptom).filter(CycleSymptom.user_id == user_id)
        if cycle_id:
            query = query.filter(CycleSymptom.cycle_id == cycle_id)
        if start_date:
            query = query.filter(CycleSymptom.record_date >= start_date)
        if end_date:
            query = query.filter(CycleSymptom.record_date <= end_date)
        return query.order_by(desc(CycleSymptom.record_date)).all()


womens_health_service = WomensHealthService()
