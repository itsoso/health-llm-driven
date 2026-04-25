"""
智能饮食推荐服务
基于用户目标、运动状态、睡眠质量等多维数据，提供个性化饮食建议
"""
import logging
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
import os

from app.models.user_profile import UserProfile
from app.models.daily_health import DietRecord, GarminData, WorkoutRecord
from app.utils.timezone import get_china_now

# RAG pipeline 暂时禁用，等待实现
# from app.services.rag_pipeline import rag_pipeline

logger = logging.getLogger(__name__)


class DietRecommendationService:
    """智能饮食推荐服务"""

    def __init__(self):
        self.knowledge_base_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'knowledge',
            'nutrition_knowledge.md'
        )

    @staticmethod
    def _parse_json_field(field_value: Any) -> List:
        """
        解析 JSON 字段，处理可能是字符串的情况

        Args:
            field_value: 字段值（可能是列表或 JSON 字符串）

        Returns:
            解析后的列表
        """
        if not field_value:
            return []

        if isinstance(field_value, list):
            return field_value

        if isinstance(field_value, str):
            try:
                parsed = json.loads(field_value)
                return parsed if isinstance(parsed, list) else []
            except:
                return []

        return []

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

    def _get_health_status(self, db: Session, user_id: int) -> Dict[str, Any]:
        """
        获取用户最近的健康状态

        Args:
            db: 数据库会话
            user_id: 用户ID

        Returns:
            健康状态数据
        """
        today = get_china_now().date()

        # 获取最近的 Garmin 数据
        recent_data = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == today
        ).first()

        if not recent_data:
            logger.info(f"[饮食推荐] 今日无 Garmin 健康数据")
            return {}

        status = {
            'sleep_score': recent_data.sleep_score,
            'sleep_hours': round(recent_data.total_sleep_duration / 60, 1) if recent_data.total_sleep_duration else None,
            'body_battery': recent_data.body_battery_current,
            'stress_level': recent_data.stress_level,
            'resting_hr': recent_data.resting_heart_rate,
            'hrv': recent_data.hrv  # 使用当日 HRV，如果为空则使用 7 天平均
        }

        logger.info(f"[饮食推荐] 健康状态: 睡眠{status['sleep_score']}/100, 身体电量{status['body_battery']}, 压力{status['stress_level']}")
        return status

    def _generate_warnings_and_tips(
        self,
        profile: UserProfile,
        daily_target: Dict[str, float],
        today_intake: Dict[str, float],
        remaining: Dict[str, float],
        health_status: Dict[str, Any],
        weight_goal: str
    ) -> tuple[List[str], List[str]]:
        """
        生成警告和健康提示

        Returns:
            (warnings, tips)
        """
        warnings = []
        tips = []

        # 1. 营养摄入警告
        if today_intake['meals_count'] > 0:
            # 蛋白质不足
            if today_intake['protein_g'] < daily_target['protein_g'] * 0.5:
                warnings.append("⚠️ 今日蛋白质摄入不足，建议补充优质蛋白质")

            # 卡路里超标
            if today_intake['calories'] > daily_target['calories'] * 1.2:
                warnings.append("⚠️ 今日卡路里摄入已超标20%，建议控制晚餐")

            # 碳水过高（减重模式）
            if weight_goal == 'lose' and today_intake['carbs_g'] > daily_target['carbs_g'] * 1.3:
                warnings.append("⚠️ 碳水摄入偏高，不利于减重目标")

        # 2. 睡眠相关提示
        sleep_score = health_status.get('sleep_score')
        if sleep_score and sleep_score < 70:
            tips.append("💤 睡眠质量欠佳，建议晚餐清淡，避免咖啡因")
            tips.append("🥛 可以喝一杯温牛奶或吃一根香蕉，有助于睡眠")

        # 3. 压力相关提示
        stress_level = health_status.get('stress_level')
        if stress_level and stress_level > 50:
            tips.append("😌 压力较大，建议多吃深绿色蔬菜和坚果，补充镁元素")
            tips.append("🍵 避免高糖食物，可以喝绿茶或花茶舒缓压力")

        # 4. 身体电量相关
        body_battery = health_status.get('body_battery')
        if body_battery and body_battery < 30:
            tips.append("⚡ 身体电量较低，建议补充优质碳水和蛋白质恢复能量")

        # 5. 慢性病相关警告
        chronic_conditions = self._parse_json_field(profile.chronic_conditions)
        if '高血压' in chronic_conditions:
            warnings.append("🩺 注意控制钠摄入（<2000mg/天），少吃腌制食品")
        if '糖尿病' in chronic_conditions:
            warnings.append("🩺 注意控制碳水总量，选择低GI食物，避免血糖波动")

        # 6. 过敏源警告
        allergies = self._parse_json_field(profile.allergies)
        if allergies:
            warnings.append(f"🚫 过敏提醒：避免 {', '.join(allergies)}")

        # 7. 体重目标相关提示
        if weight_goal == 'lose':
            tips.append("🎯 减重模式：优先选择高蛋白低脂食物，增加饱腹感")
            tips.append("🥗 多吃蔬菜，控制精制碳水（白米饭、面条）")
        elif weight_goal == 'gain':
            tips.append("🎯 增重模式：增加优质蛋白和健康脂肪摄入")
            tips.append("🥜 可以适当加餐，如坚果、牛油果、全麦面包")

        # 8. 通用健康提示
        if not tips:
            tips.append("💧 记得多喝水，保持充足水分")
            tips.append("🍎 每天至少5种不同颜色的蔬果")

        logger.info(f"[饮食推荐] 生成 {len(warnings)} 条警告, {len(tips)} 条提示")
        return warnings, tips

    def _generate_food_recommendations(
        self,
        profile: UserProfile,
        remaining: Dict[str, float],
        meal_type: Optional[str],
        health_status: Dict[str, Any],
        weight_goal: str
    ) -> List[Dict[str, Any]]:
        """
        生成具体食物推荐

        Returns:
            食物推荐列表
        """
        recommendations = []

        # 获取过敏源和慢性病
        allergies = self._parse_json_field(profile.allergies)
        chronic_conditions = self._parse_json_field(profile.chronic_conditions)
        diet_preference = profile.diet_preference

        # 1. 高蛋白食物推荐（如果蛋白质不足）
        if remaining['protein_g'] > 50:
            protein_foods = []

            # 排除过敏源
            if '海鲜' not in allergies and diet_preference != 'vegetarian':
                protein_foods.extend(['三文鱼', '鳕鱼', '虾'])
            if '牛奶' not in allergies:
                protein_foods.extend(['希腊酸奶', '低脂牛奶'])
            if diet_preference != 'vegetarian':
                protein_foods.extend(['鸡胸肉', '瘦牛肉', '鸡蛋'])

            # 素食蛋白
            if diet_preference == 'vegetarian' or not protein_foods:
                protein_foods.extend(['豆腐', '豆浆', '鹰嘴豆', '藜麦'])

            if protein_foods:
                recommendations.append({
                    'category': '优质蛋白',
                    'foods': protein_foods[:5],
                    'reason': f'补充蛋白质（还需{remaining["protein_g"]:.0f}g）',
                    'priority': 'high'
                })

        # 2. 碳水化合物推荐
        if remaining['carbs_g'] > 50:
            carb_foods = []

            if weight_goal == 'lose' or diet_preference == 'low_carb':
                # 低GI碳水
                carb_foods = ['糙米饭', '燕麦', '红薯', '全麦面包', '藜麦']
            elif diet_preference == 'keto':
                # 生酮饮食：极低碳水
                carb_foods = ['西兰花', '菠菜', '生菜', '黄瓜']
            else:
                # 正常碳水
                carb_foods = ['米饭', '面条', '土豆', '玉米', '全麦面包']

            recommendations.append({
                'category': '碳水化合物',
                'foods': carb_foods[:5],
                'reason': f'提供能量（还需{remaining["carbs_g"]:.0f}g）',
                'priority': 'medium'
            })

        # 3. 健康脂肪推荐
        if remaining['fat_g'] > 20:
            fat_foods = []

            if '花生' not in allergies:
                fat_foods.append('花生酱')
            if '坚果' not in allergies:
                fat_foods.extend(['核桃', '杏仁', '腰果'])

            fat_foods.extend(['牛油果', '橄榄油', '深海鱼油'])

            recommendations.append({
                'category': '健康脂肪',
                'foods': fat_foods[:5],
                'reason': f'补充必需脂肪酸（还需{remaining["fat_g"]:.0f}g）',
                'priority': 'medium'
            })

        # 4. 蔬菜水果推荐
        veggies = ['西兰花', '菠菜', '胡萝卜', '番茄', '黄瓜']
        fruits = ['苹果', '香蕉', '蓝莓', '橙子', '猕猴桃']

        # 根据健康状态调整
        sleep_score = health_status.get('sleep_score')
        if sleep_score and sleep_score < 70:
            # 助眠食物
            fruits = ['香蕉', '樱桃', '猕猴桃'] + fruits

        recommendations.append({
            'category': '蔬菜',
            'foods': veggies,
            'reason': '补充维生素、矿物质和膳食纤维',
            'priority': 'high'
        })

        recommendations.append({
            'category': '水果',
            'foods': fruits,
            'reason': '补充维生素C和抗氧化物',
            'priority': 'medium'
        })

        # 5. 根据餐次调整推荐
        if meal_type == 'breakfast':
            recommendations.insert(0, {
                'category': '早餐推荐',
                'foods': ['燕麦粥', '全麦面包', '鸡蛋', '牛奶', '香蕉'],
                'reason': '开启一天的能量，营养均衡',
                'priority': 'high'
            })
        elif meal_type == 'dinner':
            # 晚餐建议清淡
            recommendations.insert(0, {
                'category': '晚餐推荐',
                'foods': ['清蒸鱼', '蔬菜沙拉', '豆腐汤', '糙米饭'],
                'reason': '晚餐宜清淡，避免过饱影响睡眠',
                'priority': 'high'
            })

        logger.info(f"[饮食推荐] 生成 {len(recommendations)} 类食物推荐")
        return recommendations

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

            # 9. 获取睡眠和身体状态
            health_status = self._get_health_status(db, user_id)

            # 10. 生成警告和提示
            warnings, tips = self._generate_warnings_and_tips(
                profile=profile,
                daily_target=daily_target,
                today_intake=today_intake,
                remaining=remaining,
                health_status=health_status,
                weight_goal=weight_goal
            )

            # 11. 生成食物推荐
            food_recommendations = self._generate_food_recommendations(
                profile=profile,
                remaining=remaining,
                meal_type=meal_type,
                health_status=health_status,
                weight_goal=weight_goal
            )

            # 12. 获取科学依据和详细建议
            scientific_insights = self._get_scientific_insights(
                profile=profile,
                weight_goal=weight_goal,
                health_status=health_status,
                warnings=warnings
            )

            # 13. 生成基础推荐结果
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
                },
                "health_status": health_status,
                "warnings": warnings,
                "tips": tips,
                "food_recommendations": food_recommendations,
                "scientific_insights": scientific_insights
            }

            logger.info(f"[饮食推荐] ========== 饮食推荐生成完成 ==========")
            return result

        except Exception as e:
            logger.error(f"[饮食推荐] 生成推荐失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": f"生成推荐失败: {str(e)}"
            }

    def _get_scientific_insights(
        self,
        profile: UserProfile,
        weight_goal: str,
        health_status: Dict[str, Any],
        warnings: List[str]
    ) -> Dict[str, Any]:
        """
        使用 RAG 获取科学依据和详细营养建议

        Returns:
            科学见解和建议
        """
        try:
            # 构建查询上下文
            query_parts = []

            # 1. 体重目标相关查询
            if weight_goal == 'lose':
                query_parts.append("减重期间的营养素分配比例和科学依据")
            elif weight_goal == 'gain':
                query_parts.append("增重增肌期间的营养素分配和科学依据")
            else:
                query_parts.append("维持体重的营养素分配")

            # 2. 慢性病相关查询
            chronic_conditions = self._parse_json_field(profile.chronic_conditions)
            if '高血压' in chronic_conditions:
                query_parts.append("高血压患者的DASH饮食原则")
            if '糖尿病' in chronic_conditions:
                query_parts.append("糖尿病患者的血糖管理和低GI食物")
            if '高血脂' in chronic_conditions:
                query_parts.append("高血脂患者的脂肪摄入建议")

            # 3. 饮食偏好相关查询
            diet_preference = profile.diet_preference
            if diet_preference == 'vegetarian':
                query_parts.append("素食者的蛋白质来源和营养补充")
            elif diet_preference == 'keto':
                query_parts.append("生酮饮食的原理和注意事项")
            elif diet_preference == 'low_carb':
                query_parts.append("低碳水饮食的科学依据")

            # 4. 睡眠相关查询
            sleep_score = health_status.get('sleep_score')
            if sleep_score and sleep_score < 70:
                query_parts.append("助眠食物和睡眠营养")

            # 5. 压力相关查询
            stress_level = health_status.get('stress_level')
            if stress_level and stress_level > 50:
                query_parts.append("抗压力营养素和食物")

            # 合并查询
            combined_query = "。".join(query_parts)
            logger.info(f"[饮食推荐] RAG 查询: {combined_query}")

            # 使用 RAG 检索知识
            # RAG pipeline 暂时禁用
            logger.warning(f"[饮食推荐] RAG pipeline 暂未实现，返回空结果")
            return {
                "available": False,
                "reason": "RAG pipeline 暂未实现"
            }

            # TODO: 实现 RAG pipeline 后启用以下代码
            # if not os.path.exists(self.knowledge_base_path):
            #     logger.warning(f"[饮食推荐] 知识库文件不存在: {self.knowledge_base_path}")
            #     return {
            #         "available": False,
            #         "reason": "知识库未初始化"
            #     }
            #
            # # 调用 RAG pipeline
            # rag_result = rag_pipeline.query(
            #     query=combined_query,
            #     knowledge_base_path=self.knowledge_base_path,
            #     top_k=5
            # )
            #
            # if not rag_result or 'error' in rag_result:
            #     logger.warning(f"[饮食推荐] RAG 检索失败: {rag_result.get('error', 'Unknown error')}")
            #     return {
            #         "available": False,
            #         "reason": "知识检索失败"
            #     }

            # 提取关键信息
            insights = {
                "available": True,
                "bmr_tdee_explanation": self._extract_section(rag_result, "BMR", "TDEE"),
                "macronutrient_rationale": self._extract_section(rag_result, "营养素分配", weight_goal),
                "diet_mode_guidance": self._extract_section(rag_result, diet_preference) if diet_preference else None,
                "chronic_disease_guidance": [],
                "sleep_nutrition": self._extract_section(rag_result, "睡眠", "助眠") if sleep_score and sleep_score < 70 else None,
                "stress_nutrition": self._extract_section(rag_result, "压力", "抗压") if stress_level and stress_level > 50 else None,
                "references": rag_result.get('sources', [])
            }

            # 慢性病指导
            for condition in chronic_conditions:
                guidance = self._extract_section(rag_result, condition)
                if guidance:
                    insights["chronic_disease_guidance"].append({
                        "condition": condition,
                        "guidance": guidance
                    })

            logger.info(f"[饮食推荐] 成功获取科学见解")
            return insights

        except Exception as e:
            logger.error(f"[饮食推荐] 获取科学见解失败: {str(e)}", exc_info=True)
            return {
                "available": False,
                "reason": f"处理失败: {str(e)}"
            }

    def _extract_section(self, rag_result: Dict[str, Any], *keywords: str) -> Optional[str]:
        """
        从 RAG 结果中提取包含关键词的段落

        Args:
            rag_result: RAG 检索结果
            keywords: 关键词列表

        Returns:
            提取的文本段落
        """
        try:
            contexts = rag_result.get('contexts', [])
            if not contexts:
                return None

            # 查找包含所有关键词的段落
            for context in contexts:
                text = context.get('text', '')
                if all(keyword in text for keyword in keywords):
                    # 提取相关部分（最多500字符）
                    return text[:500] + "..." if len(text) > 500 else text

            # 如果没有找到包含所有关键词的，返回包含任一关键词的第一个
            for context in contexts:
                text = context.get('text', '')
                if any(keyword in text for keyword in keywords):
                    return text[:500] + "..." if len(text) > 500 else text

            return None

        except Exception as e:
            logger.error(f"[饮食推荐] 提取段落失败: {str(e)}")
            return None


# 创建全局实例
diet_recommendation_service = DietRecommendationService()
