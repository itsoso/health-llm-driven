"""Owner-bound source loading and natural-month queries, without AI calls."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy.orm import selectinload

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.daily_health import DietRecord
from app.models.episode import HealthEpisode
from app.models.journey_place import JourneyPlace
from app.services.journey_images import source_images
from app.schemas.journey import month_dates

SOURCE_COLUMNS = {"diet": "diet_record_id", "life_event": "life_event_id", "chat_photo": "chat_message_id"}


def source_query(db, owner_id, kind):
    if kind == "diet":
        return db.query(DietRecord).options(selectinload(DietRecord.photo_assets)).filter(DietRecord.user_id == owner_id)
    if kind == "life_event":
        return db.query(HealthEpisode).filter(HealthEpisode.user_id == owner_id, HealthEpisode.episode_type == "life_event")
    return db.query(AgentMessage).join(AgentConversation).filter(
        AgentConversation.user_id == owner_id, AgentMessage.role == "user",
        AgentMessage.image_url.isnot(None), AgentMessage.image_url != "",
    )


def load_source(db, owner_id, kind, source_id, *, lock=False):
    model = {"diet": DietRecord, "life_event": HealthEpisode, "chat_photo": AgentMessage}[kind]
    query = source_query(db, owner_id, kind).filter(model.id == source_id)
    if lock:
        # Chat ownership lives on the conversation, so lock that owner edge too.
        query = query.with_for_update(of=[model, AgentConversation] if kind == "chat_photo" else model)
    source = query.first()
    if source is None:
        raise HTTPException(404, "记录不存在或不可用")
    return source


def source_kind(place):
    for kind, column in SOURCE_COLUMNS.items():
        if getattr(place, column) is not None:
            return kind, getattr(place, column)
    raise RuntimeError("journey_source_missing")


def base_place(place):
    kind, source_id = source_kind(place)
    return {"id": place.id, "kind": kind, "source_id": source_id, "city": place.city,
            "local_date": place.local_date, "timezone": place.timezone,
            "location_source": place.location_source, "version": place.version}


def source_title(kind, source):
    return str((source.food_items or source.food_name or source.meal_type) if kind == "diet" else
               (source.headline or "生活片段") if kind == "life_event" else source.content or "聊天照片")[:500]


def source_date(kind, source, zone):
    if kind == "diet":
        return source.record_date
    timestamp = source.occurred_at if kind == "life_event" else source.created_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=ZoneInfo("Asia/Shanghai") if kind == "life_event" else timezone.utc)
    return timestamp.astimezone(ZoneInfo(zone)).date()


def place_response(db, owner_id, place):
    kind, source_id = source_kind(place)
    source = load_source(db, owner_id, kind, source_id)
    images, status = source_images(kind, source, owner_id)
    return {**base_place(place), "title": source_title(kind, source), "images": images, "image_status": status}


def place_responses(db, owner_id, places):
    """Batch all three kinds; a month page must not introduce an N+1 query."""
    sources = {}
    for kind, model in (("diet", DietRecord), ("life_event", HealthEpisode), ("chat_photo", AgentMessage)):
        ids = [source_kind(p)[1] for p in places if source_kind(p)[0] == kind]
        if ids:
            sources.update({(kind, s.id): s for s in source_query(db, owner_id, kind).filter(model.id.in_(ids)).all()})
    result = []
    for place in places:
        kind, source_id = source_kind(place)
        source = sources.get((kind, source_id))
        if source is None:
            raise HTTPException(404, "记录不存在或不可用")
        images, status = source_images(kind, source, owner_id)
        result.append({**base_place(place), "title": source_title(kind, source), "images": images, "image_status": status})
    return result


def list_sources(db, owner_id, kind, month, zone, offset, limit):
    start, end = month_dates(month)
    query = source_query(db, owner_id, kind)
    if kind == "diet":
        query = query.filter(DietRecord.record_date >= start, DietRecord.record_date < end).order_by(DietRecord.record_date, DietRecord.id)
    else:
        column = HealthEpisode.occurred_at if kind == "life_event" else AgentMessage.created_at
        model = HealthEpisode if kind == "life_event" else AgentMessage
        bounds = [datetime.combine(day, datetime.min.time(), tzinfo=ZoneInfo(zone)) for day in (start, end)]
        if kind == "life_event" and db.get_bind().dialect.name == "sqlite":
            bounds = [x.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None) for x in bounds]
        else:
            bounds = [x.astimezone(timezone.utc) for x in bounds]
            if kind == "chat_photo":
                bounds = [x.replace(tzinfo=None) for x in bounds]
        query = query.filter(column >= bounds[0], column < bounds[1]).order_by(column, model.id)
    total = query.count()
    sources = query.offset(offset).limit(limit).all()
    column = getattr(JourneyPlace, SOURCE_COLUMNS[kind])
    places = db.query(JourneyPlace).filter(JourneyPlace.user_id == owner_id, column.in_([s.id for s in sources])).all() if sources else []
    by_id = {getattr(p, SOURCE_COLUMNS[kind]): p for p in places}
    items = []
    for source in sources:
        images, status = source_images(kind, source, owner_id)
        place = by_id.get(source.id)
        items.append({"kind": kind, "source_id": source.id, "title": source_title(kind, source),
                      "suggested_date": source_date(kind, source, zone),
                      "date_basis": "message" if kind == "chat_photo" else "record",
                      "images": images, "image_status": status, "place": base_place(place) if place else None})
    return {"items": items, "total": total, "offset": offset, "limit": limit}
