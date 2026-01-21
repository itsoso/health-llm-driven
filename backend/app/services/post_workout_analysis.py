"""
运动后分析服务
基于张展晖课程，对用户的运动数据进行科学分析和建议
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.user_profile import UserProfile
from app.models.goal import Goal
from app.models.daily_health import WorkoutRecord
from app.services.digital_twin import DigitalTwinService
from app.services.knowledge.rag_pipeline import RAGPipeline
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)


class PostWorkoutAnalysisService:
    """运动后分析服务"""
    
    def __init__(self):
        self.rag_pipeline = RAGPipeline()
    
    def generate_post_workout_analysis(
        self,
        db: Session,
        user_id: int,
        workout_id: int
    ) -> Dict[str, Any]:
        """
        生成运动后分析
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            workout_id: 运动记录ID
        
        Returns:
            运动后分析结果
        """
        try:
            logger.info(f"[运动后分析] 开始为用户 {user_id} 分析运动 {workout_id}")
            
            # 1. 获取运动记录
            workout = db.query(WorkoutRecord).filter_by(
                id=workout_id,
                user_id=user_id
            ).first()
            
            if not workout:
                return {
                    "success": False,
                    "error": "运动记录不存在"
                }
            
            # 2. 获取用户信息
            profile = db.query(UserProfile).filter_by(user_id=user_id).first()
            
            # 3. 计算心率区间（用于对比）
            hr_zones = None
            if profile and profile.age:
                digital_twin = DigitalTwinService(db, user_id)
                hr_zones = digital_twin.calculate_target_heart_rate_zones()
            
            # 4. 分析心率区间分布
            hr_analysis = self._analyze_heart_rate_distribution(workout, hr_zones)
            
            # 5. 评估训练强度
            intensity_assessment = self._assess_training_intensity(workout, hr_zones)
            
            # 6. 从知识库检索相关建议
            knowledge = self._retrieve_post_workout_knowledge(
                workout=workout,
                hr_analysis=hr_analysis,
                intensity_assessment=intensity_assessment
            )
            
            # 7. 生成恢复建议
            recovery_tips = self._generate_recovery_tips(
                workout=workout,
                intensity_assessment=intensity_assessment,
                knowledge=knowledge
            )
            
            # 8. 生成改进建议
            improvement_tips = self._generate_improvement_tips(
                workout=workout,
                hr_analysis=hr_analysis,
                knowledge=knowledge
            )
            
            # 9. 计算与目标的对比
            goal_progress = self._calculate_goal_progress(db, user_id, workout)
            
            analysis = {
                "success": True,
                "workout_summary": self._format_workout_summary(workout),
                "hr_analysis": hr_analysis,
                "intensity_assessment": intensity_assessment,
                "recovery_tips": recovery_tips,
                "improvement_tips": improvement_tips,
                "goal_progress": goal_progress,
                "knowledge_points": knowledge.get("key_points", []),
                "overall_rating": self._calculate_overall_rating(
                    hr_analysis, intensity_assessment
                ),
                "generated_at": get_china_now().isoformat()
            }
            
            logger.info(f"[运动后分析] 分析完成")
            return analysis
            
        except Exception as e:
            logger.error(f"[运动后分析] 分析失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": "生成运动后分析失败，请稍后重试"
            }
    
    def _analyze_heart_rate_distribution(
        self,
        workout: WorkoutRecord,
        hr_zones: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """分析心率区间分布"""
        analysis = {
            "has_hr_data": False,
            "zones": {},
            "distribution_chart": [],
            "recommendations": []
        }
        
        # 检查是否有心率数据
        if not workout.avg_heart_rate or workout.avg_heart_rate == 0:
            analysis["recommendations"].append("建议佩戴心率监测设备，以获取更精准的训练指导")
            return analysis
        
        analysis["has_hr_data"] = True
        analysis["avg_hr"] = workout.avg_heart_rate
        analysis["max_hr"] = workout.max_heart_rate
        
        # 计算各区间时间分布
        total_seconds = workout.duration_seconds or 0
        if total_seconds == 0:
            return analysis
        
        zones_data = {
            "zone1": {
                "name": "恢复区",
                "seconds": workout.hr_zone_1_seconds or 0,
                "percentage": 0
            },
            "zone2": {
                "name": "燃脂区",
                "seconds": workout.hr_zone_2_seconds or 0,
                "percentage": 0
            },
            "zone3": {
                "name": "有氧区",
                "seconds": workout.hr_zone_3_seconds or 0,
                "percentage": 0
            },
            "zone4": {
                "name": "乳酸阈值区",
                "seconds": workout.hr_zone_4_seconds or 0,
                "percentage": 0
            },
            "zone5": {
                "name": "最大心率区",
                "seconds": workout.hr_zone_5_seconds or 0,
                "percentage": 0
            }
        }
        
        # 计算百分比
        for zone_key, zone_data in zones_data.items():
            zone_data["percentage"] = round(
                (zone_data["seconds"] / total_seconds) * 100, 1
            )
        
        analysis["zones"] = zones_data
        
        # 生成分布图数据
        analysis["distribution_chart"] = [
            {"zone": v["name"], "percentage": v["percentage"]}
            for v in zones_data.values()
        ]
        
        # 基于分布给出建议
        zone1_pct = zones_data["zone1"]["percentage"]
        zone2_pct = zones_data["zone2"]["percentage"]
        zone3_pct = zones_data["zone3"]["percentage"]
        zone4_pct = zones_data["zone4"]["percentage"]
        zone5_pct = zones_data["zone5"]["percentage"]
        
        if zone2_pct + zone3_pct > 70:
            analysis["recommendations"].append(
                "✅ 有氧训练分布合理，大部分时间在有氧区间"
            )
        
        if zone4_pct + zone5_pct > 30:
            analysis["recommendations"].append(
                "⚠️ 高强度训练时间较多，注意恢复，避免过度训练"
            )
        elif zone4_pct + zone5_pct < 5:
            analysis["recommendations"].append(
                "💡 可以适当增加高强度间歇训练，提升心肺能力"
            )
        
        if zone1_pct > 40:
            analysis["recommendations"].append(
                "📈 低强度时间较多，可以适当提升训练强度"
            )
        
        return analysis
    
    def _assess_training_intensity(
        self,
        workout: WorkoutRecord,
        hr_zones: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """评估训练强度"""
        assessment = {
            "level": "中等",
            "score": 0,
            "factors": []
        }
        
        score = 0
        
        # 1. 基于平均心率评估
        if workout.avg_heart_rate and hr_zones:
            max_hr = hr_zones.get("max_heart_rate", 180)
            hr_percentage = (workout.avg_heart_rate / max_hr) * 100
            
            if hr_percentage < 60:
                assessment["factors"].append("平均心率较低，强度偏轻")
                score += 2
            elif hr_percentage < 75:
                assessment["factors"].append("平均心率适中，有氧训练")
                score += 5
            elif hr_percentage < 85:
                assessment["factors"].append("平均心率较高，中高强度训练")
                score += 7
            else:
                assessment["factors"].append("平均心率很高，高强度训练")
                score += 9
        
        # 2. 基于时长评估
        duration_min = (workout.duration_seconds or 0) / 60
        if duration_min < 20:
            assessment["factors"].append("训练时长较短")
            score += 1
        elif duration_min < 45:
            assessment["factors"].append("训练时长适中")
            score += 3
        else:
            assessment["factors"].append("训练时长充足")
            score += 4
        
        # 3. 基于卡路里消耗评估
        if workout.calories:
            if workout.calories < 200:
                score += 1
            elif workout.calories < 400:
                score += 3
            else:
                score += 5
        
        # 计算总分并确定强度等级
        assessment["score"] = min(score, 10)
        
        if score < 4:
            assessment["level"] = "轻度"
            assessment["emoji"] = "🟢"
        elif score < 7:
            assessment["level"] = "中等"
            assessment["emoji"] = "🟡"
        else:
            assessment["level"] = "高强度"
            assessment["emoji"] = "🔴"
        
        return assessment
    
    def _retrieve_post_workout_knowledge(
        self,
        workout: WorkoutRecord,
        hr_analysis: Dict[str, Any],
        intensity_assessment: Dict[str, Any]
    ) -> Dict[str, Any]:
        """从知识库检索运动后建议"""
        try:
            if not self.rag_pipeline.is_available():
                return {"key_points": []}
            
            # 构建查询
            query_parts = [f"{workout.workout_type}运动后如何恢复？"]
            
            if intensity_assessment["level"] == "高强度":
                query_parts.append("高强度训练后的恢复策略")
            
            if hr_analysis.get("recommendations"):
                query_parts.append("心率区间训练的科学原理")
            
            query = " ".join(query_parts)
            logger.info(f"[运动后分析] 知识库查询: {query}")
            
            # 检索知识
            knowledge_results = self.rag_pipeline.retrieve_relevant_knowledge(
                query=query,
                category="exercise_science",
                n_results=3
            )
            
            if knowledge_results:
                key_points = []
                for item in knowledge_results:
                    if item.get("content"):
                        key_points.append(item["content"][:150])
                
                return {"key_points": key_points[:3]}
            else:
                return {"key_points": []}
                
        except Exception as e:
            logger.error(f"[运动后分析] 检索知识失败: {e}")
            return {"key_points": []}
    
    def _generate_recovery_tips(
        self,
        workout: WorkoutRecord,
        intensity_assessment: Dict[str, Any],
        knowledge: Dict[str, Any]
    ) -> List[str]:
        """生成恢复建议"""
        tips = []
        
        # 基础恢复建议
        tips.append("💧 运动后 30 分钟内补充水分和电解质")
        tips.append("🍎 30-60 分钟内补充碳水化合物和蛋白质（3:1 比例）")
        
        # 根据强度调整
        if intensity_assessment["level"] == "高强度":
            tips.extend([
                "🛀 温水浴或冷热交替浴促进恢复",
                "😴 确保今晚充足睡眠（8+ 小时）",
                "⏸️ 明天建议安排休息日或轻度活动"
            ])
        elif intensity_assessment["level"] == "中等":
            tips.extend([
                "🧘 进行 10-15 分钟静态拉伸",
                "😴 保证 7-8 小时睡眠",
                "🚶 明天可以进行轻度活动或休息"
            ])
        else:
            tips.extend([
                "🧘 进行 5-10 分钟拉伸放松",
                "✅ 恢复良好，明天可以继续训练"
            ])
        
        # 通用建议
        tips.append("📊 记录今天的感受，为下次训练做参考")
        
        return tips
    
    def _generate_improvement_tips(
        self,
        workout: WorkoutRecord,
        hr_analysis: Dict[str, Any],
        knowledge: Dict[str, Any]
    ) -> List[str]:
        """生成改进建议"""
        tips = []
        
        # 基于心率分析的建议
        if hr_analysis.get("recommendations"):
            tips.extend(hr_analysis["recommendations"][:2])
        
        # 基于运动类型的建议
        workout_type = workout.workout_type.lower() if workout.workout_type else ""
        
        if "running" in workout_type or "跑步" in workout_type:
            tips.append("🏃 80% 的跑步训练应该在轻松配速（能边跑边聊天）")
            tips.append("📈 每周增加训练量不超过 10%（10% 原则）")
        elif "cycling" in workout_type or "骑行" in workout_type:
            tips.append("🚴 注意保持踏频在 80-100 rpm")
        
        # 通用改进建议
        if workout.duration_seconds and workout.duration_seconds < 1800:  # < 30分钟
            tips.append("⏱️ 建议逐步延长训练时间至 30-45 分钟")
        
        return tips[:5]  # 最多5条
    
    def _calculate_goal_progress(
        self,
        db: Session,
        user_id: int,
        workout: WorkoutRecord
    ) -> Optional[Dict[str, Any]]:
        """计算与目标的对比"""
        try:
            # 获取用户的活跃目标
            active_goals = db.query(Goal).filter_by(
                user_id=user_id,
                status="active"
            ).all()
            
            if not active_goals:
                return None
            
            # 简单示例：找到运动相关的目标
            exercise_goal = next(
                (g for g in active_goals if g.goal_type in ["exercise", "weight"]),
                None
            )
            
            if not exercise_goal:
                return None
            
            return {
                "goal_title": exercise_goal.title,
                "target_value": exercise_goal.target_value,
                "target_unit": exercise_goal.target_unit,
                "today_value": workout.duration_seconds / 60 if workout.duration_seconds else 0,
                "message": f"今日完成 {workout.duration_seconds // 60} 分钟运动"
            }
            
        except Exception as e:
            logger.error(f"[运动后分析] 计算目标进度失败: {e}")
            return None
    
    def _format_workout_summary(self, workout: WorkoutRecord) -> Dict[str, Any]:
        """格式化运动摘要"""
        return {
            "id": workout.id,
            "workout_type": workout.workout_type,
            "start_time": workout.start_time.isoformat() if workout.start_time else None,
            "duration": f"{(workout.duration_seconds or 0) // 60} 分钟",
            "distance": f"{workout.distance_meters / 1000:.2f} km" if workout.distance_meters else None,
            "calories": workout.calories,
            "avg_hr": workout.avg_heart_rate,
            "max_hr": workout.max_heart_rate
        }
    
    def _calculate_overall_rating(
        self,
        hr_analysis: Dict[str, Any],
        intensity_assessment: Dict[str, Any]
    ) -> Dict[str, Any]:
        """计算整体评分"""
        score = intensity_assessment.get("score", 5)
        
        # 基于心率分布调整评分
        if hr_analysis.get("has_hr_data"):
            zones = hr_analysis.get("zones", {})
            zone2_pct = zones.get("zone2", {}).get("percentage", 0)
            zone3_pct = zones.get("zone3", {}).get("percentage", 0)
            
            if zone2_pct + zone3_pct > 60:
                score += 1  # 有氧区间分布合理，加分
        
        score = min(score, 10)
        
        if score >= 8:
            rating = "优秀"
            emoji = "🌟"
            message = "训练效果很好，继续保持！"
        elif score >= 6:
            rating = "良好"
            emoji = "👍"
            message = "训练效果不错，可以适当提升强度"
        elif score >= 4:
            rating = "一般"
            emoji = "💪"
            message = "完成训练很棒，下次可以更进一步"
        else:
            rating = "需改进"
            emoji = "📈"
            message = "建议增加训练时长或强度"
        
        return {
            "score": score,
            "rating": rating,
            "emoji": emoji,
            "message": message
        }
