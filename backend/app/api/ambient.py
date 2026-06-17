"""Ambient wearable API.

P0 covers hearables first: short audio transcript events and hearing-health
tasks. Device-specific adapters should feed this API instead of bypassing the
Health OS routing layer.
"""
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.schemas.ambient import (
    AmbientAudioInputResponse,
    AudioInputCreate,
    AudioInputEventResponse,
    HearingHealthTaskCreate,
    HearingHealthTaskEnvelope,
    HearingHealthTaskResponse,
)
from app.services import ambient_wearables as svc

router = APIRouter(prefix="/ambient", tags=["ambient-wearables"])


@router.post(
    "/audio-inputs",
    response_model=AmbientAudioInputResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_audio_input(
    body: AudioInputCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    event = svc.create_audio_input_event(
        db,
        current_user.id,
        intent=body.intent,
        transcript=body.transcript,
        source=body.source,
        device_type=body.device_type,
        confidence=body.confidence,
        captured_at=body.captured_at,
        privacy_class=body.privacy_class,
        meta=body.meta,
    )
    db.commit()
    db.refresh(event)
    return AmbientAudioInputResponse(
        event=AudioInputEventResponse.model_validate(event),
        recommended_next_action=svc.audio_next_action(body.intent),
    )


@router.post("/hearing/tasks", response_model=HearingHealthTaskEnvelope)
def create_hearing_health_task(
    body: HearingHealthTaskCreate,
    response: Response,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    task, write_intent, created = svc.ensure_hearing_health_task(
        db,
        current_user.id,
        task_type=body.task_type,
        reason=body.reason,
        source=body.source,
        due_at=body.due_at,
        priority=body.priority,
        payload=body.payload,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return HearingHealthTaskEnvelope(
        task=HearingHealthTaskResponse.model_validate(task),
        write_intent=svc.write_intent_view(write_intent),
    )


@router.get("/hearing/tasks", response_model=list[HearingHealthTaskResponse])
def list_hearing_health_tasks(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from app.models.ambient_wearable import HearingHealthTask

    tasks = (
        db.query(HearingHealthTask)
        .filter(HearingHealthTask.user_id == current_user.id)
        .order_by(HearingHealthTask.created_at.desc())
        .limit(100)
        .all()
    )
    return [HearingHealthTaskResponse.model_validate(t) for t in tasks]
