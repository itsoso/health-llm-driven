"""交互反馈服务 — 收集、聚合、查询反馈数据"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import func, and_, case
from sqlalchemy.orm import Session

from app.models.interaction_feedback import InteractionFeedback, SkillMetrics, SkillOptimizationLog

logger = logging.getLogger(__name__)


class FeedbackService:

    # ---- 写入 ----

    def submit_rating(
        self,
        db: Session,
        user_id: int,
        conversation_type: str,
        conversation_id: int,
        message_id: int,
        rating: int,
        feedback_text: Optional[str] = None,
    ) -> InteractionFeedback:
        """用户提交显式评分（👍👎）"""
        # 查找是否已有该消息的反馈记录（可能由隐式信号先创建）
        existing = db.query(InteractionFeedback).filter(
            InteractionFeedback.conversation_type == conversation_type,
            InteractionFeedback.conversation_id == conversation_id,
            InteractionFeedback.message_id == message_id,
            InteractionFeedback.user_id == user_id,
        ).first()

        if existing:
            existing.rating = rating
            existing.feedback_text = feedback_text
            db.commit()
            db.refresh(existing)
            logger.info(f"更新反馈 #{existing.id}: rating={rating}")
            return existing

        feedback = InteractionFeedback(
            user_id=user_id,
            conversation_type=conversation_type,
            conversation_id=conversation_id,
            message_id=message_id,
            rating=rating,
            feedback_text=feedback_text,
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)
        logger.info(f"新建反馈 #{feedback.id}: rating={rating}")
        return feedback

    def record_implicit(
        self,
        db: Session,
        user_id: int,
        conversation_type: str,
        conversation_id: int,
        message_id: int,
        skill_used: Optional[str] = None,
        skill_version: Optional[str] = None,
        implicit_signal: Optional[str] = None,
        success: Optional[bool] = None,
        error_type: Optional[str] = None,
        response_time_ms: Optional[int] = None,
    ) -> InteractionFeedback:
        """记录隐式信号（后端调用）"""
        existing = db.query(InteractionFeedback).filter(
            InteractionFeedback.conversation_type == conversation_type,
            InteractionFeedback.conversation_id == conversation_id,
            InteractionFeedback.message_id == message_id,
            InteractionFeedback.user_id == user_id,
        ).first()

        if existing:
            if skill_used is not None:
                existing.skill_used = skill_used
            if skill_version is not None:
                existing.skill_version = skill_version
            if implicit_signal is not None:
                existing.implicit_signal = implicit_signal
            if success is not None:
                existing.success = success
            if error_type is not None:
                existing.error_type = error_type
            if response_time_ms is not None:
                existing.response_time_ms = response_time_ms
            db.commit()
            db.refresh(existing)
            return existing

        feedback = InteractionFeedback(
            user_id=user_id,
            conversation_type=conversation_type,
            conversation_id=conversation_id,
            message_id=message_id,
            skill_used=skill_used,
            skill_version=skill_version,
            implicit_signal=implicit_signal,
            success=success,
            error_type=error_type,
            response_time_ms=response_time_ms,
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)
        return feedback

    # ---- 聚合 ----

    def aggregate_daily_metrics(self, db: Session, date: Optional[datetime] = None):
        """聚合指定日期的 Skill 指标（由定时任务调用）"""
        if date is None:
            date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)

        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        # 按 skill + version 分组聚合
        rows = db.query(
            InteractionFeedback.skill_used,
            InteractionFeedback.skill_version,
            func.count().label("total"),
            func.sum(case((InteractionFeedback.success == True, 1), else_=0)).label("success_cnt"),
            func.sum(case((InteractionFeedback.success == False, 1), else_=0)).label("fail_cnt"),
            func.count(InteractionFeedback.rating).label("rated"),
            func.avg(InteractionFeedback.rating).label("avg_rat"),
            func.sum(case((InteractionFeedback.rating == 5, 1), else_=0)).label("up"),
            func.sum(case((InteractionFeedback.rating == 1, 1), else_=0)).label("down"),
            func.avg(InteractionFeedback.response_time_ms).label("avg_rt"),
        ).filter(
            InteractionFeedback.skill_used.isnot(None),
            InteractionFeedback.created_at >= start,
            InteractionFeedback.created_at < end,
        ).group_by(
            InteractionFeedback.skill_used,
            InteractionFeedback.skill_version,
        ).all()

        for row in rows:
            total = row.total or 0
            success_cnt = row.success_cnt or 0
            fail_cnt = row.fail_cnt or 0

            existing = db.query(SkillMetrics).filter(
                SkillMetrics.skill_name == row.skill_used,
                SkillMetrics.skill_version == (row.skill_version or "unknown"),
                SkillMetrics.date == start,
            ).first()

            if existing:
                metrics = existing
            else:
                metrics = SkillMetrics(
                    skill_name=row.skill_used,
                    skill_version=row.skill_version or "unknown",
                    date=start,
                )
                db.add(metrics)

            metrics.total_calls = total
            metrics.success_count = success_cnt
            metrics.failure_count = fail_cnt
            metrics.success_rate = success_cnt / total if total > 0 else None
            metrics.rated_count = row.rated or 0
            metrics.avg_rating = float(row.avg_rat) if row.avg_rat else None
            metrics.thumbs_up = row.up or 0
            metrics.thumbs_down = row.down or 0
            metrics.avg_response_time_ms = int(row.avg_rt) if row.avg_rt else None

        db.commit()
        logger.info(f"聚合了 {len(rows)} 条 skill metrics, date={start.date()}")

    # ---- 查询 ----

    def get_skill_performance(self, db: Session, days: int = 7) -> list:
        """获取所有 Skill 最近 N 天的性能概览"""
        since = datetime.utcnow() - timedelta(days=days)

        rows = db.query(
            SkillMetrics.skill_name,
            func.max(SkillMetrics.skill_version).label("current_version"),
            func.sum(SkillMetrics.total_calls).label("total_calls"),
            func.avg(SkillMetrics.success_rate).label("avg_success_rate"),
            func.avg(SkillMetrics.avg_rating).label("avg_rating"),
            func.sum(SkillMetrics.thumbs_up).label("thumbs_up"),
            func.sum(SkillMetrics.thumbs_down).label("thumbs_down"),
        ).filter(
            SkillMetrics.date >= since,
        ).group_by(SkillMetrics.skill_name).all()

        results = []
        for row in rows:
            # 检查是否有 canary 版本
            canary = db.query(SkillMetrics).filter(
                SkillMetrics.skill_name == row.skill_name,
                SkillMetrics.is_canary == True,
            ).first()

            results.append({
                "skill_name": row.skill_name,
                "current_version": row.current_version,
                "total_calls_7d": row.total_calls or 0,
                "success_rate_7d": float(row.avg_success_rate) if row.avg_success_rate else None,
                "avg_rating_7d": float(row.avg_rating) if row.avg_rating else None,
                "thumbs_up_7d": row.thumbs_up or 0,
                "thumbs_down_7d": row.thumbs_down or 0,
                "has_canary": canary is not None,
                "canary_version": canary.skill_version if canary else None,
            })

        return results

    def get_optimization_logs(
        self, db: Session, skill_name: Optional[str] = None, limit: int = 20
    ) -> List[SkillOptimizationLog]:
        """获取优化历史"""
        q = db.query(SkillOptimizationLog).order_by(SkillOptimizationLog.created_at.desc())
        if skill_name:
            q = q.filter(SkillOptimizationLog.skill_name == skill_name)
        return q.limit(limit).all()

    def get_low_performing_skills(self, db: Session, days: int = 7, threshold: float = 0.8) -> list:
        """找出需要优化的 Skill（success_rate 低于阈值）"""
        since = datetime.utcnow() - timedelta(days=days)

        rows = db.query(
            SkillMetrics.skill_name,
            func.avg(SkillMetrics.success_rate).label("avg_sr"),
            func.avg(SkillMetrics.avg_rating).label("avg_rat"),
            func.sum(SkillMetrics.total_calls).label("total"),
        ).filter(
            SkillMetrics.date >= since,
            SkillMetrics.is_production == True,
        ).group_by(SkillMetrics.skill_name).having(
            func.avg(SkillMetrics.success_rate) < threshold,
        ).all()

        return [
            {
                "skill_name": r.skill_name,
                "avg_success_rate": float(r.avg_sr) if r.avg_sr else 0,
                "avg_rating": float(r.avg_rat) if r.avg_rat else None,
                "total_calls": r.total or 0,
            }
            for r in rows
        ]


# 单例
feedback_service = FeedbackService()
