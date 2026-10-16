"""Owner-bound groups with atomic daily confirmations and immutable event snapshots.

User locks serialize this dedicated service only. Legacy record writers remain
protected by DB uniqueness; a conflicting insert rolls this entire batch back.
"""

import hashlib
import json
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, lazyload
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.health_protocol import HealthProtocol, HealthProtocolEvent
from app.utils.timezone import resolve_timezone_name
from zoneinfo import ZoneInfo

SOURCE = "supplement_group"


def _clock(db, uid):
    # Fail closed on DB errors; do not silently switch date/timezone.
    profile = db.query(UserProfile).filter_by(user_id=uid).first()
    zone, _ = resolve_timezone_name(
        profile.manual_timezone if profile else None,
        profile.detected_timezone if profile else None,
        profile.timezone if profile else None,
    )
    now = datetime.now(ZoneInfo(zone))
    return now, zone


def _lock_owner(db, uid):
    if db.query(User).filter_by(id=uid).with_for_update().first() is None:
        raise ValueError("账号不存在")


def _owned(db, uid, gid):
    p = (
        db.query(HealthProtocol)
        .filter_by(id=gid, user_id=uid, source_model=SOURCE, status="active")
        .with_for_update()
        .populate_existing()
        .first()
    )
    if p is None:
        raise ValueError("组合不存在或已归档")
    return p


def _members(db, uid, ids, lock=False):
    q = (
        db.query(SupplementDefinition)
        .options(lazyload(SupplementDefinition.product))
        .filter(SupplementDefinition.user_id == uid, SupplementDefinition.id.in_(ids))
    )
    if lock:
        # joined product relation must not be locked on PG's nullable join.
        q = q.with_for_update(of=SupplementDefinition).populate_existing()
    found = {r.id: r for r in q.all()}
    return _member_views(ids, found)


def _member_views(ids, found):
    return [
        {
            "supplement_id": i,
            "name": found[i].name if i in found else "已移除的补剂",
            "reference_dosage": found[i].dosage if i in found else None,
            "available": bool(i in found and found[i].is_active),
        }
        for i in ids
    ]


def _definition(db, p, lock=False):
    members = _members(db, p.user_id, p.implied_quantity["supplement_ids"], lock)
    return members, _revision(p, members)


def _revision(p, members):
    content = {
        "version": p.implied_quantity["version"],
        "name": p.name,
        "members": members,
    }
    revision = hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    return revision


def _event(db, uid, gid, day):
    return (
        db.query(HealthProtocolEvent)
        .filter_by(user_id=uid, protocol_id=gid, event_date=day)
        .first()
    )


def _view(db, p, day):
    members, rev = _definition(db, p)
    ev = _event(db, p.user_id, p.id, day)
    return dict(
        id=p.id,
        name=p.name,
        revision=rev,
        members=members,
        today_confirmation=ev.value if ev else None,
    )


def list_groups(db: Session, user_id: int):
    now, zone = _clock(db, user_id)
    rows = (
        db.query(HealthProtocol)
        .filter_by(user_id=user_id, source_model=SOURCE, status="active")
        .order_by(HealthProtocol.id)
        .all()
    )
    # Bound the list path to four queries regardless of group count.
    all_ids = {i for p in rows for i in p.implied_quantity["supplement_ids"]}
    definitions = (
        {
            r.id: r
            for r in db.query(SupplementDefinition)
            .options(lazyload(SupplementDefinition.product))
            .filter(
                SupplementDefinition.user_id == user_id,
                SupplementDefinition.id.in_(all_ids),
            )
            .all()
        }
        if all_ids
        else {}
    )
    events = (
        {
            e.protocol_id: e.value
            for e in db.query(HealthProtocolEvent)
            .filter(
                HealthProtocolEvent.user_id == user_id,
                HealthProtocolEvent.protocol_id.in_([p.id for p in rows]),
                HealthProtocolEvent.event_date == now.date(),
            )
            .all()
        }
        if rows
        else {}
    )
    views = []
    for p in rows:
        members = _member_views(p.implied_quantity["supplement_ids"], definitions)
        views.append(
            dict(
                id=p.id,
                name=p.name,
                revision=_revision(p, members),
                members=members,
                today_confirmation=events.get(p.id),
            )
        )
    return dict(record_date=now.date(), timezone=zone, groups=views)


