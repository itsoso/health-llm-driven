"""
空气质量数据服务

获取实时空气质量数据，用于健康建议生成
"""

import httpx
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AirQualityService:
    """
    空气质量数据服务

    支持:
    - 实时 AQI 查询
    - PM2.5、PM10 等污染物数据
    - 健康建议生成

    数据源优先级:
    1. 和风天气 Air Quality API v1 (精度 1x1km，含健康建议)
    2. aqicn.org (官方监测站数据)
    3. Open-Meteo (全球模型估算，作为备用)
    """

    # aqicn.org API
    AQICN_URL = "https://api.waqi.info/feed"

    # Open-Meteo Air Quality API (免费，作为备用)
    OPENMETEO_AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_duration = timedelta(minutes=30)  # 缓存30分钟

        # 从配置读取 API Token
        from app.config import settings
        self.aqicn_token = settings.aqicn_api_token or "demo"

        # 和风天气 Air Quality v1 配置
        self.qweather_api_key = settings.qweather_api_key
        qweather_host = settings.qweather_api_host
        if qweather_host:
            self.qweather_air_base_url = f"https://{qweather_host}/airquality/v1"
        else:
            self.qweather_air_base_url = "https://api.qweather.com/airquality/v1"

        if self.qweather_api_key:
            logger.info(f"✅ 空气质量服务初始化完成 (主数据源: 和风天气 Air Quality v1, host: {qweather_host or 'api.qweather.com'})")
        elif self.aqicn_token == "demo":
            logger.warning("⚠️ 使用 aqicn.org demo token，数据可能不准确。建议配置 AQICN_API_TOKEN 环境变量")
        else:
            logger.info("✅ 空气质量服务初始化完成 (使用正式 API Token)")

    def _get_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """获取缓存"""
        if key in self._cache:
            if datetime.now() - self._cache_time.get(key, datetime.min) < self._cache_duration:
                return self._cache[key]
        return None

    def _set_cache(self, key: str, data: Dict[str, Any]):
        """设置缓存"""
        self._cache[key] = data
        self._cache_time[key] = datetime.now()

    def invalidate_cache_for(
        self, city: Optional[str] = None, lat: Optional[float] = None, lon: Optional[float] = None
    ) -> int:
        """清掉指定 city / 经纬度的缓存. 用户改 location 时调."""
        cleared = 0
        for key in list(self._cache.keys()):
            match_city = city and (city in key)
            match_coord = lat is not None and lon is not None and f"{lat},{lon}" in key
            if match_city or match_coord:
                self._cache.pop(key, None)
                self._cache_time.pop(key, None)
                cleared += 1
        return cleared

    async def get_air_quality(
        self,
        city: str = None,
        lat: float = None,
        lon: float = None
    ) -> Dict[str, Any]:
        """
        获取当前空气质量

        优先使用 aqicn.org (官方监测站数据)，失败时回退到 Open-Meteo

        Args:
            city: 城市名称
            lat, lon: 经纬度

        Returns:
            空气质量数据
        """
        if lat is None or lon is None:
            coords = self._city_to_coords(city)
            if coords is None:
                # 坐标未知就**不去取真 AQI** —— 用猜的坐标拿回来的是别处的真实数值,
                # 调用方无从分辨,等于编造。诚实降级: available=False。
                logger.info(f"无法解析城市 '{city}' 坐标, 返回 unavailable (不猜坐标)")
                return self._get_default_aqi(error=f"无法解析城市 '{city}' 的坐标,未获取空气质量")
            lat, lon = coords

        cache_key = f"aqi_{city or f'{lat},{lon}'}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        # 优先使用和风天气 Air Quality v1
        if self.qweather_api_key:
            try:
                result = await self._get_qweather_aqi(lat, lon)
                if result.get("available"):
                    self._set_cache(cache_key, result)
                    return result
            except Exception as e:
                logger.warning(f"和风天气 Air Quality v1 获取失败: {e}，尝试 aqicn.org")

        # 回退到 aqicn.org (官方监测站数据)
        try:
            result = await self._get_aqicn_aqi(city, lat, lon)
            if result.get("available"):
                self._set_cache(cache_key, result)
                return result
        except Exception as e:
            logger.warning(f"aqicn.org 获取失败: {e}，尝试 Open-Meteo")

        # 回退到 Open-Meteo
        try:
            result = await self._get_openmeteo_aqi(lat, lon)
            self._set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"获取空气质量数据失败: {e}")
            return self._get_default_aqi()

    async def _get_qweather_aqi(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        使用和风天气 Air Quality API v1 获取实时空气质量

        端点: /airquality/v1/current/{latitude}/{longitude}
        认证: Authorization: Bearer {api_key}
        精度: 1x1 公里
        """
        url = f"{self.qweather_air_base_url}/current/{lat:.2f}/{lon:.2f}"
        headers = {"X-QW-Api-Key": self.qweather_api_key}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers, timeout=10)

            if response.status_code == 403:
                logger.warning("和风天气 Air Quality v1 返回 403，当前订阅无空气质量权限")
                return {"available": False, "reason": "no_permission"}

            response.raise_for_status()
            data = response.json()

        indexes = data.get("indexes", [])
        pollutants = data.get("pollutants", [])

        if not indexes:
            return {"available": False}

        # 优先取中国标准 cn-mee，其次取第一个
        index = next((i for i in indexes if i.get("code") == "cn-mee"), indexes[0])

        aqi = int(index.get("aqi", 0))
        category = index.get("category", "")
        health = index.get("health", {})
        advice = health.get("advice", {})
        primary_pollutant = index.get("primaryPollutant") or {}

        # 解析污染物浓度
        def _get_pollutant(code: str) -> float:
            p = next((p for p in pollutants if p.get("code") == code), None)
            return p["concentration"]["value"] if p else 0.0

        pm25 = _get_pollutant("pm2p5")
        pm10 = _get_pollutant("pm10")
        o3 = _get_pollutant("o3")
        no2 = _get_pollutant("no2")
        so2 = _get_pollutant("so2")
        co = _get_pollutant("co")

        logger.info(f"和风天气 Air Quality v1: AQI={aqi}, 类别={category}, PM2.5={pm25}")

        return {
            "available": True,
            "source": "qweather-v1",
            "aqi": aqi,
            "aqi_level": self._aqi_to_level(aqi),
            "aqi_description": category or self._aqi_to_description(aqi),
            "primary_pollutant": primary_pollutant.get("name", ""),
            "pm25": pm25,
            "pm10": pm10,
            "o3": o3,
            "no2": no2,
            "so2": so2,
            "co": co,
            "update_time": data.get("metadata", {}).get("tag", ""),
            "health_effect": health.get("effect", ""),
            "advice_general": advice.get("generalPopulation", ""),
            "advice_sensitive": advice.get("sensitivePopulation", ""),
            "health_implications": health.get("effect") or self._get_health_implications(aqi),
            "exercise_advice": self._get_exercise_advice(aqi),
        }

    async def _get_aqicn_aqi(self, city: str, lat: float, lon: float) -> Dict[str, Any]:
        """
        使用 aqicn.org API 获取空气质量 (官方监测站数据)

        数据来源: 各地环保厅官方监测站
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 城市名到 aqicn ID 的映射
            city_mapping = {
                "杭州": "hangzhou",
                "北京": "beijing",
                "上海": "shanghai",
                "广州": "guangzhou",
                "深圳": "shenzhen",
                "南京": "nanjing",
                "成都": "chengdu",
                "武汉": "wuhan",
                "西安": "xian",
                "重庆": "chongqing",
                "苏州": "suzhou",
                "天津": "tianjin",
                "郑州": "zhengzhou",
                "长沙": "changsha",
                "青岛": "qingdao",
                "厦门": "xiamen",
                "宁波": "ningbo",
                "无锡": "wuxi",
                "合肥": "hefei",
                "福州": "fuzhou",
            }

            # 优先使用城市名查询，否则使用经纬度
            if city and city in city_mapping:
                query = city_mapping[city]
            elif lat and lon:
                query = f"geo:{lat};{lon}"
            else:
                # 默认使用杭州
                query = "hangzhou"

            logger.info(f"aqicn.org 查询: city={city}, query={query}, token={'正式' if self.aqicn_token != 'demo' else 'demo'}")
            url = f"{self.AQICN_URL}/{query}/?token={self.aqicn_token}"

            response = await client.get(url, timeout=10)
            data = response.json()

            if data.get("status") != "ok":
                logger.warning(f"aqicn.org 返回错误: {data}")
                return {"available": False}

            aqi_data = data.get("data", {})
            aqi = aqi_data.get("aqi", 0)

            # 解析各项污染物
            iaqi = aqi_data.get("iaqi", {})
            pm25 = iaqi.get("pm25", {}).get("v", 0)
            pm10 = iaqi.get("pm10", {}).get("v", 0)
            co = iaqi.get("co", {}).get("v", 0)
            no2 = iaqi.get("no2", {}).get("v", 0)
            so2 = iaqi.get("so2", {}).get("v", 0)
            o3 = iaqi.get("o3", {}).get("v", 0)

            # 获取监测站信息
            city_info = aqi_data.get("city", {})
            station_name = city_info.get("name", "")

            logger.info(f"aqicn.org 数据: {station_name}, AQI={aqi}, PM2.5={pm25}")

            # 检查返回的城市是否与请求的城市匹配 (仅 demo token 有此限制)
            if self.aqicn_token == "demo" and city and city != "上海" and "Shanghai" in station_name:
                logger.warning(f"aqicn.org demo token 限制: 请求 {city} 但返回上海数据，将使用 Open-Meteo")
                return {"available": False, "reason": "demo_token_limit"}

            return {
                "available": True,
                "source": "aqicn.org",
                "station": station_name,
                "aqi": int(aqi) if aqi else 0,
                "aqi_level": self._aqi_to_level(int(aqi) if aqi else 0),
                "aqi_description": self._aqi_to_description(int(aqi) if aqi else 0),
                "pm25": pm25,
                "pm10": pm10,
                "co": co,
                "no2": no2,
                "so2": so2,
                "o3": o3,
                "update_time": aqi_data.get("time", {}).get("s", ""),
                "health_implications": self._get_health_implications(int(aqi) if aqi else 0),
                "exercise_advice": self._get_exercise_advice(int(aqi) if aqi else 0)
            }

    async def _get_openmeteo_aqi(self, lat: float, lon: float) -> Dict[str, Any]:
        """使用 Open-Meteo API 获取空气质量"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {
                "latitude": lat,
                "longitude": lon,
                "current": "european_aqi,us_aqi,pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone",
                "timezone": "Asia/Shanghai"
            }

            response = await client.get(self.OPENMETEO_AQ_URL, params=params, timeout=10)
            data = response.json()

            current = data.get("current", {})

            # 使用美国 AQI 标准
            us_aqi = current.get("us_aqi", 0)
            pm25 = current.get("pm2_5", 0)
            pm10 = current.get("pm10", 0)

            return {
                "available": True,
                "source": "open-meteo",
                "aqi": us_aqi,
                "aqi_level": self._aqi_to_level(us_aqi),
                "aqi_description": self._aqi_to_description(us_aqi),
                "pm25": pm25,
                "pm10": pm10,
                "co": current.get("carbon_monoxide", 0),
                "no2": current.get("nitrogen_dioxide", 0),
                "so2": current.get("sulphur_dioxide", 0),
                "o3": current.get("ozone", 0),
                "update_time": current.get("time", ""),
                "health_implications": self._get_health_implications(us_aqi),
                "exercise_advice": self._get_exercise_advice(us_aqi)
            }

    def _aqi_to_level(self, aqi: int) -> str:
        """AQI 转等级"""
        if aqi <= 50:
            return "excellent"  # 优
        elif aqi <= 100:
            return "good"  # 良
        elif aqi <= 150:
            return "moderate"  # 轻度污染
        elif aqi <= 200:
            return "unhealthy"  # 中度污染
        elif aqi <= 300:
            return "very_unhealthy"  # 重度污染
        else:
            return "hazardous"  # 严重污染

    def _aqi_to_description(self, aqi: int) -> str:
        """AQI 转描述"""
        level_desc = {
            "excellent": "优",
            "good": "良",
            "moderate": "轻度污染",
            "unhealthy": "中度污染",
            "very_unhealthy": "重度污染",
            "hazardous": "严重污染"
        }
        return level_desc.get(self._aqi_to_level(aqi), "未知")

    def _get_health_implications(self, aqi: int) -> str:
        """获取健康影响说明"""
        if aqi <= 50:
            return "空气质量优良，对健康无影响"
        elif aqi <= 100:
            return "空气质量可接受，敏感人群可能有轻微不适"
        elif aqi <= 150:
            return "敏感人群可能出现健康症状，普通人群影响较小"
        elif aqi <= 200:
            return "所有人群可能开始出现健康影响，敏感人群影响加重"
        elif aqi <= 300:
            return "健康警告，所有人群可能出现较严重健康影响"
        else:
            return "健康紧急状况，所有人群都可能受到严重健康影响"

    def _get_exercise_advice(self, aqi: int) -> Dict[str, Any]:
        """获取运动建议"""
        if aqi <= 50:
            return {
                "outdoor_suitable": True,
                "level": "excellent",
                "advice": "空气质量优，非常适合户外运动",
                "recommended_activities": ["跑步", "骑行", "户外球类", "登山"]
            }
        elif aqi <= 100:
            return {
                "outdoor_suitable": True,
                "level": "good",
                "advice": "空气质量良好，适合户外运动",
                "recommended_activities": ["跑步", "骑行", "散步", "户外健身"]
            }
        elif aqi <= 150:
            return {
                "outdoor_suitable": False,
                "level": "moderate",
                "advice": "空气质量一般，敏感人群应减少户外运动",
                "recommended_activities": ["室内健身", "游泳", "瑜伽"],
                "caution": "有呼吸道疾病者应避免户外剧烈运动"
            }
        elif aqi <= 200:
            return {
                "outdoor_suitable": False,
                "level": "unhealthy",
                "advice": "空气质量较差，建议减少户外活动",
                "recommended_activities": ["室内健身", "瑜伽", "拉伸"],
                "caution": "所有人群应避免长时间户外运动"
            }
        elif aqi <= 300:
            return {
                "outdoor_suitable": False,
                "level": "very_unhealthy",
                "advice": "空气质量很差，应避免户外运动",
                "recommended_activities": ["室内轻度活动", "居家锻炼"],
                "caution": "建议佩戴口罩，减少外出"
            }
        else:
            return {
                "outdoor_suitable": False,
                "level": "hazardous",
                "advice": "空气质量极差，严禁户外运动",
                "recommended_activities": ["休息", "室内轻度拉伸"],
                "caution": "尽量待在室内，使用空气净化器"
            }

    def _city_to_coords(self, city: str) -> Optional[tuple]:
        """城市名转经纬度. 未知 city → None (而非硬编杭州坐标).

        2026-07-17 改: 对齐 weather_service._city_to_coords 在 2026-05-17 就做过的同一处
        修正 —— 本文件当时被漏掉了。老的默认杭州 (30.27, 120.16) 会拿**猜的坐标**去取
        **真的 AQI**,返回值里没有任何标记说坐标是猜的,调用方无从分辨。RhinitisSpecialist
        拿 AQI 做症状-环境因果归因,城市解析成省名("浙江",生产 10次/24h)时那条归因就是编的。
        现在统一返 None, caller 走 `_get_default_aqi()` 的诚实降级 (available=False)。
        """
        city_coords = {
            "北京": (39.9042, 116.4074),
            "上海": (31.2304, 121.4737),
            "广州": (23.1291, 113.2644),
            "深圳": (22.5431, 114.0579),
            "杭州": (30.2741, 120.1551),
            "南京": (32.0603, 118.7969),
            "成都": (30.5728, 104.0668),
            "武汉": (30.5928, 114.3055),
            "西安": (34.3416, 108.9398),
            "重庆": (29.4316, 106.9123),
        }
        if city in city_coords:
            return city_coords[city]
        logger.warning(f"城市 '{city}' 不在空气质量坐标映射中, 跳过 (不再默认杭州)")
        return None

    def _get_default_aqi(self, error: str = "无法获取空气质量数据") -> Dict[str, Any]:
        """返回默认空气质量数据.

        `available=False` 是给调用方的**诚实信号**:这里的 aqi/pm25 是占位常量,不是
        测得的真值。所有调用方都必须先判 `available` 再用数值 (env advisor / weather_service
        / api.environment / smart_plan / twin._fill_environment 均已如此)。
        """
        return {
            "available": False,
            "source": "default",
            "aqi": 50,
            "aqi_level": "good",
            "aqi_description": "良",
            "pm25": 0,
            "pm10": 0,
            "error": error,
        }

    def get_rhinitis_advice(self, aqi_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        为鼻炎患者生成空气质量相关建议

        Args:
            aqi_data: 空气质量数据

        Returns:
            鼻炎相关建议
        """
        if not aqi_data.get("available"):
            return {"advice": "空气质量数据不可用", "risk_level": "unknown"}

        aqi = aqi_data.get("aqi", 50)
        pm25 = aqi_data.get("pm25", 0)

        if aqi <= 50 and pm25 <= 35:
            return {
                "risk_level": "low",
                "advice": "空气质量好，鼻炎症状风险低",
                "recommendations": [
                    "可以适当开窗通风",
                    "适合户外活动"
                ]
            }
        elif aqi <= 100 or pm25 <= 75:
            return {
                "risk_level": "moderate",
                "advice": "空气质量一般，注意防护",
                "recommendations": [
                    "外出建议佩戴口罩",
                    "回家后及时洗鼻",
                    "保持室内空气净化"
                ]
            }
        else:
            return {
                "risk_level": "high",
                "advice": "空气质量差，鼻炎易加重",
                "recommendations": [
                    "尽量减少外出",
                    "必须外出时佩戴N95口罩",
                    "增加洗鼻频次",
                    "使用空气净化器",
                    "保持室内湿度适宜"
                ]
            }


# 单例实例
air_quality_service = AirQualityService()
