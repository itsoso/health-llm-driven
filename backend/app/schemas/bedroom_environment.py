"""卧室环境快照 API schema (设计文档 §7/§9).

字段全 Optional —— 向后兼容: 不同传感器组合提供的字段不同, HA / 任意客户端
只推它有的读数. 用户隔离在路由层用 current_user.id, body 不带 user_id.
"""

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field


class BedroomSnapshotIn(BaseModel):
    """摄入一条卧室环境快照 (HA / 客户端推)."""

    room_id: Optional[str] = Field(default=None, description="房间标识, 默认 bedroom")
    captured_at: Optional[datetime] = Field(
        default=None, description="采集时刻, 缺省取服务器当前时间"
    )
    co2_ppm: Optional[float] = None
    pm25: Optional[float] = None
    temperature_c: Optional[float] = None
    humidity_percent: Optional[float] = None
    tvoc: Optional[float] = None
    illuminance_lux: Optional[float] = None
    occupancy: Optional[bool] = None
    bed_presence: Optional[bool] = None
    sources: Optional[Dict[str, str]] = Field(
        default=None, description="指标到设备/实体的来源映射"
    )
    confidence: Optional[str] = Field(
        default=None, description="high|medium|low, 缺省 medium"
    )


class BedroomEventIn(BaseModel):
    """摄入一条卧室自动化事件 (HA automation webhook 上行, 设计文档 §7/§10).

    字段全 Optional —— 向后兼容: HA 不同自动化携带的上下文不同. event_type 在
    service 层校验非空 (缺则 422/400, 不静默写垃圾行).
    """

    room_id: Optional[str] = Field(default=None, description="房间标识, 默认 bedroom")
    event_type: Optional[str] = Field(
        default=None, description="事件类型, 例 ventilation_boost / manual_override"
    )
    reason: Optional[str] = Field(default=None, description="触发原因 (人话)")
    command_entity_id: Optional[str] = Field(
        default=None, description="命令落点实体, 例 fan.bedroom_fresh_air"
    )
    command_mode: Optional[str] = Field(
        default=None, description="命令档位/模式, 例 high / boost"
    )
    source: Optional[str] = Field(
        default=None, description="ha|reva|manual, 缺省 ha"
    )
    manual_override: Optional[bool] = Field(
        default=None, description="是否人工 override"
    )
