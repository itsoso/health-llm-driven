"""运动恢复评估服务

计算训练负荷（TRIMP）、急性:慢性负荷比（ACWR）、综合恢复就绪度。
"""
import logging
from datetime import date, timedelta
from typing import Optional
from sqlalchemy import desc
from sqlalchemy.orm import Session
from app.models.daily_health import GarminData, WorkoutRecord
from app.models.user import User
from app.services.training_load_metrics import assess_acwr
from app.utils.timezone import get_user_today

logger = logging.getLogger(__name__)

# 恢复就绪度权重
W_HRV, W_SLEEP, W_STRESS, W_BB = 0.30, 0.30, 0.20, 0.20

# TRIMP 强度系数 (%HRmax 上界, 系数)
TRIMP_COEFF = [(0.60, 1.0), (0.70, 1.5), (0.80, 2.0), (0.90, 3.0), (1.00, 4.0)]

# 训练建议参数: (intensity, types, avoid, max_min, hr_zone)
ADVICE_PARAMS = {
    "rest":     ("休息", ["拉伸", "冥想"], ["所有高强度运动"], 0, "不训练"),
    "light":    ("轻度", ["散步", "瑜伽", "轻度游泳"], ["HIIT", "间歇跑", "重量训练"], 45, "Zone 1-2"),
    "moderate": ("中等强度", ["有氧跑", "骑行", "游泳"], ["HIIT", "高强度间歇"], 75, "Zone 2-3"),
    "hard":     ("高强度", ["间歇跑", "力量训练", "HIIT", "节奏跑"], [], 90, "Zone 3-4"),
    "peak":     ("巅峰", ["比赛配速训练", "最大摄氧量间歇"], [], 75, "Zone 4-5"),
}
ADVICE_ORDER = ["rest", "light", "moderate", "hard", "peak"]
ZONE_NAMES = {"undertraining": "训练不足区", "optimal": "最佳区间", "danger": "警告区间", "overtraining": "过度训练区"}
ADVICE_NAMES = {"rest": "建议完全休息", "light": "建议轻度活动", "moderate": "建议中等强度训练", "hard": "建议高强度训练", "peak": "建议巅峰训练"}


def _clamp(v: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, v))


def _estimate_hr_max(user: User) -> int:
    if user and user.birth_date:
        age = (date.today() - user.birth_date).days // 365
        return int(208 - 0.7 * age)
    return 190


def _trimp_coeff(hr_ratio: float) -> float:
    for threshold, c in TRIMP_COEFF:
        if hr_ratio < threshold:
            return c
    return 4.0


