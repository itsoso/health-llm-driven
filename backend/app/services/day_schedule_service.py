"""每日时点日程服务 —— 把 timing_solver/timing_adapter 接上真实用户数据(让求解器「在跑」)。

数据流:
    medications(DB,药+补剂)──adapter──▶ Item[]
    user_profile(作息)─────────────────▶ DayContext
                                          │
                          forbidden_reasons(DDI/DSI 硬禁忌,见下方 SAFETY SEAM)
                                          ▼
                              timing_solver.solve_day_schedule ──▶ {scheduled, rejected, deferred}

分层:`schedule_from_medications` 是纯核心(无 DB,易单测);`build_day_schedule` 是薄 DB 包装。

⚠ SAFETY SEAM(cut 5):forbidden_reasons={med_id: reason} 当前由调用方注入,默认空。
完整 DDI/DSI 硬禁忌 prune 要接 SafetyGuardian 引擎(在已填 medication/supplement 分区的
HealthTwin 上跑规则 → 把命中的物质名映射回 med.id)—— 是独立一刀,且需 dsi/ddi WIP 落定。
在那之前:① SafetyGuardian 仍独立向用户告警(另一通道);② solver 仍强制螯合间隔与锚点。
本服务不重实现 DSI 逻辑(避免重复;删>写)。
"""
from typing import Dict, List, Optional

from app.services.timing_adapter import medications_to_items
from app.services.timing_solver import DayContext, solve_day_schedule


def _day_context(profile=None, *, overrides: Optional[dict] = None) -> DayContext:
    """从 user_profile(duck-typed)构建 DayContext;缺字段用 DayContext 默认值。"""
    ctx = DayContext()
    wake = getattr(profile, "usual_wake_time", None) if profile else None
    sleep = getattr(profile, "usual_sleep_time", None) if profile else None
    if wake:
        ctx.wake = wake
        # 早餐默认不早于「起床+30min」,避免晚起者早餐锚点跑到起床前
        if _to_min(ctx.meals["breakfast"]) < _to_min(wake) + 30:
            ctx.meals = {**ctx.meals, "breakfast": _add_min(wake, 30)}
    if sleep:
        ctx.sleep = sleep
    # 工作时间窗:浮动 nudge 避开上班时段(锚点药/补剂/餐不受影响,见 timing_solver)。
    work_start = getattr(profile, "work_start_time", None) if profile else None
    work_end = getattr(profile, "work_end_time", None) if profile else None
    if work_start:
        ctx.work_start = work_start
    if work_end:
        ctx.work_end = work_end
    for k, v in (overrides or {}).items():
        setattr(ctx, k, v)
    return ctx


def _to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _add_min(hhmm: str, delta: int) -> str:
    t = (_to_min(hhmm) + delta) % (24 * 60)
    return f"{t // 60:02d}:{t % 60:02d}"


def schedule_from_medications(
    meds,
    *,
    profile=None,
    forbidden_reasons: Optional[Dict] = None,
    ctx_overrides: Optional[dict] = None,
) -> Dict[str, list]:
    """纯核心:给定 medications + profile(+ 安全硬禁忌)→ 当日时间轴。无 DB。"""
    items = medications_to_items(meds, forbidden_reasons=forbidden_reasons or {})
    ctx = _day_context(profile, overrides=ctx_overrides)
    return solve_day_schedule(items, ctx)


def build_day_schedule(
    db,
    user_id: int,
    *,
    forbidden_reasons: Optional[Dict] = None,
    ctx_overrides: Optional[dict] = None,
) -> Dict[str, list]:
    """薄 DB 包装:查活跃 medications + user_profile,调纯核心求解。"""
    from app.models.medication import Medication
    from app.models.user_profile import UserProfile

    meds: List = (
        db.query(Medication)
        .filter(Medication.user_id == user_id, Medication.is_active.is_(True))
        .all()
    )
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

    # 日历忙碌块(CalDAV 同步来的)→ DayContext.busy,solver 浮动项避开会议。
    # 失败不阻塞排程(降级到无忙碌块);调用方传入的 ctx_overrides.busy 优先。
    overrides = dict(ctx_overrides or {})
    if "busy" not in overrides:
        try:
            from app.services.caldav_sync import today_busy_blocks
            overrides["busy"] = today_busy_blocks(db, user_id)
        except Exception:  # 忙碌块读取失败 → 退化为不避会议,不让它炸掉整条排程
            pass
    return schedule_from_medications(
        meds, profile=profile, forbidden_reasons=forbidden_reasons, ctx_overrides=overrides
    )
