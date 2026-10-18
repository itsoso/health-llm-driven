"""Bounded private GPS capture and deterministic review; no network or LLM calls."""

from datetime import datetime, timedelta, timezone, time
import hashlib
import json
import logging
import math
from statistics import median
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.daily_journey import (
    DailyJourneySession,
    DailyJourneyPoint,
    DailyJourneyRequest,
)
from app.models.user import User
from app.models.agent_audit_log import AgentAuditLog
from app.utils.number_format import format_display_number

logger = logging.getLogger(__name__)
MAX_POINTS = 10000
MAX_SESSIONS_PER_DAY = 50


def _audit(db, row, action, count=0):
    db.add(
        AgentAuditLog(
            user_id=row.user_id,
            agent_type="security_audit",
            action="daily_journey_" + action,
            result_detail={"session_id": row.id, "count": count, "status": row.status},
        )
    )


def utcnow():
    return datetime.now(timezone.utc)


def aware(value):
    # SQLite loses offset metadata; persisted values are always UTC.
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def _error(code, message):
    raise HTTPException(code, message)


def _serialize(row):
    result = {
        key: getattr(row, key)
        for key in (
            "id",
            "client_id",
            "local_date",
            "timezone",
            "status",
            "version",
            "segment",
            "started_at",
            "deadline_at",
            "ended_at",
            "expires_at",
            "retention_days",
            "point_count",
        )
    }
    for key in ("started_at", "deadline_at", "ended_at", "expires_at"):
        if result[key] is not None:
            result[key] = aware(result[key])
    return result


