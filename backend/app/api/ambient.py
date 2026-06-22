"""Ambient wearable API.

P0 covers hearables first: short audio transcript events and hearing-health
tasks. Device-specific adapters should feed this API instead of bypassing the
Health OS routing layer.
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status
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
    MealFrameCreate,
    MealFrameResponse,
    MealSessionAbortResponse,
    MealSessionConfirmCreate,
    MealSessionConfirmResponse,
    MealSessionFinishResponse,
    MealSessionResponse,
    MealSessionStartCreate,
    RokidVoiceCommandCreate,
    RokidVoiceCommandResponse,
    RokidVoiceCommandResult,
    VisualInputCreate,
    VisualInputEventResponse,
)
from app.services import ambient_wearables as svc
from app.services import meal_monitoring as meal_svc

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
    # council #11: throttle the single-shot food_scan path per user/day (it had no
    # limit, unlike the meal-session path). 429 over-limit — fail-loud, never drop.
    if body.intent == "food_scan":
        try:
            meal_svc.check_food_scan_quota(db, current_user.id)
        except meal_svc.MealThrottleError as e:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=e.reason
            )

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

    # council #2: confirmed_by_user on /visual-inputs IS the sanctioned R4 write
    # gate (single-shot path), so we keep it — but it bypasses the meal-session
    # finish summary + guidance/safety pass, so a direct-confirmed write would
    # otherwise be invisible. Log an audit entry so it's traceable.
    meta = body.meta if isinstance(body.meta, dict) else {}
    if body.intent == "food_scan" and meta.get("confirmed_by_user"):
        from app.agents import audit

        audit._write(
            db,
            user_id=current_user.id,
            agent_type="ambient_visual_input",
            action="direct_confirmed_food_write",
            result_summary=(
                f"visual-input {event.id} direct-confirmed food write "
                "(bypassed meal-session finish summary)"
            ),
            result_detail={
                "visual_input_event_id": event.id,
                "target_type": event.target_type,
                "source": body.source,
            },
        )

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


# ─────────────────────── Meal monitoring (准视频) ───────────────────────


@router.post(
    "/meal-sessions",
    response_model=MealSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_meal_session(
    body: MealSessionStartCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        session = meal_svc.start_session(
            db,
            current_user.id,
            consent=body.consent,
            source=body.source,
            device_type=body.device_type,
            meta=body.meta,
        )
    except meal_svc.MealThrottleError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=e.reason)
    except meal_svc.MealSessionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return MealSessionResponse.model_validate(session)


@router.post(
    "/meal-sessions/{session_id}/frames",
    response_model=MealFrameResponse,
    status_code=status.HTTP_201_CREATED,
)
def append_meal_frame(
    session_id: int,
    body: MealFrameCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        event = meal_svc.append_frame(
            db,
            current_user.id,
            session_id,
            image_base64=body.image_base64,
            image_uri=body.image_uri,
            captured_at=body.captured_at,
            recognition_result=body.recognition_result,
            meta=body.meta,
        )
    except meal_svc.MealThrottleError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=e.reason)
    except meal_svc.MealSessionNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    except meal_svc.MealSessionState as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    session = meal_svc.get_session(db, current_user.id, session_id)
    return MealFrameResponse(
        frame_event_id=event.id,
        session_id=session_id,
        frame_count=session.frame_count,
        status=session.status,
    )


@router.post(
    "/meal-sessions/{session_id}/finish",
    response_model=MealSessionFinishResponse,
)
async def finish_meal_session(
    session_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        summary = await meal_svc.finish_session(db, current_user.id, session_id)
    except meal_svc.MealSessionNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    except meal_svc.MealSessionState as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except meal_svc.MealSessionAnalysisError as e:
        # council #3: analysis failed but the session was reset to 'active' — this
        # is recoverable, the client may retry finish. 503, not a stuck 'analyzing'.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)
        )
    session = meal_svc.get_session(db, current_user.id, session_id)
    return MealSessionFinishResponse(
        session=MealSessionResponse.model_validate(session),
        summary=summary,
    )


@router.post(
    "/meal-sessions/{session_id}/confirm",
    response_model=MealSessionConfirmResponse,
)
def confirm_meal_session(
    session_id: int,
    body: MealSessionConfirmCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    if not body.confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="confirm must be true")
    try:
        session, record = meal_svc.confirm_session(
            db, current_user.id, session_id, meal_type=body.meal_type
        )
    except meal_svc.MealSessionNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    except meal_svc.MealSessionState as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return MealSessionConfirmResponse(
        session=MealSessionResponse.model_validate(session),
        diet_record_id=record.id if record else None,
    )


@router.post(
    "/meal-sessions/{session_id}/abort",
    response_model=MealSessionAbortResponse,
)
def abort_meal_session(
    session_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Abort a non-confirmed session: status -> aborted + raw media purged.

    R4/privacy: lets the user (or a client teardown) end a session that will
    never be confirmed, so its raw frames don't linger until the +7d TTL sweep.
    """
    try:
        session = meal_svc.abort_session(db, current_user.id, session_id)
    except meal_svc.MealSessionNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    except meal_svc.MealSessionState as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return MealSessionAbortResponse(session=MealSessionResponse.model_validate(session))


@router.get("/meal-sessions/{session_id}", response_model=MealSessionResponse)
def get_meal_session(
    session_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        session = meal_svc.get_session(db, current_user.id, session_id)
    except meal_svc.MealSessionNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    return MealSessionResponse.model_validate(session)
