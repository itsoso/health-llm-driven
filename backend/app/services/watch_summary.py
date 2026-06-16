"""Apple Watch 腕上摘要(W1 大脑)。

把 agenda_service.today() 投影成 watch 优化的紧凑视图:
- status:今日状态灯(绿/黄/红/灰)+ readiness + 一句话 headline
- top_action:此刻最该做的一件可执行事(腕上一眼)
- quick_actions:打点入口目录(喝水/补剂/运动/记一餐/打卡)—— watch 渲染按钮,各指向已有端点
- push_items:该推到手腕的关键信息(分级 P0/P1,运动/补剂/睡眠/复查),小屏只留最多 3 条

只读投影,不写库、不绕过 Safety Guardian(critical 告警仍走告警通道);headline/push 措辞不诊断不开方。
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services import agenda_service

# 打点入口目录(canonical):watch 据此渲染按钮,endpoint 指向已有写接口。
# value 由 watch 端补(喝水 ml / 运动 reps 等);diet_voice 走语音解析草稿流。
QUICK_ACTIONS: List[Dict[str, Any]] = [
    {"kind": "water", "label": "喝水", "endpoint": "/water/records/quick",
     "method": "POST", "param": "amount", "unit": "ml", "suggested": [250, 500]},
    {"kind": "supplement", "label": "补剂", "endpoint": "/supplements/records", "method": "POST"},
    {"kind": "exercise", "label": "运动", "endpoint": "/daily-health/exercise", "method": "POST",
     "hint": "俯卧撑/跑步等"},
    {"kind": "diet_voice", "label": "记一餐", "endpoint": "/diet/voice/parse", "method": "POST",
     "input": "voice"},
    {"kind": "checkin", "label": "打卡", "endpoint": "/checkin/records/quick", "method": "POST"},
]

_LIGHT_HEADLINE = {
    "green": "今日恢复良好,可按计划训练",
    "yellow": "今日恢复一般,适度为宜",
    "red": "今日建议以休息为主",
}
_PUSH_CAP = 3   # 手腕小屏:最多 3 条关键推送(对齐 R15 稀缺中断预算)


def _push_tier(item: Dict[str, Any]) -> Optional[str]:
    """该议程项是否值得推到手腕 + 分级(P0 必响应 / P1 可忽略)。其余不推。"""
    t = item.get("type")
    st = item.get("status")
    if t == "checkup" and st == "overdue":
        return "P0"                      # 逾期复查
    if t == "training" and item.get("light") == "red":
        return "P1"                      # 今日建议休息
    if t == "correction":
        return "P1"                      # 协议自纠偏
    if t == "medication" and st == "pending":
        return "P1"                      # 用药待办
    return None


def _action_view(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": item.get("title"),
        "kind": item.get("type"),
        "time_window": item.get("time_window"),
        "source": item.get("source"),
    }


def _push_view(item: Dict[str, Any], tier: str) -> Dict[str, Any]:
    return {
        "tier": tier,
        "title": item.get("title"),
        "detail": item.get("detail"),
        "kind": item.get("type"),
        "source": item.get("source"),
    }


def build_watch_summary(db: Session, user_id: int) -> Dict[str, Any]:
    """腕上摘要(只读投影 agenda.today)。"""
    agenda = agenda_service.today(db, user_id)
    items: List[Dict[str, Any]] = agenda.get("items", []) or []

    training = next((i for i in items if i.get("type") == "training"), None)
    light = (training or {}).get("light") or "gray"
    readiness = (training or {}).get("readiness_score")

    actionable = [
        i for i in items
        if (i.get("source") or {}).get("object_type") == "health_protocol"
        and i.get("status") == "pending"
    ]
    actionable.sort(key=lambda x: -(x.get("priority") or 0))
    top_action = _action_view(actionable[0]) if actionable else None

    if training and training.get("light") in _LIGHT_HEADLINE:
        headline = _LIGHT_HEADLINE[training["light"]]
    elif actionable:
        headline = f"还有 {len(actionable)} 项待打点"
    else:
        headline = "今日暂无待办"

    push: List[Dict[str, Any]] = []
    for i in items:
        tier = _push_tier(i)
        if tier:
            push.append(_push_view(i, tier))
    push.sort(key=lambda x: 0 if x["tier"] == "P0" else 1)
    push = push[:_PUSH_CAP]

    return {
        "status": {"light": light, "readiness_score": readiness, "headline": headline},
        "top_action": top_action,
        "agenda": {"total": agenda.get("count", 0), "pending": len(actionable)},
        "quick_actions": QUICK_ACTIONS,
        "push_items": push,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
