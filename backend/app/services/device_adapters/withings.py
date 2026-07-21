"""
Withings 设备适配器

支持 Withings Body Smart 秤、Sleep Analyzer 等设备。
通过 OAuth 2.0 授权 + Webhook 实时推送 + API 拉取数据。
"""
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode

import aiohttp

from .base import DeviceAdapter, DeviceType, AuthType, NormalizedHealthData

logger = logging.getLogger(__name__)

# Withings API 端点
WITHINGS_AUTH_URL = "https://account.withings.com/oauth2_user/authorize2"
WITHINGS_TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
WITHINGS_MEASURE_URL = "https://wbsapi.withings.net/measure"
WITHINGS_NOTIFY_URL = "https://wbsapi.withings.net/notify"
WITHINGS_SLEEP_URL = "https://wbsapi.withings.net/v2/sleep"

# Withings 测量类型 ID
MEAS_WEIGHT = 1          # 体重 (kg)
MEAS_HEIGHT = 4           # 身高 (m)
MEAS_FAT_FREE_MASS = 5   # 去脂体重 (kg)
MEAS_FAT_RATIO = 6       # 体脂率 (%)
MEAS_FAT_MASS = 8        # 脂肪量 (kg)
MEAS_DIASTOLIC = 9       # 舒张压 (mmHg)
MEAS_SYSTOLIC = 10        # 收缩压 (mmHg)
MEAS_HEART_PULSE = 11     # 心率 (bpm)
MEAS_MUSCLE_MASS = 76     # 肌肉量 (kg)
MEAS_HYDRATION = 77       # 水分 (kg)
MEAS_BONE_MASS = 88       # 骨量 (kg)
MEAS_PWV = 91             # 脉搏波速度 (m/s)
MEAS_BMI = 0              # BMI（需要自行计算）
MEAS_VISCERAL_FAT = 170   # 内脏脂肪
MEAS_NERVE_HEALTH = 167   # 神经健康评分

# Webhook appli 类型
APPLI_WEIGHT = 1      # 体重/体脂/体成分
APPLI_PRESSURE = 4    # 血压/心率
APPLI_ACTIVITY = 16   # 活动（步数、距离）
APPLI_SLEEP = 44      # 睡眠分析

# OAuth 权限范围
WITHINGS_SCOPES = "user.info,user.metrics,user.activity,user.sleepevents"


