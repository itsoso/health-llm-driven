"""
环境健康建议服务

综合天气和空气质量数据，生成个性化健康建议
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from .weather_service import weather_service
from .air_quality_service import air_quality_service

logger = logging.getLogger(__name__)


class EnvironmentAdvisor:
    """
    环境健康建议服务
    
    综合分析天气、空气质量等环境因素，
    为用户生成个性化的健康和运动建议
    """
    
    def __init__(self):
        self.weather = weather_service
        self.air_quality = air_quality_service
        logger.info("环境建议服务初始化完成")
    
    async def get_comprehensive_advice(
        self,
        city: str = None,
        lat: float = None,
        lon: float = None,
        user_conditions: List[str] = None
    ) -> Dict[str, Any]:
        """
        获取综合环境健康建议
        
        Args:
            city: 城市名称
            lat, lon: 经纬度
            user_conditions: 用户健康状况列表（如 ["鼻炎", "哮喘"]）
            
        Returns:
            综合建议数据
        """
        user_conditions = user_conditions or []
        
        # 获取天气和空气质量数据
        weather_data = await self.weather.get_current_weather(city, lat, lon)
        aqi_data = await self.air_quality.get_air_quality(city, lat, lon)
        
        # 生成基础运动建议
        weather_advice = self.weather.get_exercise_advice(weather_data)
        aqi_advice = aqi_data.get("exercise_advice", {})
        
        # 综合评估户外运动适宜性
        outdoor_suitable = (
            weather_advice.get("suitable", True) and 
            aqi_advice.get("outdoor_suitable", True)
        )
        
        # 生成综合建议
        combined_advices = []
        warnings = []
        
        # 添加天气相关建议
        combined_advices.extend(weather_advice.get("advices", []))
        
        # 添加空气质量相关建议
        if aqi_advice.get("advice"):
            combined_advices.append(aqi_advice["advice"])
        if aqi_advice.get("caution"):
            warnings.append(aqi_advice["caution"])
        
        # 针对特定健康状况的建议
        condition_advices = self._get_condition_specific_advice(
            weather_data, aqi_data, user_conditions
        )
        combined_advices.extend(condition_advices.get("advices", []))
        warnings.extend(condition_advices.get("warnings", []))
        
        # 推荐活动
        if outdoor_suitable:
            recommended_activities = list(set(
                weather_advice.get("recommended_activities", []) or
                aqi_advice.get("recommended_activities", ["户外运动"])
            ))
        else:
            recommended_activities = aqi_advice.get("recommended_activities", ["室内运动"])
        
        # 计算综合评分
        overall_score = self._calculate_overall_score(weather_data, aqi_data)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "location": city or f"{lat},{lon}",
            "weather": {
                "available": weather_data.get("available", False),
                "temperature": weather_data.get("temperature"),
                "feels_like": weather_data.get("feels_like"),
                "humidity": weather_data.get("humidity"),
                "weather": weather_data.get("weather"),
                "wind_speed": weather_data.get("wind_speed"),
                "summary": weather_advice.get("weather_summary", "")
            },
            "air_quality": {
                "available": aqi_data.get("available", False),
                "aqi": aqi_data.get("aqi"),
                "level": aqi_data.get("aqi_level"),
                "description": aqi_data.get("aqi_description"),
                "pm25": aqi_data.get("pm25"),
                "health_implications": aqi_data.get("health_implications")
            },
            "exercise": {
                "outdoor_suitable": outdoor_suitable,
                "score": overall_score,
                "status": self._score_to_status(overall_score),
                "recommended_activities": recommended_activities[:5]
            },
            "advices": list(set(combined_advices))[:6],
            "warnings": list(set(warnings)),
            "condition_specific": condition_advices.get("details", {})
        }
    
    def _get_condition_specific_advice(
        self,
        weather: Dict[str, Any],
        aqi: Dict[str, Any],
        conditions: List[str]
    ) -> Dict[str, Any]:
        """针对特定健康状况生成建议"""
        advices = []
        warnings = []
        details = {}
        
        for condition in conditions:
            condition_lower = condition.lower()
            
            # 鼻炎相关
            if "鼻炎" in condition or "过敏" in condition:
                rhinitis_advice = self.air_quality.get_rhinitis_advice(aqi)
                details["鼻炎"] = rhinitis_advice
                advices.extend(rhinitis_advice.get("recommendations", []))
                
                if rhinitis_advice.get("risk_level") == "high":
                    warnings.append("⚠️ 空气质量差，鼻炎患者需特别注意防护")
                
                # 天气相关的鼻炎建议
                temp = weather.get("temperature", 20)
                humidity = weather.get("humidity", 50)
                
                if temp < 10:
                    advices.append("天气寒冷，外出注意保暖防止鼻炎加重")
                if humidity < 40:
                    advices.append("空气干燥，建议使用加湿器，保持鼻腔湿润")
            
            # 哮喘相关
            if "哮喘" in condition:
                aqi_val = aqi.get("aqi", 50)
                if aqi_val > 100:
                    warnings.append("⚠️ 空气质量不佳，哮喘患者应避免户外活动")
                    advices.append("随身携带哮喘急救药物")
                details["哮喘"] = {
                    "risk_level": "high" if aqi_val > 100 else "moderate" if aqi_val > 50 else "low",
                    "advice": "空气质量影响呼吸，请注意防护"
                }
            
            # 心血管疾病相关
            if "心脏" in condition or "高血压" in condition or "心血管" in condition:
                temp = weather.get("temperature", 20)
                if temp < 5 or temp > 35:
                    warnings.append("⚠️ 极端温度可能加重心血管负担")
                    advices.append("避免在极端天气下进行剧烈运动")
                details["心血管"] = {
                    "risk_level": "high" if temp < 5 or temp > 35 else "moderate",
                    "advice": "注意温度变化对心血管的影响"
                }
            
            # 关节炎相关
            if "关节" in condition or "风湿" in condition:
                humidity = weather.get("humidity", 50)
                weather_text = weather.get("weather", "")
                if humidity > 80 or "雨" in weather_text:
                    advices.append("湿度较高，关节可能不适，注意保暖")
                details["关节"] = {
                    "risk_level": "moderate" if humidity > 70 else "low",
                    "advice": "潮湿天气注意关节保暖"
                }
        
        return {
            "advices": advices,
            "warnings": warnings,
            "details": details
        }
    
    def _calculate_overall_score(
        self,
        weather: Dict[str, Any],
        aqi: Dict[str, Any]
    ) -> int:
        """
        计算综合户外运动适宜性评分 (0-100)
        """
        score = 100
        
        # 天气评分
        if weather.get("available"):
            temp = weather.get("temperature", 20)
            humidity = weather.get("humidity", 50)
            wind_speed = weather.get("wind_speed", 0)
            weather_text = weather.get("weather", "")
            
            # 温度评分
            if 15 <= temp <= 25:
                pass  # 最佳温度
            elif 10 <= temp < 15 or 25 < temp <= 30:
                score -= 10
            elif 5 <= temp < 10 or 30 < temp <= 35:
                score -= 25
            else:
                score -= 40
            
            # 湿度评分
            if humidity > 85 or humidity < 30:
                score -= 10
            
            # 风速评分
            if wind_speed > 40:
                score -= 20
            elif wind_speed > 25:
                score -= 10
            
            # 天气状况
            bad_conditions = ["雨", "雪", "雷", "暴", "雾", "霾"]
            for condition in bad_conditions:
                if condition in weather_text:
                    score -= 25
                    break
        
        # 空气质量评分
        if aqi.get("available"):
            aqi_val = aqi.get("aqi", 50)
            if aqi_val <= 50:
                pass  # 优
            elif aqi_val <= 100:
                score -= 10
            elif aqi_val <= 150:
                score -= 25
            elif aqi_val <= 200:
                score -= 40
            else:
                score -= 50
        
        return max(0, min(100, score))
    
    def _score_to_status(self, score: int) -> str:
        """评分转状态"""
        if score >= 80:
            return "excellent"
        elif score >= 60:
            return "good"
        elif score >= 40:
            return "moderate"
        elif score >= 20:
            return "poor"
        else:
            return "not_recommended"
    
    async def get_morning_briefing(
        self,
        city: str = None,
        lat: float = None,
        lon: float = None,
        user_conditions: List[str] = None
    ) -> Dict[str, Any]:
        """
        获取早间健康简报
        
        适合每天早上推送给用户的环境健康信息
        """
        advice = await self.get_comprehensive_advice(city, lat, lon, user_conditions)
        
        # 生成简报文本
        weather_summary = advice["weather"].get("summary", "")
        aqi_desc = advice["air_quality"].get("description", "")
        aqi_val = advice["air_quality"].get("aqi", "")
        
        briefing_parts = []
        
        # 天气摘要
        if weather_summary:
            briefing_parts.append(f"今日天气：{weather_summary}")
        
        # 空气质量
        if aqi_desc and aqi_val:
            briefing_parts.append(f"空气质量：{aqi_desc}（AQI {aqi_val}）")
        
        # 运动建议
        if advice["exercise"]["outdoor_suitable"]:
            briefing_parts.append("✅ 适合户外运动")
        else:
            briefing_parts.append("❌ 不建议户外运动，推荐室内活动")
        
        # 重要提醒
        if advice.get("warnings"):
            briefing_parts.append("⚠️ 注意：" + "；".join(advice["warnings"][:2]))
        
        return {
            "briefing": "\n".join(briefing_parts),
            "outdoor_score": advice["exercise"]["score"],
            "key_advice": advice["advices"][0] if advice["advices"] else "祝您健康愉快！",
            "full_data": advice
        }


# 单例实例
environment_advisor = EnvironmentAdvisor()
