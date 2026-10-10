"""Read-only presentation of an existing daily plan; never invoke a planner."""
from __future__ import annotations

from datetime import date, datetime
import re
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.daily_operating_plan import DailyOperatingPlan

_REQUEST = re.compile(
    r"(?:请)?(?:(?:给我|展示|查看|看看)(?:一下)?)?(?:我的)?(?:今日|今天)(?:的)?(?:健康)?计划[。！!？?]?"
)


def resolve_daily_plan_request(snapshot) -> tuple[int, date] | None:
    if snapshot is None or snapshot.intent.is_write:
        return None
    owner = snapshot.context.user_id
    if type(owner) is not int or owner <= 0:
        return None
    if type(snapshot.envelope.user_id) is not int or snapshot.envelope.user_id != owner:
        return None
    text = str(snapshot.envelope.text or "").strip()
    if not _REQUEST.fullmatch(text):
        return None
    now = snapshot.context.current_time
    if now.tzinfo is None:
        return None
    return owner, now.astimezone(ZoneInfo(snapshot.context.timezone)).date()


def read_daily_plan_snapshot(db: Session, user_id: int, plan_date: date) -> dict:
    """Only SELECT. No autoflush, Twin refresh, advice audit or agenda materialization."""
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("authenticated owner required")
    with db.no_autoflush:
        row = db.query(DailyOperatingPlan).filter(
            DailyOperatingPlan.user_id == user_id,
            DailyOperatingPlan.plan_date == plan_date,
        ).one_or_none()
        if row is None:
            return {"found": False, "plan_date": plan_date.isoformat()}
        updated = row.updated_at or row.created_at
        return {
            "found": True, "id": row.id, "plan_date": row.plan_date.isoformat(),
            "status": row.status,
            "updated_at": updated.isoformat() if updated else None,
            "actions": row.actions,
            "doctor_escalation": row.doctor_escalation or {},
        }


def render_daily_plan_snapshot(payload: dict) -> str:
    day = payload["plan_date"]
    if not payload["found"]:
        return (
            f"{day} 还没有已保存的今日计划。"
            "这不代表今天无需行动。本次只查询已有安排，没有生成新计划或创建提醒。"
        )
    lines = [
        f"你的今日计划（{day}）",
        "来源：当日已保存的计划快照，本次未重新评估健康状态或生成计划。",
    ]
    if payload.get("status") != "active":
        lines.append("这份计划当前不处于执行状态，不能作为今天继续执行的指令。")
        return "\n\n".join(lines)
    actions = payload.get("actions")
    if not isinstance(actions, list):
        raise ValueError("invalid saved daily-plan actions")
    if any(not isinstance(a, dict) or not isinstance(a.get("title"), str)
           or not a["title"].strip() for a in actions):
        raise ValueError("invalid saved daily-plan action")
    visible = actions
    if not visible:
        lines.append("快照中没有待展示的行动；这不代表已完成全部目标或无需关注健康。")
    for index, action in enumerate(visible, 1):
        title = action["title"].strip()
        lines.append(f"{index}. {title}")
        why = action.get("why")
        if isinstance(why, str) and why.strip():
            lines.append(f"   原计划理由：{why.strip()}")
        boundary = action.get("claim_boundary")
        if isinstance(boundary, str) and boundary.strip():
            lines.append(f"   适用边界：{boundary.strip()}")
    escalation = payload.get("doctor_escalation")
    if isinstance(escalation, dict) and escalation.get("needed"):
        lines.append("原计划包含就医提示，请结合医生意见核对，不能据此判断当前风险已经解除。")
    lines.append("这是已有安排，不是本次重新给出的医嘱；如身体状况变化，应先核对是否仍适用。")
    return "\n\n".join(lines)


def render_daily_plan_draft(local_now: datetime) -> str:
    """Pure, unsaved routine template; no inferred health facts or business writes."""
    if local_now.tzinfo is None:
        raise ValueError("timezone-aware turn time required")
    evening = local_now.hour >= 18
    actions = (
        ["现在：简单记下今天的饮食、活动和身体感受；没记录的项目可以留空，不必补做白天的安排。",
         "休息前：把手头可延后的事情留到明天，按你平时的作息准备休息。",
         "收尾：选出明天最想关注的一件事，先写下来；今天未完成的事项可以重新安排。"]
        if evening else
        ["现在：记下今天最想完成的一件事，以及当前的身体感受，先确定今天的重点。",
         "接下来：按你原有的日常安排吃饭、工作和休息；方便时记录实际饮食和活动，不需要为完成计划额外加量。",
         "今天结束前：回顾完成了什么、有什么不舒服，把需要继续关注的事项记下来，再按平时作息准备休息。"]
    )
    lines = [f"今日计划草稿（未保存） · {local_now.date().isoformat()}",
             "今天没有已保存的计划，先给你一份可自行调整的日常安排："]
    lines.extend(f"{index}. {action}" for index, action in enumerate(actions, 1))
    lines.extend([
        "这份通用草稿仅按当前本地时间组织，不依据病史、用药或设备读数制定，未做个性化健康评估；如已有医生安排，以医生安排为准。",
        "本次没有保存计划或创建提醒。",
    ])
    return "\n\n".join(lines)
