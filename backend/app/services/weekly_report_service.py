"""周度健康报告服务 — 聚合一周数据生成结构化报告"""
import logging
from datetime import date, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.daily_health import GarminData, DietRecord
from app.models.checkin import CheckinRecord
from app.models.anomaly_alert import AnomalyAlert

logger = logging.getLogger(__name__)


class WeeklyReportService:
    """生成周度健康报告"""

    def generate_report(
        self,
        db: Session,
        user_id: int,
        week_start: date,
        week_end: date,
    ) -> Dict[str, Any]:
        """生成一周健康报告"""
        logger.info(f"[周报] 生成报告: user={user_id}, {week_start}~{week_end}")

        # 获取 Garmin 数据
        garmin_data = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= week_start,
            GarminData.record_date <= week_end,
        ).order_by(GarminData.record_date).all()

        # 获取饮食数据
        diet_data = db.query(DietRecord).filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date >= week_start,
            DietRecord.record_date <= week_end,
        ).all()

        # 获取打卡数据
        checkin_data = db.query(CheckinRecord).filter(
            CheckinRecord.user_id == user_id,
            CheckinRecord.record_date >= week_start,
            CheckinRecord.record_date <= week_end,
        ).all()

        # 获取预警
        alerts = db.query(AnomalyAlert).filter(
            AnomalyAlert.user_id == user_id,
            AnomalyAlert.detection_date >= week_start,
            AnomalyAlert.detection_date <= week_end,
        ).all()

        # 健康评分趋势
        score_trend = self._get_score_trend(db, user_id, week_start, week_end)

        report = {
            "period": f"{week_start} ~ {week_end}",
            "days_with_data": len(garmin_data),
            "score_trend": score_trend,
            "sleep_summary": self._summarize_sleep(garmin_data),
            "exercise_summary": self._summarize_exercise(garmin_data),
            "diet_summary": self._summarize_diet(diet_data),
            "checkin_summary": self._summarize_checkins(checkin_data),
            "alerts_count": len(alerts),
            "alerts_by_severity": {
                "critical": len([a for a in alerts if a.severity == "critical"]),
                "warning": len([a for a in alerts if a.severity == "warning"]),
                "info": len([a for a in alerts if a.severity == "info"]),
            },
            "highlights": [],
            "suggestions": [],
        }

        # 生成亮点和建议
        self._generate_insights(report, garmin_data)

        return report

    def _get_score_trend(self, db, user_id, week_start, week_end):
        """获取健康评分趋势"""
        try:
            from app.services.health_score_service import health_score_service
            scores = []
            d = week_start
            while d <= week_end:
                result = health_score_service.calculate_daily_score(db, user_id, target_date=d)
                if result.get("status") == "ok":
                    scores.append({"date": str(d), "score": result["total_score"]})
                d += timedelta(days=1)
            if scores:
                avg = sum(s["score"] for s in scores) / len(scores)
                return {"scores": scores, "average": round(avg, 1)}
        except Exception as e:
            logger.warning(f"获取评分趋势失败: {e}")
        return None

    def _summarize_sleep(self, garmin_data):
        """睡眠摘要"""
        scores = [g.sleep_score for g in garmin_data if g.sleep_score]
        durations = [g.total_sleep_duration for g in garmin_data if g.total_sleep_duration]
        deep = [g.deep_sleep_duration for g in garmin_data if g.deep_sleep_duration]
        if not scores:
            return None
        return {
            "avg_score": round(sum(scores) / len(scores), 1),
            "avg_duration_min": round(sum(durations) / len(durations)) if durations else None,
            "avg_deep_min": round(sum(deep) / len(deep)) if deep else None,
            "days_recorded": len(scores),
        }

    def _summarize_exercise(self, garmin_data):
        """运动摘要"""
        steps = [g.steps for g in garmin_data if g.steps]
        active = [g.active_minutes for g in garmin_data if g.active_minutes]
        calories = [g.calories for g in garmin_data if g.calories]
        if not steps:
            return None
        return {
            "avg_steps": round(sum(steps) / len(steps)),
            "total_steps": sum(steps),
            "avg_active_min": round(sum(active) / len(active)) if active else None,
            "avg_calories": round(sum(calories) / len(calories)) if calories else None,
            "days_recorded": len(steps),
        }

    def _summarize_diet(self, diet_data):
        """饮食摘要"""
        if not diet_data:
            return None
        days_calories = {}
        for r in diet_data:
            if r.calories:
                d = r.record_date
                days_calories[d] = days_calories.get(d, 0) + r.calories
        if not days_calories:
            return None
        avg_cal = sum(days_calories.values()) / len(days_calories)
        return {
            "avg_daily_calories": round(avg_cal),
            "days_recorded": len(days_calories),
            "total_meals": len(diet_data),
        }

    def _summarize_checkins(self, checkin_data):
        """打卡摘要"""
        if not checkin_data:
            return None
        by_template = {}
        for c in checkin_data:
            name = c.template_name or f"template_{c.template_id}"
            by_template.setdefault(name, []).append(c)
        return {
            "total_checkins": len(checkin_data),
            "unique_templates": len(by_template),
            "by_template": {
                name: {"count": len(records), "days": len(set(r.record_date for r in records))}
                for name, records in by_template.items()
            },
        }

    def _generate_insights(self, report, garmin_data):
        """基于数据生成亮点和建议"""
        highlights = report["highlights"]
        suggestions = report["suggestions"]

        # 睡眠
        sleep = report["sleep_summary"]
        if sleep:
            if sleep["avg_score"] >= 80:
                highlights.append(f"本周睡眠质量优秀，平均{sleep['avg_score']}分")
            elif sleep["avg_score"] < 60:
                suggestions.append(f"睡眠质量偏低(均分{sleep['avg_score']})，建议调整作息")

        # 运动
        exercise = report["exercise_summary"]
        if exercise:
            if exercise["avg_steps"] >= 10000:
                highlights.append(f"步数达标！日均{exercise['avg_steps']}步")
            elif exercise["avg_steps"] < 5000:
                suggestions.append(f"日均步数仅{exercise['avg_steps']}步，建议增加日常活动量")

        # 预警
        if report["alerts_by_severity"]["critical"] > 0:
            suggestions.append(f"本周有{report['alerts_by_severity']['critical']}条严重预警，请特别关注")

        # 打卡
        checkin = report["checkin_summary"]
        if checkin and checkin["total_checkins"] >= 14:
            highlights.append(f"打卡积极！本周完成{checkin['total_checkins']}次")


weekly_report_service = WeeklyReportService()