def _owned(db, user_id, session_id, *, lock=False):
    query = select(DailyJourneySession).where(
        DailyJourneySession.user_id == user_id,
        DailyJourneySession.id == str(session_id),
        DailyJourneySession.expires_at > utcnow(),
    )
    if lock:
        query = query.with_for_update()
    row = db.execute(
        query.execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if row is None:
        _error(404, "行程不存在或已过期")
    return row


def _end_at_deadline(row):
    if row.status != "ended" and utcnow() >= aware(row.deadline_at):
        row.status = "ended"
        row.ended_at = row.deadline_at
        if row.segment_ended_at is None:
            row.segment_ended_at = row.deadline_at
        row.version += 1


def _commit_session(db, row):
    result = _serialize(row)
    db.commit()
    return result


def start_session(db: Session, user_id, payload):
    # Owner lock serializes new starts, including after deleting/ending another
    # session. The partial unique index is the final database invariant.
    owner = db.execute(
        select(User.id).where(User.id == user_id).with_for_update()
    ).scalar_one_or_none()
    if owner is None:
        _error(404, "用户不存在")
    prior = db.get(DailyJourneyRequest, (user_id, str(payload.request_id)))
    now = utcnow()
    if prior:
        existing = db.execute(
            select(DailyJourneySession)
            .where(
                DailyJourneySession.id == prior.session_id,
                DailyJourneySession.user_id == user_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if not existing or aware(existing.expires_at) <= now:
            _error(410, "此前行程已删除或过期，请重新主动开启")
        if (
            existing.client_id != str(payload.client_id)
            or existing.timezone != payload.timezone
            or existing.retention_days != payload.retention_days
        ):
            _error(409, "开启请求已使用，请刷新行程")
        _end_at_deadline(existing)
        return _commit_session(db, existing)
    unfinished = (
        db.execute(
            select(DailyJourneySession)
            .where(
                DailyJourneySession.user_id == user_id,
                DailyJourneySession.status.in_(["active", "paused"]),
            )
            .with_for_update()
        )
        .scalars()
        .all()
    )
    for row in unfinished:
        _end_at_deadline(row)
        if row.status != "ended":
            _error(409, "请先结束当前行程")
    db.flush()
    local = now.astimezone(ZoneInfo(payload.timezone))
    deadline = datetime.combine(
        local.date() + timedelta(days=1), time.min, ZoneInfo(payload.timezone)
    ).astimezone(timezone.utc)
    deadline = min(deadline, now + timedelta(hours=24))
    # A bounded daily list also bounds review/list work and repeated opt-in abuse.
    count = (
        db.query(DailyJourneySession)
        .filter_by(user_id=user_id, local_date=local.date())
        .count()
    )
    if count >= MAX_SESSIONS_PER_DAY:
        _error(409, "今天开启次数已达上限")
    row = DailyJourneySession(
        id=str(uuid4()),
        user_id=user_id,
        client_id=str(payload.client_id),
        local_date=local.date(),
        timezone=payload.timezone,
        status="active",
        version=1,
        segment=1,
        started_at=now,
        segment_started_at=now,
        deadline_at=deadline,
        ended_at=None,
        expires_at=now + timedelta(days=payload.retention_days),
        retention_days=payload.retention_days,
        point_count=0,
        annotations="{}",
    )
    db.add(row)
    db.add(
        DailyJourneyRequest(
            user_id=user_id, request_id=str(payload.request_id), session_id=row.id
        )
    )
    db.flush()
    _audit(db, row, "started")
    logger.info("daily journey started session=%s", row.id)
    return _commit_session(db, row)


def list_sessions(db, user_id, local_date):
    rows = (
        db.execute(
            select(DailyJourneySession)
            .where(
                DailyJourneySession.user_id == user_id,
                DailyJourneySession.local_date == local_date,
                DailyJourneySession.expires_at > utcnow(),
            )
            .order_by(DailyJourneySession.started_at)
            .with_for_update()
        )
        .scalars()
        .all()
    )
    for row in rows:
        _end_at_deadline(row)
    result = {"items": [_serialize(row) for row in rows]}
    db.commit()
    return result


def get_session(db, user_id, session_id):
    row = _owned(db, user_id, session_id, lock=True)
    _end_at_deadline(row)
    return _commit_session(db, row)


def change_state(db, user_id, session_id, payload):
    row = _owned(db, user_id, session_id, lock=True)
    _end_at_deadline(row)
    action = payload.action
    command = hashlib.sha256(
        f"{action}:{payload.client_id}:{payload.expected_version}".encode()
    ).hexdigest()
    desired = {"pause": "paused", "resume": "active", "end": "ended"}[action]
    if row.version != payload.expected_version:
        if (
            row.version == payload.expected_version + 1
            and row.last_state_command == command
            and row.status == desired
        ):
            return _commit_session(db, row)
        _error(409, "行程状态已变化，请刷新")
    if action == "resume" and str(payload.client_id) != row.client_id:
        _error(409, "只能在开启行程的设备继续记录")
    desired = {"pause": "paused", "resume": "active", "end": "ended"}[action]
    if row.status == desired:
        return _commit_session(db, row)
    if row.status == "ended":
        _error(409, "行程已结束，请重新主动开启")
    if action == "resume":
        if row.segment >= 1000:
            _error(409, "暂停次数已达上限，请结束行程")
        row.segment += 1
        row.segment_started_at = utcnow()
        row.segment_ended_at = None
    else:
        row.segment_ended_at = row.segment_ended_at or utcnow()
    row.status = desired
    row.last_state_command = command
    row.version += 1
    if action == "end":
        row.ended_at = utcnow()
    _audit(db, row, desired)
    logger.info("daily journey state session=%s state=%s", row.id, desired)
    return _commit_session(db, row)


def _canonical_point(point):
    return json.dumps(
        point.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def upload_points(db, user_id, session_id, payload):
    row = _owned(db, user_id, session_id, lock=True)
    now = utcnow()
    _end_at_deadline(row)
    if row.client_id != str(payload.client_id) or row.segment != payload.segment:
        _error(409, "设备或采集区间已变化")
    # Validate entire batch before any mutation. Both stored and within-batch
    # duplicate IDs are immutable; retries cannot revise a prior observation.
    capture_end = min(
        aware(row.deadline_at),
        aware(row.segment_ended_at) if row.segment_ended_at else aware(row.deadline_at),
    )
    incoming = {}
    duplicates = 0
    for point in payload.points:
        when = point.recorded_at
        if (
            when < aware(row.segment_started_at)
            or when >= capture_end
            or when > now + timedelta(seconds=120)
        ):
            _error(422, "采样时间不在有效采集区间")
        key, value = str(point.id), _canonical_point(point)
        if key in incoming:
            if incoming[key] != value:
                _error(409, "采样编号内容不一致")
            duplicates += 1
        incoming[key] = value
    existing = (
        db.execute(
            select(DailyJourneyPoint).where(
                DailyJourneyPoint.session_id == row.id,
                DailyJourneyPoint.id.in_(list(incoming)),
            )
        )
        .scalars()
        .all()
    )
    for sample in existing:
        if sample.segment != payload.segment or sample.payload != incoming[sample.id]:
            _error(409, "采样编号内容不一致")
        del incoming[sample.id]
        duplicates += 1
    if row.point_count + len(incoming) > MAX_POINTS:
        _error(409, "当天轨迹容量已满，请结束行程")
    for key, value in incoming.items():
        db.add(
            DailyJourneyPoint(
                session_id=row.id, id=key, segment=payload.segment, payload=value
            )
        )
    row.point_count += len(incoming)
    result = {
        "accepted": len(incoming),
        "duplicate": duplicates,
        "session": _serialize(row),
    }
    if incoming:
        _audit(db, row, "points", len(incoming))
    db.commit()
    logger.info(
        "daily journey batch session=%s accepted=%s duplicate=%s",
        row.id,
        result["accepted"],
        duplicates,
    )
    return result


def _distance(a, b):
    lat1, lat2 = math.radians(a["latitude"]), math.radians(b["latitude"])
    dlat = lat2 - lat1
    dlon = math.radians(b["longitude"] - a["longitude"])
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 6371000 * 2 * math.asin(min(1, math.sqrt(max(0, h))))


def _seconds(a, b):
    return (b["recorded_at"] - a["recorded_at"]).total_seconds()


def _duration_display(seconds):
    return f"{format_display_number(seconds / 60)} 分钟"


def _estimate_mode(group, distance):
    # A coarse speed heuristic, never a statement about actual transport.
    # Running/cycling overlap remains unknown rather than inventing certainty.
    if len(group) < 5 or _seconds(group[0], group[-1]) < 120 or distance < 100:
        return "unknown"
    if any(point["accuracy_m"] > 50 for point in group):
        return "unknown"
    speeds, moving = [], 0
    for first, second in zip(group, group[1:]):
        elapsed = _seconds(first, second)
        if elapsed <= 0:
            return "unknown"
        leg_distance = _distance(first, second)
        speeds.append(leg_distance / elapsed)
        if leg_distance > max(10, (first["accuracy_m"] + second["accuracy_m"]) / 2):
            moving += 1
    if moving / len(speeds) < 0.8:
        return "unknown"
    typical = median(speeds)
    if 0.5 <= typical <= 1.8 and max(speeds) <= 2.5:
        return "walking"
    lower_quartile = sorted(speeds)[(len(speeds) - 1) // 4]
    if typical >= 12 and lower_quartile >= 8 and max(speeds) <= 60:
        return "vehicle"
    return "unknown"


def _review(db, row):
    stored = (
        db.execute(
            select(DailyJourneyPoint).where(DailyJourneyPoint.session_id == row.id)
        )
        .scalars()
        .all()
    )
    points = []
    for sample in stored:
        p = json.loads(sample.payload)
        p["recorded_at"] = datetime.fromisoformat(
            p["recorded_at"].replace("Z", "+00:00")
        )
        p["segment"] = sample.segment
        points.append(p)
    points.sort(key=lambda p: (p["recorded_at"], p["id"]))
    annotations = json.loads(row.annotations)
    groups, current, gaps = [], [], []
    previous = None
    for point in points:
        reason = None
        if previous:
            elapsed = _seconds(previous, point)
            if previous["segment"] != point["segment"]:
                reason = "pause"
            elif previous["accuracy_m"] > 100 or point["accuracy_m"] > 100:
                reason = "low_accuracy"
            elif elapsed > 300:
                reason = "signal_gap"
            elif elapsed <= 0 or _distance(previous, point) / elapsed > 70:
                reason = "implausible_speed"
        if reason:
            gaps.append(
                {
                    "started_at": previous["recorded_at"],
                    "ended_at": point["recorded_at"],
                    "reason": reason,
                }
            )
            if current:
                groups.append(current)
                current = []
        if point["accuracy_m"] <= 100:
            current.append(point)
        previous = point
    if current:
        groups.append(current)
    window_end = min(
        utcnow(),
        aware(row.deadline_at),
        aware(row.ended_at) if row.ended_at else utcnow(),
    )
    window_start = aware(row.started_at)
    if not points:
        if window_end > window_start:
            gaps.append(
                {
                    "started_at": window_start,
                    "ended_at": window_end,
                    "reason": "signal_gap",
                }
            )
    else:
        if points[0]["recorded_at"] > window_start:
            gaps.insert(
                0,
                {
                    "started_at": window_start,
                    "ended_at": min(window_end, points[0]["recorded_at"]),
                    "reason": "signal_gap",
                },
            )
        if window_end > points[-1]["recorded_at"]:
            gaps.append(
                {
                    "started_at": points[-1]["recorded_at"],
                    "ended_at": window_end,
                    "reason": "pause" if row.status == "paused" else "signal_gap",
                }
            )
    segments, stops = [], []
    total_distance = observed = 0.0
    for group in groups:
        first, last = group[0], group[-1]
        target = "segment:" + first["id"]
        correction = annotations.get(target, {})
        distance = sum(_distance(a, b) for a, b in zip(group, group[1:]))
        total_distance += distance
        observed += _seconds(first, last)
        segments.append(
            {
                "id": target,
                "point_ids": [p["id"] for p in group],
                "started_at": first["recorded_at"],
                "ended_at": last["recorded_at"],
                "distance_m": distance,
                "distance_display": f"{format_display_number(distance / 1000)} 公里",
                "mode": correction.get("mode") or _estimate_mode(group, distance),
                "mode_source": "user" if correction.get("mode") else "estimated",
                "label": correction.get("label"),
            }
        )
        # Stops require three continuous accurate observations, at least five
        # minutes, all within 60 m of the first. Never extrapolate the last fix.
        cluster = []

        def finish_stop():
            if len(cluster) < 3 or _seconds(cluster[0], cluster[-1]) < 300:
                return
            key = "stop:" + cluster[0]["id"]
            duration = _seconds(cluster[0], cluster[-1])
            stops.append(
                {
                    "id": key,
                    "latitude": cluster[0]["latitude"],
                    "longitude": cluster[0]["longitude"],
                    "started_at": cluster[0]["recorded_at"],
                    "ended_at": cluster[-1]["recorded_at"],
                    "duration_seconds": duration,
                    "duration_display": _duration_display(duration),
                    "label": annotations.get(key, {}).get("label"),
                }
            )

        for point in group:
            if cluster and _distance(cluster[0], point) > 60:
                finish_stop()
                cluster = []
            cluster.append(point)
        finish_stop()
    return {
        "session": _serialize(row),
        "points": points,
        "segments": segments,
        "stops": stops,
        "gaps": gaps,
        "summary": {
            "distance_m": total_distance,
            "distance_display": f"{format_display_number(total_distance / 1000)} 公里",
            "observed_seconds": observed,
            "observed_display": _duration_display(observed),
            "stop_count": len(stops),
            "point_count": len(points),
            "note": "里程由有效定位点估算；缺口未连接，交通方式仅按速度粗估，无法区分时不判断，可自行修正。末尾定位不代表之后的停留。",
        },
    }


def review_session(db, user_id, session_id):
    row = _owned(db, user_id, session_id, lock=True)
    _end_at_deadline(row)
    result = _review(db, row)
    db.commit()
    return result


def annotate_session(db, user_id, session_id, payload):
    row = _owned(db, user_id, session_id, lock=True)
    _end_at_deadline(row)
    if row.version != payload.expected_version:
        _error(409, "行程状态已变化，请刷新")
    review = _review(db, row)
    segments = {item["id"] for item in review["segments"]}
    stops = {item["id"] for item in review["stops"]}
    updates = {}
    for annotation in payload.annotations:
        if (
            annotation.target_id not in segments | stops
            or annotation.target_id in updates
        ):
            _error(422, "修正目标无效，请刷新复盘")
        if annotation.target_id in stops and annotation.mode is not None:
            _error(422, "停留仅支持名称修正")
        updates[annotation.target_id] = annotation.model_dump(
            exclude={"target_id"}, exclude_unset=True
        )
    current = json.loads(row.annotations)
    # Remove corrections for targets invalidated by later legitimate samples.
    current = {key: value for key, value in current.items() if key in segments | stops}
    for target, update in updates.items():
        current[target] = {**current.get(target, {}), **update}
    if len(current) > 200:
        _error(422, "修正数量已达上限")
    row.annotations = json.dumps(current, ensure_ascii=False, allow_nan=False)
    row.version += 1
    _audit(db, row, "annotated", len(updates))
    logger.info("daily journey annotated session=%s count=%s", row.id, len(updates))
    return _commit_session(db, row)


def _removal_metadata():
    # Deletion and retention must work even when encrypted fields are damaged.
    # These columns contain no GPS, annotation text, or client identifiers.
    return select(
        DailyJourneySession.id,
        DailyJourneySession.user_id,
        DailyJourneySession.status,
        DailyJourneySession.point_count,
    )


def delete_session(db, user_id, session_id):
    row = db.execute(
        _removal_metadata()
        .where(
            DailyJourneySession.user_id == user_id,
            DailyJourneySession.id == str(session_id),
        )
        .with_for_update()
    ).one_or_none()
    if row:
        db.query(DailyJourneyPoint).filter_by(session_id=row.id).delete(
            synchronize_session=False
        )
        _audit(db, row, "deleted", row.point_count)
        db.query(DailyJourneySession).filter_by(id=row.id, user_id=user_id).delete(
            synchronize_session=False
        )
        logger.info("daily journey deleted session=%s", str(session_id))
    # An absent/foreign ID has the same response. The request ledger is retained
    # and cannot be used to authorize a new session after deletion or expiration.
    db.commit()


def purge_expired(db, *, batch_size=100):
    if type(batch_size) is not int or not 1 <= batch_size <= 1000:
        raise ValueError("invalid purge batch size")
    rows = db.execute(
        _removal_metadata()
        .where(DailyJourneySession.expires_at <= utcnow())
        .order_by(DailyJourneySession.expires_at)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    ).all()
    ids = [row.id for row in rows]
    if ids:
        db.query(DailyJourneyPoint).filter(
            DailyJourneyPoint.session_id.in_(ids)
        ).delete(synchronize_session=False)
        for row in rows:
            _audit(db, row, "expired", row.point_count)
        db.query(DailyJourneySession).filter(DailyJourneySession.id.in_(ids)).delete(
            synchronize_session=False
        )
    db.commit()
    logger.info("daily journey expiry purge count=%s", len(ids))
    return len(ids)