def save_group(db, uid, name, ids, group_id=None, revision=None):
    try:
        _lock_owner(db, uid)
        if (
            not name.strip()
            or len(name) > 60
            or not 1 <= len(ids) <= 30
            or len(ids) != len(set(ids))
        ):
            raise ValueError("组合名称或成员无效")
        p = _owned(db, uid, group_id) if group_id is not None else None
        if p and _definition(db, p, True)[1] != revision:
            raise ValueError("组合或补剂资料已变化，请刷新后重新核对")
        if not all(m["available"] for m in _members(db, uid, ids, True)):
            raise ValueError("只能选择本人已启用的补剂")
        if p is None:
            if (
                db.query(HealthProtocol)
                .filter_by(user_id=uid, source_model=SOURCE, status="active")
                .count()
                >= 20
            ):
                raise ValueError("最多保存20个补剂组合")
            p = HealthProtocol(
                user_id=uid,
                domain="supplement",
                source_model=SOURCE,
                name=name.strip(),
                status="active",
                cadence="event_triggered",
                completion_mode="one_tap",
                can_default_complete=False,
                manual_track_allowed=False,
            )
            db.add(p)
            version = 1
        else:
            version = p.implied_quantity["version"] + 1
        p.name = name.strip()
        p.implied_quantity = {"version": version, "supplement_ids": ids}
        db.flush()
        result = _view(db, p, _clock(db, uid)[0].date())
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def archive_group(db, uid, gid, revision):
    try:
        _lock_owner(db, uid)
        p = _owned(db, uid, gid)
        if _definition(db, p, True)[1] != revision:
            raise ValueError("组合或补剂资料已变化，请刷新")
        p.status = "archived"
        db.commit()
        return {"archived": True}
    except Exception:
        db.rollback()
        raise


def confirm_group(db, uid, gid, revision, record_date):
    try:
        _lock_owner(db, uid)
        p = _owned(db, uid, gid)
        now, _ = _clock(db, uid)
        if record_date != now.date():
            raise ValueError("账户日期已变化，请刷新后重新确认")
        ev = _event(db, uid, gid, record_date)
        if ev:
            # Original confirmation is historical evidence, not today's mutable
            # projection. Never add newly edited members to this old event.
            result = ev.value
            db.commit()
            return result
        members, fresh = _definition(db, p, True)
        if revision != fresh or not all(m["available"] for m in members):
            raise ValueError("组合或补剂资料已变化，请刷新后重新核对")
        ids = [m["supplement_id"] for m in members]
        existing = {
            r.supplement_id: r
            for r in db.query(SupplementRecord)
            .filter(
                SupplementRecord.user_id == uid,
                SupplementRecord.supplement_id.in_(ids),
                SupplementRecord.record_date == record_date,
            )
            .with_for_update()
            .populate_existing()
            .all()
        }
        snapshots = []
        for m in members:
            r = existing.get(m["supplement_id"])
            already = bool(r and r.taken)
            if r is None:
                r = SupplementRecord(
                    user_id=uid,
                    supplement_id=m["supplement_id"],
                    record_date=record_date,
                    taken=True,
                    taken_time=now.time().replace(tzinfo=None),
                )
                db.add(r)
            elif not r.taken:
                r.taken = True
                r.taken_time = now.time().replace(tzinfo=None)
            db.flush()
            snapshots.append(
                {k: v for k, v in m.items() if k != "available"}
                | {"record_id": r.id, "already_taken": already}
            )
        ev = HealthProtocolEvent(
            user_id=uid,
            protocol_id=gid,
            event_date=record_date,
            status="completed",
            track="manual",
        )
        db.add(ev)
        db.flush()
        result = dict(
            event_id=ev.id,
            group_id=gid,
            name=p.name,
            revision=fresh,
            record_date=record_date.isoformat(),
            source="manual_group",
            members=snapshots,
        )
        ev.value = result
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("记录已发生并发变化，请刷新核对，未自动重试") from exc
    except Exception:
        db.rollback()
        raise
