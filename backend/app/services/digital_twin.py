"""
数字孪生服务 - executor.life 健康模块核心

数字孪生(Digital Twin)是用户的虚拟健康模型，包含：
1. 基础生理计算（BMR、TDEE、心率区间等）
2. 历史数据分析和趋势识别
3. 个性化健康评分
4. AI 驱动的预测和建议
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

logger = logging.getLogger(__name__)


class DigitalTwinService:
    """
    数字孪生服务
    
    为每个用户构建虚拟健康模型，提供：
    - 生理指标计算
    - 健康状态评估
    - 趋势分析
    - 个性化建议
    """
    
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self._profile = None
        self._garmin_data = None
        
    @property
    def profile(self):
        """延迟加载用户画像"""
        if self._profile is None:
            from app.models.user_profile import UserProfile
            self._profile = self.db.query(UserProfile).filter(
                UserProfile.user_id == self.user_id
            ).first()
        return self._profile
    
    # ==================== 基础生理计算 ====================
    
    def calculate_bmr(self) -> Optional[float]:
        """
        计算基础代谢率 (Basal Metabolic Rate)
        使用 Mifflin-St Jeor 公式（更准确）
        
        男性: BMR = 10 × 体重(kg) + 6.25 × 身高(cm) - 5 × 年龄 + 5
        女性: BMR = 10 × 体重(kg) + 6.25 × 身高(cm) - 5 × 年龄 - 161
        
        Returns:
            基础代谢率（千卡/天）
        """
        if not self.profile:
            return None
            
        weight = self.profile.current_weight_kg
        height = self.profile.height_cm
        age = self.profile.age
        gender = self.profile.gender
        
        if not all([weight, height, age, gender]):
            return None
        
        bmr = 10 * weight + 6.25 * height - 5 * age
        
        if gender == 'male':
            bmr += 5
        else:
            bmr -= 161
            
        return round(bmr, 0)
    
    def calculate_tdee(self, activity_level: str = None) -> Optional[float]:
        """
        计算每日总能量消耗 (Total Daily Energy Expenditure)
        
        Args:
            activity_level: sedentary/light/moderate/active/very_active
            
        Returns:
            TDEE（千卡/天）
        """
        bmr = self.calculate_bmr()
        if bmr is None:
            return None
        
        # 活动系数
        activity_multipliers = {
            'sedentary': 1.2,      # 久坐，几乎不运动
            'light': 1.375,        # 轻度活动，每周1-3天
            'moderate': 1.55,      # 中等活动，每周3-5天
            'active': 1.725,       # 高度活动，每周6-7天
            'very_active': 1.9     # 非常活跃，体力劳动或每天2次训练
        }
        
        # 如果没有指定活动水平，从画像推断
        if activity_level is None:
            exercise_freq = self.profile.exercise_frequency if self.profile else None
            activity_level = {
                'never': 'sedentary',
                'occasionally': 'light',
                'weekly': 'moderate',
                'daily': 'active'
            }.get(exercise_freq, 'light')
        
        multiplier = activity_multipliers.get(activity_level, 1.375)
        return round(bmr * multiplier, 0)
    
    def calculate_target_heart_rate_zones(self) -> Optional[Dict[str, Tuple[int, int]]]:
        """
        计算目标心率区间
        
        使用 Karvonen 公式（更个性化）
        目标心率 = ((最大心率 - 静息心率) × 强度%) + 静息心率
        
        Returns:
            各区间的心率范围 {zone_name: (min_hr, max_hr)}
        """
        age = self.profile.age if self.profile else None
        if age is None:
            return None
        
        # 最大心率（220 - 年龄）
        max_hr = 220 - age
        
        # 尝试获取静息心率
        resting_hr = self._get_average_resting_hr()
        if resting_hr is None:
            resting_hr = 60  # 默认值
        
        # 心率储备
        hr_reserve = max_hr - resting_hr
        
        def zone_range(low_pct: float, high_pct: float) -> Tuple[int, int]:
            return (
                int(hr_reserve * low_pct + resting_hr),
                int(hr_reserve * high_pct + resting_hr)
            )
        
        return {
            'zone1_recovery': zone_range(0.50, 0.60),      # 恢复区 50-60%
            'zone2_fat_burn': zone_range(0.60, 0.70),      # 燃脂区 60-70%
            'zone3_aerobic': zone_range(0.70, 0.80),       # 有氧区 70-80%
            'zone4_threshold': zone_range(0.80, 0.90),     # 乳酸阈值区 80-90%
            'zone5_max': zone_range(0.90, 1.00),           # 最大心率区 90-100%
            'max_heart_rate': max_hr,
            'resting_heart_rate': resting_hr
        }
    
    def calculate_ideal_weight_range(self) -> Optional[Dict[str, float]]:
        """
        计算理想体重范围
        
        基于 BMI 18.5-24 的健康范围
        """
        if not self.profile or not self.profile.height_cm:
            return None
            
        height_m = self.profile.height_cm / 100
        
        return {
            'min_weight': round(18.5 * height_m * height_m, 1),
            'ideal_weight': round(22 * height_m * height_m, 1),
            'max_weight': round(24 * height_m * height_m, 1)
        }
    
    # ==================== 数据分析 ====================
    
    def _get_average_resting_hr(self, days: int = 7) -> Optional[int]:
        """获取最近N天的平均静息心率"""
        from app.models.daily_health import GarminData
        
        start_date = date.today() - timedelta(days=days)
        result = self.db.query(func.avg(GarminData.resting_heart_rate)).filter(
            GarminData.user_id == self.user_id,
            GarminData.record_date >= start_date,
            GarminData.resting_heart_rate.isnot(None)
        ).scalar()
        
        return int(result) if result else None
    
    def analyze_sleep_trend(self, days: int = 30) -> Dict[str, Any]:
        """
        分析睡眠趋势
        
        Returns:
            {
                'avg_duration': 7.2,
                'avg_score': 82,
                'trend': 'improving',  # improving/declining/stable
                'issues': ['入睡较晚', '深睡不足'],
                'best_days': ['Saturday', 'Sunday']
            }
        """
        from app.models.daily_health import GarminData
        
        start_date = date.today() - timedelta(days=days)
        records = self.db.query(GarminData).filter(
            GarminData.user_id == self.user_id,
            GarminData.record_date >= start_date,
            GarminData.sleep_score.isnot(None)
        ).order_by(GarminData.record_date).all()
        
        if not records:
            return {'status': 'no_data'}
        
        scores = [r.sleep_score for r in records if r.sleep_score]
        durations = [r.total_sleep_duration / 60 for r in records if r.total_sleep_duration]  # 转为小时
        
        # 计算趋势
        if len(scores) >= 7:
            first_half = scores[:len(scores)//2]
            second_half = scores[len(scores)//2:]
            avg_diff = sum(second_half)/len(second_half) - sum(first_half)/len(first_half)
            
            if avg_diff > 3:
                trend = 'improving'
            elif avg_diff < -3:
                trend = 'declining'
            else:
                trend = 'stable'
        else:
            trend = 'insufficient_data'
        
        # 识别问题
        issues = []
        avg_duration = sum(durations) / len(durations) if durations else 0
        avg_score = sum(scores) / len(scores) if scores else 0
        
        if avg_duration < 7:
            issues.append('睡眠时长不足')
        if avg_score < 70:
            issues.append('睡眠质量偏低')
        
        # 检查深睡比例
        deep_sleep_ratios = []
        for r in records:
            if r.total_sleep_duration and r.deep_sleep_duration:
                ratio = r.deep_sleep_duration / r.total_sleep_duration * 100
                deep_sleep_ratios.append(ratio)
        
        if deep_sleep_ratios and sum(deep_sleep_ratios)/len(deep_sleep_ratios) < 15:
            issues.append('深睡比例偏低')
        
        return {
            'avg_duration_hours': round(avg_duration, 1),
            'avg_score': round(avg_score, 0),
            'trend': trend,
            'issues': issues,
            'data_points': len(records)
        }
    
    def analyze_exercise_trend(self, days: int = 30) -> Dict[str, Any]:
        """分析运动趋势"""
        from app.models.daily_health import GarminData
        from app.models.daily_health import WorkoutRecord
        
        start_date = date.today() - timedelta(days=days)
        
        # 从 Garmin 数据获取步数
        garmin_records = self.db.query(GarminData).filter(
            GarminData.user_id == self.user_id,
            GarminData.record_date >= start_date
        ).all()
        
        # 从运动记录获取详细运动
        workouts = self.db.query(WorkoutRecord).filter(
            WorkoutRecord.user_id == self.user_id,
            WorkoutRecord.workout_date >= start_date
        ).all()
        
        steps = [r.steps for r in garmin_records if r.steps]
        calories = [r.active_calories for r in garmin_records if r.active_calories]
        
        workout_types = {}
        for w in workouts:
            wtype = w.workout_type or 'unknown'
            workout_types[wtype] = workout_types.get(wtype, 0) + 1
        
        return {
            'avg_daily_steps': round(sum(steps) / len(steps), 0) if steps else 0,
            'avg_active_calories': round(sum(calories) / len(calories), 0) if calories else 0,
            'total_workouts': len(workouts),
            'workout_distribution': workout_types,
            'data_points': len(garmin_records)
        }
    
    def analyze_body_composition_trend(self, days: int = 90) -> Dict[str, Any]:
        """分析身体成分趋势（体重、体脂）"""
        from app.models.weight import WeightRecord
        
        start_date = date.today() - timedelta(days=days)
        records = self.db.query(WeightRecord).filter(
            WeightRecord.user_id == self.user_id,
            WeightRecord.record_date >= start_date
        ).order_by(WeightRecord.record_date).all()
        
        if not records:
            return {'status': 'no_data'}
        
        weights = [(r.record_date, r.weight_kg) for r in records]
        body_fats = [(r.record_date, r.body_fat_percentage) for r in records if r.body_fat_percentage]
        
        # 计算变化
        if len(weights) >= 2:
            weight_change = weights[-1][1] - weights[0][1]
        else:
            weight_change = 0
        
        return {
            'current_weight': weights[-1][1] if weights else None,
            'weight_change': round(weight_change, 1),
            'current_body_fat': body_fats[-1][1] if body_fats else None,
            'data_points': len(records)
        }
    
    # ==================== 健康评分 ====================
    
    def calculate_health_score(self) -> Dict[str, Any]:
        """
        计算综合健康评分 (0-100)
        
        维度:
        - 睡眠 (25%): 睡眠得分、时长
        - 运动 (25%): 步数、活动卡路里
        - 身体状态 (25%): HRV、静息心率、身体电量
        - 身体成分 (25%): BMI、体脂率
        """
        from app.models.daily_health import GarminData
        
        scores = {}
        weights = {'sleep': 0.25, 'exercise': 0.25, 'vitals': 0.25, 'composition': 0.25}
        
        # 获取最近7天数据
        start_date = date.today() - timedelta(days=7)
        recent_data = self.db.query(GarminData).filter(
            GarminData.user_id == self.user_id,
            GarminData.record_date >= start_date
        ).all()
        
        # 1. 睡眠评分
        sleep_scores = [r.sleep_score for r in recent_data if r.sleep_score]
        if sleep_scores:
            scores['sleep'] = sum(sleep_scores) / len(sleep_scores)
        else:
            scores['sleep'] = 50
        
        # 2. 运动评分 (基于步数目标达成率)
        target_steps = self.profile.target_steps if self.profile else 8000
        steps_list = [r.steps for r in recent_data if r.steps]
        if steps_list:
            avg_steps = sum(steps_list) / len(steps_list)
            scores['exercise'] = min(100, avg_steps / target_steps * 100)
        else:
            scores['exercise'] = 50
        
        # 3. 身体状态评分 (HRV + 静息心率)
        hrvs = [r.hrv for r in recent_data if r.hrv]
        resting_hrs = [r.resting_heart_rate for r in recent_data if r.resting_heart_rate]
        
        vitals_score = 50
        if hrvs:
            avg_hrv = sum(hrvs) / len(hrvs)
            # HRV 评分: 30ms=差, 50ms=一般, 70ms=良好, 100ms+=优秀
            hrv_score = min(100, max(0, (avg_hrv - 20) * 1.5))
            vitals_score = (vitals_score + hrv_score) / 2
        
        if resting_hrs:
            avg_rhr = sum(resting_hrs) / len(resting_hrs)
            # 静息心率评分: <50=优秀, 50-60=良好, 60-70=一般, 70-80=偏高, >80=差
            if avg_rhr < 50:
                rhr_score = 100
            elif avg_rhr < 60:
                rhr_score = 85
            elif avg_rhr < 70:
                rhr_score = 70
            elif avg_rhr < 80:
                rhr_score = 55
            else:
                rhr_score = 40
            vitals_score = (vitals_score + rhr_score) / 2
        
        scores['vitals'] = vitals_score
        
        # 4. 身体成分评分 (BMI)
        bmi = self.profile.bmi if self.profile else None
        if bmi:
            # BMI 评分: 18.5-24 = 100分，偏离越多越低
            if 18.5 <= bmi <= 24:
                scores['composition'] = 100
            elif bmi < 18.5:
                scores['composition'] = max(40, 100 - (18.5 - bmi) * 15)
            else:
                scores['composition'] = max(40, 100 - (bmi - 24) * 10)
        else:
            scores['composition'] = 50
        
        # 计算总分
        total_score = sum(scores[k] * weights[k] for k in weights)
        
        return {
            'total_score': round(total_score, 0),
            'dimensions': {
                'sleep': round(scores['sleep'], 0),
                'exercise': round(scores['exercise'], 0),
                'vitals': round(scores['vitals'], 0),
                'composition': round(scores['composition'], 0)
            },
            'grade': self._score_to_grade(total_score),
            'evaluated_at': datetime.now().isoformat()
        }
    
    def _score_to_grade(self, score: float) -> str:
        """分数转等级"""
        if score >= 90:
            return 'A'
        elif score >= 80:
            return 'B'
        elif score >= 70:
            return 'C'
        elif score >= 60:
            return 'D'
        else:
            return 'F'
    
    # ==================== 综合报告 ====================
    
    def generate_digital_twin_report(self) -> Dict[str, Any]:
        """
        生成完整的数字孪生报告
        """
        logger.info(f"为用户 {self.user_id} 生成数字孪生报告")
        
        report = {
            'user_id': self.user_id,
            'generated_at': datetime.now().isoformat(),
            
            # 基础生理指标
            'physiological': {
                'bmr': self.calculate_bmr(),
                'tdee': self.calculate_tdee(),
                'heart_rate_zones': self.calculate_target_heart_rate_zones(),
                'ideal_weight_range': self.calculate_ideal_weight_range()
            },
            
            # 健康评分
            'health_score': self.calculate_health_score(),
            
            # 趋势分析
            'trends': {
                'sleep': self.analyze_sleep_trend(),
                'exercise': self.analyze_exercise_trend(),
                'body_composition': self.analyze_body_composition_trend()
            },
            
            # 用户画像摘要
            'profile_summary': self._get_profile_summary()
        }
        
        # 生成个性化建议
        report['recommendations'] = self._generate_recommendations(report)
        
        return report
    
    def _get_profile_summary(self) -> Dict[str, Any]:
        """获取用户画像摘要"""
        if not self.profile:
            return {'status': 'no_profile'}
        
        return {
            'age': self.profile.age,
            'gender': self.profile.gender,
            'height_cm': self.profile.height_cm,
            'current_weight_kg': self.profile.current_weight_kg,
            'bmi': self.profile.bmi,
            'bmi_category': self.profile.bmi_category,
            'chronic_conditions': self.profile.chronic_conditions or [],
            'target_steps': self.profile.target_steps,
            'target_sleep_hours': self.profile.target_sleep_hours
        }
    
    def _generate_recommendations(self, report: Dict[str, Any]) -> List[Dict[str, str]]:
        """基于报告生成个性化建议"""
        recommendations = []
        
        # 根据健康评分
        score = report.get('health_score', {})
        dimensions = score.get('dimensions', {})
        
        if dimensions.get('sleep', 100) < 70:
            recommendations.append({
                'category': 'sleep',
                'priority': 'high',
                'title': '改善睡眠质量',
                'content': '您的睡眠得分偏低，建议保持规律作息，睡前1小时避免使用电子设备，保持卧室温度在18-22°C。'
            })
        
        if dimensions.get('exercise', 100) < 70:
            recommendations.append({
                'category': 'exercise',
                'priority': 'high',
                'title': '增加日常活动',
                'content': '您的运动量不足，建议每天至少步行30分钟，可以从午餐后散步开始。'
            })
        
        # 根据趋势
        sleep_trend = report.get('trends', {}).get('sleep', {})
        if sleep_trend.get('trend') == 'declining':
            recommendations.append({
                'category': 'sleep',
                'priority': 'medium',
                'title': '睡眠质量下降趋势',
                'content': '您近期睡眠质量呈下降趋势，建议检查是否有压力增加、作息变化等因素。'
            })
        
        # 根据生理指标
        physio = report.get('physiological', {})
        ideal_weight = physio.get('ideal_weight_range', {})
        current_weight = self.profile.current_weight_kg if self.profile else None
        
        if current_weight and ideal_weight:
            if current_weight > ideal_weight.get('max_weight', 999):
                tdee = physio.get('tdee')
                if tdee:
                    recommendations.append({
                        'category': 'weight',
                        'priority': 'medium',
                        'title': '体重管理建议',
                        'content': f'您的体重超出理想范围。您的每日总消耗约 {int(tdee)} 千卡，建议每日摄入控制在 {int(tdee - 500)} 千卡以内，配合运动，实现健康减重。'
                    })
        
        return recommendations


def get_digital_twin(db: Session, user_id: int) -> DigitalTwinService:
    """获取用户的数字孪生服务实例"""
    return DigitalTwinService(db, user_id)
