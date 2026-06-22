"""设备观察 API(P2 · 折叠进 HealthEvent 流,无新表)。

POST /api/v1/device-observations        摄入一条观察(SIGNAL 纯事实 / COMPLETION 闭环)
GET  /api/v1/device-observations        列出本人观察(?date=&event_type=)

认证复用 health_event 的 get_user_id_from_any_auth:JWT Bearer 优先,回退 X-API-Key
(眼镜/桌面端可用 API Key 长期摄入)。严格按 user_id 隔离。
"""
import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.health_event import get_user_id_from_any_auth
from app.database import get_db
from app.models.health_event import HealthEvent
from app.schemas.device_observation import (
    DeviceObservationIngest,
    DeviceObservationResponse,
)
from app.services import device_observation_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/device-observations", tags=["device-observations"])


def _to_response(event: HealthEvent) -> DeviceObservationResponse:
    return DeviceObservationResponse(
        id=event.id,
        event_type=event.event_type,
        provider=event.source,
        confidence=event.confidence or 0.0,
        status=event.status.value if hasattr(event.status, "value") else str(event.status),
        payload=event.raw_data,
        occurred_at=event.event_time,
    )


@router.post("/", response_model=DeviceObservationResponse)
def ingest_observation(
    body: DeviceObservationIngest,
    user_id: int = Depends(get_user_id_from_any_auth),
    db: Session = Depends(get_db),
):
    """摄入一条设备观察。

    - SIGNAL(姿态/专注信号):只记录事实,不翻议程、不发内联提醒(R15)。
    - COMPLETION(眼保健操/俯卧撑/洗鼻/手消完成):记录 + 经既有闭环核心熄灭议程项。
    """
    event = svc.record_observation(db, user_id, body)
    return _to_response(event)


@router.get("/", response_model=List[DeviceObservationResponse])
def list_observations(
    date: Optional[date] = Query(default=None, description="按发生日期过滤(YYYY-MM-DD)"),
    event_type: Optional[str] = Query(default=None, description="按观察动词过滤"),
    limit: int = Query(default=100, ge=1, le=500),
    user_id: int = Depends(get_user_id_from_any_auth),
    db: Session = Depends(get_db),
):
    """列出本人的设备观察(严格 user_id 隔离)。"""
    events = svc.list_observations(
        db, user_id, on_date=date, event_type=event_type, limit=limit,
    )
    return [_to_response(e) for e in events]