class ExerciseRecoveryService:

    def get_recovery_readiness(self, db: Session, user_id: int) -> dict:
        """综合恢复就绪度: f(HRV, sleep, stress, body_battery)"""
        today = date.today()
        # 多源按日合并 → g(最新一天) 各指标取优先级源,hrv_trend 按真实天数
        from app.services.garmin_daily_merged import merged_daily_rows
        recent = merged_daily_rows(db, user_id, since=today - timedelta(days=7))
        if not recent:
            return {"readiness_score": None, "readiness_level": "unknown", "components": {},
                    "hrv_trend": "unknown", "recommendation": "暂无 Garmin 数据，无法评估恢复状态", "record_date": str(today)}

        g = recent[0]
        hrv_s = self._hrv_score(g)
        sleep_s = float(g.sleep_score) if g.sleep_score is not None else self._sleep_fallback(g)
        stress_s = _clamp(100 - g.stress_level) if g.stress_level is not None else 50.0
        bb = g.body_battery_current or g.body_battery_most_charged
        bb_s = _clamp(float(bb)) if bb is not None else 50.0

        score = round(_clamp(W_HRV * hrv_s + W_SLEEP * sleep_s + W_STRESS * stress_s + W_BB * bb_s), 1)
        hrv_trend = self._hrv_trend(recent)

        if score >= 75:
            level, rec = "high", "完全恢复，可进行高强度训练"
        elif score >= 50:
            level, rec = "moderate", "适合中等强度训练"
        elif score >= 25:
            level, rec = "low", "恢复不足，建议轻度活动（散步、瑜伽）"
        else:
            level, rec = "very_low", "严重疲劳，建议完全休息"

        return {
            "readiness_score": score, "readiness_level": level,
            "components": {"hrv_score": round(hrv_s, 1), "sleep_score": round(sleep_s, 1),
                           "stress_score": round(stress_s, 1), "body_battery_score": round(bb_s, 1)},
            "hrv_trend": hrv_trend, "recommendation": rec, "record_date": str(g.record_date),
        }

    def get_training_load(
        self,
        db: Session,
        user_id: int,
        *,
        as_of_date: Optional[date] = None,
    ) -> dict:
        """TRIMP + ACWR (7d acute / 28d chronic rolling average)"""
        today = as_of_date or get_user_today(db, user_id)
        window_start = today - timedelta(days=27)
        user = db.query(User).filter(User.id == user_id).first()
        hr_max = _estimate_hr_max(user)

        workouts = (
            db.query(WorkoutRecord)
            .filter(
                WorkoutRecord.user_id == user_id,
                WorkoutRecord.workout_date >= window_start,
                WorkoutRecord.workout_date <= today,
            )
            .order_by(desc(WorkoutRecord.workout_date)).all()
        )
        # 按日期汇总
        dt, dty = {}, {}  # daily_trimp, daily_type
        for w in workouts:
            trimp = self._workout_trimp(w, hr_max)
            d = w.workout_date
            dt[d] = dt.get(d, 0) + trimp
            if d not in dty:
                dty[d] = w.workout_type

        loads = [round(dt.get(today - timedelta(days=i), 0), 1) for i in range(28)]
        daily_loads = [{"date": str(today - timedelta(days=i)), "trimp": loads[i],
                        "workout_type": dty.get(today - timedelta(days=i))} for i in range(14)]

        observed_rows = (
            db.query(GarminData.record_date)
            .filter(
                GarminData.user_id == user_id,
                GarminData.record_date >= window_start,
                GarminData.record_date <= today,
            )
            .distinct()
            .all()
        )
        observed_dates = {row[0] for row in observed_rows}
        observed_dates.update(dt.keys())
        observed_days = [
            today - timedelta(days=i) in observed_dates
            for i in range(28)
        ]

        assessment = assess_acwr(
            loads,
            observed_days_newest_first=observed_days,
        )
        acute_sum = assessment.acute_load_7d
        chronic_sum = assessment.chronic_load_28d
        acute_avg = acute_sum / 7
        acwr = assessment.acwr
        zone = assessment.zone

        prev_avg = sum(loads[7:14]) / 7 if any(loads[7:14]) else 0
        if prev_avg > 0:
            trend = "rising" if acute_avg > prev_avg * 1.1 else ("falling" if acute_avg < prev_avg * 0.9 else "stable")
        else:
            trend = "unknown"

        return {
            "today_trimp": round(dt.get(today, 0), 1), "acute_load_7d": round(acute_sum, 1),
            "chronic_load_28d": round(chronic_sum, 1), "acwr": acwr, "acwr_zone": zone,
            "acwr_reliable": assessment.reliable,
            "acwr_unavailable_reason": assessment.unavailable_reason,
            "baseline_active_days": assessment.baseline_active_days,
            "baseline_weeks_with_load": assessment.baseline_weeks_with_load,
            "baseline_load_21d": assessment.baseline_load_21d,
            "acute_observed_days": assessment.acute_observed_days,
            "baseline_observed_days": assessment.baseline_observed_days,
            "oldest_load_age_days": assessment.oldest_load_age_days,
            "acwr_trend": trend, "daily_loads": daily_loads, "data_days": assessment.data_days,
            "as_of_date": str(today),
        }

    def get_recommendation(self, db: Session, user_id: int) -> dict:
        """训练建议: readiness x ACWR 决策矩阵"""
        r = self.get_recovery_readiness(db, user_id)
        l = self.get_training_load(db, user_id)
        score = r.get("readiness_score")
        acwr = l.get("acwr")
        zone = l.get("acwr_zone") or "unknown"

        advice = self._decide(score, zone)
        warnings = []
        if r.get("hrv_trend") == "declining":
            warnings.append("HRV 连续下降，可能存在过度训练风险")
        if r.get("components", {}).get("body_battery_score", 50) < 20:
            warnings.append("身体电量极低，强烈建议休息")
        if r.get("components", {}).get("sleep_score", 50) < 40:
            warnings.append("睡眠质量不佳，已降低建议训练强度")
            idx = ADVICE_ORDER.index(advice) if advice in ADVICE_ORDER else 2
            advice = ADVICE_ORDER[max(0, idx - 1)]
        if l.get("acwr_unavailable_reason") == "insufficient_chronic_baseline":
            warnings.append("慢性训练基线不足，暂不计算 ACWR")
        elif l.get("acwr_unavailable_reason") == "insufficient_data_coverage":
            warnings.append("训练数据覆盖不足，暂不计算 ACWR")
        elif l.get("acwr_unavailable_reason") == "invalid_training_load_data":
            warnings.append("训练负荷数据异常，暂不计算 ACWR")
        elif l.get("acwr_unavailable_reason") == "no_recent_training":
            warnings.append("过去 7 天没有可用于计算 ACWR 的训练负荷")
        elif l.get("data_days", 0) < 14:
            warnings.append("运动负荷样本偏少，ACWR 仅供参考")

        p = ADVICE_PARAMS.get(advice, ADVICE_PARAMS["moderate"])
        parts = []
        if score is not None:
            parts.append(f"恢复就绪度 {score} 分")
        if acwr is not None:
            parts.extend([f"ACWR {acwr}", f"处于{ZONE_NAMES.get(zone, zone)}"])
        parts.append(ADVICE_NAMES.get(advice, ""))

        return {
            "training_advice": advice, "suggested_intensity": p[0], "suggested_types": p[1],
            "avoid_types": p[2], "max_duration_minutes": p[3], "target_hr_zone": p[4],
            "reasoning": "，".join(parts), "warnings": warnings, "readiness_score": score, "acwr": acwr,
        }

    # ---- internals ----

    def _hrv_score(self, g: GarminData) -> float:
        if g.hrv is None:
            return 50.0
        if g.hrv_7day_avg and g.hrv_7day_avg > 0:
            return _clamp(50 + (g.hrv - g.hrv_7day_avg) / g.hrv_7day_avg * 100)
        return _clamp(g.hrv / 80 * 100)

    def _sleep_fallback(self, g: GarminData) -> float:
        dur = g.total_sleep_duration
        if dur is None:
            return 50.0
        h = dur / 60
        if h < 6: return 30.0
        if h < 7: return 50.0
        if h < 8: return 75.0
        if h < 9: return 90.0
        return 80.0

    def _hrv_trend(self, recent: list) -> str:
        vals = [r.hrv for r in recent if r.hrv is not None]
        if len(vals) < 3:
            return "unknown"
        avg, r3 = sum(vals) / len(vals), sum(vals[:3]) / 3
        if r3 > avg * 1.1: return "rising"
        if r3 < avg * 0.85: return "declining"
        return "stable"

    def _workout_trimp(self, w: WorkoutRecord, hr_max: int) -> float:
        if w.training_load and w.training_load > 0:
            return float(w.training_load)
        dur = (w.duration_seconds or 0) / 60
        if dur <= 0:
            return 0
        coeff = _trimp_coeff(w.avg_heart_rate / hr_max) if w.avg_heart_rate and hr_max > 0 else 1.5
        return dur * coeff

    def _decide(self, score: Optional[float], zone: str) -> str:
        if score is None:
            return "moderate"
        if zone == "overtraining":
            return "rest" if score < 75 else "light"
        if zone == "danger":
            return "moderate" if score >= 75 else ("light" if score >= 50 else "rest")
        return "hard" if score >= 75 else ("moderate" if score >= 50 else "light")


exercise_recovery_service = ExerciseRecoveryService()
