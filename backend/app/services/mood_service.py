"""情绪追踪服务"""
import logging
from typing import Optional, List, Dict, Any
from datetime import date, timedelta
from collections import Counter

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc

from app.models.mood import MoodRecord
from app.schemas.mood import MoodStats, MoodDailyTrend, MoodCalendar

logger = logging.getLogger(__name__)


class MoodService:
    """情绪追踪服务"""

    def create_record(
        self,
        db: Session,
        user_id: int,
        record_date: date,
        mood_score: int,
        mood_tags: Optional[List[str]] = None,
        energy_level: Optional[int] = None,
        stress_level: Optional[int] = None,
        anxiety_level: Optional[int] = None,
        sleep_quality: Optional[int] = None,
        journal: Optional[str] = None,
        triggers: Optional[List[str]] = None,
        coping_methods: Optional[List[str]] = None,
    ) -> MoodRecord:
        """创建情绪记录"""
        logger.info(f"[Mood] 用户 {user_id} 创建情绪记录: date={record_date}, score={mood_score}")

        record = MoodRecord(
            user_id=user_id,
            record_date=record_date,
            mood_score=mood_score,
            mood_tags=mood_tags or [],
            energy_level=energy_level,
            stress_level=stress_level,
            anxiety_level=anxiety_level,
            sleep_quality=sleep_quality,
            journal=journal,
            triggers=triggers or [],
            coping_methods=coping_methods or [],
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        logger.info(f"[Mood] 情绪记录创建成功: id={record.id}")
        return record

    def update_record(
        self,
        db: Session,
        record_id: int,
        user_id: int,
        **kwargs,
    ) -> Optional[MoodRecord]:
        """更新情绪记录"""
        logger.info(f"[Mood] 用户 {user_id} 更新情绪记录: id={record_id}")

        record = db.query(MoodRecord).filter(
            MoodRecord.id == record_id,
            MoodRecord.user_id == user_id,
        ).first()

        if not record:
            logger.warning(f"[Mood] 记录不存在或无权访问: id={record_id}, user={user_id}")
            return None

        for key, value in kwargs.items():
            if value is not None and hasattr(record, key):
                setattr(record, key, value)

        db.commit()
        db.refresh(record)

        logger.info(f"[Mood] 情绪记录更新成功: id={record.id}")
        return record

    def get_record(
        self,
        db: Session,
        record_id: int,
        user_id: int,
    ) -> Optional[MoodRecord]:
        """获取单条记录"""
        return db.query(MoodRecord).filter(
            MoodRecord.id == record_id,
            MoodRecord.user_id == user_id,
        ).first()

    def get_records(
        self,
        db: Session,
        user_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 30,
    ) -> List[MoodRecord]:
        """获取情绪记录列表"""
        logger.debug(f"[Mood] 查询记录: user={user_id}, start={start_date}, end={end_date}")

        query = db.query(MoodRecord).filter(MoodRecord.user_id == user_id)

        if start_date:
            query = query.filter(MoodRecord.record_date >= start_date)
        if end_date:
            query = query.filter(MoodRecord.record_date <= end_date)

        records = query.order_by(desc(MoodRecord.record_date)).limit(limit).all()

        logger.debug(f"[Mood] 查询到 {len(records)} 条记录")
        return records

    def get_today_record(
        self,
        db: Session,
        user_id: int,
    ) -> Optional[MoodRecord]:
        """获取今日情绪记录"""
        return db.query(MoodRecord).filter(
            MoodRecord.user_id == user_id,
            MoodRecord.record_date == date.today(),
        ).first()

    def delete_record(
        self,
        db: Session,
        record_id: int,
        user_id: int,
    ) -> bool:
        """删除情绪记录，返回是否成功"""
        record = db.query(MoodRecord).filter(
            MoodRecord.id == record_id,
            MoodRecord.user_id == user_id,
        ).first()

        if not record:
            logger.warning(f"[Mood] 删除失败，记录不存在或无权访问: id={record_id}, user={user_id}")
            return False

        db.delete(record)
        db.commit()
        logger.info(f"[Mood] 记录删除成功: id={record_id}")
        return True

    def get_stats(
        self,
        db: Session,
        user_id: int,
        days: int = 7,
    ) -> MoodStats:
        """获取情绪统计"""
        logger.info(f"[Mood] 获取统计: user={user_id}, days={days}")

        start_date = date.today() - timedelta(days=days - 1)
        records = db.query(MoodRecord).filter(
            MoodRecord.user_id == user_id,
            MoodRecord.record_date >= start_date,
        ).order_by(MoodRecord.record_date).all()

        if not records:
            logger.info(f"[Mood] 无数据: user={user_id}")
            return MoodStats(total_records=0)

        # 基础统计
        mood_scores = [r.mood_score for r in records]
        energy_levels = [r.energy_level for r in records if r.energy_level is not None]
        stress_levels = [r.stress_level for r in records if r.stress_level is not None]
        anxiety_levels = [r.anxiety_level for r in records if r.anxiety_level is not None]
        sleep_qualities = [r.sleep_quality for r in records if r.sleep_quality is not None]

        avg_mood = round(sum(mood_scores) / len(mood_scores), 2)
        avg_energy = round(sum(energy_levels) / len(energy_levels), 2) if energy_levels else None
        avg_stress = round(sum(stress_levels) / len(stress_levels), 2) if stress_levels else None
        avg_anxiety = round(sum(anxiety_levels) / len(anxiety_levels), 2) if anxiety_levels else None

        # 情绪分布
        mood_distribution = dict(Counter(mood_scores))

        # 标签/触发因素/应对方式频率
        all_tags = []
        all_triggers = []
        all_coping = []
        for r in records:
            if r.mood_tags:
                all_tags.extend(r.mood_tags)
            if r.triggers:
                all_triggers.extend(r.triggers)
            if r.coping_methods:
                all_coping.extend(r.coping_methods)

        top_mood_tags = dict(Counter(all_tags).most_common(10))
        top_triggers = dict(Counter(all_triggers).most_common(10))
        top_coping_methods = dict(Counter(all_coping).most_common(10))

        # 每日趋势
        daily_trend = []
        for r in records:
            daily_trend.append(MoodDailyTrend(
                date=r.record_date,
                mood_score=r.mood_score,
                energy_level=r.energy_level,
                stress_level=r.stress_level,
                anxiety_level=r.anxiety_level,
                record_count=1,
            ))

        # 相关性计算
        mood_energy_corr = self._calculate_correlation(
            mood_scores,
            [r.energy_level for r in records],
        )
        mood_sleep_corr = self._calculate_correlation(
            mood_scores,
            [r.sleep_quality for r in records],
        )

        stats = MoodStats(
            total_records=len(records),
            avg_mood_score=avg_mood,
            avg_energy_level=avg_energy,
            avg_stress_level=avg_stress,
            avg_anxiety_level=avg_anxiety,
            mood_distribution=mood_distribution,
            top_mood_tags=top_mood_tags,
            top_triggers=top_triggers,
            top_coping_methods=top_coping_methods,
            daily_trend=daily_trend,
            mood_energy_correlation=mood_energy_corr,
            mood_sleep_correlation=mood_sleep_corr,
        )

        logger.info(f"[Mood] 统计完成: {len(records)} 条记录, avg_mood={avg_mood}")
        return stats

    def get_calendar(
        self,
        db: Session,
        user_id: int,
        year: int,
        month: int,
    ) -> MoodCalendar:
        """获取情绪日历"""
        logger.info(f"[Mood] 获取日历: user={user_id}, {year}-{month}")

        # 计算月份范围
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)

        records = db.query(MoodRecord).filter(
            MoodRecord.user_id == user_id,
            MoodRecord.record_date >= start_date,
            MoodRecord.record_date <= end_date,
        ).all()

        days = {}
        scores = []
        for r in records:
            day = r.record_date.day
            days[day] = {
                "mood_score": r.mood_score,
                "mood_tags": r.mood_tags or [],
                "has_journal": bool(r.journal),
                "energy_level": r.energy_level,
                "stress_level": r.stress_level,
            }
            scores.append(r.mood_score)

        return MoodCalendar(
            year=year,
            month=month,
            days=days,
            total_days=end_date.day,
            recorded_days=len(days),
            avg_mood_score=round(sum(scores) / len(scores), 2) if scores else None,
        )

    @staticmethod
    def _calculate_correlation(x_values: List, y_values: List) -> Optional[float]:
        """计算皮尔逊相关系数（仅在两组数据都存在时计算）"""
        # 过滤掉 None 值的配对
        pairs = [(a, b) for a, b in zip(x_values, y_values) if a is not None and b is not None]
        if len(pairs) < 3:
            return None

        x = [p[0] for p in pairs]
        y = [p[1] for p in pairs]

        n = len(pairs)
        mean_x = sum(x) / n
        mean_y = sum(y) / n

        # 计算协方差和标准差
        cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y)) / n
        std_x = (sum((xi - mean_x) ** 2 for xi in x) / n) ** 0.5
        std_y = (sum((yi - mean_y) ** 2 for yi in y) / n) ** 0.5

        if std_x == 0 or std_y == 0:
            return None

        correlation = cov / (std_x * std_y)
        return round(correlation, 4)


# 单例
mood_service = MoodService()
