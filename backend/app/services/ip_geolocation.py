"""
IP 地理位置服务 - 基于 IP 地址获取用户位置信息
使用 ip-api.com 免费 API（每分钟45次请求限制）
"""
import httpx
import logging
from typing import Optional, Dict, Any
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GeoLocation:
    """地理位置信息"""
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    timezone: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


class IPGeolocationService:
    """IP 地理位置服务"""

    # ip-api.com 免费 API 端点
    API_URL = "http://ip-api.com/json/{ip}"

    # 更新间隔（小时）
    UPDATE_INTERVAL_HOURS = 1

    # 请求超时（秒）
    REQUEST_TIMEOUT = 10

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT)
        return self._client

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def get_location_from_ip(self, ip: str) -> Optional[GeoLocation]:
        """
        根据 IP 地址获取地理位置信息

        Args:
            ip: IP 地址（支持 IPv4 和 IPv6）

        Returns:
            GeoLocation 对象，如果查询失败返回 None
        """
        # 跳过本地 IP
        if self._is_local_ip(ip):
            logger.debug(f"跳过本地 IP: {ip}")
            return None

        try:
            client = await self._get_client()

            # 调用 ip-api.com
            # 使用中文语言参数
            url = self.API_URL.format(ip=ip)
            response = await client.get(
                url,
                params={
                    "lang": "zh-CN",  # 中文
                    "fields": "status,message,country,countryCode,region,regionName,city,lat,lon,timezone"
                }
            )
            response.raise_for_status()

            data = response.json()

            if data.get("status") == "success":
                return GeoLocation(
                    city=data.get("city"),
                    region=data.get("regionName"),
                    country=data.get("country"),
                    country_code=data.get("countryCode"),
                    timezone=data.get("timezone"),
                    lat=data.get("lat"),
                    lon=data.get("lon")
                )
            else:
                logger.warning(f"IP 定位失败: {data.get('message')} (IP: {ip})")
                return None

        except httpx.TimeoutException:
            logger.error(f"IP 定位请求超时: {ip}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"IP 定位 HTTP 错误: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"IP 定位异常: {str(e)}")
            return None

    def _is_local_ip(self, ip: str) -> bool:
        """判断是否为本地 IP"""
        local_prefixes = [
            "127.",       # localhost IPv4
            "192.168.",   # 私有网络
            "10.",        # 私有网络
            "172.16.",    # 私有网络
            "172.17.",
            "172.18.",
            "172.19.",
            "172.20.",
            "172.21.",
            "172.22.",
            "172.23.",
            "172.24.",
            "172.25.",
            "172.26.",
            "172.27.",
            "172.28.",
            "172.29.",
            "172.30.",
            "172.31.",
            "::1",        # localhost IPv6
            "fe80:",      # link-local IPv6
        ]
        return any(ip.startswith(prefix) for prefix in local_prefixes)

    def should_update_location(
        self,
        last_ip: Optional[str],
        current_ip: str,
        last_update: Optional[datetime]
    ) -> bool:
        """
        判断是否需要更新位置信息

        更新条件：
        1. 从未更新过（last_update 为空）
        2. IP 地址变化
        3. 距离上次更新超过 1 小时

        Args:
            last_ip: 上次记录的 IP
            current_ip: 当前 IP
            last_update: 上次更新时间

        Returns:
            是否需要更新
        """
        # 跳过本地 IP
        if self._is_local_ip(current_ip):
            return False

        # 从未更新过
        if last_update is None:
            return True

        # IP 变化
        if last_ip != current_ip:
            return True

        # 超过更新间隔
        update_threshold = datetime.now(UTC) - timedelta(hours=self.UPDATE_INTERVAL_HOURS)
        if last_update < update_threshold:
            return True

        return False


# 全局单例
_geolocation_service: Optional[IPGeolocationService] = None


def get_geolocation_service() -> IPGeolocationService:
    """获取 IP 地理位置服务单例"""
    global _geolocation_service
    if _geolocation_service is None:
        _geolocation_service = IPGeolocationService()
    return _geolocation_service


async def update_user_location(
    db,
    user_profile,
    client_ip: str
) -> bool:
    """
    更新用户位置信息（如果需要）

    Args:
        db: 数据库会话
        user_profile: UserProfile 模型对象
        client_ip: 客户端 IP 地址

    Returns:
        是否进行了更新
    """
    service = get_geolocation_service()

    # 检查是否需要更新
    if not service.should_update_location(
        user_profile.last_ip,
        client_ip,
        user_profile.location_updated_at
    ):
        return False

    # 获取位置信息
    location = await service.get_location_from_ip(client_ip)

    if location:
        # 更新用户画像
        user_profile.detected_city = location.city
        user_profile.detected_region = location.region
        user_profile.detected_country = location.country
        user_profile.location_updated_at = datetime.now(UTC)
        user_profile.last_ip = client_ip

        db.add(user_profile)
        await db.commit()

        logger.info(f"用户位置已更新: user_id={user_profile.user_id}, "
                   f"city={location.city}, region={location.region}")
        return True

    return False
