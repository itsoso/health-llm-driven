"""
AI 个性化建议服务 - executor.life
基于用户画像生成个性化健康建议
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session

from app.models.user_profile import UserProfile
from app.models.checkin import CheckinTemplate, CheckinRecord
from app.models.daily_health import GarminData

logger = logging.getLogger(__name__)


def get_llm_advice(prompt: str) -> str:
    """调用LLM生成建议"""
    try:
        from app.services.llm_health_analyzer import LLMHealthAnalyzer
        analyzer = LLMHealthAnalyzer()
        if analyzer.is_available() and analyzer.client:
            response = analyzer.client.chat.completions.create(
                model=analyzer.model,
                messages=[
                    {"role": "system", "content": "你是一位专业的健康管理顾问，善于根据用户的个人情况提供个性化的健康建议。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            return response.choices[0].message.content
    except Exception as e:
        logger.error(f"LLM调用失败: {e}")
    
    # 如果LLM不可用，返回默认建议
    return "暂无AI建议，请确保系统已配置OpenAI API。"


class PersonalizedAdviceService:
    """个性化建议服务"""
    
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self._profile: Optional[UserProfile] = None
        self._today_checkins: Optional[List[CheckinRecord]] = None
        self._garmin_data: Optional[GarminData] = None
        
    @property
    def profile(self) -> Optional[UserProfile]:
        if self._profile is None:
            self._profile = self.db.query(UserProfile).filter(
                UserProfile.user_id == self.user_id
            ).first()
        return self._profile
    
    @property
    def today_checkins(self) -> List[CheckinRecord]:
        if self._today_checkins is None:
            today = date.today()
            self._today_checkins = self.db.query(CheckinRecord).filter(
                CheckinRecord.user_id == self.user_id,
                CheckinRecord.checkin_date == today
            ).all()
        return self._today_checkins
    
    @property
    def garmin_data(self) -> Optional[GarminData]:
        if self._garmin_data is None:
            today = date.today()
            self._garmin_data = self.db.query(GarminData).filter(
                GarminData.user_id == self.user_id,
                GarminData.record_date == today
            ).first()
        return self._garmin_data
    
    def build_user_context(self) -> str:
        """构建用户上下文信息"""
        context_parts = []
        
        # 基本信息
        if self.profile:
            profile = self.profile
            basic_info = []
            if profile.gender:
                basic_info.append(f"性别: {'男' if profile.gender == 'male' else '女'}")
            if profile.age:
                basic_info.append(f"年龄: {profile.age}岁")
            if profile.height_cm:
                basic_info.append(f"身高: {profile.height_cm}cm")
            if profile.current_weight_kg:
                basic_info.append(f"体重: {profile.current_weight_kg}kg")
            if profile.bmi:
                basic_info.append(f"BMI: {profile.bmi} ({profile.bmi_category})")
            
            if basic_info:
                context_parts.append(f"【基本信息】{', '.join(basic_info)}")
            
            # 健康状况
            health_info = []
            if profile.chronic_conditions:
                health_info.append(f"慢性病: {', '.join(profile.chronic_conditions)}")
            if profile.allergies:
                health_info.append(f"过敏源: {', '.join(profile.allergies)}")
            if profile.family_history:
                health_info.append(f"家族病史: {', '.join(profile.family_history)}")
            
            if health_info:
                context_parts.append(f"【健康状况】{'; '.join(health_info)}")
            
            # 生活习惯
            lifestyle_info = []
            if profile.exercise_frequency:
                freq_map = {
                    'never': '从不运动',
                    'occasionally': '偶尔运动',
                    'weekly': '每周1-2次',
                    'regularly': '每周3-5次',
                    'daily': '每天运动'
                }
                lifestyle_info.append(f"运动频率: {freq_map.get(profile.exercise_frequency, profile.exercise_frequency)}")
            if profile.diet_preference:
                diet_map = {
                    'normal': '正常饮食',
                    'vegetarian': '素食',
                    'low_carb': '低碳水',
                    'keto': '生酮饮食'
                }
                lifestyle_info.append(f"饮食偏好: {diet_map.get(profile.diet_preference, profile.diet_preference)}")
            if profile.sitting_hours_per_day:
                lifestyle_info.append(f"每日久坐: {profile.sitting_hours_per_day}小时")
            
            if lifestyle_info:
                context_parts.append(f"【生活习惯】{'; '.join(lifestyle_info)}")
            
            # 健康目标
            goals_info = []
            if profile.target_steps:
                goals_info.append(f"目标步数: {profile.target_steps}步")
            if profile.target_sleep_hours:
                goals_info.append(f"目标睡眠: {profile.target_sleep_hours}小时")
            if profile.target_water_ml:
                goals_info.append(f"目标饮水: {profile.target_water_ml}ml")
            if profile.target_weight_kg and profile.current_weight_kg:
                diff = profile.current_weight_kg - profile.target_weight_kg
                if diff > 0:
                    goals_info.append(f"目标减重: {diff:.1f}kg")
                elif diff < 0:
                    goals_info.append(f"目标增重: {abs(diff):.1f}kg")
            
            if goals_info:
                context_parts.append(f"【健康目标】{'; '.join(goals_info)}")
        
        # 今日数据
        if self.garmin_data:
            gd = self.garmin_data
            today_info = []
            if gd.steps:
                today_info.append(f"步数: {gd.steps}")
            if gd.total_sleep_minutes:
                hours = gd.total_sleep_minutes // 60
                mins = gd.total_sleep_minutes % 60
                today_info.append(f"睡眠: {hours}小时{mins}分钟")
            if gd.stress_avg:
                today_info.append(f"压力: {gd.stress_avg}")
            if gd.body_battery_charged:
                today_info.append(f"身体电量: {gd.body_battery_charged}")
            
            if today_info:
                context_parts.append(f"【今日数据】{'; '.join(today_info)}")
        
        # 今日打卡
        if self.today_checkins:
            checkin_info = [r.template.name for r in self.today_checkins if r.template]
            if checkin_info:
                context_parts.append(f"【今日打卡】已完成: {', '.join(checkin_info)}")
        
        return '\n'.join(context_parts) if context_parts else '暂无用户画像数据'
    
    def get_morning_advice(self) -> Dict[str, Any]:
        """获取早间健康建议"""
        context = self.build_user_context()
        
        prompt = f"""
