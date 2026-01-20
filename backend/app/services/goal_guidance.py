"""
目标智能引导服务

整合张展晖课程知识库和 Digital Twin，为用户目标提供科学指导
"""

import logging
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.user_profile import UserProfile
from app.models.daily_health import GarminData
# 不再导入 GoalType，直接使用字符串
from app.services.digital_twin import DigitalTwinService
from app.services.knowledge.rag_pipeline import rag_pipeline
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)


class GoalGuidanceService:
    """目标智能引导服务"""
    
    def __init__(self):
        pass
    
    def generate_goal_guidance(
        self,
        db: Session,
        user_id: int,
        goal_type: str,
        goal_description: str = "",
        target_value: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        为目标生成智能引导
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            goal_type: 目标类型
            goal_description: 目标描述
            target_value: 目标值
            
        Returns:
            包含训练建议、心率区间、知识要点的字典
        """
        try:
            logger.info(f"[目标引导] 开始为用户 {user_id} 生成 {goal_type} 目标的引导")
            
            # 1. 获取用户基本信息
            profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
            if not profile:
                logger.warning(f"[目标引导] 用户 {user_id} 没有个人资料")
                return self._generate_basic_guidance(goal_type)
            
            # 2. 获取最近的静息心率
            resting_hr = self._get_recent_resting_hr(db, user_id)
            
            # 3. 计算心率区间
            hr_zones = None
            if profile.age and resting_hr:
                digital_twin = DigitalTwinService(db, user_id)
                # calculate_target_heart_rate_zones() 不接受参数，从 self.profile 和内部数据获取
                hr_zones = digital_twin.calculate_target_heart_rate_zones()
                logger.info(f"[目标引导] 计算心率区间成功: {hr_zones}")
            
            # 4. 从知识库检索相关课程内容
            knowledge_guidance = self._retrieve_course_knowledge(
                goal_type=goal_type,
                goal_description=goal_description,
                user_profile=profile
            )
            
            # 5. 生成训练建议
            training_plan = self._generate_training_plan(
                goal_type=goal_type,
                target_value=target_value,
                hr_zones=hr_zones,
                knowledge_guidance=knowledge_guidance
            )
            
            # 6. 组装完整的引导信息
            guidance = {
                "success": True,
                "goal_type": goal_type,
                "heart_rate_zones": hr_zones,
                "training_plan": training_plan,
                "knowledge_points": knowledge_guidance.get("key_points", []),
                "course_references": knowledge_guidance.get("sources", []),
                "recommendations": self._generate_recommendations(
                    goal_type, hr_zones, profile
                ),
                "generated_at": get_china_now().isoformat()
            }
            
            logger.info(f"[目标引导] 生成完成，包含 {len(guidance['knowledge_points'])} 个知识要点")
            return guidance
            
        except Exception as e:
            logger.error(f"[目标引导] 生成失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": "生成引导失败，请稍后重试"
            }
    
    def _get_recent_resting_hr(self, db: Session, user_id: int) -> Optional[int]:
        """获取最近7天的平均静息心率"""
        try:
            recent_data = db.query(GarminData).filter(
                GarminData.user_id == user_id,
                GarminData.resting_heart_rate.isnot(None)
            ).order_by(GarminData.record_date.desc()).limit(7).all()
            
            if not recent_data:
                return None
            
            valid_hrs = [d.resting_heart_rate for d in recent_data if d.resting_heart_rate]
            if not valid_hrs:
                return None
            
            avg_hr = int(sum(valid_hrs) / len(valid_hrs))
            logger.info(f"[目标引导] 最近7天平均静息心率: {avg_hr} bpm")
            return avg_hr
            
        except Exception as e:
            logger.error(f"[目标引导] 获取静息心率失败: {e}")
            return None
    
    def _retrieve_course_knowledge(
        self,
        goal_type: str,
        goal_description: str,
        user_profile: UserProfile
    ) -> Dict[str, Any]:
        """从知识库检索相关课程内容"""
        try:
            # 构建查询问题
            query = self._build_knowledge_query(goal_type, goal_description, user_profile)
            logger.info(f"[目标引导] 知识库查询: {query}")
            
            # 使用 RAG 检索
            if not rag_pipeline.is_available():
                logger.warning("[目标引导] RAG 服务不可用")
                return {"key_points": [], "sources": []}
            
            # 调用 RAG - 使用 retrieve_relevant_knowledge 检索相关知识
            knowledge_results = rag_pipeline.retrieve_relevant_knowledge(
                query=query,
                category="exercise_science",  # 限定为运动科学分类
                n_results=5
            )
            
            if knowledge_results:
                # 提取关键点
                key_points = []
                sources = []
                for item in knowledge_results:
                    if item.get("content"):
                        key_points.append(item["content"][:200])  # 截取前200字符作为要点
                    if item.get("metadata", {}).get("source_title"):
                        sources.append(item["metadata"]["source_title"])
                
                return {
                    "key_points": key_points[:5],  # 最多5个要点
                    "sources": list(set(sources))[:3],  # 最多3个来源，去重
                    "raw_knowledge": knowledge_results
                }
            else:
                logger.warning(f"[目标引导] 未检索到相关知识")
                return {"key_points": [], "sources": [], "raw_knowledge": []}
                
        except Exception as e:
            logger.error(f"[目标引导] 检索课程知识失败: {e}")
            return {"key_points": [], "sources": []}
    
    def _build_knowledge_query(
        self,
        goal_type: str,
        goal_description: str,
        user_profile: UserProfile
    ) -> str:
        """构建知识库查询问题"""
        queries = {
            "WEIGHT_LOSS": f"如何科学有效地减肥？需要注意哪些训练原则和心率区间？{goal_description}",
            "MUSCLE_GAIN": f"如何进行力量训练增肌？需要注意哪些训练原则？{goal_description}",
            "CARDIO": f"如何提升心肺功能？应该在哪些心率区间训练？{goal_description}",
            "FLEXIBILITY": f"如何提高柔韧度？有哪些训练方法和注意事项？{goal_description}",
            "ENDURANCE": f"如何提升肌肉耐力？需要什么样的训练计划？{goal_description}",
            "RUNNING": f"如何科学地进行跑步训练？应该如何分配心率区间？{goal_description}",
            "EXERCISE": f"如何进行科学的运动训练？{goal_description}",
            "WEIGHT": f"如何通过运动和饮食管理体重？{goal_description}",
        }
        
        return queries.get(goal_type.upper(), f"关于 {goal_type} 训练的科学建议？{goal_description}")
    
    def _generate_training_plan(
        self,
        goal_type: str,
        target_value: Optional[float],
        hr_zones: Optional[Dict[str, Any]],
        knowledge_guidance: Dict[str, Any]
    ) -> Dict[str, Any]:
        """生成训练计划"""
        plan = {
            "frequency": self._get_recommended_frequency(goal_type),
            "duration": self._get_recommended_duration(goal_type),
            "intensity_distribution": self._get_intensity_distribution(goal_type, hr_zones),
            "weekly_structure": self._get_weekly_structure(goal_type),
            "progression": self._get_progression_strategy(goal_type, target_value)
        }
        
        return plan
    
    def _get_recommended_frequency(self, goal_type: str) -> str:
        """获取推荐训练频率"""
        frequency_map = {
            "WEIGHT_LOSS": "每周 4-5 次，有氧为主",
            "MUSCLE_GAIN": "每周 3-4 次，力量训练",
            "CARDIO": "每周 3-5 次，心肺训练",
            "FLEXIBILITY": "每天 10-15 分钟拉伸",
            "ENDURANCE": "每周 4-5 次，长时间低强度",
            "RUNNING": "每周 3-4 次，包含长跑和间歇",
            "EXERCISE": "每周 3-4 次",
            "WEIGHT": "每周 4-5 次，有氧+力量",
        }
        return frequency_map.get(goal_type.upper(), "每周 3-4 次")
    
    def _get_recommended_duration(self, goal_type: str) -> str:
        """获取推荐训练时长"""
        duration_map = {
            "WEIGHT_LOSS": "每次 45-60 分钟",
            "MUSCLE_GAIN": "每次 45-60 分钟",
            "CARDIO": "每次 30-45 分钟",
            "FLEXIBILITY": "每次 15-20 分钟",
            "ENDURANCE": "每次 60-90 分钟",
            "RUNNING": "每次 30-60 分钟",
            "EXERCISE": "每次 30-45 分钟",
            "WEIGHT": "每次 45-60 分钟",
        }
        return duration_map.get(goal_type.upper(), "每次 30-45 分钟")
    
    def _get_intensity_distribution(
        self,
        goal_type: str,
        hr_zones: Optional[Dict[str, Any]]
    ) -> Dict[str, str]:
        """获取训练强度分配"""
        if not hr_zones:
            return {"note": "需要心率数据才能提供精确的强度分配"}
        
        distribution_map = {
            "WEIGHT_LOSS": {
                "zone_2": "60% - 低强度有氧（燃脂区间）",
                "zone_3": "30% - 中等强度有氧",
                "zone_4": "10% - 高强度间歇"
            },
            "CARDIO": {
                "zone_2": "70% - 低强度有氧（建立基础）",
                "zone_3": "20% - 中等强度",
                "zone_4": "10% - 高强度间歇"
            },
            "RUNNING": {
                "zone_2": "80% - 轻松跑（建立有氧基础）",
                "zone_3": "10% - 节奏跑",
                "zone_4": "10% - 间歇跑"
            },
            "EXERCISE": {
                "zone_2": "70% - 低强度有氧",
                "zone_3": "20% - 中等强度",
                "zone_4": "10% - 高强度"
            },
        }
        
        return distribution_map.get(goal_type.upper(), {
            "note": f"根据 {goal_type} 目标调整训练强度"
        })
    
    def _get_weekly_structure(self, goal_type: str) -> List[str]:
        """获取周训练结构"""
        structure_map = {
            "WEIGHT_LOSS": [
                "周一：有氧训练 45 分钟（心率区间 2）",
                "周二：力量训练 + 有氧 30 分钟",
                "周三：休息或轻度拉伸",
                "周四：有氧训练 45 分钟（心率区间 2-3）",
                "周五：力量训练 + 有氧 30 分钟",
                "周六：长时间有氧 60 分钟（心率区间 2）",
                "周日：休息"
            ],
            "RUNNING": [
                "周一：轻松跑 30-40 分钟（心率区间 2）",
                "周二：间歇训练（心率区间 4-5）",
                "周三：休息或交叉训练",
                "周四：节奏跑 30 分钟（心率区间 3）",
                "周五：休息",
                "周六：长距离跑 60-90 分钟（心率区间 2）",
                "周日：恢复跑或休息"
            ],
        }
        
        return structure_map.get(goal_type.upper(), [
            "根据目标类型定制训练计划",
            "建议咨询专业教练"
        ])
    
    def _get_progression_strategy(
        self,
        goal_type: str,
        target_value: Optional[float]
    ) -> str:
        """获取进阶策略"""
        if target_value:
            return f"循序渐进，每周增加 5-10% 的训练量，目标值：{target_value}"
        
        return "遵循 10% 原则：每周训练量增加不超过 10%，避免过度训练"
    
    def _generate_recommendations(
        self,
        goal_type: str,
        hr_zones: Optional[Dict[str, Any]],
        profile: UserProfile
    ) -> List[str]:
        """生成个性化建议"""
        recommendations = []
        
        # 基于心率区间的建议
        if hr_zones:
            max_hr = hr_zones.get('max_heart_rate', 180)
            zone2 = hr_zones.get('zone2_fat_burn', (120, 140))
            recommendations.append(
                f"你的最大心率约为 {max_hr} bpm，"
                f"建议大部分训练保持在 {zone2[0]}-{zone2[1]} bpm（有氧燃脂区间）"
            )
        
        # 基于目标类型的建议
        type_recommendations = {
            "WEIGHT_LOSS": [
                "减肥的关键是制造热量缺口，运动 + 饮食控制",
                "有氧运动为主，配合力量训练保持肌肉",
                "避免过度节食，保证基础代谢"
            ],
            "RUNNING": [
                "80% 的训练应该是轻松跑（能边跑边聊天的配速）",
                "每周至少一次长距离跑，建立有氧基础",
                "注意跑后拉伸和恢复"
            ],
            "EXERCISE": [
                "循序渐进，避免运动损伤",
                "注意运动前热身和运动后拉伸",
                "保证充足的休息和恢复"
            ],
        }
        
        recommendations.extend(type_recommendations.get(goal_type.upper(), []))
        
        return recommendations
    
    def _generate_basic_guidance(self, goal_type: str) -> Dict[str, Any]:
        """生成基础引导（当用户数据不足时）"""
        return {
            "success": True,
            "goal_type": goal_type,
            "message": "建议完善个人资料和同步 Garmin 数据，以获得更精准的训练建议",
            "basic_recommendations": [
                "先进行基础体能评估",
                "从低强度开始，循序渐进",
                "注意训练后的恢复"
            ]
        }


# 创建全局实例
goal_guidance_service = GoalGuidanceService()
