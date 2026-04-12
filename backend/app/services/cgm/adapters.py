"""
CGM 厂商适配器。

统一接口：
- fetch_latest(credentials) -> List[CgmReadingDTO]
- fetch_range(credentials, start, end) -> List[CgmReadingDTO]

MVP 实现 ManualAdapter；LibreAdapter / DexcomAdapter 留存根，
它们的实现依赖用户授权 / 厂商 API，后续 Phase 接入。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class CgmReadingDTO:
    """Adapter 返回的标准化读数。"""

    measured_at: datetime
    glucose_mg_dl: float
    trend_arrow: Optional[str] = None
    trend_rate: Optional[float] = None
    device_serial: Optional[str] = None
    raw_id: Optional[str] = None
    source: str = "unknown"


class CgmAdapter(ABC):
    """所有 CGM 厂商适配器的抽象基类。"""

    source: str = "base"

    @abstractmethod
    async def fetch_latest(self, credentials: Dict[str, Any]) -> List[CgmReadingDTO]:
        """获取最新可用的所有读数（通常是最近 8 小时）。"""

    @abstractmethod
    async def fetch_range(
        self,
        credentials: Dict[str, Any],
        start: datetime,
        end: datetime,
    ) -> List[CgmReadingDTO]:
        """获取指定时间段内的读数。"""


class ManualAdapter(CgmAdapter):
    """
    手动录入 adapter。

    实际上不从外部拉数据 —— 用户通过 API 直接 POST 读数时被存进来。
    此 adapter 存在的意义是让手动数据也能享受统一的 fetch_* 接口。
    """

    source = "manual"

    async def fetch_latest(self, credentials: Dict[str, Any]) -> List[CgmReadingDTO]:
        return []

    async def fetch_range(
        self,
        credentials: Dict[str, Any],
        start: datetime,
        end: datetime,
    ) -> List[CgmReadingDTO]:
        return []


# ─────────────────────── 存根：未来接入 ────────────────────


class LibreAdapter(CgmAdapter):
    """
    FreeStyle Libre (LibreLinkUp) 适配器 —— 存根。

    需要：
    - LibreLinkUp 账号 email + password
    - patient_id (家人共享)
    - 定期 patient token 刷新

    实现参考: https://github.com/DiaKEM/libre-link-up-api-client
    """

    source = "libre"

    async def fetch_latest(self, credentials: Dict[str, Any]) -> List[CgmReadingDTO]:
        raise NotImplementedError("LibreAdapter 尚未实现，请使用 ManualAdapter 或手动录入")

    async def fetch_range(
        self,
        credentials: Dict[str, Any],
        start: datetime,
        end: datetime,
    ) -> List[CgmReadingDTO]:
        raise NotImplementedError("LibreAdapter 尚未实现")


class DexcomAdapter(CgmAdapter):
    """
    Dexcom (G6/G7) 适配器 —— 存根。

    需要：
    - Dexcom Share API credentials
    - OAuth flow

    实现参考: https://github.com/gagebenne/pydexcom
    """

    source = "dexcom"

    async def fetch_latest(self, credentials: Dict[str, Any]) -> List[CgmReadingDTO]:
        raise NotImplementedError("DexcomAdapter 尚未实现")

    async def fetch_range(
        self,
        credentials: Dict[str, Any],
        start: datetime,
        end: datetime,
    ) -> List[CgmReadingDTO]:
        raise NotImplementedError("DexcomAdapter 尚未实现")
