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
    AmbientVisualInputResponse,
    AudioInputCreate,
    AudioInputEventResponse,
    GlanceCardCreate,
    GlanceCardResponse,
    HearingHealthTaskCreate,
    HearingHealthTaskEnvelope,
    HearingHealthTaskResponse,
    RokidVoiceCommandCreate,
    RokidVoiceCommandResponse,
    RokidVoiceCommandResult,
    VisualInputCreate,
    VisualInputEventResponse,
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


@router.post(
    "/rokid-voice-commands",
    response_model=RokidVoiceCommandResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_rokid_voice_command(
    body: RokidVoiceCommandCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    command = svc.route_rokid_voice_command(body.transcript, context=body.context)
    public_command = {
        key: command[key]
        for key in (
            "intent",
            "client_action",
            "route",
            "voice_reply",
            "display_text",
            "requires_confirmation",
            "safety_level",
            "parameters",
            "recommended_next_action",
        )
    }
    meta = {
        **(body.meta or {}),
        "context": body.context,
        "command_intent": command["intent"],
        "client_action": command["client_action"],
        "route": command.get("route"),
    }
    event = svc.create_audio_input_event(
        db,
        current_user.id,
        intent=command["event_intent"],
        transcript=body.transcript,
        source="rokid_glasses",
        device_type="glasses",
        confidence=body.confidence,
        captured_at=body.captured_at,
        status=command["event_status"],
        privacy_class=body.privacy_class,
        target_type="rokid_voice_command",
        safety_result=command["safety_result"],
        meta=meta,
    )
    db.commit()
    db.refresh(event)
    return RokidVoiceCommandResponse(
        event=AudioInputEventResponse.model_validate(event),
        command=RokidVoiceCommandResult(**public_command),
    )


@router.post(
    "/visual-inputs",
    response_model=AmbientVisualInputResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_visual_input(
    body: VisualInputCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    event = svc.create_visual_input_event(
        db,
        current_user.id,
        intent=body.intent,
        source=body.source,
        device_type=body.device_type,
        image_uri=body.image_uri,
        image_sha256=body.image_sha256,
        ocr_text=body.ocr_text,
        recognition_result=body.recognition_result,
        confidence=body.confidence,
        captured_at=body.captured_at,
        privacy_class=body.privacy_class,
        meta=body.meta,
    )
    svc.create_food_diet_record_from_visual_event(db, current_user.id, event)
    db.commit()
    db.refresh(event)
    return AmbientVisualInputResponse(
        event=VisualInputEventResponse.model_validate(event),
        recommended_next_action=svc.visual_next_action(body.intent),
    )


@router.post(
    "/glance-cards",
    response_model=GlanceCardResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_glance_card(
    body: GlanceCardCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    card = svc.create_glance_card(
        db,
        current_user.id,
        surface=body.surface,
        card_type=body.card_type,
        title=body.title,
        body=body.body,
        priority=body.priority,
        action=body.action,
        target_type=body.target_type,
        target_id=body.target_id,
        expires_at=body.expires_at,
        meta=body.meta,
    )
    db.commit()
    db.refresh(card)
    return GlanceCardResponse.model_validate(card)


@router.get("/glance-cards", response_model=list[GlanceCardResponse])
def list_glance_cards(
    surface: str | None = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    cards = svc.list_active_glance_cards(db, current_user.id, surface=surface)
    return [GlanceCardResponse.model_validate(card) for card in cards]


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
