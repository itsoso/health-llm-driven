"""健康评分体系服务"""
import logging
from typing import Dict, Any, List, Optional
from datetime import date, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.models.daily_health import GarminData, DietRecord, WaterIntake
from app.models.weight import WeightRecord
from app.models.mood import MoodRecord

logger = logging.getLogger(__name__)


class HealthScoreService:
    """综合健康评分服务 - 基于多维度加权计算"""

    # 维度权重配置
    DIMENSION_WEIGHTS = {
        "运动": 0.20,
        "睡眠": 0.20,
        "饮食": 0.15,
        "情绪": 0.15,
        "体征": 0.10,
        "体重": 0.10,
        "水分": 0.10,
    }

    def calculate_daily_score(
        self,
        db: Session,
        user_id: int,
        target_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """计算某日综合健康评分"""
        if target_date is None:
            target_date = date.today()

        logger.info(f"[HealthScore] 计算评分: user={user_id}, date={target_date}")

        # 收集各维度数据
        exercise_score = self._score_exercise(db, user_id, target_date)
        sleep_score = self._score_sleep(db, user_id, target_date)
        diet_score = self._score_diet(db, user_id, target_date)
        mood_score = self._score_mood(db, user_id, target_date)
        vitals_score = self._score_vitals(db, user_id, target_date)
        weight_score = self._score_weight(db, user_id, target_date)
        hydration_score = self._score_hydration(db, user_id, target_date)

        dimensions = [
            exercise_score,
            sleep_score,
            diet_score,
            mood_score,
            vitals_score,
            weight_score,
            hydration_score,
        ]

        # 过滤有数据的维度
        active_dims = [d for d in dimensions if d["score"] is not None]

        if not active_dims:
            logger.info(f"[HealthScore] 无数据: user={user_id}")
            return {"status": "no_data", "total_score": 0, "dimensions": [], "suggestions": []}

        # 重新分配权重（对有数据的维度按比例重新计算）
        total_active_weight = sum(d["weight"] for d in active_dims)
        for d in active_dims:
            d["weight"] = round(d["weight"] / total_active_weight, 3)

        # 加权计算总分
        total_score = sum(d["score"] * d["weight"] for d in active_dims)
        total_score = round(min(100, max(0, total_score)))

        # 生成建议
        suggestions = self._generate_suggestions(active_dims, total_score)

        logger.info(f"[HealthScore] 评分完成: user={user_id}, score={total_score}, dims={len(active_dims)}")

        return {
            "status": "ok",
            "date": str(target_date),
            "total_score": total_score,
            "grade": self._get_grade(total_score),
            "dimensions": active_dims,
            "suggestions": suggestions,
        }

    def get_score_trend(
        self,
        db: Session,
        user_id: int,
        days: int = 7,
    ) -> Dict[str, Any]:
        """获取健康评分趋势"""
        logger.info(f"[HealthScore] 获取趋势: user={user_id}, days={days}")

        scores = []
        today = date.today()

        for i in range(days):
            d = today - timedelta(days=days - 1 - i)
            result = self.calculate_daily_score(db, user_id, target_date=d)
            if result["status"] == "ok":
                scores.append({
                    "date": str(d),
                    "score": result["total_score"],
                    "grade": result["grade"],
                })

        # 统计
        avg_score = round(sum(s["score"] for s in scores) / len(scores)) if scores else None
        trend_direction = None
        if len(scores) >= 2:
            first_half = scores[:len(scores) // 2]
            second_half = scores[len(scores) // 2:]
            first_avg = sum(s["score"] for s in first_half) / len(first_half)
            second_avg = sum(s["score"] for s in second_half) / len(second_half)
            trend_direction = "up" if second_avg > first_avg + 2 else ("down" if second_avg < first_avg - 2 else "stable")

        # 周/月对比
        score_vs_last_week = None
        score_vs_last_month = None
        if avg_score is not None:
            last_week_scores = []
            for i in range(7):
                d = today - timedelta(days=7 + i)
                r = self.calculate_daily_score(db, user_id, target_date=d)
                if r["status"] == "ok":
                    last_week_scores.append(r["total_score"])
            if last_week_scores:
                lw_avg = sum(last_week_scores) / len(last_week_scores)
                score_vs_last_week = round(avg_score - lw_avg, 1)

        return {
            "scores": scores,
            "avg_score": avg_score,
            "trend": trend_direction,
            "score_vs_last_week": score_vs_last_week,
            "best_day": max(scores, key=lambda s: s["score"]) if scores else None,
            "worst_day": min(scores, key=lambda s: s["score"]) if scores else None,
        }

    def calculate_enhanced_score(
        self,
        db: Session,
        user_id: int,
        target_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """增强版健康评分 — 在基础评分上叠加趋势修正和跨维度协同"""
        base = self.calculate_daily_score(db, user_id, target_date)
        if base["status"] != "ok":
            return base

        target_date = target_date or date.today()
        dimensions = base["dimensions"]

        # 1. 趋势修正：获取过去 7 天同维度平均分，计算趋势方向
        trend_adjustments = []
        for dim in dimensions:
            dim_name = dim["name"]
            recent_scores = []
            for i in range(1, 8):
                d = target_date - timedelta(days=i)
                past = self.calculate_daily_score(db, user_id, target_date=d)
                if past["status"] == "ok":
                    past_dim = next((pd for pd in past["dimensions"] if pd["name"] == dim_name), None)
                    if past_dim and past_dim["score"] is not None:
                        recent_scores.append(past_dim["score"])

            if len(recent_scores) >= 3:
                past_avg = sum(recent_scores) / len(recent_scores)
                current = dim["score"]
                if current > past_avg + 5:
                    modifier = 1.05  # 持续改善 +5%
                    trend_dir = "improving"
                elif current < past_avg - 5:
                    modifier = 0.90  # 持续恶化 -10%
                    trend_dir = "declining"
                else:
                    modifier = 1.0
                    trend_dir = "stable"

                adjusted = min(100, round(current * modifier))
                trend_adjustments.append({
                    "dimension": dim_name,
                    "original_score": current,
                    "adjusted_score": adjusted,
                    "trend": trend_dir,
                    "past_avg": round(past_avg, 1),
                })
                dim["score"] = adjusted
                dim["trend"] = trend_dir

        # 2. 跨维度协同效应
        synergy_alerts = []
        dim_scores = {d["name"]: d["score"] for d in dimensions if d["score"] is not None}

        sleep_s = dim_scores.get("睡眠", 100)
        exercise_s = dim_scores.get("运动", 0)
        vitals_s = dim_scores.get("体征", 100)

        if sleep_s < 40 and exercise_s > 70:
            synergy_alerts.append({
                "type": "overtraining_risk",
                "message": "睡眠差+运动量大 → 过度训练风险，建议休息",
                "score_impact": -5,
            })
        if sleep_s >= 70 and exercise_s >= 60 and dim_scores.get("饮食", 0) >= 60:
            synergy_alerts.append({
                "type": "positive_cycle",
                "message": "睡眠+运动+饮食均良好 → 身体处于良性循环",
                "score_impact": 3,
            })
        if vitals_s < 40 and sleep_s < 50:
            synergy_alerts.append({
                "type": "stress_alert",
                "message": "体征异常+睡眠差 → 身体可能处于高压状态",
                "score_impact": -5,
            })

        # 3. 重新计算总分
        synergy_impact = sum(a["score_impact"] for a in synergy_alerts)
        active_dims = [d for d in dimensions if d["score"] is not None]
        total_active_weight = sum(d["weight"] for d in active_dims)
        if total_active_weight > 0:
            for d in active_dims:
                d["weight"] = round(d["weight"] / total_active_weight, 3)
        raw_total = sum(d["score"] * d["weight"] for d in active_dims)
        enhanced_total = max(0, min(100, round(raw_total + synergy_impact)))

        base["total_score"] = enhanced_total
        base["grade"] = self._get_grade(enhanced_total)
        base["trend_adjustments"] = trend_adjustments
        base["synergy_alerts"] = synergy_alerts
        base["enhanced"] = True

        # 更新建议（加入协同效应的建议）
        for alert in synergy_alerts:
            if alert["score_impact"] < 0:
                base["suggestions"].insert(0, alert["message"])

        return base

    # ==================== 各维度评分 ====================

    def _score_exercise(self, db: Session, user_id: int, target_date: date) -> Dict[str, Any]:
        """运动维度评分"""
        garmin = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == target_date,
        ).first()

        if not garmin or garmin.steps is None:
            return {"name": "运动", "score": None, "weight": self.DIMENSION_WEIGHTS["运动"], "description": "无数据", "details": {}}

        score = 0
        details = {}

        # 步数评分 (60分权重)
        steps = garmin.steps or 0
        if steps >= 10000:
            step_score = 60
        elif steps >= 8000:
            step_score = 50
        elif steps >= 6000:
            step_score = 40
        elif steps >= 4000:
            step_score = 25
        else:
            step_score = max(5, int(steps / 4000 * 25))
        score += step_score
        details["steps"] = steps
        details["step_score"] = step_score

        # 活动消耗评分 (40分权重)
        calories = garmin.calories_burned or 0
        if calories >= 2500:
            cal_score = 40
        elif calories >= 2000:
            cal_score = 30
        elif calories >= 1500:
            cal_score = 20
        else:
            cal_score = max(5, int(calories / 1500 * 20))
        score += cal_score
        details["calories_burned"] = calories
        details["cal_score"] = cal_score

        return {"name": "运动", "score": min(100, score), "weight": self.DIMENSION_WEIGHTS["运动"], "description": self._exercise_desc(score), "details": details}

    def _score_sleep(self, db: Session, user_id: int, target_date: date) -> Dict[str, Any]:
        """睡眠维度评分"""
        garmin = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == target_date,
        ).first()

        if not garmin or (garmin.sleep_score is None and garmin.total_sleep_duration is None):
            return {"name": "睡眠", "score": None, "weight": self.DIMENSION_WEIGHTS["睡眠"], "description": "无数据", "details": {}}

        score = 0
        details = {}

        # 睡眠评分 (50分)
        if garmin.sleep_score is not None:
            ss = garmin.sleep_score
            sleep_s = min(50, int(ss / 100 * 50))
            score += sleep_s
            details["sleep_score"] = ss

        # 睡眠时长 (30分) - 理想7-9小时
        if garmin.total_sleep_duration is not None:
            dur_hours = garmin.total_sleep_duration / 60
            if 7 <= dur_hours <= 9:
                dur_score = 30
            elif 6 <= dur_hours < 7 or 9 < dur_hours <= 10:
                dur_score = 20
            elif 5 <= dur_hours < 6:
                dur_score = 10
            else:
                dur_score = 5
            score += dur_score
            details["duration_hours"] = round(dur_hours, 1)

        # 深睡比例 (20分) - 理想≥60min
        if garmin.deep_sleep_duration is not None:
            deep = garmin.deep_sleep_duration
            if deep >= 90:
                deep_score = 20
            elif deep >= 60:
                deep_score = 15
            elif deep >= 30:
                deep_score = 10
            else:
                deep_score = 5
            score += deep_score
            details["deep_sleep_min"] = deep

        return {"name": "睡眠", "score": min(100, score), "weight": self.DIMENSION_WEIGHTS["睡眠"], "description": self._sleep_desc(score), "details": details}

    def _score_diet(self, db: Session, user_id: int, target_date: date) -> Dict[str, Any]:
        """饮食维度评分"""
        records = db.query(DietRecord).filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date == target_date,
        ).all()

        if not records:
            return {"name": "饮食", "score": None, "weight": self.DIMENSION_WEIGHTS["饮食"], "description": "无数据", "details": {}}

        total_cal = sum(r.calories or 0 for r in records)
        total_protein = sum(r.protein or 0 for r in records)
        total_carbs = sum(r.carbs or 0 for r in records)
        total_fat = sum(r.fat or 0 for r in records)
        meal_count = len(records)

        score = 0
        details = {"calories": total_cal, "protein": total_protein, "carbs": total_carbs, "fat": total_fat, "meals": meal_count}

        # 记录完整度 (30分)
        if meal_count >= 3:
            score += 30
        elif meal_count >= 2:
            score += 20
        else:
            score += 10

        # 热量范围 (35分) - 1500~2500合理
        if 1500 <= total_cal <= 2500:
            score += 35
        elif 1200 <= total_cal < 1500 or 2500 < total_cal <= 3000:
            score += 20
        elif total_cal > 0:
            score += 10

        # 蛋白质 (35分) - ≥60g
        if total_protein >= 80:
            score += 35
        elif total_protein >= 60:
            score += 25
        elif total_protein >= 40:
            score += 15
        elif total_protein > 0:
            score += 5

        return {"name": "饮食", "score": min(100, score), "weight": self.DIMENSION_WEIGHTS["饮食"], "description": self._diet_desc(score), "details": details}

    def _score_mood(self, db: Session, user_id: int, target_date: date) -> Dict[str, Any]:
        """情绪维度评分"""
        mood = db.query(MoodRecord).filter(
            MoodRecord.user_id == user_id,
            MoodRecord.record_date == target_date,
        ).first()

        if not mood:
            return {"name": "情绪", "score": None, "weight": self.DIMENSION_WEIGHTS["情绪"], "description": "无数据", "details": {}}

        score = 0
        details = {}

        # 情绪评分 (50分) - 1-5映射
        ms = mood.mood_score
        mood_s = int(ms / 5 * 50)
        score += mood_s
        details["mood_score"] = ms

        # 精力评分 (25分) - 1-5映射
        if mood.energy_level:
            el = mood.energy_level
            energy_s = int(el / 5 * 25)
            score += energy_s
            details["energy_level"] = el

        # 压力评分 (25分) - 压力越低越好
        if mood.stress_level:
            sl = mood.stress_level
            stress_s = int((6 - sl) / 5 * 25)  # 反转：1最好
            score += stress_s
            details["stress_level"] = sl

        return {"name": "情绪", "score": min(100, score), "weight": self.DIMENSION_WEIGHTS["情绪"], "description": self._mood_desc(score), "details": details}

    def _score_vitals(self, db: Session, user_id: int, target_date: date) -> Dict[str, Any]:
        """体征维度评分"""
        garmin = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == target_date,
        ).first()

        if not garmin or (garmin.resting_heart_rate is None and garmin.stress_level is None and garmin.body_battery_most_charged is None):
            return {"name": "体征", "score": None, "weight": self.DIMENSION_WEIGHTS["体征"], "description": "无数据", "details": {}}

        score = 0
        count = 0
        details = {}

        # 静息心率 (40分) - 50-70正常
        if garmin.resting_heart_rate is not None:
            rhr = garmin.resting_heart_rate
            if 50 <= rhr <= 65:
                rhr_score = 40
            elif 45 <= rhr < 50 or 65 < rhr <= 75:
                rhr_score = 30
            elif 75 < rhr <= 85:
                rhr_score = 15
            else:
                rhr_score = 5
            score += rhr_score
            count += 1
            details["resting_heart_rate"] = rhr

        # 压力 (30分) - 越低越好
        if garmin.stress_level is not None:
            sl = garmin.stress_level
            if sl <= 25:
                sl_score = 30
            elif sl <= 40:
                sl_score = 22
            elif sl <= 60:
                sl_score = 12
            else:
                sl_score = 5
            score += sl_score
            count += 1
            details["stress_level"] = sl

        # Body Battery (30分)
        if garmin.body_battery_most_charged is not None:
            bb = garmin.body_battery_most_charged
            if bb >= 80:
                bb_score = 30
            elif bb >= 60:
                bb_score = 22
            elif bb >= 40:
                bb_score = 12
            else:
                bb_score = 5
            score += bb_score
            count += 1
            details["body_battery"] = bb

        # 按实际有的指标数量等比例放大
        if count < 3 and count > 0:
            score = int(score * 3 / count)

        return {"name": "体征", "score": min(100, score), "weight": self.DIMENSION_WEIGHTS["体征"], "description": self._vitals_desc(score), "details": details}

    def _score_hydration(self, db: Session, user_id: int, target_date: date) -> Dict[str, Any]:
        """饮水维度评分"""
        records = db.query(WaterIntake).filter(
            WaterIntake.user_id == user_id,
            WaterIntake.record_date == target_date,
        ).all()

        if not records:
            return {"name": "水分", "score": None, "weight": self.DIMENSION_WEIGHTS["水分"], "description": "无数据", "details": {}}

        total_ml = sum(r.amount_ml or 0 for r in records)
        details = {"total_ml": total_ml, "intake_count": len(records)}

        # 推荐饮水量 2000ml/天
        if total_ml >= 2000:
            score = 100
        elif total_ml >= 1600:
            score = 80
        elif total_ml >= 1200:
            score = 60
        elif total_ml >= 800:
            score = 40
        elif total_ml >= 400:
            score = 20
        else:
            score = 10

        return {"name": "水分", "score": score, "weight": self.DIMENSION_WEIGHTS["水分"], "description": self._hydration_desc(score), "details": details}

    def _score_weight(self, db: Session, user_id: int, target_date: date) -> Dict[str, Any]:
        """体重维度评分"""
        latest = db.query(WeightRecord).filter(
            WeightRecord.user_id == user_id,
            WeightRecord.record_date <= target_date,
        ).order_by(desc(WeightRecord.record_date)).first()

        if not latest:
            return {"name": "体重", "score": None, "weight": self.DIMENSION_WEIGHTS["体重"], "description": "无数据", "details": {}}

        score = 0
        details = {}

        # BMI 评分 (60分)
        bmi = latest.bmi
        if bmi:
            if 18.5 <= bmi < 24:
                bmi_score = 60
            elif 24 <= bmi < 28 or 17 <= bmi < 18.5:
                bmi_score = 35
            else:
                bmi_score = 15
            score += bmi_score
            details["bmi"] = bmi

        # 体脂率评分 (40分)
        bf = latest.body_fat_percentage
        if bf:
            if 15 <= bf <= 25:
                bf_score = 40
            elif 10 <= bf < 15 or 25 < bf <= 30:
                bf_score = 25
            else:
                bf_score = 10
            score += bf_score
            details["body_fat"] = bf

        # 如果只有体重没有 BMI 和体脂
        if not bmi and not bf:
            score = 50  # 有记录但缺少详细数据，给中等分
        elif not bmi or not bf:
            # 只有一个指标，按比例放大
            score = int(score * 100 / (60 if bmi else 40))

        details["weight"] = latest.weight

        return {"name": "体重", "score": min(100, score), "weight": self.DIMENSION_WEIGHTS["体重"], "description": self._weight_desc(score), "details": details}

    # ==================== 辅助方法 ====================

    @staticmethod
    def _get_grade(score: int) -> str:
        if score >= 90:
            return "优秀"
        elif score >= 75:
            return "良好"
        elif score >= 60:
            return "一般"
        elif score >= 40:
            return "较差"
        return "需改善"

    @staticmethod
    def _exercise_desc(score: int) -> str:
        if score >= 80:
            return "运动充足，保持良好习惯"
        elif score >= 60:
            return "运动量适中，可以尝试增加"
        elif score >= 40:
            return "运动不足，建议增加活动"
        return "运动严重不足，需要改善"

    @staticmethod
    def _sleep_desc(score: int) -> str:
        if score >= 80:
            return "睡眠质量优秀"
        elif score >= 60:
            return "睡眠质量良好"
        elif score >= 40:
            return "睡眠质量一般，建议改善"
        return "睡眠质量较差，需要重视"

    @staticmethod
    def _diet_desc(score: int) -> str:
        if score >= 80:
            return "饮食均衡，营养充足"
        elif score >= 60:
            return "饮食基本合理"
        elif score >= 40:
            return "饮食结构需要优化"
        return "饮食记录不足或营养不均"

    @staticmethod
    def _mood_desc(score: int) -> str:
        if score >= 80:
            return "心理状态良好"
        elif score >= 60:
            return "心理状态尚可"
        elif score >= 40:
            return "情绪状态一般"
        return "心理状态需要关注"

    @staticmethod
    def _vitals_desc(score: int) -> str:
        if score >= 80:
            return "身体机能状态良好"
        elif score >= 60:
            return "身体机能正常"
        elif score >= 40:
            return "身体机能需要注意"
        return "身体机能指标异常"

    @staticmethod
    def _weight_desc(score: int) -> str:
        if score >= 80:
            return "体重体脂在理想范围"
        elif score >= 60:
            return "体重基本正常"
        elif score >= 40:
            return "体重需要关注"
        return "体重管理需要加强"

    @staticmethod
    def _hydration_desc(score: int) -> str:
        if score >= 80:
            return "饮水充足，身体水分良好"
        elif score >= 60:
            return "饮水基本达标"
        elif score >= 40:
            return "饮水不足，建议多喝水"
        return "严重缺水，请注意补充水分"

    def _generate_suggestions(self, dimensions: List[Dict], total_score: int) -> List[str]:
        """基于各维度得分生成建议"""
        suggestions = []

        # 按得分排序，优先关注低分维度
        sorted_dims = sorted(dimensions, key=lambda d: d["score"])

        for d in sorted_dims[:3]:  # 最多3条建议
            name = d["name"]
            score = d["score"]

            if score < 40:
                if name == "运动":
                    suggestions.append("运动量严重不足，建议每天至少步行6000步或进行30分钟有氧运动")
                elif name == "睡眠":
                    suggestions.append("睡眠质量较差，建议固定作息时间，睡前避免使用电子设备")
                elif name == "饮食":
                    suggestions.append("饮食记录不完整或营养不均衡，建议每餐记录并注意蛋白质摄入")
                elif name == "情绪":
                    suggestions.append("情绪状态需要关注，建议进行适当放松活动如冥想或散步")
                elif name == "体征":
                    suggestions.append("身体机能指标异常，建议关注休息和恢复")
                elif name == "体重":
                    suggestions.append("体重管理需加强，建议控制热量摄入并增加运动")
                elif name == "水分":
                    suggestions.append("今日饮水严重不足，建议立即补水，目标每天 2000ml")
            elif score < 60:
                if name == "运动":
                    suggestions.append("运动量不足，尝试增加每日步数或安排运动计划")
                elif name == "睡眠":
                    suggestions.append("睡眠质量可以改善，注意营造良好睡眠环境")
                elif name == "饮食":
                    suggestions.append("饮食结构有待优化，增加蛋白质和蔬菜摄入")
                elif name == "水分":
                    suggestions.append("饮水量不足，建议定时提醒自己补水，目标每天 2000ml")

        if not suggestions and total_score >= 80:
            suggestions.append("整体健康状态良好，继续保持当前的生活习惯")

        return suggestions


health_score_service = HealthScoreService()
