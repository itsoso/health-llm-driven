"""
设备适配器模块

支持多种智能穿戴设备的数据采集：
- Garmin (已实现)
- 华为手表 (实现中)
- Apple Watch (计划中)
- 小米手环 (计划中)
"""

from .base import DeviceAdapter, NormalizedHealthData, DeviceType
from .manager import DeviceManager

__all__ = [
    "DeviceAdapter",
    "NormalizedHealthData", 
    "DeviceType",
    "DeviceManager",
]
