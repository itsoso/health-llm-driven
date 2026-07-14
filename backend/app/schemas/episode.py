"""Episode 相关 Pydantic schema。

`LifeEventOut` 原本内联在 `app/api/episodes.py`。D1(garmin-sync 治理 Wave 3)把 events 读
维度迁进程内直读时挪到 schema 层(leaf),让 api 层与 service 层(`agent_read_tools`)共用
同一响应契约,避免 service 层 import api 层(层倒挂)。挪动后 api 端点行为一字不变。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class LifeEventOut(BaseModel):
    id: int
    title: str
    occurred_at: datetime
    occurred_precision: str
    occurred_display: str
    notes: Optional[str] = None
