"""
运动前指导服务
基于用户目标、当前状态和张展晖课程，提供运动前的实时指导
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import time

from app.models.user_profile import UserProfile
from app.models.goal import Goal
from app.models.daily_health import GarminData
from app.services.digital_twin import DigitalTwinService
from app.services.knowledge.rag_pipeline import RAGPipeline
from app.services.environment.environment_advisor import environment_advisor
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)


class PreWorkoutGuidanceService:
    """运动前指导服务"""
    
    def __init__(self):
        self.rag_pipeline = RAGPipeline()
    
    def _init_debug_info(self) -> Dict[str, Any]:
        """初始化 debug 信息结构"""
        return {
            "steps": [],
            "data_sources": {},
            "reasoning": [],
            "performance": {},
            "timeline": []
        }
    
    def _add_debug_step(self, debug_info: Optional[Dict[str, Any]], step_name: str, start_time: float = None):
        """添加决策步骤"""
        if debug_info:
            step_num = len(debug_info["steps"]) + 1
            debug_info["steps"].append(f"{step_num}. {step_name}")
            if start_time:
                elapsed = (time.time() - start_time) * 1000
                debug_info["performance"][step_name] = f"{elapsed:.2f}ms"
                debug_info["timeline"].append({
                    "step": step_name,
                    "timestamp": time.time(),
                    "duration_ms": elapsed
                })
    
    def _add_debug_reasoning(self, debug_info: Optional[Dict[str, Any]], message: str, level: str = "info"):
        """添加推理过程"""
        if debug_info:
            icons = {
                "info": "ℹ️",
                "success": "✅",
                "warning": "⚠️",
                "error": "❌",
                "goal": "🎯",
                "data": "📊",
                "heart": "💓",
                "workout": "🏃",
                "knowledge": "📚"
            }
            icon = icons.get(level, "•")
            debug_info["reasoning"].append(f"{icon} {message}")
    
    def _add_debug_data(self, debug_info: Optional[Dict[str, Any]], key: str, value: Any):
        """添加数据来源"""
        if debug_info:
            debug_info["data_sources"][key] = value
    
    async def generate_pre_workout_guidance(
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
        overall_start = time.time()
        debug_info = self._init_debug_info() if debug else None
        
        try:
            logger.info(f"[运动前指导] 开始为用户 {user_id} 生成指导 (debug={debug})")
            
            # 1. 获取用户信息
            step_start = time.time()
            self._add_debug_step(debug_info, "获取用户基本信息", step_start)
            
            profile = db.query(UserProfile).filter_by(user_id=user_id).first()
            if not profile:
                logger.warning(f"[运动前指导] 用户 {user_id} 没有个人资料")
                self._add_debug_reasoning(debug_info, "用户未设置个人资料，使用基础指导模式", "error")
                return self._generate_basic_guidance(workout_type or "EXERCISE", debug_info)
            
            # 收集用户资料数据
            user_profile_data = {
                "age": profile.age,
                "gender": profile.gender,
                "weight_kg": profile.current_weight_kg,
                "height_cm": profile.height_cm,
                "exercise_frequency": profile.exercise_frequency,
                "bmi": profile.bmi
            }
            self._add_debug_data(debug_info, "user_profile", user_profile_data)
            
            # 格式化用户信息展示
            profile_parts = []
            if profile.age:
                profile_parts.append(f"{profile.age}岁")
            if profile.gender:
                profile_parts.append(profile.gender)
            if profile.current_weight_kg:
                profile_parts.append(f"体重{profile.current_weight_kg}kg")
            if profile.height_cm:
                profile_parts.append(f"身高{profile.height_cm}cm")
            if profile.bmi:
                profile_parts.append(f"BMI {profile.bmi}")
            
            self._add_debug_reasoning(debug_info, f"用户资料：{', '.join(profile_parts) if profile_parts else '基本信息不完整'}", "success")
            
            # 2. 获取用户目标
            step_start = time.time()
            self._add_debug_step(debug_info, "获取用户运动目标", step_start)
            
            goal = None
            if goal_id:
                goal = db.query(Goal).filter_by(id=goal_id, user_id=user_id).first()
                if goal:
                    self._add_debug_reasoning(debug_info, f"使用指定目标：{goal.title}", "goal")
            else:
                # 获取最近的活跃目标
                goal = db.query(Goal).filter_by(
                    user_id=user_id,
                    status="active"
                ).order_by(Goal.priority.desc(), Goal.created_at.desc()).first()
                if goal:
                    self._add_debug_reasoning(debug_info, f"自动选择活跃目标：{goal.title}", "goal")
                else:
                    self._add_debug_reasoning(debug_info, "用户暂无活跃目标", "warning")
            
            if goal:
                goal_data = {
                    "id": goal.id,
                    "title": goal.title,
                    "description": goal.description,
                    "goal_type": goal.goal_type,
                    "target_value": goal.target_value,
                    "target_unit": goal.target_unit,
                    "priority": goal.priority
                }
                self._add_debug_data(debug_info, "goal", goal_data)
            
            # 3. 获取最近的健康数据
            step_start = time.time()
            self._add_debug_step(debug_info, "获取最近7天Garmin健康数据", step_start)
            
            recent_data = self._get_recent_health_data(db, user_id)
            self._add_debug_data(debug_info, "recent_health", recent_data)
            
            if recent_data:
                health_summary = []
                if recent_data.get("sleep_score"):
                    health_summary.append(f"睡眠评分{recent_data['sleep_score']}")
                if recent_data.get("sleep_hours"):
                    health_summary.append(f"睡眠{recent_data['sleep_hours']}小时")
                if recent_data.get("resting_hr"):
                    health_summary.append(f"静息心率{recent_data['resting_hr']}bpm")
                if recent_data.get("hrv"):
                    health_summary.append(f"HRV {recent_data['hrv']}ms")
                if recent_data.get("body_battery"):
                    health_summary.append(f"身体电量{recent_data['body_battery']}")
                if recent_data.get("stress_level"):
                    health_summary.append(f"压力{recent_data['stress_level']}")
                
                self._add_debug_reasoning(debug_info, f"最近健康状态：{', '.join(health_summary)}", "data")
            else:
                self._add_debug_reasoning(debug_info, "未获取到最近的健康数据", "warning")
            
            # 4. 计算心率区间
            step_start = time.time()
            self._add_debug_step(debug_info, "计算个性化心率区间", step_start)
            
            hr_zones = None
            if profile.age:
                digital_twin = DigitalTwinService(db, user_id)
                hr_zones = digital_twin.calculate_target_heart_rate_zones()
                logger.info(f"[运动前指导] 心率区间: {hr_zones}")
                
                if hr_zones:
                    self._add_debug_data(debug_info, "heart_rate_zones", hr_zones)
                    
                    resting_hr = hr_zones.get('resting_heart_rate', 'N/A')
                    max_hr = hr_zones.get('max_heart_rate', 'N/A')
                    self._add_debug_reasoning(
                        debug_info,
                        f"基于年龄{profile.age}岁和静息心率{resting_hr}bpm计算5个心率区间",
                        "heart"
                    )
                    self._add_debug_reasoning(debug_info, f"最大心率: {max_hr}bpm", "info")
                    
                    zone2 = hr_zones.get('zone2_fat_burn', [])
                    if zone2:
                        self._add_debug_reasoning(
                            debug_info,
                            f"建议训练区间(Zone 2 有氧燃脂): {zone2[0]}-{zone2[1]}bpm",
                            "heart"
                        )
            else:
                self._add_debug_reasoning(debug_info, "用户未设置年龄，无法计算心率区间", "warning")
            
            # 5. 获取环境因素（天气和空气质量）
            step_start = time.time()
            self._add_debug_step(debug_info, "检测环境因素（天气和空气质量）", step_start)
            
            environment_data = None
            environment_warnings = []
            try:
                # 获取用户城市（从 profile 或默认杭州）
                user_city = profile.city if hasattr(profile, 'city') and profile.city else "杭州"
                
                # 获取用户慢性病列表
                chronic_conditions = profile.chronic_conditions if profile.chronic_conditions else []
                
                # 获取综合环境建议
                environment_data = await environment_advisor.get_comprehensive_advice(
                    city=user_city,
                    user_conditions=chronic_conditions
                )
                
                self._add_debug_data(debug_info, "environment", {
                    "city": user_city,
                    "weather": environment_data.get("weather", {}),
                    "air_quality": environment_data.get("air_quality", {}),
                    "outdoor_suitable": environment_data.get("exercise", {}).get("outdoor_suitable"),
                    "score": environment_data.get("exercise", {}).get("score")
                })
                
                # 分析环境因素
                weather = environment_data.get("weather", {})
                aqi = environment_data.get("air_quality", {})
                exercise_info = environment_data.get("exercise", {})
                
                # 天气摘要
                if weather.get("available"):
                    temp = weather.get("temperature")
                    weather_desc = weather.get("weather")
                    self._add_debug_reasoning(
                        debug_info,
                        f"当前天气：{weather_desc}，{temp}°C",
                        "info"
                    )
                
                # 空气质量
                if aqi.get("available"):
                    aqi_val = aqi.get("aqi")
                    aqi_desc = aqi.get("description")
                    aqi_level = aqi.get("level")
                    
                    self._add_debug_reasoning(
                        debug_info,
                        f"空气质量：{aqi_desc}（AQI {aqi_val}）",
                        "success" if aqi_level in ["excellent", "good"] else "warning"
                    )
                    
                    # AQI 警告
                    if aqi_val > 150:
                        environment_warnings.append(f"⚠️ 空气质量{aqi_desc}（AQI {aqi_val}），强烈建议室内运动")
                        self._add_debug_reasoning(debug_info, "空气质量差，不适合户外运动", "warning")
                    elif aqi_val > 100:
                        environment_warnings.append(f"⚠️ 空气质量{aqi_desc}（AQI {aqi_val}），建议减少户外运动时间")
                        self._add_debug_reasoning(debug_info, "空气质量一般，建议缩短户外运动时间", "warning")
                
                # 户外运动适宜性
                outdoor_suitable = exercise_info.get("outdoor_suitable", True)
                outdoor_score = exercise_info.get("score", 100)
                
                if not outdoor_suitable:
                    self._add_debug_reasoning(
                        debug_info,
                        f"户外运动适宜度：{outdoor_score}/100（不推荐户外）",
                        "warning"
                    )
                else:
                    self._add_debug_reasoning(
                        debug_info,
                        f"户外运动适宜度：{outdoor_score}/100（适合户外）",
                        "success"
                    )
                
                # 添加环境相关的警告
                env_warnings = environment_data.get("warnings", [])
                if env_warnings:
                    environment_warnings.extend(env_warnings)
                    for warning in env_warnings:
                        self._add_debug_reasoning(debug_info, warning, "warning")
                
            except Exception as e:
                logger.error(f"[运动前指导] 获取环境数据失败: {e}", exc_info=True)
                self._add_debug_reasoning(debug_info, f"环境数据获取失败：{str(e)}", "warning")
            
            # 6. 确定运动类型
            step_start = time.time()
            self._add_debug_step(debug_info, "确定运动类型", step_start)
            
            if not workout_type and goal:
                workout_type = self._infer_workout_type_from_goal(goal)
                self._add_debug_reasoning(debug_info, f"根据目标推断运动类型：{workout_type}", "workout")
            workout_type = workout_type or "EXERCISE"
            
            if not goal:
                self._add_debug_reasoning(debug_info, f"使用默认运动类型：{workout_type}", "info")
            
            # 7. 从知识库检索运动前建议
            step_start = time.time()
            self._add_debug_step(debug_info, "从张展晖课程知识库检索相关建议", step_start)
            
            knowledge = self._retrieve_pre_workout_knowledge(
                workout_type=workout_type,
                goal_description=goal.description if goal else "",
                recent_data=recent_data,
                debug_info=debug_info
            )
            
            # 8. 生成指导内容
            step_start = time.time()
            self._add_debug_step(debug_info, "生成个性化运动指导", step_start)
            
            # 生成关键提醒（包含环境因素）
            key_reminders = self._generate_key_reminders(workout_type, hr_zones, recent_data, environment_warnings)
            
            guidance = {
                "success": True,
                "workout_type": workout_type,
                "goal_info": self._format_goal_info(goal) if goal else None,
                "user_status": self._format_user_status(recent_data),
                "training_objective": self._generate_training_objective(goal, workout_type, recent_data),
                "heart_rate_zones": hr_zones,
                "environment": self._format_environment_info(environment_data) if environment_data else None,
                "warm_up": self._generate_warm_up_tips(workout_type, knowledge),
                "key_reminders": key_reminders,
                "course_insights": knowledge.get("key_points", []),
                "generated_at": get_china_now().isoformat()
            }
            
            # 添加debug信息
            if debug_info:
                total_time = (time.time() - overall_start) * 1000
                debug_info["performance"]["total_time_ms"] = f"{total_time:.2f}ms"
                debug_info["performance"]["total_time_s"] = f"{total_time/1000:.2f}s"
                
                self._add_debug_reasoning(debug_info, "生成完成，包含以下内容：", "success")
                self._add_debug_reasoning(debug_info, f"热身建议：{len(guidance['warm_up'])}条", "info")
                self._add_debug_reasoning(debug_info, f"关键提醒：{len(guidance['key_reminders'])}条", "info")
                self._add_debug_reasoning(debug_info, f"课程要点：{len(guidance['course_insights'])}条", "info")
                self._add_debug_reasoning(debug_info, f"总耗时：{total_time:.2f}ms", "info")
                
                guidance["debug"] = debug_info
            
            logger.info(f"[运动前指导] 生成完成 (debug={debug})")
            return guidance
            
        except Exception as e:
            logger.error(f"[运动前指导] 生成失败: {e}", exc_info=True)
            if debug_info:
                self._add_debug_reasoning(debug_info, f"生成失败：{str(e)}", "error")
                debug_info["error"] = str(e)
                debug_info["error_type"] = type(e).__name__
            return {
                "success": False,
                "error": str(e),
                "message": "生成运动前指导失败，请稍后重试",
                "debug": debug_info if debug else None
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
                "body_battery": latest.body_battery_most_charged,
                "recent_activity": len([r for r in recent_records if r.steps and r.steps > 5000]),
                "data_points_count": len(recent_records),
                "latest_date": str(latest.record_date) if latest.record_date else None
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
                self._add_debug_reasoning(debug_info, "知识库不可用，跳过检索", "warning")
                return {"key_points": []}
            
            # 优化查询策略：多个独立查询，提高召回率
            queries = []
            
            # 1. 运动类型相关查询（简化关键词）
            workout_keywords = {
                "RUNNING": ["跑步", "慢跑", "有氧跑", "MAF训练"],
                "CARDIO": ["心肺训练", "有氧运动", "心率训练"],
                "WEIGHT_LOSS": ["减脂", "燃脂", "有氧运动"],
                "MUSCLE_GAIN": ["力量训练", "增肌", "抗阻训练"],
                "EXERCISE": ["运动", "训练", "锻炼"]
            }
            
            keywords = workout_keywords.get(workout_type, ["运动"])
            for keyword in keywords[:2]:  # 取前2个关键词
                queries.append({
                    "query": f"{keyword}训练方法",
                    "category": None,  # 不限制分类，知识库中分类不统一
                    "n_results": 3
                })
                queries.append({
                    "query": f"{keyword}注意事项",
                    "category": None,
                    "n_results": 2
                })
            
            # 2. 根据健康状态添加查询
            if recent_data.get("sleep_score") and recent_data["sleep_score"] < 70:
                queries.append({
                    "query": "睡眠不足运动建议",
                    "category": None,
                    "n_results": 2
                })
            
            if recent_data.get("stress_level") and recent_data["stress_level"] > 50:
                queries.append({
                    "query": "压力大如何运动",
                    "category": None,
                    "n_results": 2
                })
            
            # 3. 心率相关查询
            queries.append({
                "query": "心率区间训练",
                "category": None,
                "n_results": 2
            })
            
            # 4. 热身相关查询
            queries.append({
                "query": "运动前热身",
                "category": None,
                "n_results": 2
            })
            
            self._add_debug_reasoning(debug_info, f"准备执行 {len(queries)} 个知识库查询", "knowledge")
            
            # 执行所有查询并合并结果
            all_results = []
            seen_content = set()  # 去重
            
            for q in queries:
                logger.info(f"[运动前指导] 知识库查询: {q['query']} (category={q.get('category')})")
                
                results = self.rag_pipeline.retrieve_relevant_knowledge(
                    query=q["query"],
                    category=q.get("category"),
                    n_results=q["n_results"]
                )
                
                for item in results:
                    content = item.get("content", "")[:200]  # 取前200字符作为去重标识
                    if content and content not in seen_content:
                        seen_content.add(content)
                        all_results.append(item)
                
                if results:
                    self._add_debug_reasoning(
                        debug_info,
                        f"查询 \"{q['query']}\" 找到 {len(results)} 条结果",
                        "info"
                    )
            
            if all_results:
                # 按相关度排序，取前5个
                all_results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
                top_results = all_results[:5]
                
                key_points = []
                knowledge_data = []
                for item in top_results:
                    if item.get("content"):
                        content = item["content"][:150]
                        key_points.append(content)
                        knowledge_data.append({
                            "content": content + "...",
                            "source": item.get("metadata", {}).get("source", "unknown"),
                            "title": item.get("metadata", {}).get("title", ""),
                            "relevance_score": round(item.get("relevance_score", 0), 3)
                        })
                
                self._add_debug_data(debug_info, "knowledge_queries", [q["query"] for q in queries])
                self._add_debug_data(debug_info, "knowledge_results", knowledge_data)
                self._add_debug_reasoning(
                    debug_info,
                    f"从知识库检索到 {len(all_results)} 条结果，使用前 {len(top_results)} 条",
                    "success"
                )
                
                return {"key_points": key_points[:3]}  # 最终返回前3条
            else:
                self._add_debug_reasoning(debug_info, "所有查询均未找到相关内容", "warning")
                self._add_debug_reasoning(debug_info, "可能原因：1) 知识库内容不足 2) 查询关键词不匹配 3) 相关度阈值过高", "info")
                return {"key_points": []}
                
        except Exception as e:
            logger.error(f"[运动前指导] 检索知识失败: {e}", exc_info=True)
            self._add_debug_reasoning(debug_info, f"知识库检索失败：{str(e)}", "error")
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
        recent_data: Dict[str, Any],
        environment_warnings: List[str] = None
    ) -> List[str]:
        """生成关键提醒（包含环境因素）"""
        reminders = []
        
        # 环境因素警告（优先显示）
        if environment_warnings:
            reminders.extend(environment_warnings[:2])  # 最多显示2条环境警告
        
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
    
    def _format_environment_info(self, environment_data: Dict[str, Any]) -> Dict[str, Any]:
        """格式化环境信息"""
        if not environment_data:
            return None
        
        weather = environment_data.get("weather", {})
        aqi = environment_data.get("air_quality", {})
        exercise = environment_data.get("exercise", {})
        
        return {
            "weather": {
                "temperature": weather.get("temperature"),
                "feels_like": weather.get("feels_like"),
                "humidity": weather.get("humidity"),
                "description": weather.get("weather"),
                "summary": weather.get("summary")
            },
            "air_quality": {
                "aqi": aqi.get("aqi"),
                "level": aqi.get("level"),
                "description": aqi.get("description"),
                "pm25": aqi.get("pm25")
            },
            "outdoor_suitable": exercise.get("outdoor_suitable"),
            "outdoor_score": exercise.get("score"),
            "status": exercise.get("status"),
            "recommended_activities": exercise.get("recommended_activities", []),
            "advices": environment_data.get("advices", [])[:3]  # 最多3条建议
        }
    
    def _generate_basic_guidance(self, workout_type: str, debug_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """生成基础指导（用户数据不足时）"""
        if debug_info:
            self._add_debug_reasoning(debug_info, "使用基础指导模式（用户数据不足）", "warning")
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
            "generated_at": get_china_now().isoformat(),
            "debug": debug_info if debug_info else None
        }
