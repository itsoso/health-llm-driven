"""基于大模型的健康分析服务"""
import json
import logging
from datetime import date, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from app.models.daily_health import GarminData
from app.models.user import User
from app.models.basic_health import BasicHealthData
from app.config import settings

logger = logging.getLogger(__name__)

# 尝试导入 OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI库未安装，LLM分析功能将不可用")


class LLMHealthAnalyzer:
    """
    基于大模型的健康分析器
    
    结合规则分析结果，使用大模型生成更智能、更个性化的健康建议
    """
    
    def __init__(self):
        self.client = None
        if OPENAI_AVAILABLE and settings.openai_api_key:
            self.client = OpenAI(api_key=settings.openai_api_key)
        else:
            logger.warning("OpenAI API未配置，将使用纯规则分析")
    
    def is_available(self) -> bool:
        """检查LLM服务是否可用"""
        return self.client is not None
    
    def _build_user_context(
        self,
        db: Session,
        user_id: int
    ) -> Dict[str, Any]:
        """构建用户上下文信息"""
        user = db.query(User).filter(User.id == user_id).first()
        basic_health = db.query(BasicHealthData).filter(
            BasicHealthData.user_id == user_id
        ).order_by(BasicHealthData.record_date.desc()).first()
        
        context = {
            "name": user.name if user else "用户",
            "gender": user.gender if user else None,
            "age": None
        }
        
        if user and user.birth_date:
            today = date.today()
            context["age"] = today.year - user.birth_date.year
        
        if basic_health:
            context.update({
                "height": basic_health.height,
                "weight": basic_health.weight,
                "bmi": basic_health.bmi,
                "blood_pressure": f"{basic_health.systolic_bp}/{basic_health.diastolic_bp}" if basic_health.systolic_bp else None
            })
        
        return context
    
    def _build_health_data_prompt(
        self,
        yesterday_data: GarminData,
        recent_data: List[GarminData],
        rule_analysis: Dict[str, Any],
        user_context: Dict[str, Any]
    ) -> str:
        """构建健康数据分析提示词"""
        
        # 构建用户信息部分
        user_info = f"""
用户信息:
- 姓名: {user_context.get('name', '未知')}
- 年龄: {user_context.get('age', '未知')}岁
- 性别: {user_context.get('gender', '未知')}
- 身高: {user_context.get('height', '未知')}cm
- 体重: {user_context.get('weight', '未知')}kg
- BMI: {user_context.get('bmi', '未知')}
- 血压: {user_context.get('blood_pressure', '未知')}
"""
        
        # 构建昨日数据部分
        yesterday_info = f"""
昨日健康数据 ({yesterday_data.record_date}):

【睡眠数据】
- 睡眠分数: {yesterday_data.sleep_score or '无数据'}/100
- 总睡眠时长: {round(yesterday_data.total_sleep_duration / 60, 1) if yesterday_data.total_sleep_duration else '无数据'}小时
- 深度睡眠: {yesterday_data.deep_sleep_duration or '无数据'}分钟
- REM睡眠: {yesterday_data.rem_sleep_duration or '无数据'}分钟
- 浅睡眠: {yesterday_data.light_sleep_duration or '无数据'}分钟
- 清醒时间: {yesterday_data.awake_duration or '无数据'}分钟

【心率数据】
- 静息心率: {yesterday_data.resting_heart_rate or '无数据'} bpm
- 平均心率: {yesterday_data.avg_heart_rate or '无数据'} bpm
- 最高心率: {yesterday_data.max_heart_rate or '无数据'} bpm
- 最低心率: {yesterday_data.min_heart_rate or '无数据'} bpm
- 心率变异性(HRV): {yesterday_data.hrv or '无数据'} ms

【活动数据】
- 步数: {yesterday_data.steps or '无数据'}步
- 活动分钟: {yesterday_data.active_minutes or '无数据'}分钟
- 消耗卡路里: {yesterday_data.calories_burned or '无数据'} kcal

【压力与恢复】
- 压力水平: {yesterday_data.stress_level or '无数据'}/100
- 身体电量最高值: {yesterday_data.body_battery_most_charged or '无数据'}
- 身体电量最低值: {yesterday_data.body_battery_lowest or '无数据'}
- 身体电量充电: {yesterday_data.body_battery_charged or '无数据'}
- 身体电量消耗: {yesterday_data.body_battery_drained or '无数据'}
"""
        
        # 构建趋势数据
        if recent_data and len(recent_data) > 1:
            sleep_scores = [d.sleep_score for d in recent_data if d.sleep_score]
            steps_list = [d.steps for d in recent_data if d.steps]
            rhr_list = [d.resting_heart_rate for d in recent_data if d.resting_heart_rate]
            
            trend_info = f"""
最近{len(recent_data)}天趋势:
- 平均睡眠分数: {round(sum(sleep_scores)/len(sleep_scores), 1) if sleep_scores else '无数据'}
- 平均步数: {round(sum(steps_list)/len(steps_list)) if steps_list else '无数据'}步
- 平均静息心率: {round(sum(rhr_list)/len(rhr_list), 1) if rhr_list else '无数据'} bpm
"""
        else:
            trend_info = ""
        
        # 规则分析结果摘要
        rule_summary = f"""
规则分析结果:
- 整体状态: {rule_analysis.get('overall_status', '未知')}
- 睡眠状态: {rule_analysis.get('sleep_analysis', {}).get('status', '未知')} - {rule_analysis.get('sleep_analysis', {}).get('quality_assessment', '')}
- 活动状态: {rule_analysis.get('activity_analysis', {}).get('status', '未知')}
- 心率状态: {rule_analysis.get('heart_rate_analysis', {}).get('status', '未知')}
- 恢复状态: {rule_analysis.get('stress_analysis', {}).get('recovery_status', '未知')}

规则分析发现的问题:
{chr(10).join(['- ' + issue for issue in rule_analysis.get('sleep_analysis', {}).get('issues', [])])}
{chr(10).join(['- ' + issue for issue in rule_analysis.get('activity_analysis', {}).get('issues', [])])}
{chr(10).join(['- ' + issue for issue in rule_analysis.get('heart_rate_analysis', {}).get('issues', [])])}
{chr(10).join(['- ' + issue for issue in rule_analysis.get('stress_analysis', {}).get('issues', [])])}
"""
        
        return user_info + yesterday_info + trend_info + rule_summary
    
    def analyze_daily_health(
        self,
        db: Session,
        user_id: int,
        yesterday_data: GarminData,
        recent_data: List[GarminData],
        rule_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        使用大模型分析每日健康数据
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            yesterday_data: 昨日数据
            recent_data: 最近几天的数据
            rule_analysis: 规则分析结果
            
        Returns:
            包含LLM分析结果的字典
        """
        if not self.is_available():
            return {
                "available": False,
                "message": "LLM服务不可用，请配置OpenAI API Key"
            }
        
        try:
            user_context = self._build_user_context(db, user_id)
            health_prompt = self._build_health_data_prompt(
                yesterday_data, recent_data, rule_analysis, user_context
            )
            
            system_prompt = """你是一位专业的健康顾问和运动生理学专家。
你需要基于用户的可穿戴设备数据，提供科学、个性化的健康建议。

分析原则:
1. 结合用户的个人信息（年龄、性别、BMI等）给出针对性建议
2. 关注数据趋势，不仅看单日数据
3. 建议要具体、可执行，避免泛泛而谈
4. 如果发现异常数据，要提醒用户关注
5. 保持积极鼓励的语气，同时客观指出需要改进的地方

请用JSON格式返回分析结果，包含以下字段:
{
    "health_summary": "一段话总结用户当前的健康状况（100字以内）",
    "key_insights": ["关键洞察1", "关键洞察2", "关键洞察3"],
    "sleep_advice": "针对睡眠的具体建议（基于数据分析）",
    "activity_advice": "针对运动活动的具体建议",
    "heart_health_advice": "针对心率/心血管的建议",
    "recovery_advice": "针对恢复和压力管理的建议",
    "today_focus": "今天最应该关注的一件事",
    "today_actions": ["今天要做的具体行动1", "今天要做的具体行动2", "今天要做的具体行动3"],
    "warnings": ["需要注意的健康风险（如果有）"],
    "encouragement": "一句鼓励的话"
}

注意：只返回JSON，不要有其他文字。"""

            user_prompt = f"""请基于以下健康数据，为用户提供今日健康建议：

{health_prompt}

请分析这些数据并给出具体、可执行的建议。"""

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # 使用性价比更高的模型
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=1500
            )
            
            content = response.choices[0].message.content.strip()
            
            # 尝试解析JSON
            # 处理可能的markdown代码块
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            
            llm_result = json.loads(content)
            llm_result["available"] = True
            
            logger.info(f"LLM分析完成，用户ID: {user_id}")
            return llm_result
            
        except json.JSONDecodeError as e:
            logger.error(f"LLM返回结果解析失败: {e}")
            return {
                "available": True,
                "error": "分析结果解析失败",
                "raw_response": content if 'content' in locals() else None
            }
        except Exception as e:
            logger.error(f"LLM分析失败: {e}")
            return {
                "available": False,
                "error": str(e)
            }
    
    def generate_weekly_report(
        self,
        db: Session,
        user_id: int,
        week_data: List[GarminData]
    ) -> Dict[str, Any]:
        """生成周报分析"""
        if not self.is_available():
            return {"available": False, "message": "LLM服务不可用"}
        
        if not week_data:
            return {"available": False, "message": "无周数据"}
        
        try:
            user_context = self._build_user_context(db, user_id)
            
            # 构建周数据摘要
            week_summary = self._build_week_summary(week_data)
            
            system_prompt = """你是一位专业的健康顾问。请基于用户一周的健康数据，生成一份周报分析。

请用JSON格式返回:
{
    "week_summary": "本周健康状况总结（150字以内）",
    "achievements": ["本周做得好的方面"],
    "improvements": ["需要改进的方面"],
    "trends": {
        "sleep": "睡眠趋势描述",
        "activity": "活动趋势描述",
        "heart_health": "心率趋势描述"
    },
    "next_week_goals": ["下周建议目标1", "下周建议目标2", "下周建议目标3"],
    "health_score": 85,  // 0-100的健康评分
    "key_recommendation": "最重要的一条建议"
}"""

            user_prompt = f"""用户信息:
{json.dumps(user_context, ensure_ascii=False, indent=2)}

本周健康数据摘要:
{week_summary}

请分析并生成周报。"""

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            
            result = json.loads(content)
            result["available"] = True
            return result
            
        except Exception as e:
            logger.error(f"周报生成失败: {e}")
            return {"available": False, "error": str(e)}
    
    def _build_week_summary(self, week_data: List[GarminData]) -> str:
        """构建周数据摘要"""
        if not week_data:
            return "无数据"
        
        sleep_scores = [d.sleep_score for d in week_data if d.sleep_score]
        sleep_durations = [d.total_sleep_duration for d in week_data if d.total_sleep_duration]
        steps_list = [d.steps for d in week_data if d.steps]
        rhr_list = [d.resting_heart_rate for d in week_data if d.resting_heart_rate]
        stress_list = [d.stress_level for d in week_data if d.stress_level]
        
        summary = f"""
数据天数: {len(week_data)}天
日期范围: {week_data[-1].record_date if week_data else ''} 至 {week_data[0].record_date if week_data else ''}

睡眠:
- 平均睡眠分数: {round(sum(sleep_scores)/len(sleep_scores), 1) if sleep_scores else '无数据'}
- 最高睡眠分数: {max(sleep_scores) if sleep_scores else '无数据'}
- 最低睡眠分数: {min(sleep_scores) if sleep_scores else '无数据'}
- 平均睡眠时长: {round(sum(sleep_durations)/len(sleep_durations)/60, 1) if sleep_durations else '无数据'}小时

活动:
- 平均步数: {round(sum(steps_list)/len(steps_list)) if steps_list else '无数据'}步
- 总步数: {sum(steps_list) if steps_list else '无数据'}步
- 达标天数(>10000步): {len([s for s in steps_list if s >= 10000]) if steps_list else 0}天

心率:
- 平均静息心率: {round(sum(rhr_list)/len(rhr_list), 1) if rhr_list else '无数据'} bpm
- 最低静息心率: {min(rhr_list) if rhr_list else '无数据'} bpm

压力:
- 平均压力水平: {round(sum(stress_list)/len(stress_list), 1) if stress_list else '无数据'}
"""
        return summary


# 单例实例
llm_analyzer = LLMHealthAnalyzer()

