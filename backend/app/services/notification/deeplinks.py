"""通知深链 (deep_link) 中心映射。

把"通知种类 (kind)"映射到 mobile expo-router 路由路径字符串,让用户点推送后落到
相关页面而不是首页。`mobile/hooks/useNotifications.ts` 已经会 `router.push(data.deep_link)`,
所以这里只负责"产出正确的路径";发送侧把返回值塞进 push 的 `data["deep_link"]`。

约定:
- 返回普通 expo-router 路径字符串 (如 "/calendar"、"/(tabs)/alerts")。
- **不**为这些场景发明 `health://` 自定义 scheme —— 已有的 `health://card/{id}`
  (action_card / intervention_cycle / open_loop) 由各自发送侧保留, 与此模块无关。
- kind 不认识 → 返回 None。发送侧据此**省略** deep_link 字段 (mobile 默认回首页, fail-soft)。
- deep_link 里只放路由名 / id, **绝不**放姓名、标题等 PII (隐私: link 会进 APNs payload)。

新增一种通知 kind 时, 在 `_KIND_ROUTES` 加一行 (或在 `deeplink_for` 里加分支),
并在 `backend/tests/test_notification_deeplinks.py` 补一个用例。
"""
from __future__ import annotations

from typing import Optional

# 静态 kind → 路由 的数据驱动映射 (无参数的简单场景)。
# 全部为已在 mobile/app/ 下确认存在的路由。
_KIND_ROUTES: dict[str, str] = {
    # 用药提醒 / pre_event → 记录页 (打卡用药)
    "medication": "/(tabs)/record",
    # 补剂提醒 / pre_event / 复购提醒 → 补剂库存页
    "supplement": "/supplement-inventory",
    "reorder": "/supplement-inventory",
    "reorder_nudge": "/supplement-inventory",
    # 会议 / 日历 pre_event → 日历页
    "meeting": "/calendar",
    "calendar": "/calendar",
    # 锻炼 / movement pre_event → 健身计划页
    "movement": "/fitness-plan",
    "exercise": "/fitness-plan",
    # 健康告警 (vitals / DDI / PGx / anomaly) → 安全告警 tab
    "health_alert": "/(tabs)/alerts",
}


def deeplink_for(kind: str, **params) -> Optional[str]:
    """把通知 kind (+ 可选参数) 映射成 expo-router 路径; 认不出返回 None。

    Args:
        kind: 通知种类。pre_event 提醒直接传具体 kind ("medication"/"supplement"/
              "meeting"/"movement"); 其余传上表的 key。
        **params: 仅个别 kind 需要:
            - ai_advice: domain="nutrition"|"diet"|"exercise"|"workout" 决定落点
            - workout_analysis: workout_id 决定是否带 id 进详情页

    Returns:
        路由字符串, 或 None (省略 deep_link)。
    """
    if not kind:
        return None

    if kind == "ai_advice":
        domain = (params.get("domain") or "").lower()
        if domain in {"nutrition", "diet"}:
            return "/diet"
        if domain in {"exercise", "workout", "movement"}:
            return "/fitness-plan"
        # 泛化建议无法判定落点 → 不强行落页, 回首页。
        return None

    if kind == "workout_analysis":
        workout_id = params.get("workout_id")
        if workout_id is not None:
            # workout-detail 读 query param id (非 [id] 动态段), 与既有发送侧一致。
            return f"/workout-detail?id={workout_id}"
        return "/(tabs)"

    return _KIND_ROUTES.get(kind)
