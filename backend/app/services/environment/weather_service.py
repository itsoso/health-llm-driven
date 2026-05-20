"""
天气数据服务

使用和风天气 API 或其他天气服务获取实时天气数据
"""

import httpx
import logging
import os
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from functools import lru_cache
import asyncio

logger = logging.getLogger(__name__)


def _qweather_error_message(data: Dict[str, Any], location: str) -> str:
    """qweather 把错误返成两种 shape: 老的 `{code: "404", ...}` 和新的
    `{error: {status, title, detail, ...}}`. 老 raise 只取 `code` 一字段,
    新 shape code 是 None 时日志就是 "API 返回错误: None" — 完全无法定位.
    这里两路都吃, 给出可读的诊断字符串."""
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        title = err.get("title") or err.get("type") or "unknown"
        status = err.get("status") or "?"
        detail = err.get("detail") or ""
        return f"qweather error: {title} (status={status}, location={location!r}) {detail}".strip()
    return f"qweather error: code={data.get('code')!r} location={location!r}"


class WeatherService:
    """
    天气数据服务

    支持:
    - 实时天气查询
    - 天气预报
    - 生活指数（运动、穿衣、紫外线等）
    - 空气质量查询（和风天气 API）
    """

    # 和风天气 API
    # 免费版: https://devapi.qweather.com/v7
    # 商用版: https://api.qweather.com/v7
    # 自定义Host: https://your-host.qweatherapi.com/v7
    QWEATHER_BASE_URL = "https://api.qweather.com/v7"
    QWEATHER_GEO_URL = "https://geoapi.qweather.com/v2"
    # 备用：Open-Meteo 免费 API（无需 key）
    OPENMETEO_BASE_URL = "https://api.open-meteo.com/v1"

    def __init__(self, api_key: Optional[str] = None, api_type: str = "free", api_host: Optional[str] = None):
        """
        初始化天气服务

        Args:
            api_key: 和风天气 API Key（可选，不提供则使用 Open-Meteo）
            api_type: API类型，"free" 或 "premium"（商用版）
            api_host: 自定义API Host（如：abc.qweatherapi.com）
        """
        self.api_key = api_key
        self.api_type = api_type
        self._cache: Dict[str, Any] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_duration = timedelta(minutes=30)  # 缓存30分钟
        self._geo_cache: Dict[str, dict] = {}  # GeoAPI 城市查找缓存

        # 根据API Host或类型选择URL
        # 注意 (2026-05-20): 客户专属 host (`*.re.qweatherapi.com`) 只代理 /v7 不代理
        # /v2/city/lookup → GeoAPI 永远走公用 host, 否则 city 名查 ID 全 404, 最终
        # 导致 weather/now 用脏 location 串失败, 日志刷 "API 返回错误: None".
        if api_host:
            # 使用自定义API Host（推荐方式）
            self.QWEATHER_BASE_URL = f"https://{api_host}/v7"
            self.QWEATHER_GEO_URL = "https://geoapi.qweather.com/v2"
            logger.info(f"天气服务初始化完成 (使用自定义API Host: {api_host}, GeoAPI 走公用 host)")
        elif api_type == "premium":
            self.QWEATHER_BASE_URL = "https://api.qweather.com/v7"
            self.QWEATHER_GEO_URL = "https://geoapi.qweather.com/v2"
            logger.info(f"天气服务初始化完成 (使用和风天气 PREMIUM API)")
        else:
            self.QWEATHER_BASE_URL = "https://devapi.qweather.com/v7"
            self.QWEATHER_GEO_URL = "https://geoapi.qweather.com/v2"
            logger.info(f"天气服务初始化完成 (使用和风天气 FREE API)")

        if not api_key:
            logger.info("天气服务初始化完成 (使用 Open-Meteo 免费 API)")

    def _get_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """获取缓存数据"""
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
        """清掉指定 city / 经纬度的所有缓存条目 (含 weather/forecast/aqi).

        用户改地理位置时调, 强制下次拉新数据.
        """
        cleared = 0
        keys_to_drop = []
        for key in list(self._cache.keys()):
            # 缓存 key 格式: 'weather_<city>' / 'forecast_<city>_<days>' / 'aqi_<city>' /
            #                'weather_<lat>,<lon>' 等
            match_city = city and (city in key)
            match_coord = lat is not None and lon is not None and f"{lat},{lon}" in key
            if match_city or match_coord:
                keys_to_drop.append(key)
        for k in keys_to_drop:
            self._cache.pop(k, None)
            self._cache_time.pop(k, None)
            cleared += 1
        if cleared:
            logger.info(f"[weather] 清除缓存 {cleared} 条 (city={city}, lat={lat}, lon={lon})")
        return cleared

    def invalidate_all_cache(self) -> int:
        """清掉所有天气/AQI 缓存. 用户大幅改 location (e.g. 跨城市) 时用."""
        n = len(self._cache)
        self._cache.clear()
        self._cache_time.clear()
        logger.info(f"[weather] 全量清除缓存 {n} 条")
        return n

    async def get_current_weather(
        self,
        city: str = None,
        lat: float = None,
        lon: float = None
    ) -> Dict[str, Any]:
        """
        获取当前天气

        Args:
            city: 城市名称（如：北京、上海）
            lat: 纬度（与 lon 一起使用）
            lon: 经度

        Returns:
            天气数据字典
        """
        cache_key = f"weather_{city or f'{lat},{lon}'}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            if self.api_key:
                # 使用和风天气
                result = await self._get_qweather_current(city, lat, lon)
            else:
                # 使用 Open-Meteo (免费，需要经纬度)
                if lat is None or lon is None:
                    coords = self._city_to_coords(city)
                    if coords is None:
                        logger.info(f"无法解析城市 '{city}' 坐标, 返回 unavailable")
                        return self._get_default_weather()
                    lat, lon = coords
                result = await self._get_openmeteo_current(lat, lon)

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"获取天气数据失败: {e}")
            return self._get_default_weather()

    async def get_weather_forecast(
        self,
        city: str = None,
        lat: float = None,
        lon: float = None,
        days: int = 3
    ) -> Dict[str, Any]:
        """
        获取天气预报

        Args:
            city: 城市名称
            lat, lon: 经纬度
            days: 预报天数

        Returns:
            天气预报数据
        """
        cache_key = f"forecast_{city or f'{lat},{lon}'}_{days}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            if self.api_key:
                # 使用和风天气API
                result = await self._get_qweather_forecast(city, lat, lon, days)
            else:
                # 使用Open-Meteo作为备用
                if lat is None or lon is None:
                    coords = self._city_to_coords(city)
                    if coords is None:
                        logger.info(f"无法解析城市 '{city}' 坐标, 返回空预报")
                        return {"available": False, "forecasts": [], "source": "unknown"}
                    lat, lon = coords
                result = await self._get_openmeteo_forecast(lat, lon, days)

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"获取天气预报失败: {e}")
            return {"available": False, "error": str(e)}

    async def _get_qweather_current(
        self,
        city: str = None,
        lat: float = None,
        lon: float = None
    ) -> Dict[str, Any]:
        """使用和风天气 API 获取当前天气"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 和风天气API需要Location ID或经纬度
            if city:
                location = await self._city_to_location_id_async(city)
            else:
                location = f"{lon},{lat}"

            url = f"{self.QWEATHER_BASE_URL}/weather/now"
            params = {
                "location": location,
                "key": self.api_key
            }

            response = await client.get(url, params=params, timeout=10)
            data = response.json()

            if data.get("code") == "200":
                now = data.get("now", {})
                return {
                    "available": True,
                    "source": "qweather",
                    "temperature": float(now.get("temp", 0)),
                    "feels_like": float(now.get("feelsLike", 0)),
                    "humidity": int(now.get("humidity", 0)),
                    "weather": now.get("text", ""),
                    "weather_code": now.get("icon", ""),
                    "wind_direction": now.get("windDir", ""),
                    "wind_speed": float(now.get("windSpeed", 0)),
                    "visibility": float(now.get("vis", 10)),
                    "pressure": float(now.get("pressure", 1013)),
                    "update_time": data.get("updateTime", "")
                }
            else:
                raise Exception(_qweather_error_message(data, location))

    async def _get_qweather_forecast(
        self,
        city: str = None,
        lat: float = None,
        lon: float = None,
        days: int = 3
    ) -> Dict[str, Any]:
        """使用和风天气API获取天气预报"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 和风天气API需要Location ID或经纬度
            if city:
                location = await self._city_to_location_id_async(city)
            else:
                location = f"{lon},{lat}"

            # 和风天气API只支持 3, 7, 10, 15, 30 天预报
            # 将请求天数映射到支持的天数
            if days <= 3:
                api_days = 3
            elif days <= 7:
                api_days = 7
            elif days <= 10:
                api_days = 10
            elif days <= 15:
                api_days = 15
            else:
                api_days = 30

            url = f"{self.QWEATHER_BASE_URL}/weather/{api_days}d"
            params = {
                "location": location,
                "key": self.api_key
            }

            response = await client.get(url, params=params, timeout=10)
            data = response.json()

            if data.get("code") == "200":
                daily = data.get("daily", [])
                forecasts = []

                for day in daily[:days]:
                    forecasts.append({
                        "date": day.get("fxDate", ""),
                        "weather": day.get("textDay", ""),
                        "weather_code": day.get("iconDay", ""),
                        "temp_max": float(day.get("tempMax", 0)),
                        "temp_min": float(day.get("tempMin", 0)),
                        "feels_like_max": float(day.get("tempMax", 0)),  # 和风天气预报没有体感温度
                        "feels_like_min": float(day.get("tempMin", 0)),
                        "precipitation_probability": int(float(day.get("precip", 0))),
                        "uv_index": int(float(day.get("uvIndex", 0)))
                    })

                return {
                    "available": True,
                    "source": "qweather",
                    "forecasts": forecasts
                }
            else:
                raise Exception(_qweather_error_message(data, location))

    async def _get_openmeteo_current(self, lat: float, lon: float) -> Dict[str, Any]:
        """使用 Open-Meteo API 获取当前天气（免费，无需 API Key）"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{self.OPENMETEO_BASE_URL}/forecast"
            params = {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m,surface_pressure",
                "timezone": "Asia/Shanghai"
            }

            response = await client.get(url, params=params, timeout=10)
            data = response.json()

            current = data.get("current", {})

            return {
                "available": True,
                "source": "open-meteo",
                "temperature": current.get("temperature_2m", 0),
                "feels_like": current.get("apparent_temperature", 0),
                "humidity": current.get("relative_humidity_2m", 0),
                "weather": self._weather_code_to_text(current.get("weather_code", 0)),
                "weather_code": current.get("weather_code", 0),
                "wind_direction": self._wind_direction_to_text(current.get("wind_direction_10m", 0)),
                "wind_speed": current.get("wind_speed_10m", 0),
                "pressure": current.get("surface_pressure", 1013),
                "update_time": current.get("time", "")
            }

    async def _get_openmeteo_forecast(self, lat: float, lon: float, days: int) -> Dict[str, Any]:
        """获取天气预报"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{self.OPENMETEO_BASE_URL}/forecast"
            params = {
                "latitude": lat,
                "longitude": lon,
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,precipitation_probability_max,uv_index_max",
                "timezone": "Asia/Shanghai",
                "forecast_days": days
            }

            response = await client.get(url, params=params, timeout=10)
            data = response.json()

            daily = data.get("daily", {})
            dates = daily.get("time", [])

            forecasts = []
            for i, date in enumerate(dates):
                forecasts.append({
                    "date": date,
                    "weather": self._weather_code_to_text(daily.get("weather_code", [])[i] if i < len(daily.get("weather_code", [])) else 0),
                    "weather_code": daily.get("weather_code", [])[i] if i < len(daily.get("weather_code", [])) else 0,
                    "temp_max": daily.get("temperature_2m_max", [])[i] if i < len(daily.get("temperature_2m_max", [])) else 0,
                    "temp_min": daily.get("temperature_2m_min", [])[i] if i < len(daily.get("temperature_2m_min", [])) else 0,
                    "feels_like_max": daily.get("apparent_temperature_max", [])[i] if i < len(daily.get("apparent_temperature_max", [])) else 0,
                    "feels_like_min": daily.get("apparent_temperature_min", [])[i] if i < len(daily.get("apparent_temperature_min", [])) else 0,
                    "precipitation_probability": daily.get("precipitation_probability_max", [])[i] if i < len(daily.get("precipitation_probability_max", [])) else 0,
                    "uv_index": daily.get("uv_index_max", [])[i] if i < len(daily.get("uv_index_max", [])) else 0
                })

            return {
                "available": True,
                "source": "open-meteo",
                "forecasts": forecasts
            }

    async def _lookup_city_via_geoapi(self, city: str) -> Optional[dict]:
        """
        通过和风天气 GeoAPI 动态查找城市信息

        Returns:
            {"id": "101210101", "name": "杭州", "lat": "30.28", "lon": "120.15"} or None
        """
        if not self.api_key:
            return None

        # 检查缓存
        if city in self._geo_cache:
            return self._geo_cache[city]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"{self.QWEATHER_GEO_URL}/city/lookup"
                params = {
                    "location": city,
                    "key": self.api_key,
                    "number": 1,
                    "range": "cn",  # 限定中国
                }
                response = await client.get(url, params=params, timeout=10)
                if response.status_code != 200:
                    logger.info(f"GeoAPI HTTP {response.status_code}，城市 '{city}' 将使用备用映射")
                    self._geo_cache[city] = None
                    return None
                data = response.json()

                if data.get("code") == "200" and data.get("location"):
                    loc = data["location"][0]
                    result = {
                        "id": loc.get("id", ""),
                        "name": loc.get("name", city),
                        "lat": loc.get("lat", ""),
                        "lon": loc.get("lon", ""),
                    }
                    self._geo_cache[city] = result
                    logger.info(f"GeoAPI 查找成功: {city} → id={result['id']}, ({result['lat']},{result['lon']})")
                    return result
                else:
                    logger.warning(f"GeoAPI 查找失败: {city}, code={data.get('code')}")
                    self._geo_cache[city] = None
                    return None
        except Exception as e:
            logger.warning(f"GeoAPI 查找异常: {city}, error={e}")
            return None

    def _city_to_location_id_sync(self, city: str) -> str:
        """城市名转和风天气Location ID（同步版，仅用硬编码映射）"""
        return self._CITY_LOCATION_IDS.get(city, "")

    async def _city_to_location_id_async(self, city: str) -> str:
        """城市名转和风天气Location ID（异步版，支持GeoAPI动态查找）"""
        # 先查硬编码映射
        if city in self._CITY_LOCATION_IDS:
            return self._CITY_LOCATION_IDS[city]

        # 通过GeoAPI动态查找
        geo = await self._lookup_city_via_geoapi(city)
        if geo and geo.get("id"):
            return geo["id"]

        logger.warning(f"城市 '{city}' 未找到 Location ID，尝试直接使用城市名查询")
        return city  # 和风天气也支持直接用城市名

    # 硬编码城市映射（常用城市快速查找，避免GeoAPI调用）
    _CITY_LOCATION_IDS = {
        "北京": "101010100",
        "上海": "101020100",
        "广州": "101280101",
        "深圳": "101280601",
        "杭州": "101210101",
        "南京": "101190101",
        "成都": "101270101",
        "武汉": "101200101",
        "西安": "101110101",
        "重庆": "101040100",
        "天津": "101030100",
        "苏州": "101190401",
        "青岛": "101120201",
        "大连": "101070201",
        "厦门": "101230201",
        "长沙": "101250101",
        "郑州": "101180101",
        "宁波": "101210401",
        "无锡": "101190201",
        "合肥": "101220101",
        "福州": "101230101",
        "昆明": "101290101",
        "哈尔滨": "101050101",
        "沈阳": "101070101",
        "长春": "101060101",
        "济南": "101120101",
        "石家庄": "101090101",
        "太原": "101100101",
        "兰州": "101160101",
        "拉萨": "101140101",
        "银川": "101170101",
        "乌鲁木齐": "101130101",
        "呼和浩特": "101080101",
        "南宁": "101300101",
        "贵阳": "101260101",
        "海口": "101310101",
        "三亚": "101310201",
        "珠海": "101280701",
        "江油": "101272305",
        "绵阳": "101270401",
    }

    _CITY_COORDS = {
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
        "天津": (39.0842, 117.2009),
        "苏州": (31.2989, 120.5853),
        "青岛": (36.0671, 120.3826),
        "大连": (38.9140, 121.6147),
        "厦门": (24.4798, 118.0894),
        "长沙": (28.2282, 112.9388),
        "郑州": (34.7466, 113.6254),
        "宁波": (29.8683, 121.5440),
        "无锡": (31.4912, 120.3119),
        "合肥": (31.8206, 117.2272),
        "福州": (26.0745, 119.2965),
    }

    def _city_to_location_id(self, city: str) -> str:
        """城市名转和风天气Location ID（同步版，兼容旧调用）"""
        return self._CITY_LOCATION_IDS.get(city, self._CITY_LOCATION_IDS.get("杭州", "101210101"))

    def _city_to_coords(self, city: str) -> Optional[tuple]:
        """城市名转经纬度. 未知 city → None (而非硬编杭州坐标).

        2026-05-17 改: 老的默认杭州 (30.27, 120.16) 把北京海淀的用户错指到杭州.
        现在统一返 None, callers 决定 fallback 行为 (跳过 weather 比静默错位更安全).
        正确路径: GPS 流写 detected_lat/lon, environment.py 优先用坐标透传, 根本不走这里.
        """
        if city in self._CITY_COORDS:
            return self._CITY_COORDS[city]
        logger.warning(f"城市 '{city}' 不在坐标映射中, 跳过 (不再默认杭州)")
        return None

    def _weather_code_to_text(self, code: int) -> str:
        """WMO 天气代码转文本"""
        weather_codes = {
            0: "晴朗",
            1: "大部晴朗", 2: "局部多云", 3: "多云",
            45: "雾", 48: "霜雾",
            51: "小毛毛雨", 53: "中毛毛雨", 55: "大毛毛雨",
            61: "小雨", 63: "中雨", 65: "大雨",
            66: "冻雨", 67: "大冻雨",
            71: "小雪", 73: "中雪", 75: "大雪",
            77: "雪粒",
            80: "小阵雨", 81: "中阵雨", 82: "大阵雨",
            85: "小阵雪", 86: "大阵雪",
            95: "雷暴",
            96: "雷暴伴冰雹", 99: "大雷暴伴冰雹"
        }
        return weather_codes.get(code, "未知")

    def _wind_direction_to_text(self, degrees: float) -> str:
        """风向角度转文本"""
        directions = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
        index = round(degrees / 45) % 8
        return directions[index] + "风"

    def _get_default_weather(self) -> Dict[str, Any]:
        """返回默认天气数据"""
        return {
            "available": False,
            "source": "default",
            "temperature": 20,
            "feels_like": 20,
            "humidity": 50,
            "weather": "未知",
            "weather_code": 0,
            "wind_direction": "无",
            "wind_speed": 0,
            "error": "无法获取天气数据"
        }

    def get_exercise_advice(self, weather: Dict[str, Any]) -> Dict[str, Any]:
        """
        基于天气生成运动建议

        Args:
            weather: 天气数据

        Returns:
            运动建议
        """
        if not weather.get("available"):
            return {"suitable": True, "advice": "天气数据不可用，请根据实际情况判断"}

        temp = weather.get("temperature", 20)
        humidity = weather.get("humidity", 50)
        weather_text = weather.get("weather", "")
        wind_speed = weather.get("wind_speed", 0)

        # 判断是否适合户外运动
        suitable = True
        reasons = []
        advices = []

        # 温度检查
        if temp < 5:
            suitable = False
            reasons.append(f"温度过低（{temp}°C）")
            advices.append("建议室内运动或做好保暖措施")
        elif temp > 35:
            suitable = False
            reasons.append(f"温度过高（{temp}°C）")
            advices.append("建议在空调环境下运动，避免中暑")
        elif temp > 30:
            advices.append("注意防暑降温，及时补充水分")
        elif temp < 10:
            advices.append("做好热身，注意保暖")

        # 天气检查
        bad_weather = ["雨", "雪", "雷", "暴", "雾", "霾"]
        for bw in bad_weather:
            if bw in weather_text:
                suitable = False
                reasons.append(f"天气状况不佳（{weather_text}）")
                if "雨" in weather_text or "雪" in weather_text:
                    advices.append("建议室内运动")
                elif "雾" in weather_text or "霾" in weather_text:
                    advices.append("空气质量可能较差，建议室内运动")
                break

        # 风速检查
        if wind_speed > 40:
            suitable = False
            reasons.append(f"风速过大（{wind_speed}km/h）")
            advices.append("大风天气不宜户外运动")
        elif wind_speed > 25:
            advices.append("注意风大，跑步时可选择背风方向")

        # 湿度检查
        if humidity > 85:
            advices.append("湿度较高，运动时注意散热")
        elif humidity < 30:
            advices.append("空气干燥，注意补充水分")

        # 生成最终建议
        if suitable:
            if not advices:
                advices.append("天气适宜，可以进行户外运动")
            status = "excellent" if temp >= 15 and temp <= 25 and 40 <= humidity <= 70 else "good"
        else:
            status = "not_recommended"

        return {
            "suitable": suitable,
            "status": status,
            "reasons": reasons,
            "advices": advices,
            "weather_summary": f"{weather_text}，{temp}°C，湿度{humidity}%"
        }

    async def get_lifestyle_indices(
        self,
        city: str = None,
        lat: float = None,
        lon: float = None,
        days: int = 1
    ) -> Dict[str, Any]:
        """
        获取和风天气生活指数（包括运动指数、穿衣指数等）

        Args:
            city: 城市名称
            lat: 纬度
            lon: 经度
            days: 天数（1或3）

        Returns:
            生活指数数据，包括：
            - sport: 运动指数
            - drsg: 穿衣指数
            - uv: 紫外线指数
            - comf: 舒适度指数
            - flu: 感冒指数
            等
        """
        if not self.api_key:
            logger.warning("未配置和风天气API Key，无法获取生活指数")
            return {"available": False, "error": "未配置API Key"}

        cache_key = f"indices_{city or f'{lat},{lon}'}_{days}d"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 和风天气API需要Location ID或经纬度
                if city:
                    location = await self._city_to_location_id_async(city)
                else:
                    location = f"{lon},{lat}"

                # 生活指数接口
                url = f"{self.QWEATHER_BASE_URL}/indices/{days}d"
                params = {
                    "location": location,
                    "key": self.api_key,
                    "type": "0"  # 0 = 全部生活指数
                }

                response = await client.get(url, params=params, timeout=10)
                data = response.json()

                if data.get("code") == "200":
                    daily = data.get("daily", [])

                    # 解析各项指数
                    indices = {
                        "available": True,
                        "source": "qweather",
                        "update_time": data.get("updateTime", "")
                    }

                    for item in daily:
                        idx_type = item.get("type")
                        indices[idx_type] = {
                            "name": item.get("name", ""),
                            "level": item.get("level", ""),
                            "category": item.get("category", ""),
                            "text": item.get("text", ""),
                            "date": item.get("date", "")
                        }

                    self._set_cache(cache_key, indices)
                    return indices
                else:
                    logger.error(f"获取生活指数失败: {data.get('code')}")
                    return {"available": False, "error": f"API返回错误: {data.get('code')}"}

        except Exception as e:
            logger.error(f"获取生活指数失败: {e}")
            return {"available": False, "error": str(e)}

    async def get_air_quality(
        self,
        city: str = None,
        lat: float = None,
        lon: float = None
    ) -> Dict[str, Any]:
        """
        使用和风天气API获取实时空气质量

        Args:
            city: 城市名称
            lat, lon: 经纬度

        Returns:
            空气质量数据
        """
        if not self.api_key:
            return {"available": False, "error": "未配置和风天气API Key"}

        cache_key = f"qweather_aqi_{city or f'{lat},{lon}'}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if city:
                    location = await self._city_to_location_id_async(city)
                else:
                    location = f"{lon},{lat}"

                url = f"{self.QWEATHER_BASE_URL}/air/now"
                params = {
                    "location": location,
                    "key": self.api_key
                }

                response = await client.get(url, params=params, timeout=10)

                # 处理HTTP错误（如403无权限）
                if response.status_code != 200:
                    logger.info(f"和风天气空气质量API HTTP {response.status_code}，将使用备用数据源")
                    return {"available": False, "error": f"HTTP {response.status_code}"}

                data = response.json()

                if data.get("code") == "200":
                    now = data.get("now", {})
                    aqi = int(now.get("aqi", 0))

                    result = {
                        "available": True,
                        "source": "qweather",
                        "station": now.get("primary", ""),
                        "aqi": aqi,
                        "aqi_level": self._aqi_to_level(aqi),
                        "aqi_description": self._aqi_to_description(aqi),
                        "pm25": float(now.get("pm2p5", 0)),
                        "pm10": float(now.get("pm10", 0)),
                        "co": float(now.get("co", 0)),
                        "no2": float(now.get("no2", 0)),
                        "so2": float(now.get("so2", 0)),
                        "o3": float(now.get("o3", 0)),
                        "category": now.get("category", ""),
                        "update_time": data.get("updateTime", ""),
                    }
                    logger.info(f"和风天气空气质量: {city or location}, AQI={aqi}, {result['aqi_description']}")
                    self._set_cache(cache_key, result)
                    return result
                else:
                    logger.info(f"和风天气空气质量API返回: code={data.get('code')}，将使用备用数据源")
                    return {"available": False, "error": f"API error: {data.get('code')}"}

        except Exception as e:
            logger.error(f"和风天气空气质量获取失败: {e}")
            return {"available": False, "error": str(e)}

    @staticmethod
    def _aqi_to_level(aqi: int) -> str:
        """AQI 转等级"""
        if aqi <= 50:
            return "excellent"
        elif aqi <= 100:
            return "good"
        elif aqi <= 150:
            return "moderate"
        elif aqi <= 200:
            return "unhealthy"
        elif aqi <= 300:
            return "very_unhealthy"
        else:
            return "hazardous"

    @staticmethod
    def _aqi_to_description(aqi: int) -> str:
        """AQI 转中文描述"""
        if aqi <= 50:
            return "优"
        elif aqi <= 100:
            return "良"
        elif aqi <= 150:
            return "轻度污染"
        elif aqi <= 200:
            return "中度污染"
        elif aqi <= 300:
            return "重度污染"
        else:
            return "严重污染"

    async def get_comprehensive_context(
        self,
        city: str = None,
        latitude: float = None,
        longitude: float = None
    ) -> Dict[str, Any]:
        """
        获取完整的天气和空气质量上下文

        用于 AI 生成建议时提供环境信息

        Args:
            city: 城市名称
            latitude: 纬度
            longitude: 经度

        Returns:
            {
                "weather": {...},
                "air_quality": {...},
                "lifestyle_indices": {...},  # 生活指数，包括运动指数
                "location": {"city": "北京", "latitude": 39.9, "longitude": 116.4}
            }
        """
        # 获取天气数据
        weather = await self.get_current_weather(city, latitude, longitude)

        # 获取空气质量数据（优先使用和风天气API，失败回退到旧服务）
        air_quality = await self.get_air_quality(city, latitude, longitude)
        if not air_quality.get("available"):
            from .air_quality_service import air_quality_service
            air_quality = await air_quality_service.get_air_quality(city, latitude, longitude)

        # 获取生活指数（包括运动指数）
        lifestyle_indices = await self.get_lifestyle_indices(city, latitude, longitude)

        return {
            "weather": weather,
            "air_quality": air_quality,
            "lifestyle_indices": lifestyle_indices,
            "location": {
                "city": city,
                "latitude": latitude,
                "longitude": longitude
            }
        }


# 单例实例 - 从 settings 配置读取（确保环境变量已加载）
from app.config import settings

weather_service = WeatherService(
    api_key=settings.qweather_api_key,
    api_type=settings.qweather_api_type,
    api_host=settings.qweather_api_host
)
