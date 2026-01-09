"""
华为运动健康适配器

通过华为 Health Kit REST API 获取用户健康数据

认证方式：OAuth 2.0
API 文档：https://developer.huawei.com/consumer/cn/doc/development/HMSCore-Guides/overview-0000001080746960

使用流程：
1. 用户点击"绑定华为手表"
2. 跳转到华为授权页面，用户登录并授权
3. 华为回调我们的服务器，带上授权码 (code)
4. 后端用 code 换取 access_token
5. 使用 access_token 调用 Health Kit API 获取数据

需要配置：
- HUAWEI_CLIENT_ID: 华为开发者应用 Client ID
- HUAWEI_CLIENT_SECRET: 华为开发者应用 Client Secret
"""

import os
import aiohttp
import logging
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode

from .base import (
    DeviceAdapter, 
    DeviceType, 
    AuthType, 
    NormalizedHealthData,
    HeartRateSample,
    WorkoutData
)

logger = logging.getLogger(__name__)


class HuaweiHealthAdapter(DeviceAdapter):
    """
    华为运动健康适配器
    
    支持数据：
    - 步数、距离、卡路里
    - 心率（静息、平均、最大、最小）
    - 睡眠（时长、分段）
    - 血氧
    - 压力
    """
    
    # ===== 华为 OAuth 配置 =====
    # 中国区
    HUAWEI_AUTH_URL_CN = "https://oauth-login.cloud.huawei.com/oauth2/v3/authorize"
    HUAWEI_TOKEN_URL_CN = "https://oauth-login.cloud.huawei.com/oauth2/v3/token"
    HUAWEI_API_BASE_CN = "https://health-api.cloud.huawei.com"
    
    # 国际版（备用）
    HUAWEI_AUTH_URL_GLOBAL = "https://oauth-login.cloud.huawei.com/oauth2/v3/authorize"
    HUAWEI_TOKEN_URL_GLOBAL = "https://oauth-login.cloud.huawei.com/oauth2/v3/token"
    HUAWEI_API_BASE_GLOBAL = "https://health-api.cloud.huawei.com"
    
    # 授权范围
    OAUTH_SCOPES = [
        "https://www.huawei.com/healthkit/step.read",        # 步数
        "https://www.huawei.com/healthkit/heartrate.read",   # 心率
        "https://www.huawei.com/healthkit/sleep.read",       # 睡眠
        "https://www.huawei.com/healthkit/calories.read",    # 卡路里
        "https://www.huawei.com/healthkit/distance.read",    # 距离
        "https://www.huawei.com/healthkit/activity.read",    # 活动
        "https://www.huawei.com/healthkit/oxygen.read",      # 血氧
        "https://www.huawei.com/healthkit/stress.read",      # 压力
    ]
    
    def __init__(
        self, 
        client_id: str = None, 
        client_secret: str = None,
        access_token: str = None,
        refresh_token: str = None,
        is_cn: bool = True
    ):
        """
        初始化华为健康适配器
        
        Args:
            client_id: 华为开发者应用 Client ID
            client_secret: 华为开发者应用 Client Secret
            access_token: 用户 OAuth access_token（可选，已授权时传入）
            refresh_token: 用户 OAuth refresh_token（可选）
            is_cn: 是否使用中国区 API，默认 True
        """
        self.client_id = client_id or os.getenv("HUAWEI_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("HUAWEI_CLIENT_SECRET", "")
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.is_cn = is_cn
        
        # 根据区域选择 API 地址
        if is_cn:
            self.auth_url = self.HUAWEI_AUTH_URL_CN
            self.token_url = self.HUAWEI_TOKEN_URL_CN
            self.api_base = self.HUAWEI_API_BASE_CN
        else:
            self.auth_url = self.HUAWEI_AUTH_URL_GLOBAL
            self.token_url = self.HUAWEI_TOKEN_URL_GLOBAL
            self.api_base = self.HUAWEI_API_BASE_GLOBAL
    
    @property
    def device_type(self) -> DeviceType:
        return DeviceType.HUAWEI
    
    @property
    def display_name(self) -> str:
        return "华为手表"
    
    @property
    def auth_type(self) -> AuthType:
        return AuthType.OAUTH2
    
    def get_oauth_url(self, redirect_uri: str, state: str) -> str:
        """
        生成 OAuth 授权 URL
        
        用户访问此 URL 后会跳转到华为登录页面，
        授权完成后华为会重定向到 redirect_uri 并带上 code 参数
        
        Args:
            redirect_uri: 授权后的回调地址
            state: 状态参数（用于防止 CSRF，建议使用随机字符串）
            
        Returns:
            完整的授权 URL
        """
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(self.OAUTH_SCOPES),
            "state": state,
            "access_type": "offline",  # 获取 refresh_token
        }
        return f"{self.auth_url}?{urlencode(params)}"
    
    async def exchange_code_for_token(
        self, 
        code: str, 
        redirect_uri: str
    ) -> Dict[str, Any]:
        """
        用授权码换取 Access Token
        
        Args:
            code: 授权码（从回调 URL 获取）
            redirect_uri: 回调地址（必须与授权时一致）
            
        Returns:
            {
                "access_token": "...",
                "refresh_token": "...",
                "expires_in": 3600,
                "token_type": "Bearer"
            }
        """
        async with aiohttp.ClientSession() as session:
            data = {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": redirect_uri,
            }
            
            async with session.post(
                self.token_url, 
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            ) as resp:
                result = await resp.json()
                
                if "error" in result:
                    logger.error(f"华为 Token 换取失败: {result}")
                    raise Exception(f"Token换取失败: {result.get('error_description', result.get('error'))}")
                
                # 保存 Token
                self.access_token = result.get("access_token")
                self.refresh_token = result.get("refresh_token")
                
                return result
    
    async def refresh_token(self) -> bool:
        """
        刷新 Access Token
        
        Returns:
            刷新是否成功
        """
        if not self.refresh_token:
            logger.warning("无 refresh_token，无法刷新")
            return False
        
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                }
                
                async with session.post(
                    self.token_url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                ) as resp:
                    result = await resp.json()
                    
                    if "error" in result:
                        logger.error(f"华为 Token 刷新失败: {result}")
                        return False
                    
                    self.access_token = result.get("access_token")
                    if result.get("refresh_token"):
                        self.refresh_token = result.get("refresh_token")
                    
                    logger.info("华为 Token 刷新成功")
                    return True
                    
        except Exception as e:
            logger.error(f"华为 Token 刷新异常: {e}")
            return False
    
    async def authenticate(self, credentials: Dict[str, Any]) -> bool:
        """
        验证凭证
        
        Args:
            credentials: {
                "access_token": "...",
                "refresh_token": "...",  # 可选
            }
        """
        self.access_token = credentials.get("access_token")
        self.refresh_token = credentials.get("refresh_token")
        
        if not self.access_token:
            return False
        
        # 测试连接验证 Token 是否有效
        result = await self.test_connection()
        return result.get("success", False)
    
    async def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        if not self.access_token:
            return {"success": False, "message": "未设置 access_token"}
        
        try:
            # 尝试获取今日步数来验证连接
            today = date.today()
            headers = self._get_auth_headers()
            
            async with aiohttp.ClientSession() as session:
                # 使用步数 API 测试连接
                url = f"{self.api_base}/healthkit/v1/data/step/daily"
                params = {
                    "startTime": self._date_to_timestamp(today),
                    "endTime": self._date_to_timestamp(today + timedelta(days=1)),
                }
                
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status == 401:
                        # Token 过期，尝试刷新
                        if await self.refresh_token():
                            return await self.test_connection()
                        return {"success": False, "message": "Token 已过期，请重新授权"}
                    
                    if resp.status == 200:
                        return {"success": True, "message": "连接成功"}
                    
                    result = await resp.json()
                    return {
                        "success": False, 
                        "message": f"连接失败: {result.get('message', resp.status)}"
                    }
                    
        except Exception as e:
            logger.error(f"华为连接测试失败: {e}")
            return {"success": False, "message": f"连接异常: {str(e)}"}
    
    async def fetch_daily_data(self, target_date: date) -> Optional[NormalizedHealthData]:
        """获取指定日期的健康数据"""
        if not self.access_token:
            raise ValueError("未认证，请先完成 OAuth 授权")
        
        try:
            # 并行获取各项数据
            steps_data = await self._fetch_steps(target_date)
            heart_rate_data = await self._fetch_heart_rate(target_date)
            sleep_data = await self._fetch_sleep(target_date)
            calories_data = await self._fetch_calories(target_date)
            stress_data = await self._fetch_stress(target_date)
            spo2_data = await self._fetch_spo2(target_date)
            
            # 规范化数据
            return NormalizedHealthData(
                record_date=target_date,
                source=self.device_type.value,
                
                # 步数与距离
                steps=steps_data.get("steps"),
                distance_meters=steps_data.get("distance"),
                
                # 心率
                resting_heart_rate=heart_rate_data.get("resting"),
                avg_heart_rate=heart_rate_data.get("avg"),
                max_heart_rate=heart_rate_data.get("max"),
                min_heart_rate=heart_rate_data.get("min"),
                
                # 睡眠
                total_sleep_minutes=sleep_data.get("total_minutes"),
                deep_sleep_minutes=sleep_data.get("deep_minutes"),
                light_sleep_minutes=sleep_data.get("light_minutes"),
                rem_sleep_minutes=sleep_data.get("rem_minutes"),
                awake_minutes=sleep_data.get("awake_minutes"),
                
                # 卡路里
                calories_total=calories_data.get("total"),
                calories_active=calories_data.get("active"),
                
                # 压力
                stress_level=stress_data.get("avg_stress"),
                
                # 血氧
                spo2_avg=spo2_data.get("avg"),
                spo2_min=spo2_data.get("min"),
                
                # 原始数据
                raw_data={
                    "steps": steps_data,
                    "heart_rate": heart_rate_data,
                    "sleep": sleep_data,
                    "calories": calories_data,
                    "stress": stress_data,
                    "spo2": spo2_data,
                }
            )
            
        except Exception as e:
            logger.error(f"华为健康数据获取失败 ({target_date}): {e}")
            return None
    
    async def fetch_heart_rate_samples(self, target_date: date) -> List[HeartRateSample]:
        """获取心率采样数据"""
        if not self.access_token:
            return []
        
        try:
            headers = self._get_auth_headers()
            start_ts = self._date_to_timestamp(target_date)
            end_ts = self._date_to_timestamp(target_date + timedelta(days=1))
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_base}/healthkit/v1/data/heartrate/detail"
                params = {
                    "startTime": start_ts,
                    "endTime": end_ts,
                }
                
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status != 200:
                        return []
                    
                    result = await resp.json()
                    samples = []
                    
                    for item in result.get("data", []):
                        try:
                            ts = item.get("timestamp", 0)
                            hr = item.get("heartRate", 0)
                            if ts and hr:
                                samples.append(HeartRateSample(
                                    timestamp=datetime.fromtimestamp(ts / 1000),
                                    heart_rate=hr,
                                    source=self.device_type.value
                                ))
                        except Exception:
                            continue
                    
                    return samples
                    
        except Exception as e:
            logger.error(f"华为心率采样获取失败: {e}")
            return []
    
    # ===== 私有方法 =====
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """获取认证请求头"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
    
    def _date_to_timestamp(self, d: date) -> int:
        """日期转毫秒时间戳"""
        return int(datetime.combine(d, datetime.min.time()).timestamp() * 1000)
    
    async def _fetch_steps(self, target_date: date) -> Dict[str, Any]:
        """获取步数数据"""
        try:
            headers = self._get_auth_headers()
            start_ts = self._date_to_timestamp(target_date)
            end_ts = self._date_to_timestamp(target_date + timedelta(days=1))
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_base}/healthkit/v1/data/step/daily"
                params = {"startTime": start_ts, "endTime": end_ts}
                
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status != 200:
                        return {}
                    
                    result = await resp.json()
                    data = result.get("data", [])
                    
                    if data:
                        item = data[0]
                        return {
                            "steps": item.get("step", 0),
                            "distance": item.get("distance", 0),  # 米
                        }
                    return {}
                    
        except Exception as e:
            logger.warning(f"华为步数获取失败: {e}")
            return {}
    
    async def _fetch_heart_rate(self, target_date: date) -> Dict[str, Any]:
        """获取心率数据"""
        try:
            headers = self._get_auth_headers()
            start_ts = self._date_to_timestamp(target_date)
            end_ts = self._date_to_timestamp(target_date + timedelta(days=1))
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_base}/healthkit/v1/data/heartrate/daily"
                params = {"startTime": start_ts, "endTime": end_ts}
                
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status != 200:
                        return {}
                    
                    result = await resp.json()
                    data = result.get("data", [])
                    
                    if data:
                        item = data[0]
                        return {
                            "resting": item.get("restingHeartRate"),
                            "avg": item.get("avgHeartRate"),
                            "max": item.get("maxHeartRate"),
                            "min": item.get("minHeartRate"),
                        }
                    return {}
                    
        except Exception as e:
            logger.warning(f"华为心率获取失败: {e}")
            return {}
    
    async def _fetch_sleep(self, target_date: date) -> Dict[str, Any]:
        """获取睡眠数据"""
        try:
            headers = self._get_auth_headers()
            # 睡眠数据查询前一天晚上到当天早上
            start_ts = self._date_to_timestamp(target_date - timedelta(days=1))
            end_ts = self._date_to_timestamp(target_date + timedelta(days=1))
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_base}/healthkit/v1/data/sleep/daily"
                params = {"startTime": start_ts, "endTime": end_ts}
                
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status != 200:
                        return {}
                    
                    result = await resp.json()
                    data = result.get("data", [])
                    
                    if data:
                        item = data[0]
                        # 华为返回的是秒，转换为分钟
                        return {
                            "total_minutes": item.get("totalSleepTime", 0) // 60,
                            "deep_minutes": item.get("deepSleepTime", 0) // 60,
                            "light_minutes": item.get("lightSleepTime", 0) // 60,
                            "rem_minutes": item.get("remSleepTime", 0) // 60,
                            "awake_minutes": item.get("awakeTime", 0) // 60,
                        }
                    return {}
                    
        except Exception as e:
            logger.warning(f"华为睡眠获取失败: {e}")
            return {}
    
    async def _fetch_calories(self, target_date: date) -> Dict[str, Any]:
        """获取卡路里数据"""
        try:
            headers = self._get_auth_headers()
            start_ts = self._date_to_timestamp(target_date)
            end_ts = self._date_to_timestamp(target_date + timedelta(days=1))
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_base}/healthkit/v1/data/calories/daily"
                params = {"startTime": start_ts, "endTime": end_ts}
                
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status != 200:
                        return {}
                    
                    result = await resp.json()
                    data = result.get("data", [])
                    
                    if data:
                        item = data[0]
                        return {
                            "total": item.get("totalCalories", 0),
                            "active": item.get("activeCalories", 0),
                        }
                    return {}
                    
        except Exception as e:
            logger.warning(f"华为卡路里获取失败: {e}")
            return {}
    
    async def _fetch_stress(self, target_date: date) -> Dict[str, Any]:
        """获取压力数据"""
        try:
            headers = self._get_auth_headers()
            start_ts = self._date_to_timestamp(target_date)
            end_ts = self._date_to_timestamp(target_date + timedelta(days=1))
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_base}/healthkit/v1/data/stress/daily"
                params = {"startTime": start_ts, "endTime": end_ts}
                
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status != 200:
                        return {}
                    
                    result = await resp.json()
                    data = result.get("data", [])
                    
                    if data:
                        item = data[0]
                        return {
                            "avg_stress": item.get("avgStress"),
                            "max_stress": item.get("maxStress"),
                        }
                    return {}
                    
        except Exception as e:
            logger.warning(f"华为压力获取失败: {e}")
            return {}
    
    async def _fetch_spo2(self, target_date: date) -> Dict[str, Any]:
        """获取血氧数据"""
        try:
            headers = self._get_auth_headers()
            start_ts = self._date_to_timestamp(target_date)
            end_ts = self._date_to_timestamp(target_date + timedelta(days=1))
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_base}/healthkit/v1/data/oxygen/daily"
                params = {"startTime": start_ts, "endTime": end_ts}
                
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status != 200:
                        return {}
                    
                    result = await resp.json()
                    data = result.get("data", [])
                    
                    if data:
                        item = data[0]
                        return {
                            "avg": item.get("avgOxygen"),
                            "min": item.get("minOxygen"),
                            "max": item.get("maxOxygen"),
                        }
                    return {}
                    
        except Exception as e:
            logger.warning(f"华为血氧获取失败: {e}")
            return {}
