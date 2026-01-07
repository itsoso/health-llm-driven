"""运动训练AI分析服务"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import json
import logging
from openai import OpenAI

from app.models.daily_health import WorkoutRecord
from app.config import settings

logger = logging.getLogger(__name__)


class WorkoutAnalysisService:
    """运动训练分析服务"""
    
    def __init__(self):
        self.client = None
        if settings.openai_api_key:
            self.client = OpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url
            )
        self.model = settings.openai_model or "gpt-4o-mini"
    
    def _format_duration(self, seconds: int) -> str:
        """格式化时长"""
        if not seconds:
            return "0分钟"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if hours > 0:
            return f"{hours}小时{minutes}分钟"
        return f"{minutes}分钟"
    
    def _format_pace(self, seconds_per_km: int) -> str:
        """格式化配速"""
        if not seconds_per_km:
            return "--:--"
        minutes = seconds_per_km // 60
        secs = seconds_per_km % 60
        return f"{minutes}'{secs:02d}\"/km"
    
    def _get_workout_type_name(self, workout_type: str) -> str:
        """获取运动类型的中文名"""
        type_names = {
            "running": "跑步",
            "cycling": "骑行",
            "swimming": "游泳",
            "hiit": "HIIT训练",
            "cardio": "有氧运动",
            "strength": "力量训练",
            "yoga": "瑜伽",
            "walking": "步行",
            "hiking": "徒步",
            "other": "其他运动"
        }
        return type_names.get(workout_type, workout_type)
    
    def _analyze_heart_rate_zones(self, record: WorkoutRecord) -> str:
        """分析心率区间分布"""
        zones = [
            record.hr_zone_1_seconds or 0,
            record.hr_zone_2_seconds or 0,
            record.hr_zone_3_seconds or 0,
            record.hr_zone_4_seconds or 0,
            record.hr_zone_5_seconds or 0
        ]
        total = sum(zones)
        if total == 0:
            return "无心率区间数据"
        
        zone_names = ["热身区(1区)", "燃脂区(2区)", "有氧区(3区)", "阈值区(4区)", "极限区(5区)"]
        zone_percents = [round(z / total * 100, 1) for z in zones]
        
        # 找出主要区间
        max_zone_idx = zone_percents.index(max(zone_percents))
        
        analysis = f"主要在{zone_names[max_zone_idx]}训练({zone_percents[max_zone_idx]}%)"
        
        # 根据运动类型评估
        if record.workout_type == "running":
            if zone_percents[1] + zone_percents[2] > 70:
                analysis += "，属于轻松有氧跑，适合基础耐力建设"
            elif zone_percents[3] + zone_percents[4] > 50:
                analysis += "，强度较高，注意恢复"
        elif record.workout_type == "hiit":
            if zone_percents[4] + zone_percents[3] > 40:
                analysis += "，HIIT效果良好"
        
        return analysis
    
    def _compare_with_history(
        self,
        current: WorkoutRecord,
        history: List[WorkoutRecord]
    ) -> str:
        """与历史记录对比"""
        if not history:
            return "这是您的第一次此类运动记录，继续保持！"
        
        same_type = [h for h in history if h.workout_type == current.workout_type]
        if not same_type:
            return "这是您第一次记录此类运动"
        
        comparisons = []
        
        # 对比配速（跑步/骑行）
        if current.avg_pace_seconds_per_km:
            avg_paces = [h.avg_pace_seconds_per_km for h in same_type if h.avg_pace_seconds_per_km]
            if avg_paces:
                avg_history_pace = sum(avg_paces) / len(avg_paces)
                diff = current.avg_pace_seconds_per_km - avg_history_pace
                if diff < -10:
                    comparisons.append(f"配速比历史平均快{abs(int(diff))}秒/公里，表现优秀！")
                elif diff > 10:
                    comparisons.append(f"配速比历史平均慢{int(diff)}秒/公里")
        
        # 对比距离
        if current.distance_meters:
            avg_distances = [h.distance_meters for h in same_type if h.distance_meters]
            if avg_distances:
                avg_dist = sum(avg_distances) / len(avg_distances)
                if current.distance_meters > avg_dist * 1.2:
                    comparisons.append(f"距离比平时长{round((current.distance_meters/avg_dist - 1) * 100)}%")
        
        # 对比心率
        if current.avg_heart_rate:
            avg_hrs = [h.avg_heart_rate for h in same_type if h.avg_heart_rate]
            if avg_hrs:
                avg_hr = sum(avg_hrs) / len(avg_hrs)
                if current.avg_heart_rate < avg_hr - 5:
                    comparisons.append("心率控制更好，有氧能力提升")
                elif current.avg_heart_rate > avg_hr + 10:
                    comparisons.append("心率偏高，注意控制强度")
        
        if not comparisons:
            return "表现与历史水平持平"
        
        return "；".join(comparisons)
    
    def _generate_rule_based_analysis(
        self,
        record: WorkoutRecord,
        history: List[WorkoutRecord]
    ) -> Dict[str, Any]:
        """基于规则的分析（不使用LLM）"""
        workout_type_name = self._get_workout_type_name(record.workout_type)
        
        # 整体评级
        overall_rating = "good"
        if record.training_effect_aerobic:
            if record.training_effect_aerobic >= 4:
                overall_rating = "excellent"
            elif record.training_effect_aerobic >= 3:
                overall_rating = "good"
            elif record.training_effect_aerobic >= 2:
                overall_rating = "moderate"
            else:
                overall_rating = "needs_improvement"
        
        # 强度评估
        intensity = "中等强度"
        if record.avg_heart_rate:
            if record.avg_heart_rate > 160:
                intensity = "高强度"
            elif record.avg_heart_rate > 140:
                intensity = "中高强度"
            elif record.avg_heart_rate < 120:
                intensity = "低强度"
        
        # 心率分析
        hr_analysis = None
        if record.avg_heart_rate and record.max_heart_rate:
            hr_analysis = f"平均心率{record.avg_heart_rate}bpm，最高{record.max_heart_rate}bpm"
            if record.max_heart_rate > 180:
                hr_analysis += "，最高心率较高，注意不要过度"
        
        # 配速分析
        pace_analysis = None
        if record.avg_pace_seconds_per_km:
            pace_analysis = f"平均配速{self._format_pace(record.avg_pace_seconds_per_km)}"
            if record.best_pace_seconds_per_km:
                pace_analysis += f"，最佳配速{self._format_pace(record.best_pace_seconds_per_km)}"
        
        # 训练效果
        te_summary = None
        if record.training_effect_aerobic or record.training_effect_anaerobic:
            te_parts = []
            if record.training_effect_aerobic:
                te_parts.append(f"有氧效果{record.training_effect_aerobic}")
            if record.training_effect_anaerobic:
                te_parts.append(f"无氧效果{record.training_effect_anaerobic}")
            te_summary = "，".join(te_parts)
        
        # 恢复建议
        recovery = "建议休息1-2天再进行下次高强度训练"
        if record.training_effect_aerobic:
            if record.training_effect_aerobic >= 4:
                recovery = "高强度训练，建议休息48小时以上"
            elif record.training_effect_aerobic >= 3:
                recovery = "中等强度训练，建议休息24-48小时"
            else:
                recovery = "轻松训练，可以继续日常活动"
        
        # 下次建议
        next_suggestion = "继续保持当前训练节奏"
        if record.workout_type == "running":
            if record.avg_pace_seconds_per_km and record.avg_pace_seconds_per_km > 400:
                next_suggestion = "可以尝试加入一些间歇训练提升配速"
            else:
                next_suggestion = "配速不错，可以尝试增加距离"
        elif record.workout_type == "hiit":
            next_suggestion = "HIIT后建议进行一次轻松有氧恢复"
        
        # 关键洞察
        insights = []
        if record.duration_seconds and record.duration_seconds > 3600:
            insights.append(f"完成了超过1小时的{workout_type_name}，耐力很好！")
        if record.distance_meters and record.distance_meters > 10000:
            insights.append(f"完成了{round(record.distance_meters/1000, 1)}公里，距离不错！")
        if record.calories and record.calories > 500:
            insights.append(f"消耗了{record.calories}卡路里")
        if not insights:
            insights.append(f"完成了{self._format_duration(record.duration_seconds or 0)}的{workout_type_name}")
        
        # 改进建议
        tips = []
        if record.workout_type == "running":
            if not record.avg_cadence or record.avg_cadence < 170:
                tips.append("尝试提高步频到170-180步/分钟，可以减少受伤风险")
            if record.avg_heart_rate and record.avg_heart_rate > 160:
                tips.append("可以尝试更多低心率有氧训练，提升基础耐力")
        if record.workout_type == "strength":
            tips.append("力量训练后注意补充蛋白质促进恢复")
        if not tips:
            tips.append("保持训练规律性，每周3-5次运动效果最佳")
        
        return {
            "overall_rating": overall_rating,
            "intensity_assessment": intensity,
            "heart_rate_analysis": hr_analysis,
            "hr_zone_assessment": self._analyze_heart_rate_zones(record),
            "pace_analysis": pace_analysis,
            "training_effect_summary": te_summary,
            "recovery_recommendation": recovery,
            "next_workout_suggestion": next_suggestion,
            "comparison_with_history": self._compare_with_history(record, history),
            "key_insights": insights,
            "improvement_tips": tips
        }
    
    async def analyze_workout(
        self,
        record: WorkoutRecord,
        history: List[WorkoutRecord]
    ) -> Dict[str, Any]:
        """分析运动记录"""
        # 首先生成基于规则的分析
        rule_analysis = self._generate_rule_based_analysis(record, history)
        
        # 如果LLM可用，用LLM增强分析
        if self.client and settings.openai_api_key:
            try:
                llm_enhanced = await self._enhance_with_llm(record, history, rule_analysis)
                if llm_enhanced:
                    # 合并LLM分析结果
                    rule_analysis.update(llm_enhanced)
            except Exception as e:
                logger.warning(f"LLM分析失败，使用规则分析: {e}")
        
        return rule_analysis
    
    async def _enhance_with_llm(
        self,
        record: WorkoutRecord,
        history: List[WorkoutRecord],
        rule_analysis: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """使用LLM增强分析"""
        workout_type_name = self._get_workout_type_name(record.workout_type)
        
        # 构建提示
        workout_info = f"""
