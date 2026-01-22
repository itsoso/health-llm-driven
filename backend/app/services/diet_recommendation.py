"""
智能饮食推荐服务
基于用户目标、运动状态、睡眠质量等多维数据，提供个性化饮食建议
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.user_profile import UserProfile
from app.models.daily_health import DietRecord, GarminData, WorkoutRecord
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)


class DietRecommendationService:
    """智能饮食推荐服务"""
    
    def __init__(self):
        pass
    
    def calculate_bmr(self, gender: str, weight_kg: float, height_cm: float, age: int) -> float:
        """
        计算基础代谢率 (BMR) - Mifflin-St Jeor 公式
        
        Args:
            gender: 性别 (male/female)
            weight_kg: 体重 (kg)
            height_cm: 身高 (cm)
            age: 年龄
            
        Returns:
            基础代谢率 (kcal/day)
        """
        if gender == 'male':
            bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
        else:
            bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
        
        logger.info(f"[饮食推荐] BMR计算: gender={gender}, weight={weight_kg}kg, height={height_cm}cm, age={age} => BMR={bmr:.0f} kcal/day")
        return bmr
    
    def calculate_tdee(
        self, 
        bmr: float, 
        activity_level: str = 'moderate',
        exercise_calories: int = 0
    ) -> float:
        """
        计算每日总能量消耗 (TDEE)
        
        Args:
            bmr: 基础代谢率
            activity_level: 活动水平 (sedentary/light/moderate/active/very_active)
            exercise_calories: 额外运动消耗的卡路里
            
        Returns:
            每日总能量消耗 (kcal/day)
        """
        multipliers = {
            'sedentary': 1.2,      # 久坐，几乎不运动
            'light': 1.375,        # 轻度活动，每周1-3次运动
            'moderate': 1.55,      # 中度活动，每周3-5次运动
            'active': 1.725,       # 高度活动，每周6-7次运动
            'very_active': 1.9     # 非常活跃，体力劳动或每天多次训练
        }
        
        multiplier = multipliers.get(activity_level, 1.55)
        base_tdee = bmr * multiplier
        total_tdee = base_tdee + exercise_calories
        
        logger.info(f"[饮食推荐] TDEE计算: BMR={bmr:.0f} × {multiplier} + {exercise_calories} = {total_tdee:.0f} kcal/day")
        return total_tdee
    
    def calculate_daily_target(
        self,
        tdee: float,
        weight_goal: str = 'maintain',
        diet_preference: Optional[str] = None
    ) -> Dict[str, float]:
        """
        计算每日营养目标
        
        Args:
            tdee: 每日总能量消耗
            weight_goal: 体重目标 (lose/maintain/gain)
            diet_preference: 饮食偏好 (normal/vegetarian/low_carb/keto)
            
        Returns:
            每日营养目标 {calories, protein_g, carbs_g, fat_g}
        """
        # 根据体重目标调整卡路里
        if weight_goal == 'lose':
            target_calories = tdee - 500  # 每周减重约0.5kg
            logger.info(f"[饮食推荐] 减重模式: TDEE {tdee:.0f} - 500 = {target_calories:.0f} kcal/day")
        elif weight_goal == 'gain':
            target_calories = tdee + 300  # 每周增重约0.3kg
            logger.info(f"[饮食推荐] 增重模式: TDEE {tdee:.0f} + 300 = {target_calories:.0f} kcal/day")
        else:
            target_calories = tdee
            logger.info(f"[饮食推荐] 维持模式: TDEE {tdee:.0f} kcal/day")
        
        # 根据饮食偏好调整宏量营养素比例
        if diet_preference == 'keto':
            # 生酮饮食: 5% 碳水, 75% 脂肪, 20% 蛋白质
            protein_ratio, carbs_ratio, fat_ratio = 0.20, 0.05, 0.75
            logger.info(f"[饮食推荐] 生酮饮食模式: 蛋白质20%, 碳水5%, 脂肪75%")
        elif diet_preference == 'low_carb':
            # 低碳水: 25% 碳水, 35% 蛋白质, 40% 脂肪
            protein_ratio, carbs_ratio, fat_ratio = 0.35, 0.25, 0.40
            logger.info(f"[饮食推荐] 低碳水模式: 蛋白质35%, 碳水25%, 脂肪40%")
        else:
            # 正常/素食: 25% 蛋白质, 45% 碳水, 30% 脂肪
            protein_ratio, carbs_ratio, fat_ratio = 0.25, 0.45, 0.30
            logger.info(f"[饮食推荐] 标准模式: 蛋白质25%, 碳水45%, 脂肪30%")
        
        # 计算各营养素克数 (蛋白质和碳水: 4 kcal/g, 脂肪: 9 kcal/g)
        protein_g = (target_calories * protein_ratio) / 4
        carbs_g = (target_calories * carbs_ratio) / 4
        fat_g = (target_calories * fat_ratio) / 9
        
        result = {
            'calories': round(target_calories),
            'protein_g': round(protein_g, 1),
            'carbs_g': round(carbs_g, 1),
            'fat_g': round(fat_g, 1)
        }
        
        logger.info(f"[饮食推荐] 每日营养目标: {result}")
        return result
    
    def get_today_intake(self, db: Session, user_id: int) -> Dict[str, float]:
        """
        获取今日已摄入的营养
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            今日摄入 {calories, protein_g, carbs_g, fat_g, meals_count}
        """
        today = get_china_now().date()
        
        # 查询今日所有饮食记录
        records = db.query(DietRecord).filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date == today
        ).all()
        
        # 汇总营养数据
        total_calories = sum(r.calories or 0 for r in records)
        total_protein = sum(r.protein or 0 for r in records)
        total_carbs = sum(r.carbs or 0 for r in records)
        total_fat = sum(r.fat or 0 for r in records)
        
        result = {
            'calories': round(total_calories, 1),
            'protein_g': round(total_protein, 1),
            'carbs_g': round(total_carbs, 1),
            'fat_g': round(total_fat, 1),
            'meals_count': len(records)
        }
        
        logger.info(f"[饮食推荐] 今日已摄入: {result}")
        return result
    
    def get_recent_workout_calories(self, db: Session, user_id: int, days: int = 7) -> int:
        """
        获取最近N天平均运动消耗
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            days: 天数
            
        Returns:
            平均每日运动消耗 (kcal)
        """
        end_date = get_china_now().date()
        start_date = end_date - timedelta(days=days)
        
        # 查询最近的运动记录
        workouts = db.query(WorkoutRecord).filter(
            WorkoutRecord.user_id == user_id,
            WorkoutRecord.start_time >= start_date,
            WorkoutRecord.start_time < end_date + timedelta(days=1)
        ).all()
        
        if not workouts:
            logger.info(f"[饮食推荐] 最近{days}天无运动记录")
            return 0
        
        total_calories = sum(w.calories or 0 for w in workouts)
        avg_calories = total_calories / days
        
        logger.info(f"[饮食推荐] 最近{days}天运动: 总消耗{total_calories}kcal, 平均{avg_calories:.0f}kcal/day")
        return int(avg_calories)
    
    def get_activity_level(self, db: Session, user_id: int) -> str:
        """
        根据用户最近运动频率判断活动水平
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            活动水平 (sedentary/light/moderate/active/very_active)
        """
        end_date = get_china_now().date()
        start_date = end_date - timedelta(days=7)
        
        # 统计最近7天运动次数
        workout_count = db.query(WorkoutRecord).filter(
            WorkoutRecord.user_id == user_id,
            WorkoutRecord.start_time >= start_date,
            WorkoutRecord.start_time < end_date + timedelta(days=1)
        ).count()
        
        # 根据运动频率判断活动水平
        if workout_count == 0:
            level = 'sedentary'
        elif workout_count <= 2:
            level = 'light'
        elif workout_count <= 4:
            level = 'moderate'
        elif workout_count <= 6:
            level = 'active'
        else:
            level = 'very_active'
        
        logger.info(f"[饮食推荐] 最近7天运动{workout_count}次 => 活动水平: {level}")
        return level
    
    def determine_weight_goal(self, current_weight: float, target_weight: Optional[float]) -> str:
        """
        判断体重目标
        
        Args:
            current_weight: 当前体重
            target_weight: 目标体重
            
        Returns:
            体重目标 (lose/maintain/gain)
        """
        if not target_weight:
            return 'maintain'
        
        diff = target_weight - current_weight
        
        if diff < -1:  # 目标体重低于当前1kg以上
            return 'lose'
        elif diff > 1:  # 目标体重高于当前1kg以上
            return 'gain'
        else:
            return 'maintain'
    
    async def generate_diet_recommendation(
        self,
        db: Session,
        user_id: int,
        meal_type: Optional[str] = None,
        debug: bool = False
    ) -> Dict[str, Any]:
        """
        生成智能饮食推荐
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            meal_type: 餐次类型 (breakfast/lunch/dinner/snack)
            debug: 是否返回调试信息
            
        Returns:
            饮食推荐信息
        """
        try:
            logger.info(f"[饮食推荐] ========== 开始为用户 {user_id} 生成饮食推荐 ==========")
            
            # 1. 获取用户画像
            profile = db.query(UserProfile).filter_by(user_id=user_id).first()
            if not profile:
                logger.warning(f"[饮食推荐] 用户 {user_id} 没有个人资料")
                return {
                    "success": False,
                    "error": "用户资料不完整，请先完善个人信息"
                }
            
            # 检查必要信息
            if not all([profile.gender, profile.birth_date, profile.height_cm, profile.current_weight_kg]):
                logger.warning(f"[饮食推荐] 用户 {user_id} 缺少必要信息")
                return {
                    "success": False,
                    "error": "请先完善性别、年龄、身高、体重等基本信息"
                }
            
            # 计算年龄
            today = get_china_now().date()
            age = today.year - profile.birth_date.year
            if today.month < profile.birth_date.month or (
                today.month == profile.birth_date.month and today.day < profile.birth_date.day
            ):
                age -= 1
            
            # 2. 计算 BMR
            bmr = self.calculate_bmr(
                gender=profile.gender,
                weight_kg=profile.current_weight_kg,
                height_cm=profile.height_cm,
                age=age
            )
            
            # 3. 获取活动水平和运动消耗
            activity_level = self.get_activity_level(db, user_id)
            avg_exercise_calories = self.get_recent_workout_calories(db, user_id, days=7)
            
            # 4. 计算 TDEE
            tdee = self.calculate_tdee(
                bmr=bmr,
                activity_level=activity_level,
                exercise_calories=avg_exercise_calories
            )
            
            # 5. 判断体重目标
            weight_goal = self.determine_weight_goal(
                current_weight=profile.current_weight_kg,
                target_weight=profile.target_weight_kg
            )
            
            # 6. 计算每日营养目标
            daily_target = self.calculate_daily_target(
                tdee=tdee,
                weight_goal=weight_goal,
                diet_preference=profile.diet_preference
            )
            
            # 7. 获取今日已摄入
            today_intake = self.get_today_intake(db, user_id)
            
            # 8. 计算剩余可摄入
            remaining = {
                'calories': daily_target['calories'] - today_intake['calories'],
                'protein_g': daily_target['protein_g'] - today_intake['protein_g'],
                'carbs_g': daily_target['carbs_g'] - today_intake['carbs_g'],
                'fat_g': daily_target['fat_g'] - today_intake['fat_g']
            }
            
            logger.info(f"[饮食推荐] 剩余可摄入: {remaining}")
            
            # 9. 生成基础推荐结果
            result = {
                "success": True,
                "user_info": {
                    "age": age,
                    "gender": profile.gender,
                    "height_cm": profile.height_cm,
                    "current_weight_kg": profile.current_weight_kg,
                    "target_weight_kg": profile.target_weight_kg,
                    "weight_goal": weight_goal,
                    "diet_preference": profile.diet_preference,
                    "activity_level": activity_level
                },
                "metabolism": {
                    "bmr": round(bmr),
                    "tdee": round(tdee),
                    "avg_exercise_calories": avg_exercise_calories
                },
                "daily_target": daily_target,
                "today_intake": today_intake,
                "remaining": remaining,
                "progress": {
                    "calories_percent": round((today_intake['calories'] / daily_target['calories']) * 100, 1) if daily_target['calories'] > 0 else 0,
                    "protein_percent": round((today_intake['protein_g'] / daily_target['protein_g']) * 100, 1) if daily_target['protein_g'] > 0 else 0,
                    "carbs_percent": round((today_intake['carbs_g'] / daily_target['carbs_g']) * 100, 1) if daily_target['carbs_g'] > 0 else 0,
                    "fat_percent": round((today_intake['fat_g'] / daily_target['fat_g']) * 100, 1) if daily_target['fat_g'] > 0 else 0
                }
            }
            
            logger.info(f"[饮食推荐] ========== 饮食推荐生成完成 ==========")
            return result
            
        except Exception as e:
            logger.error(f"[饮食推荐] 生成推荐失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": f"生成推荐失败: {str(e)}"
            }


# 创建全局实例
diet_recommendation_service = DietRecommendationService()
