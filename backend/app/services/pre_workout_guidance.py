"""
运动前指导服务
基于用户目标、当前状态和张展晖课程，提供运动前的实时指导
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models.user_profile import UserProfile
from app.models.goal import Goal
from app.models.daily_health import GarminData
from app.services.digital_twin import DigitalTwinService
from app.services.knowledge.rag_pipeline import RAGPipeline
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)


class PreWorkoutGuidanceService:
    """运动前指导服务"""
    
    def __init__(self):
        self.rag_pipeline = RAGPipeline()
    
    def generate_pre_workout_guidance(
        self,
        db: Session,
        user_id: int,
        goal_id: Optional[int] = None,
        workout_type: Optional[str] = None,
        debug: bool = False
    ) -> Dict[str, Any]:
        """
        生成运动前指导
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            goal_id: 目标ID（可选）
            workout_type: 运动类型（可选，如 RUNNING, CARDIO 等）
            debug: 是否返回调试信息（默认False）
        
        Returns:
            运动前指导信息（debug模式下包含决策过程）
        """
        # Debug模式：记录决策过程
        debug_info = {
            "steps": [],
            "data_sources": {},
            "reasoning": []
        } if debug else None
        
        try:
            logger.info(f"[运动前指导] 开始为用户 {user_id} 生成指导 (debug={debug})")
            
            # 1. 获取用户信息
            if debug_info:
                debug_info["steps"].append("1. 获取用户基本信息")
            
            profile = db.query(UserProfile).filter_by(user_id=user_id).first()
            if not profile:
                logger.warning(f"[运动前指导] 用户 {user_id} 没有个人资料")
                if debug_info:
                    debug_info["reasoning"].append("❌ 用户未设置个人资料，使用基础指导模式")
                return self._generate_basic_guidance(workout_type or "EXERCISE")
            
            if debug_info:
                debug_info["data_sources"]["user_profile"] = {
                    "age": profile.age,
                    "gender": profile.gender,
                    "weight": profile.current_weight_kg,
                    "height": profile.height_cm,
                    "exercise_frequency": profile.exercise_frequency
                }
                weight_str = f"{profile.current_weight_kg}kg" if profile.current_weight_kg else "未设置"
                debug_info["reasoning"].append(f"✅ 用户资料：{profile.age}岁，{profile.gender}，体重{weight_str}")
            
            # 2. 获取用户目标
            if debug_info:
                debug_info["steps"].append("2. 获取用户运动目标")
            
            goal = None
            if goal_id:
                goal = db.query(Goal).filter_by(id=goal_id, user_id=user_id).first()
                if debug_info and goal:
                    debug_info["reasoning"].append(f"🎯 使用指定目标：{goal.title}")
            else:
                # 获取最近的活跃目标
                goal = db.query(Goal).filter_by(
                    user_id=user_id,
                    status="active"
                ).order_by(Goal.priority.desc(), Goal.created_at.desc()).first()
                if debug_info:
                    if goal:
                        debug_info["reasoning"].append(f"🎯 自动选择活跃目标：{goal.title}")
                    else:
                        debug_info["reasoning"].append("⚠️ 用户暂无活跃目标")
            
            if debug_info and goal:
                debug_info["data_sources"]["goal"] = {
                    "title": goal.title,
                    "description": goal.description,
                    "goal_type": goal.goal_type,
                    "target_value": goal.target_value,
                    "target_unit": goal.target_unit
                }
            
            # 3. 获取最近的健康数据
            if debug_info:
                debug_info["steps"].append("3. 获取最近7天Garmin健康数据")
            
            recent_data = self._get_recent_health_data(db, user_id)
            
            if debug_info:
                debug_info["data_sources"]["recent_health"] = recent_data
                if recent_data:
                    health_summary = []
                    if recent_data.get("sleep_score"):
                        health_summary.append(f"睡眠评分{recent_data['sleep_score']}")
                    if recent_data.get("resting_hr"):
                        health_summary.append(f"静息心率{recent_data['resting_hr']}bpm")
                    if recent_data.get("hrv"):
                        health_summary.append(f"HRV {recent_data['hrv']}ms")
                    if recent_data.get("body_battery"):
                        health_summary.append(f"身体电量{recent_data['body_battery']}")
                    debug_info["reasoning"].append(f"📊 最近健康状态：{', '.join(health_summary)}")
                else:
                    debug_info["reasoning"].append("⚠️ 未获取到最近的健康数据")
            
            # 4. 计算心率区间
            if debug_info:
                debug_info["steps"].append("4. 计算个性化心率区间")
            
            hr_zones = None
            if profile.age:
                digital_twin = DigitalTwinService(db, user_id)
                hr_zones = digital_twin.calculate_target_heart_rate_zones()
                logger.info(f"[运动前指导] 心率区间: {hr_zones}")
                
                if debug_info and hr_zones:
                    debug_info["data_sources"]["heart_rate_zones"] = hr_zones
                    debug_info["reasoning"].append(
                        f"💓 基于年龄{profile.age}岁和静息心率{hr_zones.get('resting_heart_rate', 'N/A')}bpm计算5个心率区间"
                    )
                    debug_info["reasoning"].append(
                        f"   - 最大心率: {hr_zones.get('max_heart_rate')}bpm"
                    )
                    zone2 = hr_zones.get('zone2_fat_burn', [])
                    if zone2:
                        debug_info["reasoning"].append(
                            f"   - 建议训练区间(Zone 2): {zone2[0]}-{zone2[1]}bpm"
                        )
            elif debug_info:
                debug_info["reasoning"].append("⚠️ 用户未设置年龄，无法计算心率区间")
            
            # 5. 确定运动类型
            if debug_info:
                debug_info["steps"].append("5. 确定运动类型")
            
            if not workout_type and goal:
                workout_type = self._infer_workout_type_from_goal(goal)
                if debug_info:
                    debug_info["reasoning"].append(f"🏃 根据目标推断运动类型：{workout_type}")
            workout_type = workout_type or "EXERCISE"
            
            if debug_info and not goal:
                debug_info["reasoning"].append(f"🏃 使用默认运动类型：{workout_type}")
            
            # 6. 从知识库检索运动前建议
            if debug_info:
                debug_info["steps"].append("6. 从张展晖课程知识库检索相关建议")
            
            knowledge = self._retrieve_pre_workout_knowledge(
                workout_type=workout_type,
                goal_description=goal.description if goal else "",
                recent_data=recent_data,
                debug_info=debug_info
            )
            
            # 7. 生成指导内容
            if debug_info:
                debug_info["steps"].append("7. 生成个性化运动指导")
            
            guidance = {
                "success": True,
                "workout_type": workout_type,
                "goal_info": self._format_goal_info(goal) if goal else None,
                "user_status": self._format_user_status(recent_data),
                "training_objective": self._generate_training_objective(goal, workout_type, recent_data),
                "heart_rate_zones": hr_zones,
                "warm_up": self._generate_warm_up_tips(workout_type, knowledge),
                "key_reminders": self._generate_key_reminders(workout_type, hr_zones, recent_data),
                "course_insights": knowledge.get("key_points", []),
                "generated_at": get_china_now().isoformat()
            }
            
            # 添加debug信息
            if debug_info:
                debug_info["reasoning"].append("✅ 生成完成，包含以下内容：")
                debug_info["reasoning"].append(f"   - 热身建议：{len(guidance['warm_up'])}条")
                debug_info["reasoning"].append(f"   - 关键提醒：{len(guidance['key_reminders'])}条")
                debug_info["reasoning"].append(f"   - 课程要点：{len(guidance['course_insights'])}条")
                
                guidance["debug"] = debug_info
            
            logger.info(f"[运动前指导] 生成完成 (debug={debug})")
            return guidance
            
        except Exception as e:
            logger.error(f"[运动前指导] 生成失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": "生成运动前指导失败，请稍后重试"
            }
    
    def _get_recent_health_data(self, db: Session, user_id: int) -> Dict[str, Any]:
        """获取最近的健康数据"""
        try:
            # 获取最近7天的数据
            end_date = get_china_now().date()
            start_date = end_date - timedelta(days=7)
            
            recent_records = db.query(GarminData).filter(
                GarminData.user_id == user_id,
                GarminData.record_date >= start_date,
                GarminData.record_date <= end_date
            ).order_by(GarminData.record_date.desc()).all()
            
            if not recent_records:
                return {}
            
            latest = recent_records[0]
            
            # 将睡眠时长从分钟转换为小时
            sleep_hours = None
            if latest.total_sleep_duration:
                sleep_hours = round(latest.total_sleep_duration / 60, 1)
            
            return {
                "sleep_score": latest.sleep_score,
                "sleep_hours": sleep_hours,
                "stress_level": latest.stress_level,
                "resting_hr": latest.resting_heart_rate,
                "hrv": latest.hrv,
                "body_battery": latest.body_battery_most_charged,  # 使用最高充电值
                "recent_activity": len([r for r in recent_records if r.steps and r.steps > 5000])
            }
        except Exception as e:
            logger.error(f"[运动前指导] 获取健康数据失败: {e}")
            return {}
    
    def _infer_workout_type_from_goal(self, goal: Goal) -> str:
        """从目标推断运动类型"""
        goal_type = goal.goal_type.lower()
        title = goal.title.lower()
        description = (goal.description or "").lower()
        
        # 关键词映射
        if any(kw in title + description for kw in ["跑步", "跑", "running"]):
            return "RUNNING"
        elif any(kw in title + description for kw in ["心肺", "有氧", "cardio"]):
            return "CARDIO"
        elif any(kw in title + description for kw in ["减肥", "减脂", "weight loss"]):
            return "WEIGHT_LOSS"
        elif any(kw in title + description for kw in ["力量", "增肌", "strength"]):
            return "MUSCLE_GAIN"
        elif goal_type == "exercise":
            return "EXERCISE"
        else:
            return "EXERCISE"
    
    def _retrieve_pre_workout_knowledge(
        self,
        workout_type: str,
        goal_description: str,
        recent_data: Dict[str, Any],
        debug_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """从知识库检索运动前建议"""
        try:
            if not self.rag_pipeline.is_available():
                if debug_info:
                    debug_info["reasoning"].append("⚠️ 知识库不可用，跳过检索")
                return {"key_points": []}
            
            # 构建查询
            query_parts = [f"进行{workout_type}训练前需要注意什么？"]
            
            if goal_description:
                query_parts.append(goal_description)
            
            if recent_data.get("sleep_score") and recent_data["sleep_score"] < 70:
                query_parts.append("睡眠不足时如何调整训练？")
            
            if recent_data.get("stress_level") and recent_data["stress_level"] > 50:
                query_parts.append("压力较大时如何训练？")
            
            query = " ".join(query_parts)
            logger.info(f"[运动前指导] 知识库查询: {query}")
            
            if debug_info:
                debug_info["data_sources"]["knowledge_query"] = query
                debug_info["reasoning"].append(f"📚 知识库查询：{query}")
            
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
                
                if debug_info:
                    debug_info["data_sources"]["knowledge_results"] = [
                        {
                            "content": item.get("content", "")[:100] + "...",
                            "source": item.get("source", "unknown"),
                            "score": item.get("score", 0)
                        }
                        for item in knowledge_results[:3]
                    ]
                    debug_info["reasoning"].append(f"📖 从知识库检索到{len(knowledge_results)}条相关内容")
                
                return {"key_points": key_points[:3]}
            else:
                if debug_info:
                    debug_info["reasoning"].append("⚠️ 知识库未找到相关内容")
                return {"key_points": []}
                
        except Exception as e:
            logger.error(f"[运动前指导] 检索知识失败: {e}")
            if debug_info:
                debug_info["reasoning"].append(f"❌ 知识库检索失败：{str(e)}")
            return {"key_points": []}
    
    def _format_goal_info(self, goal: Goal) -> Dict[str, Any]:
        """格式化目标信息"""
        return {
            "id": goal.id,
            "title": goal.title,
            "description": goal.description,
            "goal_type": goal.goal_type,
            "target_value": goal.target_value,
            "target_unit": goal.target_unit
        }
    
    def _generate_today_target(
        self,
        goal: Optional[Goal],
        workout_type: str,
        hr_zones: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """生成今日训练目标"""
        target = {
            "workout_type": workout_type,
            "duration": "30-45 分钟",
            "intensity": "中等强度"
        }
        
        if goal and goal.target_value:
            target["goal_value"] = f"{goal.target_value} {goal.target_unit or ''}"
        
        if hr_zones:
            zone2 = hr_zones.get("zone2_fat_burn", (120, 140))
            target["recommended_hr_range"] = f"{zone2[0]}-{zone2[1]} bpm"
            target["hr_zone_name"] = "有氧燃脂区间"
        
        # 根据运动类型调整
        if workout_type == "RUNNING":
            target["duration"] = "30-60 分钟"
            target["intensity"] = "轻松跑为主"
        elif workout_type == "WEIGHT_LOSS":
            target["duration"] = "45-60 分钟"
            target["intensity"] = "低-中等强度有氧"
        elif workout_type == "CARDIO":
            target["duration"] = "30-45 分钟"
            target["intensity"] = "中等强度心肺训练"
        
        return target
    
    def _generate_warm_up_tips(
        self,
        workout_type: str,
        knowledge: Dict[str, Any]
    ) -> List[str]:
        """生成热身建议"""
        base_tips = [
            "动态拉伸 5-10 分钟，激活肌肉",
            "从低强度开始，逐渐提升心率",
            "关节活动：颈部、肩部、腰部、膝盖、脚踝"
        ]
        
        type_specific = {
            "RUNNING": ["慢跑 5 分钟热身", "高抬腿、后踢腿各 20 次"],
            "CARDIO": ["原地踏步 3 分钟", "开合跳 20 次 × 2 组"],
            "WEIGHT_LOSS": ["快走 5 分钟", "全身动态拉伸"],
            "MUSCLE_GAIN": ["空杠铃动作练习", "目标肌群激活"]
        }
        
        tips = base_tips.copy()
        if workout_type in type_specific:
            tips.extend(type_specific[workout_type])
        
        return tips
    
    def _generate_key_reminders(
        self,
        workout_type: str,
        hr_zones: Optional[Dict[str, Any]],
        recent_data: Dict[str, Any]
    ) -> List[str]:
        """生成关键提醒"""
        reminders = []
        
        # 心率提醒
        if hr_zones:
            zone2 = hr_zones.get("zone2_fat_burn", (120, 140))
            reminders.append(f"💓 保持心率在 {zone2[0]}-{zone2[1]} bpm（有氧区间）")
        
        # 根据睡眠状态提醒
        if recent_data.get("sleep_score"):
            if recent_data["sleep_score"] < 70:
                reminders.append("😴 昨晚睡眠不足，建议降低训练强度 20-30%")
            elif recent_data["sleep_score"] > 85:
                reminders.append("✨ 睡眠充足，状态良好，可以正常训练")
        
        # 根据压力水平提醒
        if recent_data.get("stress_level"):
            if recent_data["stress_level"] > 60:
                reminders.append("😌 压力较大，避免高强度训练，以恢复为主")
        
        # 通用提醒
        reminders.extend([
            "💧 运动前 30 分钟补充 200-300ml 水",
            "🎯 循序渐进，避免运动损伤",
            "⏱️ 运动中每 15-20 分钟补水一次"
        ])
        
        return reminders
    
    def _format_user_status(self, recent_data: Dict[str, Any]) -> Dict[str, Any]:
        """格式化用户状态（扁平结构，供前端使用）"""
        # 评估准备度
        readiness = "良好"
        if recent_data.get("sleep_score") and recent_data["sleep_score"] < 60:
            readiness = "需要休息"
        elif recent_data.get("stress_level") and recent_data["stress_level"] > 70:
            readiness = "压力较大，建议轻度运动"
        elif recent_data.get("body_battery") and recent_data["body_battery"] < 30:
            readiness = "能量不足，建议休息"
        
        return {
            "body_battery": recent_data.get("body_battery"),
            "hrv": recent_data.get("hrv"),
            "sleep_score": recent_data.get("sleep_score"),
            "stress_level": recent_data.get("stress_level"),
            "readiness": readiness
        }
    
    def _generate_training_objective(
        self, 
        goal: Optional[Goal], 
        workout_type: str, 
        recent_data: Dict[str, Any]
    ) -> str:
        """生成训练目标描述"""
        if goal and goal.description:
            return f"今日目标：{goal.description}。建议进行{workout_type}训练，保持在目标心率区间。"
        else:
            return f"今日建议进行{workout_type}训练，保持适当强度，注意心率控制。"
    
    def _generate_basic_guidance(self, workout_type: str) -> Dict[str, Any]:
        """生成基础指导（用户数据不足时）"""
        return {
            "success": True,
            "workout_type": workout_type,
            "today_target": {
                "duration": "30-45 分钟",
                "intensity": "中等强度"
            },
            "warm_up_tips": self._generate_warm_up_tips(workout_type, {}),
            "key_reminders": [
                "💓 注意监测心率，避免过度训练",
                "💧 运动前后及时补水",
                "🎯 循序渐进，避免运动损伤"
            ],
            "message": "建议完善个人资料以获取更精准的指导",
            "generated_at": get_china_now().isoformat()
        }