运动类型: {workout_type_name}
日期: {record.workout_date}
时长: {self._format_duration(record.duration_seconds or 0)}
距离: {round(record.distance_meters / 1000, 2) if record.distance_meters else '未记录'}公里
平均心率: {record.avg_heart_rate or '未记录'}bpm
最高心率: {record.max_heart_rate or '未记录'}bpm
平均配速: {self._format_pace(record.avg_pace_seconds_per_km) if record.avg_pace_seconds_per_km else '未记录'}
消耗卡路里: {record.calories or '未记录'}
有氧训练效果: {record.training_effect_aerobic or '未记录'}
无氧训练效果: {record.training_effect_anaerobic or '未记录'}
"""
        
        # 历史对比信息
        history_info = ""
        if history:
            recent = history[:5]
            history_info = f"\n最近{len(recent)}次同类运动记录:\n"
            for h in recent:
                history_info += f"- {h.workout_date}: {self._format_duration(h.duration_seconds or 0)}, "
                if h.distance_meters:
                    history_info += f"{round(h.distance_meters/1000, 2)}km, "
                if h.avg_heart_rate:
                    history_info += f"心率{h.avg_heart_rate}bpm"
                history_info += "\n"
        
        prompt = f"""作为专业的运动教练，请分析以下运动数据并给出专业建议。

{workout_info}
{history_info}

请用简洁的中文回答，提供：
1. 训练强度评估（一句话）
2. 2-3条关键洞察
3. 2-3条具体改进建议
4. 恢复建议
5. 下次训练建议

请直接给出建议，不要重复数据。"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一位专业的运动教练和健康顾问，擅长分析运动数据并给出个性化建议。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=800,
                temperature=0.7
            )
            
            llm_response = response.choices[0].message.content
            
            # 将LLM响应添加到分析结果
            return {
                "ai_enhanced_insights": llm_response
            }
            
        except Exception as e:
            logger.error(f"LLM分析失败: {e}")
            return None

