"""
复盘服务 - 数据聚合和汇总
"""
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.review import DailyReview, PeriodReview, ReviewPeriod
from app.models.daily_health import GarminData, DietRecord, WaterIntake, WorkoutRecord
from app.models.checkin import CheckinRecord
from app.models.supplement import SupplementRecord
from app.models.health_checkin import HealthCheckin
from app.schemas.review import DailyHealthSummary, ReviewPeriodType

logger = logging.getLogger(__name__)


class ReviewService:
    """复盘服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_daily_health_summary(self, user_id: int, target_date: date) -> DailyHealthSummary:
        """
        获取指定日期的健康数据汇总
        """
        summary = DailyHealthSummary(date=target_date)
        
        # 1. 获取 Garmin 数据（睡眠、步数、身体状态等）
        garmin = self.db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == target_date
        ).first()
        
        if garmin:
            summary.sleep_score = garmin.sleep_score
            if garmin.total_sleep_duration:
                summary.sleep_duration_hours = round(garmin.total_sleep_duration / 60, 1)
            summary.steps = garmin.steps or 0
            summary.active_calories = garmin.active_calories or 0
            summary.body_battery_high = garmin.body_battery_most_charged
            summary.body_battery_low = garmin.body_battery_lowest
            summary.stress_avg = garmin.stress_level
            summary.resting_hr = garmin.resting_heart_rate
        
        # 2. 获取运动数据
        workouts = self.db.query(WorkoutRecord).filter(
            WorkoutRecord.user_id == user_id,
            WorkoutRecord.workout_date == target_date
        ).all()
        
        for w in workouts:
            summary.workouts.append({
                "id": w.id,
                "type": w.workout_type,
                "name": w.workout_name,
                "duration_minutes": (w.duration_seconds or 0) // 60,
                "calories": w.calories or 0,
            })
            summary.total_workout_minutes += (w.duration_seconds or 0) // 60
            summary.total_workout_calories += w.calories or 0
        
        # 3. 获取饮食数据
        meals = self.db.query(DietRecord).filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date == target_date
        ).all()
        
        for m in meals:
            summary.meals.append({
                "id": m.id,
                "meal_type": m.meal_type,
                "food_items": m.food_items,
                "calories": m.calories or 0,
                "protein": m.protein or 0,
                "carbs": m.carbs or 0,
                "fat": m.fat or 0,
            })
            summary.total_calories += int(m.calories or 0)
            summary.total_protein += m.protein or 0
            summary.total_carbs += m.carbs or 0
            summary.total_fat += m.fat or 0
        
        # 4. 获取饮水数据
        water_records = self.db.query(WaterIntake).filter(
            WaterIntake.user_id == user_id,
            WaterIntake.record_date == target_date
        ).all()
        
        for w in water_records:
            summary.water_records.append({
                "id": w.id,
                "amount_ml": w.amount_ml,
                "time": str(w.intake_time) if w.intake_time else None,
            })
            summary.water_intake_ml += w.amount_ml or 0
        
        # 5. 获取打卡数据
        checkins = self.db.query(CheckinRecord).filter(
            CheckinRecord.user_id == user_id,
            CheckinRecord.checkin_date == target_date
        ).all()
        
        for c in checkins:
            summary.checkins.append({
                "id": c.id,
                "type": c.checkin_type,
                "completed": c.completed,
                "value": c.value,
                "notes": c.notes,
            })
            summary.checkin_total += 1
            if c.completed:
                summary.checkin_completed += 1
        
        # 6. 获取洗鼻数据（从 HealthCheckin）
        rhinitis = self.db.query(HealthCheckin).filter(
            HealthCheckin.user_id == user_id,
            HealthCheckin.checkin_date == target_date
        ).first()
        
        if rhinitis:
            summary.nasal_wash_done = rhinitis.nasal_wash_done or False
            summary.nasal_wash_count = rhinitis.nasal_wash_count or 0
        
        # 7. 获取补剂数据
        supplements = self.db.query(SupplementRecord).filter(
            SupplementRecord.user_id == user_id,
            SupplementRecord.taken_date == target_date
        ).all()
        
        for s in supplements:
            summary.supplements.append({
                "id": s.id,
                "supplement_id": s.supplement_id,
                "taken_time": s.taken_time,
                "dosage": s.dosage,
            })
        
        return summary
    
    def create_or_update_daily_review(
        self, 
        user_id: int, 
        target_date: date,
        user_input: Optional[Dict[str, Any]] = None
    ) -> DailyReview:
        """
        创建或更新每日复盘，自动填充健康数据
        """
        # 查找现有记录
        review = self.db.query(DailyReview).filter(
            DailyReview.user_id == user_id,
            DailyReview.review_date == target_date
        ).first()
        
        if not review:
            review = DailyReview(user_id=user_id, review_date=target_date)
            self.db.add(review)
        
        # 获取健康数据汇总
        summary = self.get_daily_health_summary(user_id, target_date)
        
        # 填充自动数据
        review.sleep_score = summary.sleep_score
        review.sleep_duration_hours = summary.sleep_duration_hours
        
        review.workout_count = len(summary.workouts)
        review.workout_duration_minutes = summary.total_workout_minutes
        review.workout_calories = summary.total_workout_calories
        review.workout_types = ",".join([w["type"] for w in summary.workouts]) if summary.workouts else None
        
        review.steps = summary.steps
        review.active_calories = summary.active_calories
        
        review.meals_count = len(summary.meals)
        review.total_calories_in = summary.total_calories
        review.total_protein = summary.total_protein
        review.total_carbs = summary.total_carbs
        review.total_fat = summary.total_fat
        
        review.water_intake_ml = summary.water_intake_ml
        review.water_goal_met = summary.water_intake_ml >= 2000
        
        review.nasal_wash_done = summary.nasal_wash_done
        review.nasal_wash_count = summary.nasal_wash_count
        
        review.checkin_completed = summary.checkin_completed
        review.checkin_total = summary.checkin_total
        review.checkin_items = json.dumps(summary.checkins, ensure_ascii=False) if summary.checkins else None
        
        review.supplements_taken = len(summary.supplements)
        review.supplements_list = json.dumps(summary.supplements, ensure_ascii=False) if summary.supplements else None
        
        review.body_battery_high = summary.body_battery_high
        review.body_battery_low = summary.body_battery_low
        review.stress_avg = summary.stress_avg
        review.resting_hr = summary.resting_hr
        
        # 填充用户输入
        if user_input:
            if "mood_score" in user_input:
                review.mood_score = user_input["mood_score"]
            if "energy_score" in user_input:
                review.energy_score = user_input["energy_score"]
            if "productivity_score" in user_input:
                review.productivity_score = user_input["productivity_score"]
            if "highlights" in user_input:
                review.highlights = user_input["highlights"]
            if "challenges" in user_input:
                review.challenges = user_input["challenges"]
            if "learnings" in user_input:
                review.learnings = user_input["learnings"]
            if "gratitude" in user_input:
                review.gratitude = user_input["gratitude"]
            if "tomorrow_plan" in user_input:
                review.tomorrow_plan = user_input["tomorrow_plan"]
            if "summary" in user_input:
                review.summary = user_input["summary"]
            if "is_completed" in user_input:
                review.is_completed = user_input["is_completed"]
        
        review.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(review)
        
        return review
    
    def get_daily_review(self, user_id: int, target_date: date) -> Optional[DailyReview]:
        """获取指定日期的复盘"""
        return self.db.query(DailyReview).filter(
            DailyReview.user_id == user_id,
            DailyReview.review_date == target_date
        ).first()
    
    def list_daily_reviews(
        self, 
        user_id: int, 
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 30
    ) -> List[DailyReview]:
        """获取复盘列表"""
        query = self.db.query(DailyReview).filter(DailyReview.user_id == user_id)
        
        if start_date:
            query = query.filter(DailyReview.review_date >= start_date)
        if end_date:
            query = query.filter(DailyReview.review_date <= end_date)
        
        return query.order_by(DailyReview.review_date.desc()).limit(limit).all()
    
    def create_period_review(
        self,
        user_id: int,
        period_type: ReviewPeriod,
        start_date: date,
        end_date: date
    ) -> PeriodReview:
        """
        创建周期复盘，自动汇总数据
        """
        # 查找现有记录
        review = self.db.query(PeriodReview).filter(
            PeriodReview.user_id == user_id,
            PeriodReview.period_type == period_type,
            PeriodReview.start_date == start_date,
            PeriodReview.end_date == end_date
        ).first()
        
        if not review:
            review = PeriodReview(
                user_id=user_id,
                period_type=period_type,
                start_date=start_date,
                end_date=end_date
            )
            self.db.add(review)
        
        # 生成周期标签
        if period_type == ReviewPeriod.WEEKLY:
            week_num = start_date.isocalendar()[1]
            review.period_label = f"{start_date.year}年第{week_num}周"
        elif period_type == ReviewPeriod.MONTHLY:
            review.period_label = f"{start_date.year}年{start_date.month}月"
        elif period_type == ReviewPeriod.QUARTERLY:
            quarter = (start_date.month - 1) // 3 + 1
            review.period_label = f"{start_date.year}年Q{quarter}"
        elif period_type == ReviewPeriod.YEARLY:
            review.period_label = f"{start_date.year}年"
        
        # 获取该周期内的每日复盘
        daily_reviews = self.db.query(DailyReview).filter(
            DailyReview.user_id == user_id,
            DailyReview.review_date >= start_date,
            DailyReview.review_date <= end_date
        ).all()
        
        # 计算总天数
        review.total_days = (end_date - start_date).days + 1
        review.review_days = len([r for r in daily_reviews if r.is_completed])
        
        # 汇总统计
        if daily_reviews:
            # 睡眠统计
            sleep_scores = [r.sleep_score for r in daily_reviews if r.sleep_score]
            if sleep_scores:
                review.avg_sleep_score = round(sum(sleep_scores) / len(sleep_scores), 1)
            
            sleep_durations = [r.sleep_duration_hours for r in daily_reviews if r.sleep_duration_hours]
            if sleep_durations:
                review.avg_sleep_duration = round(sum(sleep_durations) / len(sleep_durations), 1)
            
            # 运动统计
            review.total_workouts = sum(r.workout_count or 0 for r in daily_reviews)
            review.total_workout_minutes = sum(r.workout_duration_minutes or 0 for r in daily_reviews)
            review.total_workout_calories = sum(r.workout_calories or 0 for r in daily_reviews)
            review.workout_days = len([r for r in daily_reviews if r.workout_count and r.workout_count > 0])
            
            # 步数统计
            steps_list = [(r.review_date, r.steps or 0) for r in daily_reviews]
            review.total_steps = sum(s[1] for s in steps_list)
            if steps_list:
                review.avg_steps = review.total_steps // len(steps_list)
                best_steps = max(steps_list, key=lambda x: x[1])
                review.best_steps_date = best_steps[0]
            
            # 饮食统计
            calories_list = [r.total_calories_in or 0 for r in daily_reviews]
            if calories_list:
                review.avg_calories_in = sum(calories_list) // len(calories_list)
            
            protein_list = [r.total_protein or 0 for r in daily_reviews]
            if protein_list:
                review.avg_protein = round(sum(protein_list) / len(protein_list), 1)
            
            # 饮水统计
            water_list = [r.water_intake_ml or 0 for r in daily_reviews]
            if water_list:
                review.avg_water_intake = sum(water_list) // len(water_list)
            review.water_goal_days = len([r for r in daily_reviews if r.water_goal_met])
            
            # 打卡统计
            checkin_rates = []
            for r in daily_reviews:
                if r.checkin_total and r.checkin_total > 0:
                    checkin_rates.append(r.checkin_completed / r.checkin_total)
            if checkin_rates:
                review.avg_checkin_rate = round(sum(checkin_rates) / len(checkin_rates) * 100, 1)
            
            review.perfect_days = len([
                r for r in daily_reviews 
                if r.checkin_total and r.checkin_total > 0 and r.checkin_completed == r.checkin_total
            ])
        
        review.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(review)
        
        return review
    
    def get_current_week_range(self, target_date: date = None) -> tuple:
        """获取当前周的日期范围（周一到周日）"""
        if target_date is None:
            target_date = date.today()
        
        # 计算本周一
        monday = target_date - timedelta(days=target_date.weekday())
        sunday = monday + timedelta(days=6)
        
        return monday, sunday
    
    def get_current_month_range(self, target_date: date = None) -> tuple:
        """获取当前月的日期范围"""
        if target_date is None:
            target_date = date.today()
        
        first_day = target_date.replace(day=1)
        # 下个月第一天减一天
        if target_date.month == 12:
            last_day = target_date.replace(year=target_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            last_day = target_date.replace(month=target_date.month + 1, day=1) - timedelta(days=1)
        
        return first_day, last_day
    
    def generate_ai_summary(self, user_id: int, target_date: date, period: str = "daily") -> str:
        """
        使用 AI 生成复盘总结
        """
        try:
            if period == "daily":
                review = self.get_daily_review(user_id, target_date)
                if not review:
                    return "暂无数据可供总结"
                
                # 构建提示词
                data_summary = []
                
                if review.sleep_score:
                    data_summary.append(f"睡眠分数{review.sleep_score}分")
                if review.sleep_duration_hours:
                    data_summary.append(f"睡眠{review.sleep_duration_hours:.1f}小时")
                if review.workout_count:
                    data_summary.append(f"运动{review.workout_count}次，消耗{review.workout_calories}卡")
                if review.steps:
                    data_summary.append(f"步数{review.steps}")
                if review.meals_count:
                    data_summary.append(f"进食{review.meals_count}餐，摄入{review.total_calories_in}卡")
                if review.water_intake_ml:
                    status = "达标" if review.water_goal_met else "未达标"
                    data_summary.append(f"饮水{review.water_intake_ml}ml({status})")
                if review.nasal_wash_count:
                    data_summary.append(f"洗鼻{review.nasal_wash_count}次")
                if review.checkin_total:
                    data_summary.append(f"打卡完成{review.checkin_completed}/{review.checkin_total}")
                
                user_inputs = []
                if review.highlights:
                    user_inputs.append(f"亮点：{review.highlights}")
                if review.challenges:
                    user_inputs.append(f"挑战：{review.challenges}")
                if review.learnings:
                    user_inputs.append(f"收获：{review.learnings}")
                
                # 生成简洁总结
                summary_parts = []
                
                # 睡眠评价
                if review.sleep_score:
                    if review.sleep_score >= 85:
                        summary_parts.append("昨晚睡眠质量优秀")
                    elif review.sleep_score >= 70:
                        summary_parts.append("昨晚睡眠质量良好")
                    else:
                        summary_parts.append("昨晚睡眠质量一般，需要关注")
                
                # 运动评价
                if review.workout_count and review.workout_count > 0:
                    summary_parts.append(f"今日完成{review.workout_count}次运动，消耗{review.workout_calories}卡路里")
                elif review.steps and review.steps >= 8000:
                    summary_parts.append(f"今日步数{review.steps}，活动量达标")
                else:
                    summary_parts.append("今日运动量偏少，建议增加活动")
                
                # 饮食评价
                if review.meals_count:
                    if review.total_calories_in > 2500:
                        summary_parts.append("今日热量摄入偏高")
                    elif review.total_calories_in < 1200:
                        summary_parts.append("今日热量摄入偏低")
                    else:
                        summary_parts.append("今日饮食摄入适中")
                
                # 习惯完成情况
                habits_done = []
                if review.water_goal_met:
                    habits_done.append("饮水达标")
                if review.nasal_wash_done:
                    habits_done.append("洗鼻完成")
                if review.checkin_total and review.checkin_completed == review.checkin_total:
                    habits_done.append("打卡全勤")
                
                if habits_done:
                    summary_parts.append(f"健康习惯：{', '.join(habits_done)}")
                
                # 用户输入的亮点
                if review.highlights:
                    summary_parts.append(f"今日亮点：{review.highlights[:50]}")
                
                # 生成最终总结
                ai_summary = "。".join(summary_parts) + "。"
                
                # 添加鼓励语
                if review.mood_score and review.mood_score >= 4:
                    ai_summary += " 保持好心情，继续加油！💪"
                elif review.mood_score and review.mood_score <= 2:
                    ai_summary += " 明天会更好，好好休息！🌙"
                else:
                    ai_summary += " 每一天都是新的开始！✨"
                
                # 保存 AI 总结
                review.ai_summary = ai_summary
                self.db.commit()
                
                return ai_summary
            
            elif period in ["weekly", "monthly"]:
                # 周/月复盘总结
                if period == "weekly":
                    start_date, end_date = self.get_current_week_range(target_date)
                    period_review = self.db.query(PeriodReview).filter(
                        PeriodReview.user_id == user_id,
                        PeriodReview.period_type == ReviewPeriod.WEEKLY,
                        PeriodReview.start_date == start_date
                    ).first()
                else:
                    start_date, end_date = self.get_current_month_range(target_date)
                    period_review = self.db.query(PeriodReview).filter(
                        PeriodReview.user_id == user_id,
                        PeriodReview.period_type == ReviewPeriod.MONTHLY,
                        PeriodReview.start_date == start_date
                    ).first()
                
                if not period_review:
                    return "暂无数据可供总结"
                
                summary_parts = []
                period_name = "本周" if period == "weekly" else "本月"
                
                # 复盘完成情况
                if period_review.review_days and period_review.total_days:
                    rate = period_review.review_days / period_review.total_days * 100
                    summary_parts.append(f"{period_name}完成{period_review.review_days}天复盘，完成率{rate:.0f}%")
                
                # 睡眠总结
                if period_review.avg_sleep_score:
                    if period_review.avg_sleep_score >= 85:
                        summary_parts.append(f"平均睡眠分数{period_review.avg_sleep_score:.0f}分，睡眠质量优秀")
                    elif period_review.avg_sleep_score >= 70:
                        summary_parts.append(f"平均睡眠分数{period_review.avg_sleep_score:.0f}分，睡眠质量良好")
                    else:
                        summary_parts.append(f"平均睡眠分数{period_review.avg_sleep_score:.0f}分，需要改善睡眠")
                
                # 运动总结
                if period_review.workout_days:
                    summary_parts.append(f"运动{period_review.workout_days}天，总消耗{period_review.total_workout_calories}卡")
                
                # 步数总结
                if period_review.avg_steps:
                    if period_review.avg_steps >= 8000:
                        summary_parts.append(f"日均步数{period_review.avg_steps}，活动量充足")
                    else:
                        summary_parts.append(f"日均步数{period_review.avg_steps}，建议增加活动")
                
                # 打卡总结
                if period_review.perfect_days:
                    summary_parts.append(f"全勤打卡{period_review.perfect_days}天")
                
                # 饮水总结
                if period_review.water_goal_days:
                    summary_parts.append(f"饮水达标{period_review.water_goal_days}天")
                
                ai_summary = "。".join(summary_parts) + "。"
                ai_summary += f" {period_name}整体表现{'不错' if period_review.perfect_days > period_review.total_days / 2 else '还有提升空间'}，继续保持！💪"
                
                # 保存
                period_review.ai_summary = ai_summary
                self.db.commit()
                
                return ai_summary
            
            return "不支持的复盘类型"
            
        except Exception as e:
            logger.error(f"AI生成总结失败: {e}")
            return f"生成总结时出错: {str(e)}"
