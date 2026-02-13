"""健康报告服务 - 聚合多维度数据生成周报/月报"""
import logging
from typing import Optional, List, Dict, Any
from datetime import date, timedelta
from collections import Counter

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc

from app.models.health_report import HealthReport
from app.models.daily_health import GarminData, DietRecord
from app.models.weight import WeightRecord
from app.models.mood import MoodRecord
from app.models.checkin import CheckinTemplate, CheckinRecord
from app.models.blood_pressure import BloodPressureRecord
from app.models.daily_health import ExerciseRecord

logger = logging.getLogger(__name__)


class HealthReportService:
    """健康报告服务"""

    def generate_report(
        self,
        db: Session,
        user_id: int,
        report_type: str = "weekly",
        start_date: Optional[date] = None,
    ) -> HealthReport:
        """生成健康报告"""
        logger.info(f"[Report] 生成报告: user={user_id}, type={report_type}")

        today = date.today()

        # 计算时间范围
        if report_type == "weekly":
            days = 7
            end = today
            start = start_date or (end - timedelta(days=6))
        elif report_type == "monthly":
            days = 30
            end = today
            start = start_date or (end - timedelta(days=29))
        else:
            days = 365
            end = today
            start = start_date or (end - timedelta(days=364))

        # 生成标题
        title = self._generate_title(report_type, start, end)

        # 收集各维度数据
        exercise_summary = self._collect_exercise_summary(db, user_id, start, end)
        diet_summary = self._collect_diet_summary(db, user_id, start, end)
        sleep_summary = self._collect_sleep_summary(db, user_id, start, end)
        weight_summary = self._collect_weight_summary(db, user_id, start, end)
        mood_summary = self._collect_mood_summary(db, user_id, start, end)
        checkin_summary = self._collect_checkin_summary(db, user_id, start, end)
        vital_signs_summary = self._collect_vital_signs_summary(db, user_id, start, end)

        # 计算健康评分
        health_score = self._calculate_health_score(
            exercise_summary, diet_summary, sleep_summary,
            weight_summary, mood_summary, checkin_summary, vital_signs_summary,
        )

        # 获取上期报告进行对比
        comparison = self._generate_comparison(
            db, user_id, report_type, start, days,
            exercise_summary, sleep_summary, mood_summary, health_score,
        )

        # 生成 AI 建议（简单规则，不依赖外部 API）
        recommendations = self._generate_recommendations(
            exercise_summary, diet_summary, sleep_summary,
            mood_summary, vital_signs_summary,
        )

        # 保存报告
        report = HealthReport(
            user_id=user_id,
            report_type=report_type,
            start_date=start,
            end_date=end,
            title=title,
            exercise_summary=exercise_summary,
            diet_summary=diet_summary,
            sleep_summary=sleep_summary,
            weight_summary=weight_summary,
            mood_summary=mood_summary,
            checkin_summary=checkin_summary,
            vital_signs_summary=vital_signs_summary,
            ai_recommendations=recommendations,
            health_score=health_score,
            comparison=comparison,
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        logger.info(f"[Report] 报告生成成功: id={report.id}, score={health_score}")
        return report

    def list_reports(
        self,
        db: Session,
        user_id: int,
        report_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[HealthReport]:
        """列出用户的报告"""
        query = db.query(HealthReport).filter(HealthReport.user_id == user_id)
        if report_type:
            query = query.filter(HealthReport.report_type == report_type)
        return query.order_by(desc(HealthReport.created_at)).limit(limit).all()

    def get_report(self, db: Session, report_id: int, user_id: int) -> Optional[HealthReport]:
        """获取单个报告"""
        return db.query(HealthReport).filter(
            HealthReport.id == report_id,
            HealthReport.user_id == user_id,
        ).first()

    def delete_report(self, db: Session, report_id: int, user_id: int) -> bool:
        """删除报告"""
        report = db.query(HealthReport).filter(
            HealthReport.id == report_id,
            HealthReport.user_id == user_id,
        ).first()
        if not report:
            return False
        db.delete(report)
        db.commit()
        return True

    # === 数据收集方法 ===

    def _collect_exercise_summary(
        self, db: Session, user_id: int, start: date, end: date
    ) -> Dict[str, Any]:
        """收集运动数据"""
        logger.debug(f"[Report] 收集运动数据: {start} - {end}")

        garmin_data = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start,
            GarminData.record_date <= end,
        ).all()

        if not garmin_data:
            return {"total_steps": 0, "avg_daily_steps": 0, "total_active_minutes": 0}

        steps = [g.steps or 0 for g in garmin_data]
        active_cals = [g.active_calories or 0 for g in garmin_data]
        heart_rates = [g.avg_heart_rate for g in garmin_data if g.avg_heart_rate]

        days = (end - start).days + 1

        return {
            "total_steps": sum(steps),
            "avg_daily_steps": round(sum(steps) / days),
            "total_calories_burned": round(sum(active_cals), 1),
            "avg_heart_rate": round(sum(heart_rates) / len(heart_rates), 1) if heart_rates else None,
            "max_heart_rate": max([g.avg_heart_rate for g in garmin_data if g.avg_heart_rate] or [0]),
            "data_days": len(garmin_data),
        }

    def _collect_diet_summary(
        self, db: Session, user_id: int, start: date, end: date
    ) -> Dict[str, Any]:
        """收集饮食数据"""
        logger.debug(f"[Report] 收集饮食数据: {start} - {end}")

        records = db.query(DietRecord).filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date >= start,
            DietRecord.record_date <= end,
        ).all()

        if not records:
            return {"record_days": 0, "meal_count": 0}

        # 按天统计
        daily_calories = {}
        daily_protein = {}
        daily_carbs = {}
        daily_fat = {}

        for r in records:
            d = str(r.record_date)
            daily_calories[d] = daily_calories.get(d, 0) + (r.calories or 0)
            daily_protein[d] = daily_protein.get(d, 0) + (r.protein or 0)
            daily_carbs[d] = daily_carbs.get(d, 0) + (r.carbs or 0)
            daily_fat[d] = daily_fat.get(d, 0) + (r.fat or 0)

        record_days = len(daily_calories)

        return {
            "avg_daily_calories": round(sum(daily_calories.values()) / record_days, 1) if record_days else None,
            "avg_daily_protein": round(sum(daily_protein.values()) / record_days, 1) if record_days else None,
            "avg_daily_carbs": round(sum(daily_carbs.values()) / record_days, 1) if record_days else None,
            "avg_daily_fat": round(sum(daily_fat.values()) / record_days, 1) if record_days else None,
            "meal_count": len(records),
            "record_days": record_days,
        }

    def _collect_sleep_summary(
        self, db: Session, user_id: int, start: date, end: date
    ) -> Dict[str, Any]:
        """收集睡眠数据"""
        logger.debug(f"[Report] 收集睡眠数据: {start} - {end}")

        garmin_data = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start,
            GarminData.record_date <= end,
            GarminData.total_sleep_duration.isnot(None),
        ).all()

        if not garmin_data:
            return {}

        durations = [g.total_sleep_duration for g in garmin_data if g.total_sleep_duration]
        scores = [g.sleep_score for g in garmin_data if g.sleep_score]
        deep = [g.deep_sleep_duration for g in garmin_data if g.deep_sleep_duration]
        rem = [g.rem_sleep_duration for g in garmin_data if g.rem_sleep_duration]

        best = max(garmin_data, key=lambda g: g.sleep_score or 0)
        worst = min(garmin_data, key=lambda g: g.sleep_score or 999)

        return {
            "avg_sleep_duration": round(sum(durations) / len(durations), 1) if durations else None,
            "avg_sleep_score": round(sum(scores) / len(scores), 1) if scores else None,
            "avg_deep_sleep": round(sum(deep) / len(deep), 1) if deep else None,
            "avg_rem_sleep": round(sum(rem) / len(rem), 1) if rem else None,
            "best_sleep_date": str(best.record_date) if best.sleep_score else None,
            "worst_sleep_date": str(worst.record_date) if worst.sleep_score else None,
            "data_days": len(garmin_data),
        }

    def _collect_weight_summary(
        self, db: Session, user_id: int, start: date, end: date
    ) -> Dict[str, Any]:
        """收集体重数据"""
        logger.debug(f"[Report] 收集体重数据: {start} - {end}")

        records = db.query(WeightRecord).filter(
            WeightRecord.user_id == user_id,
            WeightRecord.record_date >= start,
            WeightRecord.record_date <= end,
        ).order_by(WeightRecord.record_date).all()

        if not records:
            return {"record_count": 0}

        weights = [r.weight for r in records if r.weight]

        return {
            "start_weight": records[0].weight,
            "end_weight": records[-1].weight,
            "weight_change": round(records[-1].weight - records[0].weight, 2) if len(records) >= 2 else None,
            "min_weight": min(weights) if weights else None,
            "max_weight": max(weights) if weights else None,
            "record_count": len(records),
        }

    def _collect_mood_summary(
        self, db: Session, user_id: int, start: date, end: date
    ) -> Dict[str, Any]:
        """收集情绪数据"""
        logger.debug(f"[Report] 收集情绪数据: {start} - {end}")

        records = db.query(MoodRecord).filter(
            MoodRecord.user_id == user_id,
            MoodRecord.record_date >= start,
            MoodRecord.record_date <= end,
        ).all()

        if not records:
            return {"record_days": 0}

        scores = [r.mood_score for r in records]
        energy = [r.energy_level for r in records if r.energy_level]
        stress = [r.stress_level for r in records if r.stress_level]
        all_tags = []
        all_triggers = []
        for r in records:
            if r.mood_tags:
                all_tags.extend(r.mood_tags)
            if r.triggers:
                all_triggers.extend(r.triggers)

        return {
            "avg_mood_score": round(sum(scores) / len(scores), 2),
            "avg_energy_level": round(sum(energy) / len(energy), 2) if energy else None,
            "avg_stress_level": round(sum(stress) / len(stress), 2) if stress else None,
            "record_days": len(records),
            "top_mood_tags": [t for t, _ in Counter(all_tags).most_common(5)],
            "top_triggers": [t for t, _ in Counter(all_triggers).most_common(5)],
        }

    def _collect_checkin_summary(
        self, db: Session, user_id: int, start: date, end: date
    ) -> Dict[str, Any]:
        """收集打卡数据"""
        logger.debug(f"[Report] 收集打卡数据: {start} - {end}")

        templates = db.query(CheckinTemplate).filter(
            CheckinTemplate.user_id == user_id,
            CheckinTemplate.is_active == True,
        ).all()

        records = db.query(CheckinRecord).filter(
            CheckinRecord.user_id == user_id,
            CheckinRecord.checkin_date >= start,
            CheckinRecord.checkin_date <= end,
        ).all()

        days = (end - start).days + 1
        active_count = len(templates)
        total_expected = active_count * days if active_count > 0 else 1

        return {
            "total_checkins": len(records),
            "active_templates": active_count,
            "avg_completion_rate": round(len(records) / total_expected * 100, 1) if total_expected > 0 else None,
        }

    def _collect_vital_signs_summary(
        self, db: Session, user_id: int, start: date, end: date
    ) -> Dict[str, Any]:
        """收集体征数据"""
        logger.debug(f"[Report] 收集体征数据: {start} - {end}")

        garmin_data = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start,
            GarminData.record_date <= end,
        ).all()

        if not garmin_data:
            return {}

        rhr = [g.resting_heart_rate for g in garmin_data if g.resting_heart_rate]
        hrv = [g.hrv for g in garmin_data if g.hrv]
        stress = [g.stress_level for g in garmin_data if g.stress_level]
        battery = [g.body_battery_current for g in garmin_data if g.body_battery_current]
        spo2 = [g.spo2_avg for g in garmin_data if g.spo2_avg]

        return {
            "avg_resting_heart_rate": round(sum(rhr) / len(rhr), 1) if rhr else None,
            "avg_hrv": round(sum(hrv) / len(hrv), 1) if hrv else None,
            "avg_stress_level": round(sum(stress) / len(stress), 1) if stress else None,
            "avg_body_battery": round(sum(battery) / len(battery), 1) if battery else None,
            "avg_spo2": round(sum(spo2) / len(spo2), 1) if spo2 else None,
        }

    # === 辅助方法 ===

    def _calculate_health_score(
        self, exercise, diet, sleep, weight, mood, checkin, vitals,
    ) -> int:
        """计算综合健康评分 (0-100)"""
        scores = []
        weights_list = []

        # 运动评分 (权重 25%)
        if exercise.get("avg_daily_steps", 0) > 0:
            step_score = min(exercise["avg_daily_steps"] / 10000 * 100, 100)
            scores.append(step_score)
            weights_list.append(25)

        # 睡眠评分 (权重 25%)
        if sleep.get("avg_sleep_score"):
            scores.append(sleep["avg_sleep_score"])
            weights_list.append(25)

        # 情绪评分 (权重 20%)
        if mood.get("avg_mood_score"):
            mood_score = mood["avg_mood_score"] / 5 * 100
            scores.append(mood_score)
            weights_list.append(20)

        # 饮食评分 (权重 15%)
        if diet.get("record_days", 0) > 0:
            # 基于记录天数的完成度
            diet_score = min(diet["record_days"] / 7 * 100, 100)
            scores.append(diet_score)
            weights_list.append(15)

        # 打卡评分 (权重 15%)
        if checkin.get("avg_completion_rate"):
            scores.append(min(checkin["avg_completion_rate"], 100))
            weights_list.append(15)

        if not scores:
            return 50  # 无数据时默认中等

        total_weight = sum(weights_list)
        weighted_sum = sum(s * w for s, w in zip(scores, weights_list))
        final_score = round(weighted_sum / total_weight)

        return max(0, min(100, final_score))

    def _generate_comparison(
        self, db, user_id, report_type, current_start, days,
        exercise, sleep, mood, health_score,
    ) -> Dict[str, Any]:
        """与上期对比"""
        prev_end = current_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=days - 1)

        prev_report = db.query(HealthReport).filter(
            HealthReport.user_id == user_id,
            HealthReport.report_type == report_type,
            HealthReport.start_date >= prev_start,
            HealthReport.end_date <= prev_end,
        ).first()

        if not prev_report:
            return {}

        comparison = {}

        # 健康评分对比
        if prev_report.health_score:
            comparison["health_score_change"] = health_score - prev_report.health_score

        # 步数对比
        prev_steps = (prev_report.exercise_summary or {}).get("avg_daily_steps", 0)
        curr_steps = exercise.get("avg_daily_steps", 0)
        if prev_steps > 0:
            comparison["steps_change_pct"] = round((curr_steps - prev_steps) / prev_steps * 100, 1)

        # 睡眠对比
        prev_sleep = (prev_report.sleep_summary or {}).get("avg_sleep_score")
        curr_sleep = sleep.get("avg_sleep_score")
        if prev_sleep and curr_sleep:
            comparison["sleep_score_change"] = round(curr_sleep - prev_sleep, 1)

        # 情绪对比
        prev_mood = (prev_report.mood_summary or {}).get("avg_mood_score")
        curr_mood = mood.get("avg_mood_score")
        if prev_mood and curr_mood:
            comparison["mood_score_change"] = round(curr_mood - prev_mood, 2)

        return comparison

    def _generate_recommendations(
        self, exercise, diet, sleep, mood, vitals,
    ) -> List[str]:
        """基于数据生成建议"""
        recommendations = []

        # 运动建议
        avg_steps = exercise.get("avg_daily_steps", 0)
        if avg_steps < 5000:
            recommendations.append("日均步数不足5000步，建议增加日常活动量，可以从每天散步30分钟开始")
        elif avg_steps < 8000:
            recommendations.append("日均步数尚可，建议争取达到每天8000-10000步")

        # 睡眠建议
        avg_sleep_score = sleep.get("avg_sleep_score")
        if avg_sleep_score and avg_sleep_score < 70:
            recommendations.append("睡眠质量有待提升，建议保持规律作息，睡前避免使用电子设备")

        avg_duration = sleep.get("avg_sleep_duration")
        if avg_duration and avg_duration < 420:  # 7小时
            recommendations.append("平均睡眠时间不足7小时，建议适当提前就寝时间")

        # 情绪建议
        avg_mood = mood.get("avg_mood_score")
        if avg_mood and avg_mood < 3:
            recommendations.append("近期情绪偏低，建议多进行户外运动或与朋友交流，必要时可尝试冥想放松")
        avg_stress = mood.get("avg_stress_level")
        if avg_stress and avg_stress > 3.5:
            recommendations.append("压力水平较高，建议合理安排工作休息，尝试深呼吸或瑜伽缓解压力")

        # 饮食建议
        if diet.get("record_days", 0) < 3:
            recommendations.append("饮食记录较少，坚持记录饮食有助于了解营养摄入状况")

        # 体征建议
        rhr = vitals.get("avg_resting_heart_rate")
        if rhr and rhr > 80:
            recommendations.append("静息心率偏高，建议加强有氧运动以改善心肺功能")

        if not recommendations:
            recommendations.append("各项指标表现良好，继续保持当前的健康生活方式！")

        return recommendations

    @staticmethod
    def _generate_title(report_type: str, start: date, end: date) -> str:
        """生成报告标题"""
        if report_type == "weekly":
            week_num = start.isocalendar()[1]
            return f"{start.year}年第{week_num}周健康报告"
        elif report_type == "monthly":
            return f"{start.year}年{start.month}月健康报告"
        else:
            return f"{start.year}年度健康报告"


health_report_service = HealthReportService()
