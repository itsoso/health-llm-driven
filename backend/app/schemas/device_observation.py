"""设备观察事件 Schema(P2 · 折叠进 HealthEvent 流,无新表)。

观察 = 设备/环境对一个**事实**的报告(姿态不良、专注开始、眼保健操已完成…),
不含诊断/处方(R4)。两类:
- SIGNAL(纯事实):posture_bad/posture_ok/screen_focus_started/screen_focus_ended ——
  只记录,不翻议程、不发内联提醒(R15 预算层稍后读累积信号)。
- COMPLETION(完成式):eye_break_completed/pushup_set_completed/nasal_wash_completed/
  hand_sanitize_completed —— 经既有闭环核心熄灭对应议程项。

隐私硬约束:绝不持久化原始帧/图片/音频(validator 拦截);payload 仅结构化标量。
"""
import json
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 允许的观察 event_type(白名单)。新增设备观察动词时在此登记 + 在 service 分类。
OBSERVATION_EVENT_TYPES = frozenset({
    # SIGNAL（纯事实，不闭环）
    "posture_bad",
    "posture_ok",
    "screen_focus_started",
    "screen_focus_ended",
    # COMPLETION（完成式，闭环熄灭议程项）
    "eye_break_completed",
    "pushup_set_completed",
    "nasal_wash_completed",
    "hand_sanitize_completed",
})

# 原始媒体键 —— payload 里出现任一即拒绝(绝不持久化帧/图/音/视频/base64)。
_RAW_MEDIA_KEYS = frozenset({
    "image", "frame", "audio", "photo", "media", "base64", "video",
})

# payload 体量上限(防滥用 / 防夹带大 blob)。观察是稀疏标量,几个键足够。
_MAX_PAYLOAD_KEYS = 32
_MAX_PAYLOAD_JSON_CHARS = 4000


class DeviceObservationIngest(BaseModel):
    """设备观察摄入请求。"""

    provider: str = Field(..., max_length=50, description="来源/设备厂商: rokid, mac_screen, apple_watch...")
    device_type: Optional[str] = Field(default=None, max_length=50, description="设备类型: glasses, desktop...")
    event_type: str = Field(..., max_length=50, description="观察动词(白名单)")
    occurred_at: Optional[datetime] = Field(default=None, description="观察发生时刻(缺省=服务器 now)")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度 0..1")
    source_session_id: Optional[str] = Field(default=None, max_length=120, description="可选会话关联")
    payload: Optional[Dict[str, Any]] = Field(default=None, description="结构化标量;严禁原始媒体")

    @field_validator("event_type")
    @classmethod
    def _normalize_event_type(cls, value: str) -> str:
        text = (value or "").strip().lower()
        if text not in OBSERVATION_EVENT_TYPES:
            raise ValueError(f"unsupported device observation event_type: {text}")
        return text

    @field_validator("provider")
    @classmethod
    def _normalize_provider(cls, value: str) -> str:
        text = (value or "").strip().lower()
        if not text:
            raise ValueError("provider is required")
        return text

    @field_validator("payload")
    @classmethod
    def _reject_raw_media(cls, value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("payload must be an object")
        if len(value) > _MAX_PAYLOAD_KEYS:
            raise ValueError(f"payload too large: > {_MAX_PAYLOAD_KEYS} keys")
        for key in value:
            if str(key).strip().lower() in _RAW_MEDIA_KEYS:
                # 隐私硬红线:绝不持久化原始帧/图/音/视频 —— fail loud,整条拒绝。
                raise ValueError(f"raw media not allowed in payload: {key}")
        try:
            blob = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as e:
            raise ValueError(f"payload not serializable: {e}") from e
        if len(blob) > _MAX_PAYLOAD_JSON_CHARS:
            raise ValueError(f"payload too large: > {_MAX_PAYLOAD_JSON_CHARS} chars")
        return value


class DeviceObservationResponse(BaseModel):
    """设备观察响应(HealthEvent 的投影)。"""

    id: int
    event_type: str
    provider: str
    confidence: float = 0.0
    status: str
    payload: Optional[Dict[str, Any]] = None
    occurred_at: datetime

    model_config = ConfigDict(from_attributes=True)
