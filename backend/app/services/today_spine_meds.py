"""今日脊柱 · 用药/补剂源 + 时间感知 now-marker + 时间排序键。

从 ``today_timeline_service`` 抽出的内聚子模块(控复杂度预算,主文件 <500 行):
- ``med_supplement_items`` —— medications 表的药/补剂 → 带真实时点的脊柱行动项
  (组合 day_schedule 时点 × medication_service 今日完成度,不重造、不 fork 完成路径)。
- ``sort_key`` —— 统一时间轴排序键(有时点项按时间升序在前,anytime 在后)。
- ``select_now_item`` —— 「现在该做什么」单项选择(当下/下一项,非清晨第一项)。

纯投影,无写、无副作用。fail-soft:任一取数失败 → 记 warning 返回空,不拖垮脊柱。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.agenda_service import _TW_ORDER  # 复用议程时间窗排序

logger = logging.getLogger(__name__)

# 仅药/补剂两域的图标/色(与 today_timeline_service._DOMAIN_STYLE 同源风格,本地最小副本避免循环 import)
_MED_STYLE: Dict[str, tuple[str, str]] = {
    "medication": ("medkit-outline", "#AF52DE"),
    "supplement": ("nutrition-outline", "#34C759"),
}


def _med_id_from_schedule(sched_id: str) -> Optional[int]:
    """day_schedule scheduled item 的 id(形如 "med:42")→ medication_id。"""
    if not isinstance(sched_id, str) or not sched_id.startswith("med:"):
        return None
    try:
        return int(sched_id.split(":", 1)[1])
    except (ValueError, IndexError):
        return None


def _minutes(hhmm: Optional[str]) -> Optional[int]:
    """HH:MM → 当日分钟;无/解析失败 → None。"""
    if not hhmm:
        return None
    try:
        h, m = (int(x) for x in str(hhmm).split(":")[:2])
        return h * 60 + m
    except (ValueError, AttributeError):
        return None


def _window(hhmm: Optional[str]) -> str:
    """HH:MM → 时间窗(与 today_timeline_service._current_window 同词表)。无时点 → anytime。"""
    mn = _minutes(hhmm)
    if mn is None:
        return "anytime"
    h = mn // 60
    if h < 11:
        return "morning"
    if h < 14:
        return "noon"
    if h < 17:
        return "afternoon"
    if h < 20:
        return "evening"
    if h < 23:
        return "bedtime"
    return "anytime"


def med_supplement_items(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """用药 + 补剂(medications 表)→ 带真实时点的脊柱行动项。

    统一脊柱核心缺口修复:meds/supplements 存在 medications 表(非 HealthProtocol),
    此前完全不进脊柱 → 首页回退 legacy 卡。这里把两个已有服务 **组合**(不重造):
    - ``build_day_schedule`` 的 scheduled item(id=med:{id},带 timing_solver 求解的真实 HH:MM
      时点 + domain=medication|supplement)给「这项几点做」。
    - ``medication_service.get_today_status`` 给「今天服了没」(taken/pending,按 times_per_day)。

    完成走既有闭环(complete_ref={medication|supplement, med_id};上游 _attach_event_ids 物化
    HealthEvent;agenda_service.complete_item / timeline_agenda_service 已处理 med/supplement)
    —— 不 fork 完成路径。

    R4:subtitle 仅记录性「建议时点 + 今日进度」描述,不含剂量处方/因果。
    fail-soft:排程或状态查询任一失败 → 记 warning 返回空(不拖垮脊柱;med 仍经 SafetyGuardian
    / 其它通道告警)。
    """
    from app.services.day_schedule_service import build_day_schedule
    from app.services.medication_service import medication_service

    try:
        sched = build_day_schedule(db, user_id)
    except Exception as e:  # noqa: BLE001 — 排程失败降级:无 med 行,不崩
        logger.warning("[today_timeline] day_schedule build failed user=%s: %s", user_id, e)
        return []
    try:
        status_rows = medication_service.get_today_status(db, user_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("[today_timeline] med today_status failed user=%s: %s", user_id, e)
        return []

    status_by_id = {row["medication_id"]: row for row in status_rows}

    items: List[Dict[str, Any]] = []
    for s in sched.get("scheduled", []):
        domain = s.get("domain")
        if domain not in ("medication", "supplement"):
            continue  # 锻炼/餐/睡眠块由各自路径投影,这里只取药/补剂
        med_id = _med_id_from_schedule(s.get("id", ""))
        if med_id is None:
            continue
        st = status_by_id.get(med_id)
        # F5b:真多剂(reminder_times ≥2 个确定时点)→ 每槽一行(各带 slot);否则单行(无 slot,
        # 与改前逐字节相同)。timing_solver 把 BID 折成单项(只取 times[0]),这里按 med 的
        # reminder_times 在投影层展开,让 BID 两剂各成脊柱行(各自闭环、各自 uq_medlog 槽)。
        slots = [t for t in ((st or {}).get("reminder_times") or []) if t]
        if len(slots) >= 2:
            items.extend(_multidose_items(domain, med_id, s, st, slots))
        else:
            items.append(_single_item(domain, med_id, s, st))
    return items


def _single_item(domain: str, med_id: int, s: Dict[str, Any],
                 st: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """单剂/每日一次药 → 一条脊柱行(无 slot,与 F5b 前逐字节相同)。"""
    total = (st or {}).get("total_count") or 1
    taken = (st or {}).get("taken_count") or 0
    done = taken >= total
    scheduled_for = s.get("time")  # timing_solver 求解的真实 HH:MM

    # subtitle:记录性描述(几点建议 + 今日进度),非处方。R4:不出剂量数字命令。
    timing_label = (st or {}).get("timing_label")
    bits: List[str] = []
    if scheduled_for:
        bits.append(f"建议 {scheduled_for}")
    if timing_label:
        bits.append(timing_label)
    if total > 1:
        bits.append(f"今日 {taken}/{total}")
    subtitle = " · ".join(bits) or None

    icon, color = _MED_STYLE[domain]
    return {
        "id": f"med_{med_id}",
        "kind": "action",
        "driver": "plan_driven",  # 在服药/补剂 = 预定承诺(医嘱/计划)
        "time_window": _window(scheduled_for),
        "scheduled_for": scheduled_for,
        "title": s.get("title") or (st or {}).get("name") or "用药",
        "subtitle": subtitle,
        "icon": icon,
        "color": color,
        "status": "completed" if done else "pending",
        "priority": 50,  # 与协议同档(都是今日承诺待办)
        "can_complete": not done,
        "complete_ref": {"object_type": domain, "object_id": med_id},
        "event_id": None,
        "action_kind": domain,
        "deep_link": None,
        "severity": None,
        "proof": None,
    }


def _multidose_items(domain: str, med_id: int, s: Dict[str, Any],
                     st: Optional[Dict[str, Any]], slots: List[str]) -> List[Dict[str, Any]]:
    """真多剂药(reminder_times ≥2)→ 每个排程时点一条脊柱行,各带剂量槽 slot。

    每槽 done = 该槽 HH:MM 有 taken 的 MedicationLog(来自 get_today_status 的 logs)。
    complete_ref 带 slot → 闭环时各成独立议程 HealthEvent + 各自确定性 taken_time 槽,
    BID 两剂互不幂等短路;同槽再点 → 同 HealthEvent + 同 uq_medlog 幂等。
    R4:subtitle 仅记录性(几点 + 今日进度),不出剂量数字命令。
    """
    icon, color = _MED_STYLE[domain]
    name = s.get("title") or (st or {}).get("name") or "用药"
    timing_label = (st or {}).get("timing_label")
    total = len(slots)
    # 该槽是否已服:匹配 taken 日志的 taken_time(确定性槽 = scheduled_for HH:MM)。
    # 按「当日分钟数」归一化比对,robust 于零填充差异("8:00" vs "08:00")——避免 done 标记
    # 漏判(纯 UI 显示侧;权威完成态仍由 _attach_event_ids 用 HealthEvent 覆盖,见安全评审 A1)。
    taken_minutes = {
        _minutes(log.get("time"))
        for log in ((st or {}).get("logs") or [])
        if log.get("status") == "taken"
    }
    taken_minutes.discard(None)

    out: List[Dict[str, Any]] = []
    for slot in slots:
        done = _minutes(slot) in taken_minutes
        bits: List[str] = [f"建议 {slot}"]
        if timing_label:
            bits.append(timing_label)
        bits.append(f"今日 {total} 次")
        subtitle = " · ".join(bits)
        # id 带 slot 后缀 → 每槽脊柱行各有稳定唯一 id(now-marker / 客户端 key 不撞)。
        slot_id = slot.replace(":", "")
        out.append({
            "id": f"med_{med_id}_{slot_id}",
            "kind": "action",
            "driver": "plan_driven",
            "time_window": _window(slot),
            "scheduled_for": slot,
            "title": name,
            "subtitle": subtitle,
            "icon": icon,
            "color": color,
            "status": "completed" if done else "pending",
            "priority": 50,
            "can_complete": not done,
            "complete_ref": {"object_type": domain, "object_id": med_id, "slot": slot},
            "event_id": None,
            "action_kind": domain,
            "deep_link": None,
            "severity": None,
            "proof": None,
        })
    return out


def sort_key(item: Dict[str, Any]):
    """脊柱排序键:带时点(scheduled_for HH:MM)优先按时间升序,无时点者按时间窗;
    同一时段内按优先级降序。返回 (has_time 0/1, 分钟数 or 大数, 时间窗序, -priority)。"""
    mn = _minutes(item.get("scheduled_for"))
    has_time = 0 if mn is not None else 1
    minutes = mn if mn is not None else 24 * 60 + 1  # 无时点 → 排在所有有时点项之后
    return (
        has_time,
        minutes,
        _TW_ORDER.get(item.get("time_window"), 9),
        -int(item.get("priority") or 0),
    )


def select_now_item(items: List[Dict[str, Any]], now: datetime) -> Optional[str]:
    """选「现在该做什么」单项的 id(时间感知 now-marker)。

    候选 = 可完成、未终态的行动项(can_complete=True)。规则:
    1. 已到点(scheduled_for <= now)里取**最靠后**一个(刚到点的优先于早上漏掉的更早项)。
    2. 否则取下一个未到点的(now 之后最近)。
    3. 仍无 → 无时点可完成项里优先级最高者(anytime 兜底)。
    None = 今天没有可完成的下一步(全完成/无待办)。

    不渲染 morning weigh-in 这种「第一项」错觉:严格按当前时刻挑当下/下一项。
    """
    cur_min = now.hour * 60 + now.minute
    candidates = [it for it in items if it.get("can_complete")]
    if not candidates:
        return None

    timed = [(it, _minutes(it.get("scheduled_for"))) for it in candidates]
    timed = [(it, mn) for it, mn in timed if mn is not None]

    # 1) 已到点(scheduled <= now)且时间最靠后的 = 最该现在做的
    due_now = [(it, mn) for it, mn in timed if mn <= cur_min]
    if due_now:
        due_now.sort(key=lambda x: (-x[1], -int(x[0].get("priority") or 0)))
        return due_now[0][0]["id"]

    # 2) 下一个未到点的(now 之后最近)
    upcoming = sorted(timed, key=lambda x: (x[1], -int(x[0].get("priority") or 0)))
    if upcoming:
        return upcoming[0][0]["id"]

    # 3) 无时点可完成项 → 优先级最高者
    anytime = sorted(candidates, key=lambda it: -int(it.get("priority") or 0))
    return anytime[0]["id"] if anytime else None
