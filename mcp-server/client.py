"""Health API HTTP 客户端"""
import logging
from typing import Any, Dict, Optional

import httpx

from config import Config

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0


class HealthAPIClient:
    """健康系统 API 客户端"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
    ):
        self.base_url = (base_url or Config.HEALTH_API_URL).rstrip("/")
        self.token = token or Config.HEALTH_API_TOKEN

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def get(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """GET 请求"""
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.get(url, headers=self._get_headers(), params=params)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"GET {path} failed: {e}")
            return {"error": str(e)}

    async def post(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST 请求"""
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.post(
                    url, headers=self._get_headers(), json=data, params=params
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"POST {path} failed: {e}")
            return {"error": str(e)}
