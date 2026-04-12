"""
CGM (Continuous Glucose Monitor) 服务。

导出：
- CgmService: 高层 API，供 API 层和其他 agent 调用
- CgmAdapter: 厂商适配器抽象基类
- LibreAdapter / DexcomAdapter / StelicAdapter: 具体实现（存根 + 可配置）
"""

from app.services.cgm.adapters import CgmAdapter, ManualAdapter
from app.services.cgm.cgm_service import CgmService

__all__ = ["CgmAdapter", "CgmService", "ManualAdapter"]