class WithingsHealthAdapter(DeviceAdapter):
    """Withings 健康设备适配器"""

    def __init__(
        self,
        client_id: str = None,
        client_secret: str = None,
        access_token: str = None,
        refresh_token: str = None,
        **kwargs,
    ):
        self.client_id = client_id or os.getenv("WITHINGS_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("WITHINGS_CLIENT_SECRET", "")
        self.access_token = access_token
        self._refresh_token = refresh_token

    # ========== DeviceAdapter 接口实现 ==========

    @property
    def device_type(self) -> DeviceType:
        return DeviceType.MANUAL  # 复用 MANUAL 类型，或后续扩展 WITHINGS

    @property
    def display_name(self) -> str:
        return "Withings"

    @property
    def auth_type(self) -> AuthType:
        return AuthType.OAUTH2

    async def authenticate(self, credentials: Dict[str, Any]) -> bool:
        self.access_token = credentials.get("access_token")
        self._refresh_token = credentials.get("refresh_token")
        return bool(self.access_token)

    async def test_connection(self) -> Dict[str, Any]:
        """测试连接 - 获取用户设备列表"""
        try:
            data = await self._api_request(
                WITHINGS_MEASURE_URL,
                {"action": "getmeas", "lastupdate": 0, "limit": 1},
            )
            return {
                "success": True,
                "message": "Withings 连接成功",
                "user_info": {"status": data.get("status")},
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def fetch_daily_data(self, target_date: date) -> Optional[NormalizedHealthData]:
        """拉取指定日期的所有健康数据"""
        start_ts = int(datetime.combine(target_date, datetime.min.time()).timestamp())
        end_ts = int(datetime.combine(target_date + timedelta(days=1), datetime.min.time()).timestamp())

        raw = {}
        normalized = NormalizedHealthData(record_date=target_date)

        # 1. 体重/体脂/体成分
        try:
            measures = await self._get_measures(start_ts, end_ts)
            raw["measures"] = measures
            self._parse_measures_to_normalized(measures, normalized)
        except Exception as e:
            logger.warning(f"Withings fetch measures failed for {target_date}: {e}")

        # 2. 睡眠数据
        try:
            sleep = await self._get_sleep(target_date)
            raw["sleep"] = sleep
            self._parse_sleep_to_normalized(sleep, normalized)
        except Exception as e:
            logger.warning(f"Withings fetch sleep failed for {target_date}: {e}")

        normalized.raw_data = raw
        return normalized

    # ========== OAuth 流程 ==========

    def get_oauth_url(self, redirect_uri: str, state: str) -> str:
        """生成 Withings OAuth 授权 URL"""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": WITHINGS_SCOPES,
            "state": state,
        }
        return f"{WITHINGS_AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """用授权码换取 access_token 和 refresh_token"""
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15, connect=5)) as session:
            data = {
                "action": "requesttoken",
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            }
            async with session.post(
                WITHINGS_TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as resp:
                result = await resp.json()
                logger.info(f"Withings token exchange response status: {result.get('status')}")

                if result.get("status") != 0:
                    raise Exception(
                        f"Withings token exchange failed: status={result.get('status')}"
                    )

                body = result.get("body", {})
                self.access_token = body.get("access_token")
                self._refresh_token = body.get("refresh_token")
                return body

    async def refresh_token(self) -> bool:
        """刷新 access_token（有效期 3 小时）"""
        if not self._refresh_token:
            return False

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15, connect=5)) as session:
                data = {
                    "action": "requesttoken",
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self._refresh_token,
                }
                async with session.post(
                    WITHINGS_TOKEN_URL,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                ) as resp:
                    result = await resp.json()
                    if result.get("status") != 0:
                        logger.error(
                            "Withings token refresh failed: status=%s",
                            result.get("status"),
                        )
                        return False

                    body = result.get("body", {})
                    self.access_token = body.get("access_token")
                    if body.get("refresh_token"):
                        self._refresh_token = body.get("refresh_token")
                    logger.info("Withings token refreshed successfully")
                    return True
        except Exception as e:
            logger.error(f"Withings token refresh error: {e}")
            return False

    # ========== Webhook 订阅 ==========

    async def subscribe_webhook(self, callback_url: str, appli: int, comment: str = "") -> Dict:
        """订阅 Webhook 通知"""
        data = {
            "action": "subscribe",
            "callbackurl": callback_url,
            "appli": appli,
        }
        if comment:
            data["comment"] = comment
        return await self._api_request(WITHINGS_NOTIFY_URL, data)

    async def subscribe_all_webhooks(self, base_callback_url: str) -> List[Dict]:
        """订阅所有相关的 Webhook 通知"""
        results = []
        for appli, name in [
            (APPLI_WEIGHT, "体重/体脂"),
            (APPLI_PRESSURE, "血压"),
            (APPLI_SLEEP, "睡眠"),
        ]:
            try:
                result = await self.subscribe_webhook(
                    base_callback_url, appli, f"executor-life {name}"
                )
                results.append({"appli": appli, "name": name, "success": True, "result": result})
                logger.info(f"Withings webhook subscribed: appli={appli} ({name})")
            except Exception as e:
                results.append({"appli": appli, "name": name, "success": False, "error": str(e)})
                logger.error(f"Withings webhook subscribe failed: appli={appli}: {e}")
        return results

    async def list_webhooks(self) -> Dict:
        """查看已订阅的 Webhook"""
        return await self._api_request(WITHINGS_NOTIFY_URL, {"action": "list"})

    # ========== 数据拉取 ==========

    async def get_measures_by_timestamp(self, startdate: int, enddate: int) -> List[Dict]:
        """按时间戳范围获取测量数据（供 Webhook 回调使用）"""
        return await self._get_measures(startdate, enddate)

    async def _get_measures(self, startdate: int, enddate: int) -> List[Dict]:
        """获取测量数据"""
        data = {
            "action": "getmeas",
            "startdate": startdate,
            "enddate": enddate,
            "category": 1,  # 1=真实测量，2=用户目标
        }
        result = await self._api_request(WITHINGS_MEASURE_URL, data)
        return result.get("body", {}).get("measuregrps", [])

    async def _get_sleep(self, target_date: date) -> Dict:
        """获取睡眠数据"""
        data = {
            "action": "getsummary",
            "startdateymd": target_date.isoformat(),
            "enddateymd": (target_date + timedelta(days=1)).isoformat(),
        }
        result = await self._api_request(WITHINGS_SLEEP_URL, data)
        return result.get("body", {})

    # ========== 数据解析 ==========

    @staticmethod
    def parse_webhook_measures(measure_groups: List[Dict]) -> List[Dict]:
        """
        解析 Withings 测量组为结构化数据。
        每个测量组可能包含多个指标（体重秤一次测量返回体重+体脂+肌肉量等）。

        返回: [{"timestamp": ..., "weight": 80.2, "body_fat_percentage": 22.1, ...}, ...]
        """
        results = []
        for grp in measure_groups:
            record = {
                "timestamp": grp.get("date"),
                "grpid": grp.get("grpid"),
                "category": grp.get("category"),  # 1=真实测量
                "deviceid": grp.get("deviceid"),
            }
            for m in grp.get("measures", []):
                mtype = m.get("type")
                # Withings 用 value * 10^unit 表示实际值
                value = m.get("value", 0) * (10 ** m.get("unit", 0))

                if mtype == MEAS_WEIGHT:
                    record["weight"] = round(value, 2)
                elif mtype == MEAS_FAT_RATIO:
                    record["body_fat_percentage"] = round(value, 2)
                elif mtype == MEAS_FAT_MASS:
                    record["fat_mass_kg"] = round(value, 2)
                elif mtype == MEAS_FAT_FREE_MASS:
                    record["fat_free_mass_kg"] = round(value, 2)
                elif mtype == MEAS_MUSCLE_MASS:
                    record["muscle_mass_kg"] = round(value, 2)
                elif mtype == MEAS_BONE_MASS:
                    record["bone_mass_kg"] = round(value, 2)
                elif mtype == MEAS_HYDRATION:
                    record["water_mass_kg"] = round(value, 2)
                elif mtype == MEAS_VISCERAL_FAT:
                    record["visceral_fat"] = round(value)
                elif mtype == MEAS_SYSTOLIC:
                    record["systolic"] = round(value)
                elif mtype == MEAS_DIASTOLIC:
                    record["diastolic"] = round(value)
                elif mtype == MEAS_HEART_PULSE:
                    record["heart_rate"] = round(value)
                elif mtype == MEAS_PWV:
                    record["pulse_wave_velocity"] = round(value, 2)

            results.append(record)
        return results

    def _parse_measures_to_normalized(self, measure_groups: List[Dict], norm: NormalizedHealthData):
        """解析测量数据到 NormalizedHealthData"""
        parsed = self.parse_webhook_measures(measure_groups)
        for record in parsed:
            if "heart_rate" in record and norm.resting_heart_rate is None:
                norm.resting_heart_rate = record["heart_rate"]

    def _parse_sleep_to_normalized(self, sleep_data: Dict, norm: NormalizedHealthData):
        """解析睡眠数据到 NormalizedHealthData"""
        series = sleep_data.get("series", [])
        if not series:
            return

        # 取最新的一条睡眠记录
        latest = series[-1]
        data = latest.get("data", {})

        norm.total_sleep_minutes = data.get("total_sleep_duration", 0) // 60
        norm.deep_sleep_minutes = data.get("deepsleepduration", 0) // 60
        norm.rem_sleep_minutes = data.get("remsleepduration", 0) // 60
        norm.light_sleep_minutes = data.get("lightsleepduration", 0) // 60
        norm.awake_minutes = data.get("wakeupcount", 0)  # 近似
        norm.sleep_score = data.get("sleep_score")

        if data.get("hr_average"):
            norm.avg_heart_rate = data["hr_average"]
        if data.get("rr_average"):
            norm.respiration_rate_avg = data["rr_average"]

    # ========== 内部方法 ==========

    async def _api_request(self, url: str, data: Dict, retry: bool = True) -> Dict:
        """发送 Withings API 请求（自动处理 token 刷新）"""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15, connect=5)) as session:
            async with session.post(url, data=data, headers=headers) as resp:
                result = await resp.json()

                # status=401 表示 token 过期
                if result.get("status") == 401 and retry:
                    logger.info("Withings token expired, refreshing...")
                    if await self.refresh_token():
                        return await self._api_request(url, data, retry=False)
                    raise Exception("Withings token refresh failed")

                if result.get("status") != 0:
                    raise Exception(f"Withings API error: status={result.get('status')}, error={result.get('error')}")

                return result
