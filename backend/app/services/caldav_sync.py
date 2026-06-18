"""CalDAV 同步:连外部日历 → 当日忙碌块(加密标题)→ upsert。供 timing-solver 避让。

- lazy import caldav(避免冷启/未装依赖时炸整个 app)。
- 只读外部日历;凭据/标题加密;失败 fail loud(记 last_error 并抛,绝不假装同步成功)。
- 全量替换「当日本源块」:每次同步先删今日 caldav 块再写,保证幂等 + 删除已取消事件。
- user_id 一律由调用方按 token 传入。
"""
import ipaddress
import logging
import socket
from datetime import date, datetime, timedelta, timezone as _tz
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.calendar_sync import CalendarBusyBlock, CalendarCredential

logger = logging.getLogger(__name__)
_BEIJING = _tz(timedelta(hours=8))


def _assert_safe_caldav_url(url: str) -> None:
    """SSRF 护栏(连接前校验):仅 https + 拒私网/环回/链路本地/保留地址。
    防把服务端当跳板探内网(如 169.254.169.254 / localhost / 10.x)。DNS 解析后逐 IP 检查。"""
    p = urlparse(url or "")
    if p.scheme != "https":
        raise ValueError("CalDAV 地址必须是 https://")
    host = p.hostname
    if not host:
        raise ValueError("CalDAV 地址无效")
    try:
        infos = socket.getaddrinfo(host, p.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError("CalDAV 主机无法解析")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise ValueError("CalDAV 地址不可指向内网/环回/保留地址")


def save_credentials(db: Session, user_id: int, *, url: str, username: str, password: str) -> CalendarCredential:
    """保存/更新 CalDAV 凭据(加密)。用户在 App 自填,后端只加密存。"""
    cred = db.query(CalendarCredential).filter(CalendarCredential.user_id == user_id).first()
    if cred is None:
        cred = CalendarCredential(user_id=user_id)
        db.add(cred)
    cred.set_credentials({"url": url, "username": username, "password": password})
    cred.provider = "caldav"
    cred.sync_enabled = True
    cred.last_error = None
    db.commit()
    db.refresh(cred)
    return cred


def _china_today() -> date:
    return datetime.now(_BEIJING).date()


def _hhmm(dt: datetime) -> str:
    d = dt.astimezone(_BEIJING) if dt.tzinfo else dt
    return f"{d.hour:02d}:{d.minute:02d}"


def _fetch_events(url: str, username: str, password: str, day: date) -> List[Tuple[datetime, datetime, str, str]]:
    """连 CalDAV → 当天有时刻的事件 [(start_dt,end_dt,uid,title)]。lazy import caldav。

    全天事件(date 非 datetime)跳过(无具体时间块);跨午夜留给上层/solver 的 bs<be 守卫处理。
    """
    _assert_safe_caldav_url(url)  # SSRF 护栏:连接前校验 https + 非内网
    import caldav  # lazy

    client = caldav.DAVClient(url=url, username=username, password=password)
    principal = client.principal()
    start = datetime(day.year, day.month, day.day, 0, 0)
    end = start + timedelta(days=1)
    out: List[Tuple[datetime, datetime, str, str]] = []
    for cal in principal.calendars():
        for ev in cal.search(start=start, end=end, event=True, expand=True):
            comp = ev.icalendar_component
            if comp is None:
                continue
            dtstart = comp.get("dtstart")
            dtend = comp.get("dtend")
            if not dtstart or not dtend:
                continue
            s, e = dtstart.dt, dtend.dt
            if not isinstance(s, datetime) or not isinstance(e, datetime):
                continue  # 全天事件:无时间块,跳过
            out.append((s, e, str(comp.get("uid") or ""), str(comp.get("summary") or "")))
    return out


def sync_today(db: Session, user_id: int) -> dict:
    """同步今日忙碌块。无凭据→跳过;连接/解析失败→记 last_error 并抛(fail loud)。"""
    cred = (
        db.query(CalendarCredential)
        .filter(CalendarCredential.user_id == user_id, CalendarCredential.sync_enabled.is_(True))
        .first()
    )
    if cred is None:
        return {"synced": 0, "skipped": "no_credential"}
    c = cred.get_credentials()
    if not c.get("url"):
        return {"synced": 0, "skipped": "no_url"}

    today = _china_today()
    try:
        events = _fetch_events(c["url"], c.get("username", ""), c.get("password", ""), today)
    except Exception as e:  # fail loud — 不假装同步成功
        cred.last_error = str(e)[:500]
        db.commit()
        logger.warning("[caldav] user=%s 同步失败: %s", user_id, e)
        raise

    # 全量替换今天的 caldav 块(删已取消事件 + 幂等)
    db.query(CalendarBusyBlock).filter(
        CalendarBusyBlock.user_id == user_id,
        CalendarBusyBlock.event_date == today,
        CalendarBusyBlock.source == "caldav",
    ).delete(synchronize_session=False)

    n = 0
    for s, e, uid, title in events:
        sm, em = _hhmm(s), _hhmm(e)
        if sm >= em:  # 跨午夜/零长 → solver 的 bs<be 守卫也会丢,这里先不存
            continue
        blk = CalendarBusyBlock(
            user_id=user_id, event_date=today, start_time=sm, end_time=em,
            external_uid=(uid or None), source="caldav",
        )
        blk.set_title(title)
        db.add(blk)
        n += 1
    cred.last_sync_at = datetime.now(_BEIJING)
    cred.last_error = None
    db.commit()
    return {"synced": n}


def today_busy_blocks(db: Session, user_id: int) -> List[Tuple[str, str]]:
    """今日忙碌块 [(start,end)] 供 timing-solver(DayContext.busy)。标题不出本函数。"""
    rows = (
        db.query(CalendarBusyBlock)
        .filter(CalendarBusyBlock.user_id == user_id, CalendarBusyBlock.event_date == _china_today())
        .all()
    )
    return [(r.start_time, r.end_time) for r in rows]
