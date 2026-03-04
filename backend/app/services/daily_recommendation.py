"""每日健康分析与建议服务"""
from datetime import date, timedelta, datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from app.models.daily_health import GarminData
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.basic_health import BasicHealthData
from app.models.daily_recommendation import DailyRecommendation
from app.services.llm_health_analyzer import llm_analyzer
from app.utils.timezone import get_china_today, get_china_now
import logging
import json
import asyncio

logger = logging.getLogger(__name__)

# 尝试导入 RAG Pipeline
try:
    from app.services.knowledge.rag_pipeline import rag_pipeline
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    logger.warning("RAG Pipeline 未导入，知识库增强功能将不可用")

# 尝试导入环境服务 (直接从子模块导入，避免 app.services 包的循环依赖)
try:
    from app.services.environment.environment_advisor import environment_advisor
    ENVIRONMENT_AVAILABLE = True
    logger.info("✅ 环境服务已成功导入")
except ImportError as e:
    ENVIRONMENT_AVAILABLE = False
    logger.warning(f"环境服务未导入，环境建议功能将不可用: {e}")


class DailyRecommendationService:
    """
    每日健康分析与建议服务
    
    基于前一天的Garmin数据（睡眠、运动、心率等），
    生成今天的个性化健康建议
    """
    
    async def get_environment_data(
        self,
        db: Session,
        user_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        获取用户所在城市的环境数据（天气、空气质量）
        
        Returns:
            包含天气、空气质量和运动建议的字典
        """
        if not ENVIRONMENT_AVAILABLE:
            return None
        
        try:
            # 获取用户画像中的城市
            profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
            city = profile.city if profile and profile.city else "北京"
            user_conditions = profile.chronic_conditions if profile else []
            
            # 获取综合环境建议
            env_advice = await environment_advisor.get_comprehensive_advice(
                city=city,
                user_conditions=user_conditions
            )
            
            logger.info(f"获取环境数据成功 - 城市: {city}, 用户: {user_id}")
            return env_advice
            
        except Exception as e:
            logger.error(f"获取环境数据失败: {e}")
            return None
    
    def get_environment_data_sync(
        self,
        db: Session,
        user_id: int
    ) -> Optional[Dict[str, Any]]:
        """同步方式获取环境数据（修复异步事件循环问题）"""
        if not ENVIRONMENT_AVAILABLE:
            return None
        
        try:
            # 获取用户画像中的城市
            profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
            city = profile.city if profile and profile.city else "北京"
            user_conditions = profile.chronic_conditions if profile else []
            
            # 使用新的事件循环运行异步函数
            def run_async():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(
                        environment_advisor.get_comprehensive_advice(
                            city=city,
                            user_conditions=user_conditions
                        )
                    )
                finally:
                    loop.close()
            
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_async)
                result = future.result(timeout=15)
                logger.info(f"获取环境数据成功 - 城市: {city}, 用户: {user_id}")
                return result
                
        except Exception as e:
            logger.error(f"同步获取环境数据失败: {e}", exc_info=True)
            return None
    
    def get_latest_data(
        self,
        db: Session,
        user_id: int
    ) -> Optional[GarminData]:
        """获取最新的有效Garmin数据（有实际值的数据）"""
        # 首先尝试获取今天的数据
        today_data = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == get_china_today()
        ).first()
        
        # 检查今天的数据是否有实际值（至少有睡眠分数、步数或心率之一）
        if today_data and self._has_meaningful_data(today_data):
            return today_data
        
        # 如果今天没有有效数据，获取昨天的
        yesterday = get_china_today() - timedelta(days=1)
        yesterday_data = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == yesterday
        ).first()
        
        if yesterday_data and self._has_meaningful_data(yesterday_data):
            return yesterday_data
        
        # 如果昨天也没有，尝试获取最近7天内有数据的记录
        week_ago = get_china_today() - timedelta(days=7)
        return db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= week_ago,
            GarminData.record_date <= get_china_today()
        ).order_by(GarminData.record_date.desc()).first()
    
    def _has_meaningful_data(self, data: GarminData) -> bool:
        """检查数据是否有实际值"""
        return bool(
            data.sleep_score or 
            data.total_sleep_duration or 
            data.steps or 
            data.resting_heart_rate or
            data.avg_heart_rate
        )
    
    def get_yesterday_data(
        self,
        db: Session,
        user_id: int,
        reference_date: Optional[date] = None
    ) -> Optional[GarminData]:
        """获取昨天的Garmin数据（兼容旧方法）"""
        if reference_date is None:
            reference_date = get_china_today()
        
        yesterday = reference_date - timedelta(days=1)
        
        return db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == yesterday
        ).first()
    
    def get_recent_data(
        self,
        db: Session,
        user_id: int,
        days: int = 7,
        include_today: bool = True
    ) -> List[GarminData]:
        """获取最近N天的数据用于趋势分析"""
        end_date = get_china_today() if include_today else get_china_today() - timedelta(days=1)
        start_date = end_date - timedelta(days=days - 1)
        
        return db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start_date,
            GarminData.record_date <= end_date
        ).order_by(GarminData.record_date.desc()).all()
    
    def analyze_sleep(self, yesterday: GarminData, recent_data: List[GarminData]) -> Dict[str, Any]:
        """分析睡眠数据"""
        analysis = {
            "status": "unknown",
            "score": None,
            "duration_hours": None,
            "quality_assessment": "",
            "trend": "stable",
            "issues": [],
            "recommendations": []
        }
        
        if not yesterday:
            analysis["quality_assessment"] = "无昨日睡眠数据"
            return analysis
        
        # 基础数据
        sleep_score = yesterday.sleep_score
        sleep_duration = yesterday.total_sleep_duration  # 分钟
        deep_sleep = yesterday.deep_sleep_duration or 0
        rem_sleep = yesterday.rem_sleep_duration or 0
        
        analysis["score"] = sleep_score
        analysis["duration_hours"] = round(sleep_duration / 60, 1) if sleep_duration else None
        analysis["deep_sleep_minutes"] = deep_sleep
        analysis["rem_sleep_minutes"] = rem_sleep
        
        # 睡眠时长评估 (成人建议7-9小时)
        if sleep_duration:
            duration_hours = sleep_duration / 60
            if duration_hours < 6:
                analysis["issues"].append("睡眠时间严重不足")
                analysis["status"] = "poor"
                analysis["recommendations"].append("今晚尽量提前1-2小时入睡")
                analysis["recommendations"].append("避免晚间使用电子设备")
            elif duration_hours < 7:
                analysis["issues"].append("睡眠时间略短")
                analysis["status"] = "fair"
                analysis["recommendations"].append("今晚尝试提前30分钟入睡")
            elif duration_hours <= 9:
                analysis["status"] = "good"
            else:
                analysis["issues"].append("睡眠时间偏长")
                analysis["status"] = "fair"
                analysis["recommendations"].append("检查是否有疲劳积累，适当增加白天活动")
        
        # 睡眠分数评估
        if sleep_score:
            if sleep_score >= 85:
                analysis["quality_assessment"] = "睡眠质量优秀"
                if analysis["status"] != "poor":
                    analysis["status"] = "excellent"
            elif sleep_score >= 70:
                analysis["quality_assessment"] = "睡眠质量良好"
                if analysis["status"] == "unknown":
                    analysis["status"] = "good"
            elif sleep_score >= 50:
                analysis["quality_assessment"] = "睡眠质量一般"
                analysis["status"] = "fair"
                analysis["recommendations"].append("睡前避免咖啡因和酒精")
                analysis["recommendations"].append("保持卧室凉爽、黑暗、安静")
            else:
                analysis["quality_assessment"] = "睡眠质量较差"
                analysis["status"] = "poor"
                analysis["issues"].append("睡眠质量需要改善")
                analysis["recommendations"].append("建议建立规律的睡眠时间表")
                analysis["recommendations"].append("睡前进行放松活动如冥想或阅读")
        
        # 深度睡眠评估 (建议占总睡眠15-20%)
        if sleep_duration and deep_sleep:
            deep_ratio = deep_sleep / sleep_duration * 100
            if deep_ratio < 10:
                analysis["issues"].append("深度睡眠不足")
                analysis["recommendations"].append("增加白天的体力活动")
                analysis["recommendations"].append("避免睡前2小时进食")
            elif deep_ratio >= 20:
                analysis["quality_assessment"] += "，深度睡眠充足"
        
        # 趋势分析
        if len(recent_data) >= 3:
            recent_scores = [d.sleep_score for d in recent_data if d.sleep_score]
            if len(recent_scores) >= 3:
                avg_recent = sum(recent_scores) / len(recent_scores)
                if sleep_score and sleep_score > avg_recent + 5:
                    analysis["trend"] = "improving"
                elif sleep_score and sleep_score < avg_recent - 5:
                    analysis["trend"] = "declining"
                    analysis["recommendations"].append("注意睡眠质量下降趋势，检查近期压力或作息变化")
        
        return analysis
    
    def analyze_activity(self, yesterday: GarminData, recent_data: List[GarminData]) -> Dict[str, Any]:
        """分析活动数据"""
        analysis = {
            "status": "unknown",
            "steps": None,
            "steps_goal_met": False,
            "active_minutes": None,
            "calories_burned": None,
            "trend": "stable",
            "issues": [],
            "recommendations": []
        }
        
        if not yesterday:
            return analysis
        
        steps = yesterday.steps
        # 注意：这里的 active_minutes 是 Garmin 记录的全天活动分钟数
        # 不是实际的运动训练时间（运动训练时间在 workout_records 表中）
        active_minutes = yesterday.active_minutes or 0
        calories = yesterday.calories_burned
        
        analysis["steps"] = steps
        analysis["active_minutes"] = active_minutes
        analysis["calories_burned"] = calories
        
        # 步数评估 (WHO建议每天至少7000-10000步)
        if steps:
            if steps >= 10000:
                analysis["status"] = "excellent"
                analysis["steps_goal_met"] = True
            elif steps >= 7000:
                analysis["status"] = "good"
                analysis["steps_goal_met"] = True
            elif steps >= 5000:
                analysis["status"] = "fair"
                analysis["issues"].append("步数未达到推荐目标")
                analysis["recommendations"].append(f"今天尝试多走 {10000 - steps} 步达到目标")
                analysis["recommendations"].append("尝试午餐后散步15-20分钟")
            else:
                analysis["status"] = "poor"
                analysis["issues"].append("活动量严重不足")
                analysis["recommendations"].append("建议每小时站起来活动5分钟")
                analysis["recommendations"].append("考虑增加短距离步行，如走楼梯代替电梯")
        
        # 活动分钟数评估 (WHO建议每周150分钟中等强度运动)
        if active_minutes:
            daily_goal = 150 / 7  # 约21分钟/天
            if active_minutes >= daily_goal * 1.5:
                analysis["recommendations"].append("昨天活动量充足，今天可以适当恢复")
            elif active_minutes < daily_goal:
                analysis["recommendations"].append(f"今天尝试增加{int(daily_goal - active_minutes)}分钟中等强度活动")
        
        # 趋势分析
        if len(recent_data) >= 3:
            recent_steps = [d.steps for d in recent_data if d.steps]
            if len(recent_steps) >= 3:
                avg_steps = sum(recent_steps) / len(recent_steps)
                if steps and steps > avg_steps * 1.2:
                    analysis["trend"] = "improving"
                elif steps and steps < avg_steps * 0.8:
                    analysis["trend"] = "declining"
                    analysis["recommendations"].append("注意活动量下降趋势")
        
        return analysis
    
    def analyze_heart_rate(self, yesterday: GarminData, recent_data: List[GarminData]) -> Dict[str, Any]:
        """分析心率数据"""
        analysis = {
            "status": "unknown",
            "resting_hr": None,
            "avg_hr": None,
            "hrv": None,
            "trend": "stable",
            "issues": [],
            "recommendations": []
        }
        
        if not yesterday:
            return analysis
        
        resting_hr = yesterday.resting_heart_rate
        avg_hr = yesterday.avg_heart_rate
        hrv = yesterday.hrv
        max_hr = yesterday.max_heart_rate
        min_hr = yesterday.min_heart_rate
        
        analysis["resting_hr"] = resting_hr
        analysis["avg_hr"] = avg_hr
        analysis["hrv"] = hrv
        analysis["max_hr"] = max_hr
        analysis["min_hr"] = min_hr
        
        # 静息心率评估 (成人正常范围60-100，运动员可能更低)
        if resting_hr:
            if resting_hr < 50:
                analysis["status"] = "excellent"
                analysis["recommendations"].append("静息心率很低，表明心血管健康状况良好")
            elif resting_hr < 60:
                analysis["status"] = "excellent"
            elif resting_hr <= 70:
                analysis["status"] = "good"
            elif resting_hr <= 80:
                analysis["status"] = "fair"
                analysis["recommendations"].append("可以通过增加有氧运动来降低静息心率")
            else:
                analysis["status"] = "concerning"
                analysis["issues"].append("静息心率偏高")
                analysis["recommendations"].append("建议增加规律的有氧运动")
                analysis["recommendations"].append("注意控制压力和咖啡因摄入")
        
        # HRV评估 (心率变异性，越高通常越好)
        if hrv:
            if hrv >= 50:
                analysis["recommendations"].append("HRV良好，身体恢复状态佳")
            elif hrv >= 30:
                pass  # 正常范围
            else:
                analysis["issues"].append("HRV偏低")
                analysis["recommendations"].append("注意休息和恢复，今天避免高强度运动")
        
        # 趋势分析
        if len(recent_data) >= 5:
            recent_rhr = [d.resting_heart_rate for d in recent_data if d.resting_heart_rate]
            if len(recent_rhr) >= 5:
                avg_rhr = sum(recent_rhr) / len(recent_rhr)
                if resting_hr and resting_hr < avg_rhr - 3:
                    analysis["trend"] = "improving"
                elif resting_hr and resting_hr > avg_rhr + 5:
                    analysis["trend"] = "concerning"
                    analysis["issues"].append("静息心率有上升趋势")
                    analysis["recommendations"].append("建议关注休息质量和压力水平")
        
        return analysis
    
    def analyze_stress_and_energy(self, yesterday: GarminData) -> Dict[str, Any]:
        """分析压力和能量数据"""
        analysis = {
            "stress_level": None,
            "body_battery_charged": None,
            "body_battery_drained": None,
            "body_battery_highest": None,
            "body_battery_lowest": None,
            "recovery_status": "unknown",
            "issues": [],
            "recommendations": []
        }
        
        if not yesterday:
            return analysis
        
        stress = yesterday.stress_level
        bb_charged = yesterday.body_battery_charged
        bb_drained = yesterday.body_battery_drained
        bb_highest = yesterday.body_battery_most_charged
        bb_lowest = yesterday.body_battery_lowest
        
        analysis["stress_level"] = stress
        analysis["body_battery_charged"] = bb_charged
        analysis["body_battery_drained"] = bb_drained
        analysis["body_battery_highest"] = bb_highest
        analysis["body_battery_lowest"] = bb_lowest
        
        # 压力评估
        if stress:
            if stress <= 25:
                analysis["recommendations"].append("昨天压力水平很低，状态良好")
            elif stress <= 50:
                pass  # 正常范围
            elif stress <= 75:
                analysis["issues"].append("压力水平中等偏高")
                analysis["recommendations"].append("今天安排一些放松活动，如深呼吸或冥想")
            else:
                analysis["issues"].append("压力水平较高")
                analysis["recommendations"].append("今天优先安排休息和恢复")
                analysis["recommendations"].append("考虑进行轻松的散步或瑜伽")
        
        # 身体电量评估
        if bb_highest:
            if bb_highest >= 75:
                analysis["recovery_status"] = "well_recovered"
                analysis["recommendations"].append("身体恢复良好，可以进行正常训练")
            elif bb_highest >= 50:
                analysis["recovery_status"] = "partially_recovered"
                analysis["recommendations"].append("身体部分恢复，建议中等强度活动")
            else:
                analysis["recovery_status"] = "needs_rest"
                analysis["issues"].append("身体电量恢复不足")
                analysis["recommendations"].append("今天以休息为主，避免高强度运动")
        
        # 消耗与恢复平衡
        if bb_charged and bb_drained:
            if bb_charged > bb_drained:
                analysis["recommendations"].append("昨天恢复大于消耗，今天可以增加活动量")
            elif bb_drained > bb_charged * 1.5:
                analysis["issues"].append("消耗过大，恢复不足")
                analysis["recommendations"].append("今天注意休息，适当减少活动强度")
        
        return analysis
    
    def generate_daily_summary(
        self,
        db: Session,
        user_id: int,
        reference_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        生成每日健康分析摘要
        
        数据获取逻辑：
        - 睡眠数据：使用今天的 record_date（因为 Garmin 按醒来日期记录，今天的数据=昨晚的睡眠）
        - 运动数据：使用昨天的 record_date（因为今天才刚开始，运动数据不完整）
        
        Returns:
            包含睡眠、活动、心率、压力分析和综合建议的完整报告
        """
        if reference_date is None:
            reference_date = get_china_today()
        
        china_today = get_china_today()
        china_yesterday = china_today - timedelta(days=1)
        
        # 获取今天的数据（用于睡眠分析 - 昨晚的睡眠）
        today_data = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == china_today
        ).first()
        
        # 获取昨天的数据（用于运动分析 - 昨天全天的运动）
        yesterday_data = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == china_yesterday
        ).first()
        
        # 获取最近7天的数据（用于趋势分析，不包括今天）
        recent_data = self.get_recent_data(db, user_id, 7, include_today=False)
        
        # 获取用户信息
        user = db.query(User).filter(User.id == user_id).first()
        
        # 优先使用今天的睡眠数据，如果没有则用昨天的
        primary_data = today_data if (today_data and self._has_meaningful_data(today_data)) else yesterday_data
        
        if not primary_data:
            return {
                "status": "no_data",
                "message": "暂无健康数据",
                "date": reference_date.isoformat(),
                "user": user.name if user else None,
                "sleep_analysis": None,
                "activity_analysis": None,
                "heart_rate_analysis": None,
                "stress_analysis": None,
                "overall_status": "unknown",
                "priority_recommendations": ["请先同步Garmin数据"],
                "daily_goals": []
            }
        
        # 使用组合数据进行分析
        # 睡眠分析：优先用今天的数据（昨晚的睡眠）
        sleep_data = today_data if (today_data and today_data.sleep_score) else yesterday_data
        # 运动分析：用昨天的数据（昨天全天的运动）
        activity_data = yesterday_data if yesterday_data else today_data
        # 心率/压力分析：优先用今天的数据
        vital_data = today_data if today_data else yesterday_data
        
        # 各项分析
        sleep_analysis = self.analyze_sleep(sleep_data, recent_data) if sleep_data else None
        activity_analysis = self.analyze_activity(activity_data, recent_data) if activity_data else None
        heart_rate_analysis = self.analyze_heart_rate(vital_data, recent_data) if vital_data else None
        stress_analysis = self.analyze_stress_and_energy(vital_data) if vital_data else None
        
        # 综合评估
        overall_status = self._calculate_overall_status(
            sleep_analysis, activity_analysis, heart_rate_analysis, stress_analysis
        )
        
        # 生成优先建议
        priority_recommendations = self._generate_priority_recommendations(
            sleep_analysis, activity_analysis, heart_rate_analysis, stress_analysis
        )
        
        # 生成今日目标
        daily_goals = self._generate_daily_goals(
            activity_data or vital_data, sleep_analysis, activity_analysis, stress_analysis
        )
        
        # 构建规则分析结果
        rule_analysis = {
            "overall_status": overall_status,
            "sleep_analysis": sleep_analysis,
            "activity_analysis": activity_analysis,
            "heart_rate_analysis": heart_rate_analysis,
            "stress_analysis": stress_analysis
        }
        
        return {
            "status": "success",
            "date": (sleep_data or activity_data or vital_data).record_date.isoformat(),
            "analysis_date": reference_date.isoformat(),
            "user": user.name if user else None,
            "sleep_analysis": sleep_analysis,
            "activity_analysis": activity_analysis,
            "heart_rate_analysis": heart_rate_analysis,
            "stress_analysis": stress_analysis,
            "overall_status": overall_status,
            "priority_recommendations": priority_recommendations,
            "daily_goals": daily_goals,
            "raw_data": {
                "sleep_score": sleep_data.sleep_score if sleep_data else None,
                "sleep_duration_minutes": sleep_data.total_sleep_duration if sleep_data else None,
                "steps": activity_data.steps if activity_data else None,
                "resting_heart_rate": vital_data.resting_heart_rate if vital_data else None,
                "stress_level": vital_data.stress_level if vital_data else None,
                "body_battery_highest": vital_data.body_battery_most_charged if vital_data else None,
                "body_battery_current": vital_data.body_battery_current if vital_data else None,
                "body_battery_lowest": vital_data.body_battery_lowest if vital_data else None,
                "body_battery_drained": vital_data.body_battery_drained if vital_data else None
            },
            # 保存分析上下文供LLM使用
            "_rule_analysis": rule_analysis,
            "_sleep_data": sleep_data,  # 今天的睡眠数据（昨晚的睡眠）
            "_activity_data": activity_data,  # 昨天的运动数据
            "_yesterday_data": activity_data or sleep_data or vital_data,  # 兼容性
            "_recent_data": recent_data
        }
    
    async def generate_daily_summary_with_llm(
        self,
        db: Session,
        user_id: int,
        reference_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        生成结合规则分析和大模型分析的每日健康摘要
        
        Returns:
            包含规则分析和LLM智能建议的完整报告
        """
        # 先执行规则分析
        rule_result = self.generate_daily_summary(db, user_id, reference_date)
        
        if rule_result.get("status") != "success":
            return rule_result
        
        # 提取上下文数据
        sleep_data = rule_result.pop("_sleep_data", None)  # 今天的睡眠数据
        activity_data = rule_result.pop("_activity_data", None)  # 昨天的运动数据
        yesterday_data = rule_result.pop("_yesterday_data", None)  # 兼容性
        recent_data = rule_result.pop("_recent_data", [])
        rule_analysis = rule_result.pop("_rule_analysis", {})
        
        # 获取环境数据
        environment_data = None
        logger.info(f"[环境数据] ENVIRONMENT_AVAILABLE={ENVIRONMENT_AVAILABLE}, 用户: {user_id}")
        if ENVIRONMENT_AVAILABLE:
            try:
                logger.info(f"[环境数据] 开始获取环境数据，用户: {user_id}")
                environment_data = self.get_environment_data_sync(db, user_id)
                logger.info(f"[环境数据] 获取结果: {'成功' if environment_data else '无数据'}")
                if environment_data:
                    rule_result["environment"] = {
                        "weather": environment_data.get("weather", {}),
                        "air_quality": environment_data.get("air_quality", {}),
                        "exercise": environment_data.get("exercise", {}),
                        "advices": environment_data.get("advices", []),
                        "warnings": environment_data.get("warnings", [])
                    }
                    logger.info(f"[环境数据] 已添加到建议中，温度: {environment_data.get('weather', {}).get('temperature')}°C, AQI: {environment_data.get('air_quality', {}).get('aqi')}")
            except Exception as e:
                logger.error(f"[环境数据] 获取失败: {e}", exc_info=True)
        else:
            logger.warning(f"[环境数据] 环境服务不可用，跳过环境数据获取")
        
        # 执行LLM分析（传入环境数据）
        # 注意：传递给LLM的数据需要区分睡眠和运动
        # - 睡眠数据来自今天的记录（昨晚的睡眠）
        # - 运动数据来自昨天的记录（昨天全天的运动）
        # 为了兼容现有接口，我们创建一个组合数据对象
        combined_data = activity_data or sleep_data or yesterday_data
        if combined_data and sleep_data and sleep_data != activity_data:
            # 如果睡眠和运动数据来自不同日期，需要在提示词中明确说明
            logger.info(f"睡眠数据日期: {sleep_data.record_date if sleep_data else 'N/A'}, 运动数据日期: {activity_data.record_date if activity_data else 'N/A'}")
        
        llm_result = await llm_analyzer.analyze_daily_health(
            db=db,
            user_id=user_id,
            yesterday_data=combined_data,
            recent_data=recent_data,
            rule_analysis=rule_analysis,
            environment_data=environment_data
        )
        
        # 合并结果
        rule_result["llm_analysis"] = llm_result
        
        # 如果LLM分析成功，用LLM的建议增强规则建议
        if llm_result.get("available") and "today_actions" in llm_result:
            # 将LLM的行动建议添加到优先建议中
            llm_actions = llm_result.get("today_actions", [])
            existing_recs = set(rule_result.get("priority_recommendations", []))
            
            # 合并去重
            combined_recs = list(rule_result.get("priority_recommendations", []))
            for action in llm_actions:
                if action not in existing_recs:
                    combined_recs.append(action)
            
            rule_result["enhanced_recommendations"] = combined_recs[:7]
            
            # 添加LLM的核心洞察
            rule_result["ai_insights"] = {
                "health_summary": llm_result.get("health_summary"),
                "key_insights": llm_result.get("key_insights", []),
                "today_focus": llm_result.get("today_focus"),
                "encouragement": llm_result.get("encouragement"),
                "warnings": llm_result.get("warnings", [])
            }
            
            # 添加LLM的详细建议
            rule_result["ai_advice"] = {
                "sleep": llm_result.get("sleep_advice"),
                "activity": llm_result.get("activity_advice"),
                "heart_health": llm_result.get("heart_health_advice"),
                "recovery": llm_result.get("recovery_advice"),
                "environment": llm_result.get("environment_advice")
            }
            
            # 添加运动推荐
            if llm_result.get("exercise_recommendations"):
                rule_result["exercise_recommendations"] = llm_result.get("exercise_recommendations")
        
        # RAG 知识库增强（如果可用）
        if RAG_AVAILABLE and rag_pipeline.is_available():
            try:
                # 构建用户上下文
                user_context = llm_analyzer._build_user_context(db, user_id)
                
                # 获取知识库增强建议
                rag_result = rag_pipeline.enhance_daily_advice(
                    rule_analysis=rule_analysis,
                    user_context=user_context,
                    health_data={
                        "sleep_score": yesterday_data.sleep_score if yesterday_data else None,
                        "steps": yesterday_data.steps if yesterday_data else None,
                        "resting_heart_rate": yesterday_data.resting_heart_rate if yesterday_data else None,
                        "stress_level": yesterday_data.stress_level if yesterday_data else None,
                        "body_battery": yesterday_data.body_battery_most_charged if yesterday_data else None
                    }
                )
                
                if rag_result.get("enhanced"):
                    rule_result["knowledge_enhanced"] = True
                    rule_result["knowledge_tips"] = rag_result.get("enhanced_tips", [])
                    rule_result["knowledge_highlights"] = rag_result.get("knowledge_highlights", [])
                    rule_result["personalized_focus"] = rag_result.get("personalized_focus")
                    logger.info(f"RAG 知识库增强成功，使用了 {rag_result.get('knowledge_sources', 0)} 条知识")
                else:
                    rule_result["knowledge_enhanced"] = False
                    
            except Exception as e:
                logger.error(f"RAG 知识库增强失败: {e}")
                rule_result["knowledge_enhanced"] = False
        else:
            rule_result["knowledge_enhanced"] = False
        
        return rule_result
    
    def _calculate_overall_status(
        self,
        sleep: Dict,
        activity: Dict,
        heart_rate: Dict,
        stress: Dict
    ) -> str:
        """计算综合健康状态"""
        status_scores = {
            "excellent": 4,
            "good": 3,
            "fair": 2,
            "poor": 1,
            "concerning": 1,
            "unknown": 2.5
        }
        
        statuses = [
            sleep.get("status", "unknown"),
            activity.get("status", "unknown"),
            heart_rate.get("status", "unknown")
        ]
        
        # 如果有恢复状态，也纳入考虑
        recovery = stress.get("recovery_status")
        if recovery == "well_recovered":
            statuses.append("excellent")
        elif recovery == "needs_rest":
            statuses.append("fair")
        
        scores = [status_scores.get(s, 2.5) for s in statuses]
        avg_score = sum(scores) / len(scores)
        
        if avg_score >= 3.5:
            return "excellent"
        elif avg_score >= 2.8:
            return "good"
        elif avg_score >= 2:
            return "fair"
        else:
            return "needs_attention"
    
    def _generate_priority_recommendations(
        self,
        sleep: Dict,
        activity: Dict,
        heart_rate: Dict,
        stress: Dict
    ) -> List[str]:
        """生成优先建议（最多5条最重要的建议）"""
        all_recommendations = []
        
        # 收集所有问题和建议
        for analysis in [sleep, activity, heart_rate, stress]:
            issues = analysis.get("issues", [])
            recs = analysis.get("recommendations", [])
            
            # 问题对应的建议优先级更高
            for issue in issues:
                for rec in recs:
                    all_recommendations.append((rec, "high"))
            
            for rec in recs:
                if (rec, "high") not in all_recommendations:
                    all_recommendations.append((rec, "normal"))
        
        # 去重并按优先级排序
        seen = set()
        priority_recs = []
        
        # 先添加高优先级
        for rec, priority in all_recommendations:
            if priority == "high" and rec not in seen:
                priority_recs.append(rec)
                seen.add(rec)
        
        # 再添加普通优先级
        for rec, priority in all_recommendations:
            if rec not in seen:
                priority_recs.append(rec)
                seen.add(rec)
        
        # 最多返回5条
        return priority_recs[:5]
    
    def _generate_daily_goals(
        self,
        yesterday: Optional[GarminData],
        sleep: Dict,
        activity: Dict,
        stress: Dict
    ) -> List[Dict[str, Any]]:
        """生成今日目标"""
        goals = []
        
        # 步数目标
        yesterday_steps = (yesterday.steps or 0) if yesterday else 0
        if yesterday_steps < 10000:
            target_steps = min(yesterday_steps + 2000, 10000)
            goals.append({
                "category": "activity",
                "goal": f"今日步数目标: {target_steps:,} 步",
                "icon": "🚶",
                "target_value": target_steps,
                "unit": "步"
            })
        else:
            goals.append({
                "category": "activity",
                "goal": "保持昨天的活动量",
                "icon": "🚶",
                "target_value": 10000,
                "unit": "步"
            })
        
        # 睡眠目标
        if sleep.get("status") in ["poor", "fair"]:
            goals.append({
                "category": "sleep",
                "goal": "今晚提前30分钟入睡",
                "icon": "😴",
                "target_value": 7.5,
                "unit": "小时"
            })
        else:
            goals.append({
                "category": "sleep",
                "goal": "保持规律作息",
                "icon": "😴",
                "target_value": 7,
                "unit": "小时"
            })
        
        # 活动分钟目标
        goals.append({
            "category": "exercise",
            "goal": "进行30分钟中等强度运动",
            "icon": "🏃",
            "target_value": 30,
            "unit": "分钟"
        })
        
        # 恢复目标（如果需要）
        if stress.get("recovery_status") == "needs_rest":
            goals.append({
                "category": "recovery",
                "goal": "安排15分钟放松活动",
                "icon": "🧘",
                "target_value": 15,
                "unit": "分钟"
            })
        
        # 水分摄入目标
        goals.append({
            "category": "hydration",
            "goal": "饮水2000ml以上",
            "icon": "💧",
            "target_value": 2000,
            "unit": "ml"
        })
        
        return goals
    
    async def get_or_generate_recommendations(
        self,
        db: Session,
        user_id: int,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        获取或生成每日建议（带缓存）
        
        检查数据库中是否有今天的建议，如果没有则生成并保存
        返回1天和7天的建议
        """
        today = get_china_today()
        
        # 获取最新数据的日期
        latest_data = self.get_latest_data(db, user_id)
        analysis_date = latest_data.record_date if latest_data else today
        
        # 检查缓存
        cached = db.query(DailyRecommendation).filter(
            DailyRecommendation.user_id == user_id,
            DailyRecommendation.recommendation_date == today
        ).first()
        
        # 只有当缓存存在且分析数据日期与最新数据日期一致时才使用缓存
        # 这样当今天的数据同步后，会重新生成基于今天数据的建议
        cache_valid = (
            cached 
            and cached.one_day_recommendation 
            and cached.seven_day_recommendation
            and cached.analysis_date == analysis_date  # 确保分析的是最新数据
        )
        
        if cache_valid:
            logger.info(f"使用缓存的建议数据（用户 {user_id}，日期 {today}，分析数据日期 {analysis_date}）")
            return {
                "status": "success",
                "date": today.isoformat(),
                "analysis_date": cached.analysis_date.isoformat() if cached.analysis_date else analysis_date.isoformat(),
                "one_day": cached.one_day_recommendation,
                "seven_day": cached.seven_day_recommendation,
                "cached": True
            }
        
        # 生成新建议
        logger.info(f"生成新的建议数据（用户 {user_id}，日期 {today}，分析数据日期 {analysis_date}）")
        
        # 生成1天建议（基于最新的数据）
        one_day_rec = await self.generate_one_day_recommendation(db, user_id, use_llm)

        # 生成7天建议（基于最近7天的数据）
        seven_day_rec = await self.generate_seven_day_recommendation(db, user_id, use_llm)
        
        # 保存到数据库
        if cached:
            # 更新现有记录
            cached.one_day_recommendation = one_day_rec
            cached.seven_day_recommendation = seven_day_rec
            cached.analysis_date = analysis_date
            cached.updated_at = datetime.utcnow()
        else:
            # 创建新记录
            cached = DailyRecommendation(
                user_id=user_id,
                recommendation_date=today,
                analysis_date=analysis_date,
                one_day_recommendation=one_day_rec,
                seven_day_recommendation=seven_day_rec
            )
            db.add(cached)
        
        db.commit()
        db.refresh(cached)
        
        return {
            "status": "success",
            "date": today.isoformat(),
            "analysis_date": analysis_date.isoformat(),
            "one_day": one_day_rec,
            "seven_day": seven_day_rec,
            "cached": False
        }
    
    async def generate_one_day_recommendation(
        self,
        db: Session,
        user_id: int,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """生成1天建议（基于昨天的数据）"""
        if use_llm:
            return await self.generate_daily_summary_with_llm(db, user_id)
        else:
            result = self.generate_daily_summary(db, user_id)
            # 清理内部字段
            result.pop("_rule_analysis", None)
            result.pop("_yesterday_data", None)
            result.pop("_recent_data", None)
            return result
    
    async def generate_seven_day_recommendation(
        self,
        db: Session,
        user_id: int,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """生成本周建议（基于北京时间周一到今天的数据）"""
        today = get_china_today()
        
        # 计算本周周一（北京时间）
        # weekday() 返回 0=周一, 1=周二, ..., 6=周日
        days_since_monday = today.weekday()
        monday = today - timedelta(days=days_since_monday)
        
        start_date = monday  # 从周一开始
        end_date = today  # 到今天
        
        # 获取本周的数据（从周一到今天）
        recent_data = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start_date,
            GarminData.record_date <= end_date
        ).order_by(GarminData.record_date.desc()).all()
        
        if not recent_data:
            return {
                "status": "no_data",
                "message": "暂无本周的数据",
                "date": today.isoformat(),
                "analysis_period": f"{start_date.isoformat()} 至 {end_date.isoformat()} (本周)"
            }
        
        # 获取用户信息
        user = db.query(User).filter(User.id == user_id).first()
        
        # 计算7天平均值
        sleep_scores = [d.sleep_score for d in recent_data if d.sleep_score]
        avg_sleep_score = sum(sleep_scores) / len(sleep_scores) if sleep_scores else None
        
        total_sleep_durations = [d.total_sleep_duration for d in recent_data if d.total_sleep_duration]
        avg_sleep_duration = sum(total_sleep_durations) / len(total_sleep_durations) if total_sleep_durations else None
        
        steps_list = [d.steps for d in recent_data if d.steps]
        avg_steps = sum(steps_list) / len(steps_list) if steps_list else None
        
        resting_hrs = [d.resting_heart_rate for d in recent_data if d.resting_heart_rate]
        avg_resting_hr = sum(resting_hrs) / len(resting_hrs) if resting_hrs else None
        
        hrvs = [d.hrv for d in recent_data if d.hrv]
        avg_hrv = sum(hrvs) / len(hrvs) if hrvs else None
        
        stress_levels = [d.stress_level for d in recent_data if d.stress_level]
        avg_stress = sum(stress_levels) / len(stress_levels) if stress_levels else None
        
        body_batteries = [d.body_battery_charged for d in recent_data if d.body_battery_charged]
        avg_body_battery = sum(body_batteries) / len(body_batteries) if body_batteries else None
        
        # 使用最后一天的数据作为主要分析对象，但结合7天趋势
        yesterday_data = recent_data[0] if recent_data else None
        
        # 生成分析
        sleep_analysis = self.analyze_sleep(yesterday_data, recent_data)
        activity_analysis = self.analyze_activity(yesterday_data, recent_data)
        heart_rate_analysis = self.analyze_heart_rate(yesterday_data, recent_data)
        stress_analysis = self.analyze_stress_and_energy(yesterday_data)
        
        # 综合评估
        overall_status = self._calculate_overall_status(
            sleep_analysis, activity_analysis, heart_rate_analysis, stress_analysis
        )
        
        # 生成优先建议
        priority_recommendations = self._generate_priority_recommendations(
            sleep_analysis, activity_analysis, heart_rate_analysis, stress_analysis
        )
        
        # 生成每日目标
        daily_goals = self._generate_daily_goals(
            yesterday_data, sleep_analysis, activity_analysis, stress_analysis
        )
        
        result = {
            "status": "success",
            "date": today.isoformat(),
            "analysis_date": end_date.isoformat(),
            "analysis_period": f"{start_date.isoformat()} 至 {end_date.isoformat()} (本周)",
            "user": user.name if user else None,
            "sleep_analysis": sleep_analysis,
            "activity_analysis": activity_analysis,
            "heart_rate_analysis": heart_rate_analysis,
            "stress_analysis": stress_analysis,
            "overall_status": overall_status,
            "priority_recommendations": priority_recommendations,
            "daily_goals": daily_goals,
            "averages": {
                "sleep_score": round(avg_sleep_score, 1) if avg_sleep_score else None,
                "sleep_duration_minutes": round(avg_sleep_duration, 1) if avg_sleep_duration else None,
                "steps": round(avg_steps, 0) if avg_steps else None,
                "resting_heart_rate": round(avg_resting_hr, 1) if avg_resting_hr else None,
                "hrv": round(avg_hrv, 1) if avg_hrv else None,
                "stress_level": round(avg_stress, 1) if avg_stress else None,
                "body_battery": round(avg_body_battery, 1) if avg_body_battery else None,
            },
            "raw_data": {
                "sleep_score": yesterday_data.sleep_score if yesterday_data else None,
                "sleep_duration_minutes": yesterday_data.total_sleep_duration if yesterday_data else None,
                "steps": yesterday_data.steps if yesterday_data else None,
                "resting_heart_rate": yesterday_data.resting_heart_rate if yesterday_data else None,
                "stress_level": yesterday_data.stress_level if yesterday_data else None,
                "body_battery_highest": yesterday_data.body_battery_most_charged if yesterday_data else None,
                "body_battery_current": yesterday_data.body_battery_current if yesterday_data else None,
                "body_battery_lowest": yesterday_data.body_battery_lowest if yesterday_data else None,
                "body_battery_drained": yesterday_data.body_battery_drained if yesterday_data else None,
            }
        }
        
        # 如果启用LLM，添加LLM分析
        if use_llm and yesterday_data:
            try:
                llm_result = await llm_analyzer.analyze_daily_health(
                    db=db,
                    user_id=user_id,
                    yesterday_data=yesterday_data,
                    recent_data=recent_data,
                    rule_analysis={
                        "sleep": sleep_analysis,
                        "activity": activity_analysis,
                        "heart_rate": heart_rate_analysis,
                        "stress": stress_analysis
                    }
                )
                result["llm_analysis"] = llm_result
                
                if llm_result.get("available") and "today_actions" in llm_result:
                    llm_actions = llm_result.get("today_actions", [])
                    existing_recs = set(priority_recommendations)
                    combined_recs = list(priority_recommendations)
                    for action in llm_actions:
                        if action not in existing_recs:
                            combined_recs.append(action)
                    result["enhanced_recommendations"] = combined_recs[:7]
                    
                    result["ai_insights"] = {
                        "health_summary": llm_result.get("summary", ""),
                        "key_insights": llm_result.get("insights", []),
                        "today_focus": llm_result.get("focus", ""),
                        "encouragement": llm_result.get("encouragement", ""),
                        "warnings": llm_result.get("warnings", [])
                    }
            except Exception as e:
                logger.error(f"LLM分析失败: {e}")
                result["llm_analysis"] = {"available": False, "error": str(e)}
        
        return result

