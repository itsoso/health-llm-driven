"""每日健康分析与建议服务"""
from datetime import date, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from app.models.daily_health import GarminData
from app.models.user import User
from app.models.basic_health import BasicHealthData
from app.services.llm_health_analyzer import llm_analyzer
import logging

logger = logging.getLogger(__name__)


class DailyRecommendationService:
    """
    每日健康分析与建议服务
    
    基于前一天的Garmin数据（睡眠、运动、心率等），
    生成今天的个性化健康建议
    """
    
    def get_yesterday_data(
        self,
        db: Session,
        user_id: int,
        reference_date: Optional[date] = None
    ) -> Optional[GarminData]:
        """获取昨天的Garmin数据"""
        if reference_date is None:
            reference_date = date.today()
        
        yesterday = reference_date - timedelta(days=1)
        
        return db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == yesterday
        ).first()
    
    def get_recent_data(
        self,
        db: Session,
        user_id: int,
        days: int = 7
    ) -> List[GarminData]:
        """获取最近N天的数据用于趋势分析"""
        end_date = date.today() - timedelta(days=1)
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
        
        Returns:
            包含睡眠、活动、心率、压力分析和综合建议的完整报告
        """
        if reference_date is None:
            reference_date = date.today()
        
        yesterday = self.get_yesterday_data(db, user_id, reference_date)
        recent_data = self.get_recent_data(db, user_id, 7)
        
        # 获取用户信息
        user = db.query(User).filter(User.id == user_id).first()
        
        if not yesterday:
            return {
                "status": "no_data",
                "message": "暂无昨日数据",
                "date": (reference_date - timedelta(days=1)).isoformat(),
                "user": user.name if user else None,
                "sleep_analysis": None,
                "activity_analysis": None,
                "heart_rate_analysis": None,
                "stress_analysis": None,
                "overall_status": "unknown",
                "priority_recommendations": ["请先同步Garmin数据"],
                "daily_goals": []
            }
        
        # 各项分析
        sleep_analysis = self.analyze_sleep(yesterday, recent_data)
        activity_analysis = self.analyze_activity(yesterday, recent_data)
        heart_rate_analysis = self.analyze_heart_rate(yesterday, recent_data)
        stress_analysis = self.analyze_stress_and_energy(yesterday)
        
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
            yesterday, sleep_analysis, activity_analysis, stress_analysis
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
            "date": yesterday.record_date.isoformat(),
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
                "sleep_score": yesterday.sleep_score,
                "sleep_duration_minutes": yesterday.total_sleep_duration,
                "steps": yesterday.steps,
                "resting_heart_rate": yesterday.resting_heart_rate,
                "stress_level": yesterday.stress_level,
                "body_battery_highest": yesterday.body_battery_most_charged
            },
            # 保存分析上下文供LLM使用
            "_rule_analysis": rule_analysis,
            "_yesterday_data": yesterday,
            "_recent_data": recent_data
        }
    
    def generate_daily_summary_with_llm(
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
        yesterday_data = rule_result.pop("_yesterday_data", None)
        recent_data = rule_result.pop("_recent_data", [])
        rule_analysis = rule_result.pop("_rule_analysis", {})
        
        # 执行LLM分析
        llm_result = llm_analyzer.analyze_daily_health(
            db=db,
            user_id=user_id,
            yesterday_data=yesterday_data,
            recent_data=recent_data,
            rule_analysis=rule_analysis
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
                "recovery": llm_result.get("recovery_advice")
            }
        
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
        yesterday: GarminData,
        sleep: Dict,
        activity: Dict,
        stress: Dict
    ) -> List[Dict[str, Any]]:
        """生成今日目标"""
        goals = []
        
        # 步数目标
        yesterday_steps = yesterday.steps or 0
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