作为专业的健康管理顾问，请根据以下用户信息，给出今日早间健康建议。

{context}

请提供：
1. 今日健康提醒（基于用户的慢性病和过敏情况）
2. 运动建议（考虑用户的运动习惯和目标）
3. 饮食建议（考虑用户的饮食偏好）
4. 需要特别注意的事项

要求：
- 建议要具体、可执行
- 考虑用户的个人情况
- 语言亲切、鼓励
- 每条建议不超过50字
"""
        
        try:
            advice = get_llm_advice(prompt)
            return {
                'type': 'morning',
                'content': advice,
                'generated_at': datetime.now().isoformat(),
                'context_summary': context[:200] + '...' if len(context) > 200 else context
            }
        except Exception as e:
            logger.error(f"生成早间建议失败: {e}")
            return {
                'type': 'morning',
                'content': self._get_default_morning_advice(),
                'generated_at': datetime.now().isoformat(),
                'is_default': True
            }
    
    def get_checkin_advice(self, template_name: str) -> str:
        """获取打卡前的鼓励建议"""
        profile = self.profile
        
        # 基于慢性病给出特定建议
        if profile and profile.chronic_conditions:
            conditions = profile.chronic_conditions
            
            if '鼻炎' in conditions and '洗鼻' in template_name:
                return "坚持洗鼻对缓解鼻炎症状很有帮助！记得使用温热的生理盐水，效果更好。"
            
            if any(c in conditions for c in ['高血压', '心脏病']) and template_name in ['俯卧撑', '深蹲', '跳绳']:
                return "注意控制运动强度，循序渐进。如感到不适请立即停止。"
        
        # 通用鼓励
        encouragements = {
            '俯卧撑': "每一个俯卧撑都在让你变得更强壮！加油！💪",
            '深蹲': "深蹲是锻炼下肢力量的王牌动作，坚持下去！🏋️",
            '洗鼻': "保持鼻腔清洁，呼吸更顺畅！👃",
            '喝水': "及时补充水分，保持身体活力！💧",
            '冥想': "给自己一段安静的时光，放松身心～🧘",
            '早睡': "良好的睡眠是健康的基础！🌙",
        }
        
        return encouragements.get(template_name, f"坚持打卡{template_name}，养成好习惯！✨")
    
    def get_completion_advice(self, template_name: str, streak_days: int) -> str:
        """获取打卡完成后的反馈"""
        if streak_days >= 30:
            return f"🎉 太棒了！你已经连续打卡{streak_days}天，习惯已经养成！继续保持！"
        elif streak_days >= 7:
            return f"👏 连续{streak_days}天打卡，你正在建立良好的习惯！距离21天养成习惯还有{21-streak_days}天！"
        elif streak_days >= 3:
            return f"💪 连续{streak_days}天，好的开始！坚持就是胜利！"
        else:
            return "✅ 今日打卡完成！每一次坚持都是进步！"
    
    def get_daily_summary_advice(self) -> Dict[str, Any]:
        """获取每日总结建议"""
        context = self.build_user_context()
        
        # 获取打卡统计
        templates = self.db.query(CheckinTemplate).filter(
            CheckinTemplate.user_id == self.user_id,
            CheckinTemplate.is_active == True
        ).all()
        
        total = len(templates)
        completed = len(self.today_checkins)
        rate = (completed / total * 100) if total > 0 else 0
        
        # 分析完成情况
        completed_names = [r.template.name for r in self.today_checkins if r.template]
        uncompleted_templates = [t for t in templates if t.id not in {r.template_id for r in self.today_checkins}]
        uncompleted_names = [t.name for t in uncompleted_templates[:5]]  # 只取前5个
        
        summary = {
            'total_templates': total,
            'completed': completed,
            'completion_rate': round(rate, 1),
            'completed_items': completed_names,
            'uncompleted_items': uncompleted_names,
        }
        
        # 生成AI总结
        prompt = f"""
