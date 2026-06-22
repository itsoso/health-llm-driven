"""P1-B 事件前提醒(pre-event reminders)。

在排程项 / 日历事件**开始前**按类提前量推送一次,让用户有缓冲。每分钟扫描:
对每个有今日排程/日历/协议项的用户,收集带时刻的项(排程 med/supplement/movement/diet +
今日 CalendarEvent 会议 + 到期未完成的行为协议),命中提前量窗口就推。

行为协议(健康协议层)走 lead=0 的「到点轻推」(非 pre-event 提前量),tier 恒 P1
(绝不消耗 P0 预算);洗鼻类遇活跃禁忌红旗(鼻出血/鼻痛/发热/术后)抑制提醒(§3)。

提前量(分钟,常量;后续可做成 per-user 配置):
    会议/日历 = 10、服药 = 15、补剂 = 15、锻炼(workout) = 20、餐(diet) = 0、睡眠 = 0。
0 表示不做事件前提醒(餐/睡眠由既有分时提醒覆盖,这里不重复打扰)。

触发窗口:项开始 T,当 now ∈ [T − lead, T − lead + 1min) 时推(1 分钟扫描节拍)。北京时区。

幂等:每 (user_id, item_key, remind_date) 至多一次 —— 先写 SentEventReminder
(UniqueConstraint 兜底),冲突即视为已推,绝不跨扫描二次推。

稀缺门:全部过 `proactive_coordinator.can_notify_proactively`(R15 通知预算)。
会议/服药走 P0(较高优先级),补剂/锻炼走 P1。**不绕过**。

医疗边界:措辞 hedged,只提示"该做某事",不给剂量/处方/因果断言。
隐私:会议提醒推给**用户本人设备**,可带标题(本人通知,非 LLM 路径,
calendar_event_for_llm 脱敏门不适用);标题绝不进任何 LLM/agent 路径。

fail-soft:单个用户失败不影响整批,记日志。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy.exc import IntegrityError

from app.celery_app import celery_app
from app.database import SessionLocal
from app.services.notification.deeplinks import deeplink_for
from app.services.notification.push_service import PushService
from app.utils.async_helpers import run_async
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)

# 每类事件前提醒提前量(分钟)。0 = 不做事件前提醒。
LEAD_MINUTES: dict[str, int] = {
    "meeting": 10,      # 日历会议
    "medication": 15,
    "supplement": 15,
    "movement": 20,     # 锻炼/workout
    "diet": 0,          # 餐 — 由既有分时提醒覆盖
    "sleep": 0,         # 睡前 — 由既有睡眠提醒覆盖
    "protocol": 0,      # 行为协议 = 到点轻推(due-time nudge),无 pre-event 提前量
}

# 类 → 通知预算 tier(R15)。会议/服药较高优先级(P0),其余可忽略(P1)。
# protocol(行为轻推)显式 P1:绝不消耗 P0 周预算(P0 留给处方/异常生命体征)。
_KIND_TIER: dict[str, str] = {
    "meeting": "P0",
    "medication": "P0",
    "supplement": "P1",
    "movement": "P1",
    "protocol": "P1",
}

# 行为协议的 coarse time_window → 该日的 HH:MM 到点时刻(start_min 来源)。
# "anytime" 不在表内 → 无固定到点,跳过(不做到点提醒,避免无谓打扰)。
# bedtime=21:30:落在默认免打扰(22:00 起)之前,否则睡前轻推会被静默门吞掉成 no-op;
# 也契合「睡前 30–60 分钟开始放松」的提前量(safety review 观察)。
_TIME_WINDOW_TO_HHMM: dict[str, str] = {
    "morning": "08:00",
    "noon": "12:00",
    "afternoon": "15:00",
    "evening": "19:00",
    "bedtime": "21:30",
}


def _to_minutes(hhmm: str) -> int | None:
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def _schedule_kind(domain: str) -> str:
    """排程项 domain → 提醒类。medication/supplement/movement/diet 直接同名。"""
    return domain


def _push_body(kind: str, title: str, lead: int) -> tuple[str, str]:
    """生成 (推送标题, 正文)。hedged,无剂量/处方/因果断言。"""
    if kind == "meeting":
        return ("📅 日程提醒", f"「{title}」{lead} 分钟后开始,可以开始收尾了。")
    if kind == "medication":
        return ("💊 用药提醒", f"{title} 大约 {lead} 分钟后到点,可以准备一下。")
    if kind == "supplement":
        return ("🌿 补剂提醒", f"{title} 大约 {lead} 分钟后到点,可以准备一下。")
    if kind == "movement":
        return ("🏃 运动提醒", f"{title} 计划在 {lead} 分钟后开始,留点时间热身。")
    if kind == "protocol":
        # 到点轻推(lead=0):只提示「该做了」,完成与否由用户决定。无量、无处方、无因果。
        return ("✅ 健康提醒", f"现在可以做「{title}」了,完成后点一下确认。")
    return ("⏰ 提醒", f"{title} 大约 {lead} 分钟后开始。")


def _complete_ref_for(schedule_id: str | None, kind: str) -> dict | None:
    """day-schedule item id → 闭环完成的 source 引用(complete_ref)。

    timing_adapter 把药/补剂都编成 `med:{medication_id}`(同存 medications 表,domain 区分)。
    据此给 push 一个自描述的 complete_ref,让点完成的客户端能调
    POST /timeline/events/{id}/complete(经脊柱物化的 HealthEvent;handler 后续增量接)。
    认不出格式 → None(不假装能完成,守 Rule #1)。
    """
    if not schedule_id or ":" not in str(schedule_id):
        return None
    prefix, _, raw_id = str(schedule_id).partition(":")
    try:
        object_id = int(raw_id)
    except (ValueError, TypeError):
        return None
    if prefix == "med":
        # 药与补剂同表;按提醒类(kind)区分 object_type,客户端据此走对应完成 UI。
        return {"object_type": kind, "object_id": object_id}
    return None


def _collect_timed_items(db, user_id: int, today: date) -> list[dict]:
    """收集该用户今日带时刻的项: 排程(med/supplement/movement/diet) + 会议。

    返回 [{item_key, kind, title, start_min(int), lead(int), complete_ref}],
    只含 lead>0 的可提醒项。complete_ref 为闭环完成的 source 引用(可为 None)。
    """
    items: list[dict] = []

    # 1) 当日排程(timing-solver) — med/supplement/movement/diet
    try:
        from app.services.day_schedule_service import build_day_schedule

        schedule = build_day_schedule(db, user_id)
        for s in schedule.get("scheduled", []):
            kind = _schedule_kind(s.get("domain", ""))
            lead = LEAD_MINUTES.get(kind, 0)
            if lead <= 0:
                continue
            start_min = _to_minutes(s.get("time", ""))
            if start_min is None:
                continue
            sched_id = s.get("id")
            items.append({
                "item_key": str(sched_id or f"{kind}:?"),
                "kind": kind,
                "title": s.get("title") or "",
                "start_min": start_min,
                "lead": lead,
                "complete_ref": _complete_ref_for(sched_id, kind),
            })
    except Exception as e:  # noqa: BLE001
        logger.warning("[event-reminder] build_day_schedule 失败 user=%s: %s", user_id, e)

    # 2) 今日日历会议(CalendarEvent;带时刻、非全天)
    lead = LEAD_MINUTES.get("meeting", 0)
    if lead > 0:
        try:
            from app.models.calendar_sync import CalendarEvent

            day_start = datetime.combine(today, datetime.min.time())
            day_end = day_start + timedelta(days=1)
            events = (
                db.query(CalendarEvent)
                .filter(
                    CalendarEvent.user_id == user_id,
                    CalendarEvent.all_day.is_(False),
                    CalendarEvent.start_time.isnot(None),
                    CalendarEvent.start_time >= day_start,
                    CalendarEvent.start_time < day_end,
                )
                .all()
            )
            for ev in events:
                st = ev.start_time
                start_min = st.hour * 60 + st.minute
                # 标题可带给本人通知(非 LLM 路径);失败回退通用词。
                try:
                    title = ev.get_title() or "日程"
                except Exception:  # noqa: BLE001
                    title = "日程"
                items.append({
                    "item_key": f"cal:{ev.id}",
                    "kind": "meeting",
                    "title": title,
                    "start_min": start_min,
                    "lead": lead,
                    "complete_ref": None,  # 会议不走议程完成
                })
        except Exception as e:  # noqa: BLE001
            logger.warning("[event-reminder] 日历事件读取失败 user=%s: %s", user_id, e)

    # 3) 行为协议(健康协议层)— 到期 + 今日 pending + 有固定到点时间窗 → 到点轻推。
    try:
        from app.services import health_protocol_service as hp_svc
        from app.services.protocol_templates import nasal_red_flag_active

        nasal_suppressed: bool | None = None  # 懒求值,仅当确有洗鼻项才查
        for st in hp_svc.today_status(db, user_id):
            if not st.get("is_due_today") or st.get("today_status") != "pending":
                continue
            tw = st.get("time_window")
            hhmm = _TIME_WINDOW_TO_HHMM.get(tw or "")
            if hhmm is None:   # anytime / 未知 → 无固定到点,不推
                continue
            start_min = _to_minutes(hhmm)
            if start_min is None:
                continue
            iq = st.get("implied_quantity") or {}
            tkey = iq.get("template_key") or ""
            # §3 红旗抑制:洗鼻模板遇活跃禁忌(鼻出血/鼻痛/发热/术后)→ 跳过提醒。
            # caveat 已固定在 advisory_note(home 卡仍可见),这里只抑制主动推送。
            if tkey in ("nasal_wash_morning", "nasal_wash_evening"):
                if nasal_suppressed is None:
                    nasal_suppressed = nasal_red_flag_active(db, user_id)
                if nasal_suppressed:
                    continue
            pid = st.get("protocol_id")
            items.append({
                "item_key": f"protocol:{pid}",
                "kind": "protocol",
                "title": st.get("name") or "健康行动",
                "start_min": start_min,
                "lead": LEAD_MINUTES.get("protocol", 0),  # 0 = 到点推
                # 显式 complete_ref(不走 med-only 的 _complete_ref_for):
                # 客户端「完成/跳过」按钮直接拿它 POST /agenda/complete。
                "complete_ref": {"object_type": "health_protocol", "object_id": pid},
            })
    except Exception as e:  # noqa: BLE001
        logger.warning("[event-reminder] 协议读取失败 user=%s: %s", user_id, e)

    return items


def _candidate_user_ids(db, today: date) -> list[int]:
    """候选用户: 活跃用药/补剂用户 ∪ 今日有会议的用户 ∪ 有活跃协议的用户。"""
    from app.models.calendar_sync import CalendarEvent
    from app.models.health_protocol import HealthProtocol
    from app.models.medication import Medication

    ids: set[int] = set()
    for (uid,) in db.query(Medication.user_id).filter(Medication.is_active.is_(True)).distinct():
        if uid is not None:
            ids.add(uid)

    day_start = datetime.combine(today, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    rows = (
        db.query(CalendarEvent.user_id)
        .filter(
            CalendarEvent.all_day.is_(False),
            CalendarEvent.start_time.isnot(None),
            CalendarEvent.start_time >= day_start,
            CalendarEvent.start_time < day_end,
        )
        .distinct()
    )
    for (uid,) in rows:
        if uid is not None:
            ids.add(uid)

    # 有活跃 HealthProtocol 的用户(到点行为轻推由 _collect_timed_items 的协议源产出)。
    for (uid,) in (
        db.query(HealthProtocol.user_id)
        .filter(HealthProtocol.status == "active")
        .distinct()
    ):
        if uid is not None:
            ids.add(uid)
    return sorted(ids)


def _try_mark_sent(db, user_id: int, item_key: str, remind_date: date, kind: str) -> bool:
    """先占坑去重: INSERT 成功 → True(本次该推);UniqueConstraint 冲突 → False(已推过)。"""
    from app.models.sent_event_reminder import SentEventReminder

    row = SentEventReminder(
        user_id=user_id, item_key=item_key, remind_date=remind_date, kind=kind,
    )
    db.add(row)
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


@celery_app.task
def scan_event_reminders():
    """每分钟扫描: 推送"未来 N 分钟将开始的项"的事件前提醒(P1-B)。"""
    from app.agents.audit import log_proactive_trigger
    from app.services.proactive_coordinator import can_notify_proactively

    now_cn = get_china_now()
    now_min = now_cn.hour * 60 + now_cn.minute
    today = now_cn.date()

    sent = 0
    with SessionLocal() as db:
        try:
            user_ids = _candidate_user_ids(db, today)
        except Exception as e:  # noqa: BLE001
            logger.error("[event-reminder] 候选用户枚举失败: %s", e)
            return {"sent": 0}

        push_service = PushService(db)

        for user_id in user_ids:
            try:
                items = _collect_timed_items(db, user_id, today)
                for it in items:
                    # 触发窗口: now ∈ [T − lead, T − lead + 1min)
                    fire_min = it["start_min"] - it["lead"]
                    if now_min != fire_min:
                        continue

                    kind = it["kind"]
                    tier = _KIND_TIER.get(kind, "P1")

                    # 稀缺门(R15): 不通过则不推。
                    if not can_notify_proactively(db, user_id, tier=tier):
                        continue

                    # 幂等占坑: 已推过则跳过。
                    if not _try_mark_sent(db, user_id, it["item_key"], today, kind):
                        continue

                    title, body = _push_body(kind, it["title"], it["lead"])
                    # 点推送落到与该 kind 相关的页面 (认不出则省略, 回首页)。
                    deep_link = deeplink_for(kind)
                    complete_ref = it.get("complete_ref")
                    # 可完成的行动项 → 带 AGENDA_ACTION 类目 + 闭环完成端点。
                    # 推送上的「完成」按钮直接拿 complete_ref 当 body POST /api/v1/agenda/complete
                    # (该端点懒物化议程 HealthEvent 再闭环完成,无需先知道 event_id;
                    # 不在此 Celery 任务里物化,保持 producer 写轻量)。
                    data = {
                        "category": "AGENDA_ACTION" if complete_ref else "PRE_EVENT_REMINDER",
                        "reminder_type": "pre_event",
                        "kind": kind,
                        "item_key": it["item_key"],
                    }
                    if complete_ref:
                        data["complete_ref"] = complete_ref
                        data["complete_endpoint"] = "/api/v1/agenda/complete"
                    if deep_link:
                        data["deep_link"] = deep_link
                    try:
                        run_async(push_service.send_notification(
                            user_id=user_id,
                            notification_type="reminder",
                            title=title,
                            content=body,
                            data=data,
                        ))
                        sent += 1
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            "[event-reminder] 推送失败 user=%s item=%s: %s",
                            user_id, it["item_key"], e,
                        )
                        continue

                    # 预算埋点(让 proactive_coordinator 计入周上限)。旁路,失败不抛。
                    log_proactive_trigger(
                        db, user_id,
                        agent_type="event_reminder_watch",
                        metric=kind, kind="pre_event",
                        delta=float(it["lead"]), notable=True, notified=True,
                        tier=tier,
                    )
            except Exception as e:  # noqa: BLE001
                logger.error("[event-reminder] 用户 %s 处理失败: %s", user_id, e)

    if sent:
        logger.info("[event-reminder] %s 发送 %s 条", today.isoformat(), sent)
    return {"sent": sent}
