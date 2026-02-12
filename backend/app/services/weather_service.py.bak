"""天气和空气质量服务"""
import httpx
from typing import Optional, Dict, Any
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class WeatherService:
    """和风天气 API 服务"""

    def __init__(self):
        self.api_key = settings.qweather_api_key
        self.api_type = settings.qweather_api_type
        # 免费版使用 devapi，付费版使用 api
        self.base_url = "https://devapi.qweather.com" if self.api_type == "free" else "https://api.qweather.com"

    async def get_location_id(self, city: str = None, latitude: float = None, longitude: float = None) -> Optional[str]:
        """
        获取位置 ID（和风天气使用 LocationID 查询）
        优先使用经纬度，其次使用城市名
        """
        if not self.api_key:
            logger.warning("QWeather API key not configured")
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if latitude is not None and longitude is not None:
                    # 使用经纬度查询
                    url = f"{self.base_url}/v2/city/lookup"
                    params = {
                        "location": f"{longitude},{latitude}",
                        "key": self.api_key
                    }
                elif city:
                    # 使用城市名查询
                    url = f"{self.base_url}/v2/city/lookup"
                    params = {
                        "location": city,
                        "key": self.api_key
                    }
                else:
                    return None

                response = await client.get(url, params=params)
                data = response.json()

                if data.get("code") == "200" and data.get("location"):
                    return data["location"][0]["id"]

                return None

        except Exception as e:
            logger.error(f"Failed to get location ID: {e}")
            return None

    async def get_weather(
        self,
        city: str = None,
        latitude: float = None,
        longitude: float = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取实时天气
        返回格式：{
            "temperature": 25.0,  # 摄氏度
            "feels_like": 27.0,   # 体感温度
            "humidity": 65,       # 湿度 %
            "weather_condition": "晴",
            "weather_description": "晴朗",
            "wind_speed": 12.0,   # km/h
            "wind_direction": "东南风",
            "pressure": 1013,     # hPa
            "visibility": 10,     # km
            "uv_index": 5
        }
        """
        if not self.api_key:
            logger.warning("QWeather API key not configured")
            return None

        try:
            # 获取 Location ID
            location_id = await self.get_location_id(city, latitude, longitude)
            if not location_id:
                logger.warning(f"Could not find location for city={city}, lat={latitude}, lon={longitude}")
                return None

            # 获取实时天气
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"{self.base_url}/v7/weather/now"
                params = {
                    "location": location_id,
                    "key": self.api_key
                }

                response = await client.get(url, params=params)
                data = response.json()

                if data.get("code") != "200":
                    logger.error(f"QWeather API error: {data}")
                    return None

                now = data.get("now", {})
                return {
                    "temperature": float(now.get("temp", 0)),
                    "feels_like": float(now.get("feelsLike", now.get("temp", 0))),
                    "humidity": int(now.get("humidity", 0)),
                    "weather_condition": now.get("text", ""),
                    "weather_description": now.get("text", ""),
                    "wind_speed": float(now.get("windSpeed", 0)),
                    "wind_direction": now.get("windDir", ""),
                    "pressure": int(now.get("pressure", 0)),
                    "visibility": int(now.get("vis", 0)),
                    "uv_index": int(now.get("uvIndex", 0))
                }

        except Exception as e:
            logger.error(f"Failed to get weather: {e}")
            return None

    async def get_air_quality(
        self,
        city: str = None,
        latitude: float = None,
        longitude: float = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取空气质量
        返回格式：{
            "aqi": 55,
            "pm25": 35.0,
            "pm10": 50.0,
            "no2": 25.0,
            "so2": 10.0,
            "co": 0.5,
            "o3": 60.0,
            "quality_level": "良",  # 优/良/轻度污染/中度污染/重度污染/严重污染
            "health_tip": "空气质量可接受，但某些污染物可能对极少数异常敏感人群健康有较弱影响"
        }
        """
        if not self.api_key:
            logger.warning("QWeather API key not configured")
            return None

        try:
            # 获取 Location ID
            location_id = await self.get_location_id(city, latitude, longitude)
            if not location_id:
                return None

            # 获取空气质量
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"{self.base_url}/v7/air/now"
                params = {
                    "location": location_id,
                    "key": self.api_key
                }

                response = await client.get(url, params=params)
                data = response.json()

                if data.get("code") != "200":
                    logger.error(f"QWeather Air API error: {data}")
                    return None

                now = data.get("now", {})
                return {
                    "aqi": int(now.get("aqi", 0)),
                    "pm25": float(now.get("pm2p5", 0)),
                    "pm10": float(now.get("pm10", 0)),
                    "no2": float(now.get("no2", 0)),
                    "so2": float(now.get("so2", 0)),
                    "co": float(now.get("co", 0)),
                    "o3": float(now.get("o3", 0)),
                    "quality_level": now.get("category", ""),
                    "health_tip": self._get_health_tip(int(now.get("aqi", 0)))
                }

        except Exception as e:
            logger.error(f"Failed to get air quality: {e}")
            return None

    def _get_health_tip(self, aqi: int) -> str:
        """根据 AQI 值返回健康建议"""
        if aqi <= 50:
            return "空气质量令人满意，基本无空气污染"
        elif aqi <= 100:
            return "空气质量可接受，但某些污染物可能对极少数异常敏感人群健康有较弱影响"
        elif aqi <= 150:
            return "易感人群症状有轻度加剧，健康人群出现刺激症状。建议儿童、老年人及心脏病、呼吸系统疾病患者应减少长时间、高强度的户外锻炼"
        elif aqi <= 200:
            return "进一步加剧易感人群症状，可能对健康人群心脏、呼吸系统有影响。建议疾病患者避免长时间、高强度的户外锻炼，一般人群适量减少户外运动"
        elif aqi <= 300:
            return "心脏病和肺病患者症状显著加剧，运动耐受力降低，健康人群普遍出现症状。建议儿童、老年人和心脏病、肺病患者应停留在室内，停止户外运动，一般人群减少户外运动"
        else:
            return "健康人群运动耐受力降低，有明显强烈症状，提前出现某些疾病。建议儿童、老年人和病人应当留在室内，避免体力消耗，一般人群应避免户外活动"

    async def get_comprehensive_context(
        self,
        city: str = None,
        latitude: float = None,
        longitude: float = None
    ) -> Dict[str, Any]:
        """
        获取完整的天气和空气质量上下文
        返回：{
            "weather": {...},
            "air_quality": {...},
            "location": {"city": "北京", "latitude": 39.9, "longitude": 116.4}
        }
        """
        weather = await self.get_weather(city, latitude, longitude)
        air_quality = await self.get_air_quality(city, latitude, longitude)

        return {
            "weather": weather,
            "air_quality": air_quality,
            "location": {
                "city": city,
                "latitude": latitude,
                "longitude": longitude
            }
        }


# 创建全局实例
weather_service = WeatherService()
