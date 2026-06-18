"""CalDAV 同步:连外部日历 → 当日忙碌块(加密标题)→ upsert。供 timing-solver 避让。

- lazy import caldav(避免冷启/未装依赖时炸整个 app)。
- 只读外部日历;凭据/标题加密;失败 fail loud(记 last_error 并抛,绝不假装同步成功)。
- 全量替换「当日本源块」:每次同步先删今日 caldav 块再写,保证幂等 + 删除已取消事件。
- user_id 一律由调用方按 token 传入。
"""
import ipaddress
import logging
import re
import socket
from datetime import date, datetime, timedelta, timezone as _tz
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.calendar_sync import (
    CalendarBusyBlock, CalendarCredential, CalendarEvent, CalendarSource,
)

logger = logging.getLogger(__name__)
_BEIJING = _tz(timedelta(hours=8))


def _assert_safe_url(url: str, *, label: str = "日历") -> None:
    """SSRF 护栏(连接前校验):仅 https + 拒私网/环回/链路本地/保留地址。
    caldav 与 ics 共用:防把服务端当跳板探内网(169.254.169.254 / localhost / 10.x)。"""
    p = urlparse(url or "")
    if p.scheme != "https":
        raise ValueError(f"{label}地址必须是 https://")
    host = p.hostname
    if not host:
        raise ValueError(f"{label}地址无效")
    try:
        infos = socket.getaddrinfo(host, p.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError(f"{label}主机无法解析")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise ValueError(f"{label}地址不可指向内网/环回/保留地址")


def _assert_safe_caldav_url(url: str) -> None:
    """SSRF 护栏(CalDAV);保留旧名做 back-compat,委托 _assert_safe_url。"""
    _assert_safe_url(url, label="CalDAV ")


def _assert_safe_ics_url(url: str) -> None:
    """SSRF 护栏(ics 订阅)。"""
    _assert_safe_url(url, label="ICS ")


_URL_WITH_CREDS_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s'\"]+")


def _scrub_error(e: Exception) -> str:
    """同步错误存 last_error / 打日志前脱敏:剥掉可能含凭据的 URL
    (caldav 异常常含 https://user:pass@host),只留异常类型 + 去 URL 的概述。"""
    return f"{type(e).__name__}: {_URL_WITH_CREDS_RE.sub('<url>', str(e))}"[:500]


import urllib.request as _urllib_request  # noqa: E402 — 模块级,供 redirect handler 子类


class _GuardedRedirectHandler(_urllib_request.HTTPRedirectHandler):
    """逐跳重过 SSRF 护栏:公网 .ics 可 302→169.254/localhost/内网 把服务端当跳板。
    每个重定向目标重新校验 https + 非内网,不安全则 raise 中断(初始 URL 过护栏 ≠ 跳转安全)。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _assert_safe_ics_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


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
        cred.last_error = _scrub_error(e)
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
    """今日(北京)忙碌块 [(start_hhmm,end_hhmm)] 供 timing-solver(DayContext.busy)。

    从 CalendarEvent 派生(v2:跨所有源);只取有时刻的(非全天)事件,丢零/负长度。
    标题/PII 绝不出本函数 —— 只返回 (HH:MM, HH:MM)。shape 与 v1 完全一致。
    """
    today = _china_today()
    rows = (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.user_id == user_id,
            CalendarEvent.all_day.is_(False),
            CalendarEvent.start_time.isnot(None),
            CalendarEvent.end_time.isnot(None),
        )
        .all()
    )
    out: List[Tuple[str, str]] = []
    for r in rows:
        s, e = r.start_time, r.end_time
        if s is None or e is None:
            continue
        sl = s.astimezone(_BEIJING) if s.tzinfo else s.replace(tzinfo=_BEIJING)
        el = e.astimezone(_BEIJING) if e.tzinfo else e.replace(tzinfo=_BEIJING)
        if sl.date() != today:
            continue
        sm, em = _hhmm(sl), _hhmm(el)
        if sm >= em:  # 零/负长度 → 丢(solver bs<be 守卫亦会丢)
            continue
        out.append((sm, em))
    return out


# ── Calendar v2 (C1) 同步引擎 ──────────────────────────────────────────────

def _parse_vevent(comp) -> Optional[dict]:
    """从一个 VEVENT icalendar 组件抽字段。返回 None 表示该组件无可用时间。
    返回 {uid,title,location,description,attendees(list),status,start,end,all_day}。"""
    dtstart = comp.get("dtstart")
    if not dtstart:
        return None
    s = dtstart.dt
    dtend = comp.get("dtend")
    e = dtend.dt if dtend else None
    all_day = not isinstance(s, datetime)
    if all_day:
        # date(非 datetime)→ 全天:跨当日 00:00 → 次日 00:00
        start = datetime(s.year, s.month, s.day, 0, 0, tzinfo=_BEIJING)
        if e is not None and not isinstance(e, datetime):
            end = datetime(e.year, e.month, e.day, 0, 0, tzinfo=_BEIJING)
        else:
            end = start + timedelta(days=1)
    else:
        start = s if s.tzinfo else s.replace(tzinfo=_BEIJING)
        if isinstance(e, datetime):
            end = e if e.tzinfo else e.replace(tzinfo=_BEIJING)
        else:
            end = start + timedelta(hours=1)
    attendees: List[str] = []
    raw_att = comp.get("attendee")
    if raw_att is not None:
        items = raw_att if isinstance(raw_att, list) else [raw_att]
        for a in items:
            cn = None
            try:
                cn = a.params.get("CN")  # type: ignore[attr-defined]
            except Exception:
                cn = None
            attendees.append(str(cn) if cn else str(a).replace("mailto:", ""))
    return {
        "uid": str(comp.get("uid") or ""),
        "title": str(comp.get("summary") or ""),
        "location": str(comp.get("location") or "") or None,
        "description": str(comp.get("description") or "") or None,
        "attendees": attendees,
        "status": str(comp.get("status") or "") or None,
        "start": start,
        "end": end,
        "all_day": all_day,
    }


def _fetch_caldav_range(url: str, username: str, password: str,
                        start: datetime, end: datetime) -> List[dict]:
    """连 CalDAV 抓 [start,end) 窗口内所有事件(明细)。lazy import caldav。"""
    _assert_safe_caldav_url(url)  # SSRF 护栏
    import caldav  # lazy

    client = caldav.DAVClient(url=url, username=username, password=password)
    principal = client.principal()
    out: List[dict] = []
    for cal in principal.calendars():
        for ev in cal.search(start=start, end=end, event=True, expand=True):
            comp = ev.icalendar_component
            if comp is None:
                continue
            parsed = _parse_vevent(comp)
            if parsed and parsed["uid"]:
                out.append(parsed)
    return out


def _fetch_ics_text(url: str, *, timeout: int = 15) -> str:
    """SSRF-guard 后用 stdlib 拉 .ics 文本。

    重定向必须**逐跳重新过护栏**:urlopen 默认跟随 302,公网 .ics 可 302→
    169.254.169.254 / localhost / 10.x 把服务端当跳板(初始 URL 过护栏不代表跳转目标安全)。
    """
    _assert_safe_ics_url(url)  # SSRF 护栏(初始 URL)
    import urllib.request  # lazy

    opener = urllib.request.build_opener(_GuardedRedirectHandler)
    req = urllib.request.Request(url, headers={"User-Agent": "health-calendar/1.0"})
    with opener.open(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse_ics(text: str) -> List[dict]:
    """解析 .ics 文本 → 事件明细列表。lazy import icalendar。"""
    from icalendar import Calendar  # lazy

    cal = Calendar.from_ical(text)
    out: List[dict] = []
    for comp in cal.walk("VEVENT"):
        parsed = _parse_vevent(comp)
        if parsed and parsed["uid"]:
            out.append(parsed)
    return out


def _fetch_source_events(source: CalendarSource, start: datetime, end: datetime) -> List[dict]:
    """按 provider 分派抓取。creds 解密只在内存,绝不外发。"""
    c = source.get_credentials()
    url = c.get("url")
    if not url:
        raise ValueError("源缺少 url")
    if source.provider == "ics":
        events = _parse_ics(_fetch_ics_text(url))
        # ics 是订阅窗口外的也会带,过滤到窗口内
        return [e for e in events if e["end"] > start and e["start"] < end]
    # 默认 caldav
    return _fetch_caldav_range(url, c.get("username", ""), c.get("password", ""), start, end)


def sync_source(db: Session, source: CalendarSource, *,
                window_days_back: int = 7, window_days_fwd: int = 30) -> dict:
    """同步单个源:SSRF 校验 → 抓窗口事件 → 全量替换该源窗口内事件(按 uid upsert)。

    幂等:先删 source_id 在窗口内的旧事件,再按 (source_id,uid) upsert。
    成功清 last_error;失败由调用方记 last_error(此函数直接抛 → fail loud)。
    """
    now = datetime.now(_BEIJING)
    start = now - timedelta(days=window_days_back)
    end = now + timedelta(days=window_days_fwd)
    events = _fetch_source_events(source, start, end)

    # 全量替换窗口内本源事件(删已取消 + 幂等)
    db.query(CalendarEvent).filter(
        CalendarEvent.source_id == source.id,
        CalendarEvent.start_time >= start,
        CalendarEvent.start_time < end,
    ).delete(synchronize_session=False)

    seen = set()
    n = 0
    for ev in events:
        uid = ev["uid"]
        if uid in seen:  # 同一 uid 窗口内重复(重复事件实例)→ 取首条
            continue
        seen.add(uid)
        row = CalendarEvent(
            user_id=source.user_id, source_id=source.id, uid=uid,
            start_time=ev["start"], end_time=ev["end"], all_day=ev["all_day"],
            status=ev["status"], last_synced_at=now,
        )
        row.set_title(ev["title"])
        row.set_location(ev["location"])
        row.set_description(ev["description"])
        row.set_attendees(ev["attendees"])
        db.add(row)
        n += 1
    source.last_sync_at = now
    source.last_error = None
    return {"synced": n}


def sync_all_sources(db: Session, user_id: int) -> dict:
    """同步该用户所有 sync_enabled 源。每源 try/except 隔离:一源坏只记它的 last_error,不阻断其它(fail-soft per source)。"""
    sources = (
        db.query(CalendarSource)
        .filter(CalendarSource.user_id == user_id, CalendarSource.sync_enabled.is_(True))
        .all()
    )
    summary: dict = {}
    for src in sources:
        try:
            summary[src.id] = sync_source(db, src)
            db.commit()
        except Exception as e:  # fail-soft per source — 记 last_error,不抛
            db.rollback()
            src.last_error = _scrub_error(e)
            db.commit()
            logger.warning("[calendar] source=%s 同步失败: %s", src.id, e)
            summary[src.id] = {"error": _scrub_error(e)}
    return {"sources": summary, "count": len(sources)}


# ── 隐私接缝(HARD boundary)──────────────────────────────────────────────
# 这是 CalendarEvent → 任何 LLM/agent 路径的唯一门。绝不返回 title/location/
# description/attendees/uid/notes —— 只给粗粒度 busy 窗口。任何 agent 读日历必须经此。

def calendar_event_for_llm(event: CalendarEvent) -> dict:
    """LLM/agent 安全视图:只暴露非身份性的粗粒度字段。

    返回 {start, end, busy, all_day, source_label}。绝不含 title/location/
    description/attendees/uid。这是日历 → LLM 的不可绕过边界(隐私接缝)。
    """
    # 固定通用词 —— 绝不外泄用户自定义源名(可能含人名,如 "张总 1on1");别改成 src.name。
    label = "日历"
    return {
        "start": event.start_time.isoformat() if event.start_time else None,
        "end": event.end_time.isoformat() if event.end_time else None,
        "busy": True,
        "all_day": bool(event.all_day),
        "source_label": label,
    }
