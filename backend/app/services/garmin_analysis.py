"""Garmin数据分析服务"""
from typing import List, Dict, Any, Optional
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.daily_health import GarminData


class GarminAnalysisService:
    """Garmin数据分析服务"""
    
    def analyze_sleep_quality(
        self,
        db: Session,
        user_id: int,
        days: int = 7
    ) -> Dict[str, Any]:
        """分析睡眠质量"""
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        sleep_data = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start_date,
            GarminData.record_date <= end_date,
            GarminData.sleep_score.isnot(None)
        ).order_by(GarminData.record_date.desc()).all()
        
        if not sleep_data:
            return {
                "status": "no_data",
                "message": "没有足够的睡眠数据",
                "days_analyzed": 0
            }
        
        # 计算统计数据
        sleep_scores = [d.sleep_score for d in sleep_data if d.sleep_score]
        avg_sleep_score = sum(sleep_scores) / len(sleep_scores) if sleep_scores else 0
        
        total_sleep_durations = [d.total_sleep_duration for d in sleep_data if d.total_sleep_duration]
        avg_sleep_duration = sum(total_sleep_durations) / len(total_sleep_durations) if total_sleep_durations else 0
        
        deep_sleep_durations = [d.deep_sleep_duration for d in sleep_data if d.deep_sleep_duration]
        avg_deep_sleep = sum(deep_sleep_durations) / len(deep_sleep_durations) if deep_sleep_durations else 0
        
        rem_sleep_durations = [d.rem_sleep_duration for d in sleep_data if d.rem_sleep_duration]
        avg_rem_sleep = sum(rem_sleep_durations) / len(rem_sleep_durations) if rem_sleep_durations else 0
        
        awake_durations = [d.awake_duration for d in sleep_data if d.awake_duration]
        avg_awake = sum(awake_durations) / len(awake_durations) if awake_durations else 0
        
        # 评估睡眠质量
        quality_assessment = self._assess_sleep_quality(avg_sleep_score, avg_sleep_duration, avg_deep_sleep)
        
        return {
            "status": "success",
            "days_analyzed": len(sleep_data),
            "average_sleep_score": round(avg_sleep_score, 1),
            "average_sleep_duration_minutes": round(avg_sleep_duration, 1),
            "average_sleep_duration_hours": round(avg_sleep_duration / 60, 1),
            "average_deep_sleep_minutes": round(avg_deep_sleep, 1),
            "average_rem_sleep_minutes": round(avg_rem_sleep, 1),
            "average_awake_minutes": round(avg_awake, 1),
            "quality_assessment": quality_assessment,
            "recommendations": self._get_sleep_recommendations(avg_sleep_score, avg_sleep_duration, avg_deep_sleep, avg_awake),
            "daily_data": [
                {
                    "date": d.record_date.isoformat(),
                    "sleep_score": d.sleep_score,
                    "total_sleep_duration": d.total_sleep_duration,
                    "deep_sleep_duration": d.deep_sleep_duration,
                    "rem_sleep_duration": d.rem_sleep_duration,
                    "awake_duration": d.awake_duration,
                }
                for d in sleep_data
            ]
        }
    
    def analyze_heart_rate(
        self,
        db: Session,
        user_id: int,
        days: int = 7
    ) -> Dict[str, Any]:
        """分析心率数据"""
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        hr_data = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start_date,
            GarminData.record_date <= end_date,
            GarminData.avg_heart_rate.isnot(None)
        ).order_by(GarminData.record_date.desc()).all()
        
        if not hr_data:
            return {
                "status": "no_data",
                "message": "没有足够的心率数据"
            }
        
        # 计算统计数据
        avg_hrs = [d.avg_heart_rate for d in hr_data if d.avg_heart_rate]
        resting_hrs = [d.resting_heart_rate for d in hr_data if d.resting_heart_rate]
        hrvs = [d.hrv for d in hr_data if d.hrv]
        
        avg_hr = sum(avg_hrs) / len(avg_hrs) if avg_hrs else None
        avg_resting_hr = sum(resting_hrs) / len(resting_hrs) if resting_hrs else None
        avg_hrv = sum(hrvs) / len(hrvs) if hrvs else None
        
        # 评估心率健康
        hr_assessment = self._assess_heart_rate(avg_hr, avg_resting_hr, avg_hrv)
        
        return {
            "status": "success",
            "days_analyzed": len(hr_data),
            "average_heart_rate": round(avg_hr, 1) if avg_hr else None,
            "average_resting_heart_rate": round(avg_resting_hr, 1) if avg_resting_hr else None,
            "average_hrv": round(avg_hrv, 1) if avg_hrv else None,
            "assessment": hr_assessment,
            "recommendations": self._get_heart_rate_recommendations(avg_hr, avg_resting_hr, avg_hrv),
            "daily_data": [
                {
                    "date": d.record_date.isoformat(),
                    "avg_heart_rate": d.avg_heart_rate,
                    "resting_heart_rate": d.resting_heart_rate,
                    "hrv": d.hrv,
                }
                for d in hr_data
            ]
        }
    
    def analyze_body_battery(
        self,
        db: Session,
        user_id: int,
        days: int = 7
    ) -> Dict[str, Any]:
        """分析身体电量"""
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        battery_data = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start_date,
            GarminData.record_date <= end_date,
            GarminData.body_battery_charged.isnot(None)
        ).order_by(GarminData.record_date.desc()).all()
        
        if not battery_data:
            return {
                "status": "no_data",
                "message": "没有足够的身体电量数据"
            }
        
        # 计算统计数据
        charged_values = [d.body_battery_charged for d in battery_data if d.body_battery_charged]
        drained_values = [d.body_battery_drained for d in battery_data if d.body_battery_drained]
        most_charged = [d.body_battery_most_charged for d in battery_data if d.body_battery_most_charged]
        lowest = [d.body_battery_lowest for d in battery_data if d.body_battery_lowest]
        
        avg_charged = sum(charged_values) / len(charged_values) if charged_values else None
        avg_drained = sum(drained_values) / len(drained_values) if drained_values else None
        avg_most_charged = sum(most_charged) / len(most_charged) if most_charged else None
        avg_lowest = sum(lowest) / len(lowest) if lowest else None
        
        return {
            "status": "success",
            "days_analyzed": len(battery_data),
            "average_charged": round(avg_charged, 1) if avg_charged else None,
            "average_drained": round(avg_drained, 1) if avg_drained else None,
            "average_most_charged": round(avg_most_charged, 1) if avg_most_charged else None,
            "average_lowest": round(avg_lowest, 1) if avg_lowest else None,
            "assessment": self._assess_body_battery(avg_charged, avg_lowest),
            "daily_data": [
                {
                    "date": d.record_date.isoformat(),
                    "charged": d.body_battery_charged,
                    "drained": d.body_battery_drained,
                    "most_charged": d.body_battery_most_charged,
                    "lowest": d.body_battery_lowest,
                }
                for d in battery_data
            ]
        }
    
    def analyze_activity(
        self,
        db: Session,
        user_id: int,
        days: int = 7
    ) -> Dict[str, Any]:
        """分析活动数据"""
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        activity_data = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start_date,
            GarminData.record_date <= end_date
        ).order_by(GarminData.record_date.desc()).all()
        
        if not activity_data:
            return {
                "status": "no_data",
                "message": "没有足够的活动数据"
            }
        
        # 计算统计数据
        steps_list = [d.steps for d in activity_data if d.steps]
        calories_list = [d.calories_burned for d in activity_data if d.calories_burned]
        active_minutes_list = [d.active_minutes for d in activity_data if d.active_minutes]
        
        total_steps = sum(steps_list)
        avg_steps = total_steps / len(steps_list) if steps_list else 0
        total_calories = sum(calories_list)
        avg_calories = total_calories / len(calories_list) if calories_list else 0
        total_active_minutes = sum(active_minutes_list)
        avg_active_minutes = total_active_minutes / len(active_minutes_list) if active_minutes_list else 0
        
        return {
            "status": "success",
            "days_analyzed": len(activity_data),
            "total_steps": total_steps,
            "average_steps_per_day": round(avg_steps, 0),
            "total_calories_burned": total_calories,
            "average_calories_per_day": round(avg_calories, 0),
            "total_active_minutes": total_active_minutes,
            "average_active_minutes_per_day": round(avg_active_minutes, 1),
            "assessment": self._assess_activity(avg_steps, avg_active_minutes),
            "daily_data": [
                {
                    "date": d.record_date.isoformat(),
                    "steps": d.steps,
                    "calories_burned": d.calories_burned,
                    "active_minutes": d.active_minutes,
                }
                for d in activity_data
            ]
        }
    
    def get_comprehensive_analysis(
        self,
        db: Session,
        user_id: int,
        days: int = 7
    ) -> Dict[str, Any]:
        """获取综合分析"""
        return {
            "sleep": self.analyze_sleep_quality(db, user_id, days),
            "heart_rate": self.analyze_heart_rate(db, user_id, days),
            "body_battery": self.analyze_body_battery(db, user_id, days),
            "activity": self.analyze_activity(db, user_id, days),
        }
    
    def _assess_sleep_quality(
        self,
        sleep_score: float,
        sleep_duration: float,
        deep_sleep: float
    ) -> Dict[str, Any]:
        """评估睡眠质量"""
        score_level = "excellent" if sleep_score >= 80 else "good" if sleep_score >= 60 else "fair" if sleep_score >= 40 else "poor"
        duration_level = "adequate" if sleep_duration >= 420 else "insufficient" if sleep_duration >= 360 else "very_insufficient"
        deep_sleep_level = "good" if deep_sleep >= 90 else "fair" if deep_sleep >= 60 else "insufficient"
        
        return {
            "overall": score_level,
            "sleep_score_level": score_level,
            "duration_level": duration_level,
            "deep_sleep_level": deep_sleep_level,
        }
    
    def _assess_heart_rate(
        self,
        avg_hr: Optional[float],
        resting_hr: Optional[float],
        hrv: Optional[float]
    ) -> Dict[str, Any]:
        """评估心率健康"""
        if not resting_hr:
            return {"status": "insufficient_data"}
        
        # 正常静息心率范围：60-100 bpm
        if resting_hr < 60:
            hr_status = "low"  # 可能表示训练有素或健康问题
        elif resting_hr <= 100:
            hr_status = "normal"
        else:
            hr_status = "high"  # 可能表示压力或健康问题
        
        return {
            "resting_hr_status": hr_status,
            "hrv_status": "good" if hrv and hrv > 30 else "fair" if hrv and hrv > 20 else "low" if hrv else "unknown"
        }
    
    def _assess_body_battery(
        self,
        avg_charged: Optional[float],
        avg_lowest: Optional[float]
    ) -> Dict[str, Any]:
        """评估身体电量"""
        if not avg_charged:
            return {"status": "insufficient_data"}
        
        if avg_charged >= 80:
            status = "excellent"
        elif avg_charged >= 60:
            status = "good"
        elif avg_charged >= 40:
            status = "fair"
        else:
            status = "low"
        
        return {
            "status": status,
            "energy_level": "high" if avg_lowest and avg_lowest >= 50 else "moderate" if avg_lowest and avg_lowest >= 30 else "low"
        }
    
    def _assess_activity(
        self,
        avg_steps: float,
        avg_active_minutes: float
    ) -> Dict[str, Any]:
        """评估活动水平"""
        # WHO建议：每天至少10000步或150分钟中等强度活动
        steps_status = "excellent" if avg_steps >= 10000 else "good" if avg_steps >= 7500 else "fair" if avg_steps >= 5000 else "insufficient"
        activity_status = "excellent" if avg_active_minutes >= 150 else "good" if avg_active_minutes >= 75 else "fair" if avg_active_minutes >= 30 else "insufficient"
        
        return {
            "steps_status": steps_status,
            "activity_status": activity_status,
            "meets_who_recommendations": avg_steps >= 10000 or avg_active_minutes >= 150
        }
    
    def _get_sleep_recommendations(
        self,
        sleep_score: float,
        sleep_duration: float,
        deep_sleep: float,
        awake: float = 0
    ) -> List[str]:
        """获取睡眠建议"""
        recommendations = []
        
        if sleep_score < 60:
            recommendations.append("睡眠质量需要改善，建议保持规律作息")
        
        if sleep_duration < 420:  # 7小时
            recommendations.append(f"睡眠时长不足（当前{round(sleep_duration/60, 1)}小时），建议至少7-8小时")
        
        if deep_sleep < 60:
            recommendations.append("深度睡眠不足，建议睡前避免使用电子设备，保持卧室环境舒适")
        
        if awake > 60:  # 清醒时间超过60分钟
            recommendations.append(f"夜间清醒时间较长（{round(awake, 0)}分钟），建议检查睡眠环境，避免睡前摄入咖啡因或酒精")
        
        if not recommendations:
            recommendations.append("睡眠质量良好，继续保持")
        
        return recommendations
    
    def _get_heart_rate_recommendations(
        self,
        avg_hr: Optional[float],
        resting_hr: Optional[float],
        hrv: Optional[float]
    ) -> List[str]:
        """获取心率建议"""
        recommendations = []
        
        if resting_hr and resting_hr > 100:
            recommendations.append("静息心率偏高，建议减少压力，增加有氧运动")
        elif resting_hr and resting_hr < 50:
            recommendations.append("静息心率偏低，如无不适症状，可能是训练有素的表现")
        
        if hrv and hrv < 20:
            recommendations.append("心率变异性较低，可能表示压力较大或恢复不足，建议增加休息")
        
        if not recommendations:
            recommendations.append("心率指标正常，继续保持")
        
        return recommendations