请根据以下用户今日的健康数据，给出简短的每日总结和明日建议。

{context}

今日打卡情况：
- 完成: {completed}/{total} ({rate:.1f}%)
- 已完成: {', '.join(completed_names) if completed_names else '无'}
- 未完成: {', '.join(uncompleted_names) if uncompleted_names else '全部完成！'}

请提供：
1. 今日总结（1-2句话）
2. 明日建议（1-2条具体建议）
3. 鼓励的话（1句）

语言要简洁、亲切、鼓励。
"""
        
        try:
            advice = get_llm_advice(prompt)
            summary['ai_advice'] = advice
        except Exception as e:
            logger.error(f"生成每日总结失败: {e}")
            summary['ai_advice'] = self._get_default_summary_advice(rate)
        
        summary['generated_at'] = datetime.now().isoformat()
        return summary
    
    def _get_default_morning_advice(self) -> str:
        """默认早间建议"""
        profile = self.profile
        advices = ["早安！新的一天开始了。"]
        
        if profile:
            if profile.chronic_conditions and '鼻炎' in profile.chronic_conditions:
                advices.append("记得按时洗鼻，保持鼻腔清洁。")
            
            if profile.target_steps:
                advices.append(f"今天的步数目标是{profile.target_steps}步，加油！")
            
            if profile.target_water_ml:
                advices.append(f"记得多喝水，目标{profile.target_water_ml}ml。")
        
        advices.append("祝你今天精力充沛！")
        return '\n'.join(advices)
    
    def _get_default_summary_advice(self, completion_rate: float) -> str:
        """默认每日总结"""
        if completion_rate >= 80:
            return "今天表现很棒！继续保持这种状态！🌟"
        elif completion_rate >= 50:
            return "今天完成了一半以上，明天再接再厉！💪"
        else:
            return "今天有些项目没完成，没关系，明天继续努力！🌱"


def get_personalized_advice(db: Session, user_id: int, advice_type: str = 'morning') -> Dict[str, Any]:
    """获取个性化建议的快捷函数"""
    service = PersonalizedAdviceService(db, user_id)
    
    if advice_type == 'morning':
        return service.get_morning_advice()
    elif advice_type == 'summary':
        return service.get_daily_summary_advice()
    else:
        return {'error': f'Unknown advice type: {advice_type}'}
