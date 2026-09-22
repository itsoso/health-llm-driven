"""Transactional journey writes and version-bound share projection."""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.agent_audit_log import AgentAuditLog
from app.models.journey_place import JourneyPlace
from app.schemas.journey import month_dates
from app.services.journey_images import source_images
from app.services.journey_sources import SOURCE_COLUMNS, load_source, source_kind, place_response, place_responses

def audit(db, owner_id, action, ids, image_count=0):
    db.add(AgentAuditLog(user_id=owner_id, agent_type="security_audit", action=action,
                         result_detail={"place_ids": ids, "count": len(ids), "image_count": image_count}))


def put_place(db, owner_id, kind, source_id, payload):
    source = load_source(db, owner_id, kind, source_id, lock=True)
    if kind == "chat_photo" and source_images(kind, source, owner_id)[1] != "ready":
        raise HTTPException(409, "照片不可用，请重新选择记录")
    column = getattr(JourneyPlace, SOURCE_COLUMNS[kind])
    query = db.query(JourneyPlace).filter(JourneyPlace.user_id == owner_id, column == source_id)
    existing = query.first()
    if payload.expected_version == 0:
        if existing is not None:
            raise HTTPException(409, "地点已存在，请重新加载后编辑")
        place = JourneyPlace(user_id=owner_id, **{SOURCE_COLUMNS[kind]: source_id},
                             **payload.model_dump(exclude={"expected_version", "confirmed"}), version=1)
        db.add(place)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "记录已变化，请重新加载") from None
    else:
        if existing is None:
            raise HTTPException(404, "地点不存在或不可用")
        count = query.filter(JourneyPlace.version == payload.expected_version).update(
            {**payload.model_dump(exclude={"expected_version", "confirmed"}),
             "version": payload.expected_version + 1, "updated_at": datetime.now(timezone.utc)}, synchronize_session=False)
        if count != 1:
            raise HTTPException(409, "地点已变化，请重新加载")
        db.expire(existing)
        place = existing
    audit(db, owner_id, "journey_place_saved", [place.id])
    response = place_response(db, owner_id, place)
    db.commit()
    return response


def delete_place(db, owner_id, place_id, expected_version):
    query = db.query(JourneyPlace).filter(JourneyPlace.id == place_id, JourneyPlace.user_id == owner_id)
    if query.first() is None:
        raise HTTPException(404, "地点不存在或不可用")
    if query.filter(JourneyPlace.version == expected_version).delete(synchronize_session=False) != 1:
        raise HTTPException(409, "地点已变化，请重新加载")
    audit(db, owner_id, "journey_place_deleted", [place_id])
    db.commit()


def list_month(db, owner_id, month, offset, limit):
    start, end = month_dates(month)
    query = db.query(JourneyPlace).filter(JourneyPlace.user_id == owner_id, JourneyPlace.local_date >= start, JourneyPlace.local_date < end)
    total = query.count()
    places = query.order_by(JourneyPlace.local_date, JourneyPlace.id).offset(offset).limit(limit).all()
    return {"month": month, "items": place_responses(db, owner_id, places), "total": total, "offset": offset, "limit": limit}


def export_preview(db, owner_id, request):
    ids = [s.place_id for s in request.items]
    query = db.query(JourneyPlace).filter(JourneyPlace.user_id == owner_id, JourneyPlace.id.in_(ids)).order_by(JourneyPlace.id)
    places = query.all()
    if len(places) != len(ids):
        raise HTTPException(404, "片段不存在或不可用")
    # Same lock order as PUT: sources, then annotations. This prevents deadlock
    # between editing and export and checks source existence before signing.
    sources = {}
    for kind, source_id in sorted(source_kind(p) for p in places):
        sources[(kind, source_id)] = load_source(db, owner_id, kind, source_id, lock=True)
    places = query.populate_existing().with_for_update().all()
    if len(places) != len(ids):
        raise HTTPException(404, "片段不存在或不可用")
    by_id = {p.id: p for p in places}
    months = {p.local_date.strftime("%Y-%m") for p in places}
    if len(months) != 1:
        raise HTTPException(422, "请选择同一月份的片段")
    items = []
    for selection in request.items:
        place = by_id[selection.place_id]
        if place.version != selection.version:
            raise HTTPException(409, "片段已变化，请重新预览")
        kind, source_id = source_kind(place)
        source = sources[(kind, source_id)]
        images, status = source_images(kind, source, owner_id)
        allowed = {image["key"]: image for image in images}
        if any(key not in allowed for key in selection.image_keys):
            raise HTTPException(409, "照片已变化或不可用，请重新选择")
        items.append({"city": place.city, "local_date": place.local_date, "kind": kind,
                      "images": [allowed[key] for key in selection.image_keys]})
    audit(db, owner_id, "journey_export_preview", ids, sum(len(item["images"]) for item in items))
    db.commit()
    return {"month": months.pop(), "items": items}
