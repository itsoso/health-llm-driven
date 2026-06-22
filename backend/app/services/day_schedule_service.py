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
import logging
from typing import Dict, List, Optional

from app.services.timing_adapter import medications_to_items
from app.services.timing_solver import (
    RED,
    DayContext,
    Item,
    _to_hhmm,
    pick_workout_start,
    solve_day_schedule,
)

logger = logging.getLogger(__name__)

DEFAULT_WORKOUT_MINUTES = 40  # 用户未设 workout_target_minutes 时的缺省锻炼时长

# Garmin training_readiness_level → solver readiness 灯。仅「poor」判 Red(剔锻炼→休息);
# 其余(含缺值)留 gray/不门控——保守:只有明确低恢复才劝休息,不无信号瞎拦。
_READINESS_LEVEL_TO_ZONE = {"poor": RED}


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
    workout_rx: Optional[dict] = None,
    nutrition_rx: Optional[dict] = None,
    sleep_rx: Optional[dict] = None,
) -> Dict[str, list]:
    """纯核心:给定 medications + profile(+ 安全硬禁忌)→ 当日时间轴。无 DB。

    安全 seam(cut 5):跑 DDI/DSI 硬禁忌 → 补剂侧拒排(并入 forbidden_reasons)、处方药侧行警告。

    排程顺序(顺序敏感):
      1. 构建 ctx + 算锻炼块(_maybe_workout_item 设 ctx.workout_start)
      2. 围训练餐对齐(align_post_workout_meal 改 ctx.meals)—— 必须早于 meds 锚定餐
      3. medications_to_items 按(已对齐的)ctx.meals 锚定药/补剂
      4. 追加 diet(D1)+ sleep(D2)项
    """
    from app.services.schedule_safety_seam import compute_seam
    from app.services.schedule_diet_sleep import (
        align_post_workout_meal,
        meal_items,
        sleep_items,
    )

    seam_forbidden, warnings = compute_seam(meds)
    merged_forbidden = {**(forbidden_reasons or {}), **seam_forbidden}

    ctx = _day_context(profile, overrides=ctx_overrides)

    # 锻炼时点(cut 7)+ 处方化(cut A):有偏好窗 → 排锻炼块,块带 movement_coach 处方
    # (类型/强度/时长/RPE/ACTN3);intensity=rest → 拒排为「今日恢复」。workout_rx 由 DB 包装层算好传入
    # (纯核心不连库);None → 通用块。_maybe_workout_item 会设 ctx.workout_start(若排上锻炼)。
    workout = _maybe_workout_item(profile, ctx, workout_rx)

    # D1 围训练餐对齐:把离训练最近的餐拉到训练结束后 ≤60min(蛋白/碳水窗)。
    # 必须在 medications_to_items 之前 —— 餐锚定的药/补剂会按 ctx.meals 落桩。
    workout_min = (workout_rx or {}).get("duration_min") \
        or (getattr(profile, "workout_target_minutes", None) if profile else None) \
        or DEFAULT_WORKOUT_MINUTES
    align_post_workout_meal(ctx, workout_minutes=workout_min)

    items = medications_to_items(meds, forbidden_reasons=merged_forbidden)
    if warnings:
        for it in items:
            try:
                mid = int(str(it.id).split(":", 1)[1])
            except (ValueError, IndexError):
                continue
            if mid in warnings:
                it.warning = warnings[mid]

    if workout is not None:
        items.append(workout)

    # D1 三餐 + D2 睡眠卫生(均带 prescription,经 solver/agenda/watch 透传到各端)。
    items.extend(meal_items(ctx, nutrition_rx))
    items.extend(sleep_items(ctx, sleep_rx))

    return solve_day_schedule(items, ctx)


# cut A:movement_coach intensity_code → 时长/RPE/类型(处方化锻炼块)。
_RX_DURATION = {"high": 45, "moderate": 50, "low": 30}      # rest/unknown 不在此(rest→拒排)
_RX_RPE = {"high": "7-9", "moderate": "6-7", "low": "≤5"}
_RX_TYPE = {"high": "interval_or_strength", "moderate": "aerobic_z2", "low": "easy_aerobic"}
_RX_LABEL = {"high": "高强度训练", "moderate": "Z2 有氧", "low": "轻有氧"}


def workout_prescription(db, user_id: int) -> Optional[dict]:
    """movement_coach 处方(ACWR×readiness×ACTN3)→ 结构化 dict,供 _maybe_workout_item 用。

    fail-soft:取数/build_twin 任一失败 → None(回退通用块),失败记 warning(不静默吞)。
    复用 movement_coach 的矩阵函数(_resolve_training_status/_today_intensity/_gene_bias),
    不重实现。twin 用 use_cache=True(与 agenda 的训练灯同源,5min 缓存)。
    """
    try:
        from app.twin.builder import build_twin
        from app.agents.recovery_coach import compute_readiness
        from app.agents.movement_coach import coach as mc

        twin = build_twin(db, user_id, use_cache=True)
        try:
            zone = compute_readiness(twin).zone  # rest/light/moderate/hard
        except Exception:
            zone = None
        status, _src = mc._resolve_training_status(twin)
        intensity, guidance = mc._today_intensity(status, zone)
        # 急性不适/生病门控:与 movement_coach.run 同源(twin.acute.should_rest_from_training)。
        # 必须在这里复刻 —— 本函数走矩阵函数而非 coach.run,否则急性病人可能被排中等强度训练。
        acute = getattr(twin, "acute", None)
        if bool(getattr(acute, "should_rest_from_training", False)):
            intensity = "rest"
            guidance = getattr(acute, "training_guardrail", None) \
                or "当前有急性不适/生病状态,今天优先休息,不安排训练。"
        gene = mc._gene_bias(twin) or {}
        gene_tip = gene.get("tip") if isinstance(gene, dict) else None  # _gene_bias 返单数 "tip"(已 join)
        rx = {
            "intensity": intensity,
            "type": _RX_TYPE.get(intensity, "general"),
            "guidance": guidance,
        }
        if intensity in _RX_DURATION:
            rx["duration_min"] = _RX_DURATION[intensity]
            rx["rpe"] = _RX_RPE[intensity]
        if gene_tip:
            rx["gene_note"] = gene_tip
        return rx
    except Exception:
        logger.warning("workout_prescription failed for user %s", user_id, exc_info=True)
        return None


def _maybe_workout_item(profile, ctx: DayContext, rx: Optional[dict] = None) -> Optional[Item]:
    """据 profile 偏好选锻炼起点,设 ctx.workout_start(对齐围训练营养),返回 movement Item。

    - 无偏好窗 → None(不排锻炼)。
    - 处方 intensity=rest → Item(hard_forbidden, reason=guidance) 让 solver 拒排为「今日恢复」。
    - 当日无合适空档 → None(MVP 不强塞)。
    - readiness=Red → 仍返回 Item(requires_strength)让 solver 剔为「改拉伸/休息」,且不设
      ctx.workout_start(锻炼会被剔,围训练营养不应锚到不存在的锻炼)。
    - rx(cut A)→ 块带结构化处方(类型/强度/时长/RPE/ACTN3),title 用处方简短串。
    """
    pref = getattr(profile, "workout_pref_window", None) if profile else None
    if not pref:
        return None
    # 处方判定休息(过载/急性)→ 不排锻炼,拒排为恢复项(复用 hard_forbidden 拒排通道)。
    if rx and rx.get("intensity") == "rest":
        return Item(
            id="workout:today", domain="movement", title="今日主动恢复",
            hard_forbidden=True, forbidden_reason=rx.get("guidance") or "今日建议恢复,不安排训练",
            deferrable=False, severity=55, prescription=rx,
        )
    dur = (rx or {}).get("duration_min") \
        or (getattr(profile, "workout_target_minutes", None) if profile else None) \
        or DEFAULT_WORKOUT_MINUTES
    start = pick_workout_start(ctx, pref, dur)
    if start is None:
        return None
    if ctx.readiness != RED:
        ctx.workout_start = _to_hhmm(start)
    label = _RX_LABEL.get((rx or {}).get("intensity"))
    title = f"{label} {dur} 分钟" if label else f"锻炼 {dur} 分钟"
    return Item(
        id="workout:today",
        domain="movement",
        title=title,
        fixed_time=_to_hhmm(start),
        requires_strength=True,  # Red 下由 solver Step 0 剔除为「改拉伸/休息」
        deferrable=False,
        severity=55,
        prescription=rx,
    )


def build_workout_chain_steps(db, user_id: int) -> Optional[dict]:
    """P4 锻炼链:据已算好的 rx + ctx 产出链步描述符(供 agenda 物化成 N 条 HealthProtocol)。

    **复用 _maybe_workout_item 的同款 rx/ctx/pick_workout_start 计算**(不另起一套门控):
    - rx 由 workout_prescription 算好(ACWR×readiness×ACTN3 + 急性休息门控)。
    - readiness=Red / rx.intensity=="rest" → build_workout_chain 内部走降级(只拉伸/可选淋浴)。
    - 无 workout_pref_window → None(不建链)。
    - 当日无合适锻炼空档 且 非降级 → None(MVP 不强塞,与 _maybe_workout_item 一致)。

    返回 {chain_id, steps} 或 None。chain_id 按 (user, date) 稳定 → 跨刷新同 id → 幂等去重。
    """
    from app.models.user_profile import UserProfile
    from app.services.workout_chain_service import build_workout_chain
    from app.utils.timezone import get_china_today

    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    pref = getattr(profile, "workout_pref_window", None) if profile else None
    if not pref:
        return None

    rx = workout_prescription(db, user_id)

    # readiness 灯(与 build_day_schedule 同源:仅 poor→Red)。失败/无信号 → 不门控。
    ctx = _day_context(profile)
    try:
        zone = _latest_readiness_zone(db, user_id)
        if zone:
            ctx.readiness = zone
    except Exception:  # noqa: BLE001 — readiness 读取失败不阻塞链,留默认灯
        pass

    dur = (rx or {}).get("duration_min") \
        or (getattr(profile, "workout_target_minutes", None) if profile else None) \
        or DEFAULT_WORKOUT_MINUTES

    is_rest = bool(rx and rx.get("intensity") == "rest")
    if not is_rest:
        # 非降级:落锻炼起点(与 _maybe_workout_item 同款,Red 下不设 workout_start)。
        start = pick_workout_start(ctx, pref, dur)
        if start is None:
            return None  # 当日无空档,不建链(MVP 不强塞)
        if ctx.readiness != RED:
            ctx.workout_start = _to_hhmm(start)
        else:
            # Red 但非急性 rest:与 _maybe_workout_item 一致——锻炼会被剔,走降级链(只拉伸)。
            is_rest = True
            if rx is None:
                rx = {}
            rx["intensity"] = "rest"
            rx.setdefault("guidance", "今日恢复就绪度偏低,建议改为轻度拉伸/休息。")

    # 围训练餐对齐(改 ctx.meals)——与纯核心排程同款,保证链 meal 步时点合理。
    if ctx.workout_start:
        from app.services.schedule_diet_sleep import align_post_workout_meal
        align_post_workout_meal(ctx, workout_minutes=dur)

    steps = build_workout_chain(rx, ctx, workout_minutes=dur)
    if not steps:
        return None
    # chain_id 用确定性中国日(与 trigger_date / _is_due_today 同基准),避免午夜边界换天导致
    # chain 身份漂移、同日重复物化新链。
    chain_id = f"workout_chain:{user_id}:{get_china_today().isoformat()}"
    return {"chain_id": chain_id, "steps": steps}


def _latest_readiness_zone(db, user_id: int) -> Optional[str]:
    """最近一条带 training_readiness_level 的 garmin 行 → solver readiness 灯(仅 poor→Red)。"""
    from app.models.daily_health import GarminData

    row = (
        db.query(GarminData.training_readiness_level)
        .filter(
            GarminData.user_id == user_id,
            GarminData.training_readiness_level.isnot(None),
        )
        .order_by(GarminData.record_date.desc())
        .first()
    )
    if not row or not row[0]:
        return None
    return _READINESS_LEVEL_TO_ZONE.get(str(row[0]).strip().lower())


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

    # 锻炼 readiness 门控(cut 7):取最近一条有 training_readiness_level 的 garmin 行 → 灯。
    # 失败/无信号 → 不门控(留 gray),保守只在明确低恢复(poor→Red)时劝休息。
    if "readiness" not in overrides:
        try:
            zone = _latest_readiness_zone(db, user_id)
            if zone:
                overrides["readiness"] = zone
        except Exception:
            pass

    # 锻炼处方(cut A):movement_coach intensity×类型×ACTN3。fail-soft(None→通用块)。
    rx = workout_prescription(db, user_id) if getattr(profile, "workout_pref_window", None) else None

    # D1 营养处方 + D2 睡眠处方:薄 DB 层,fail-soft(None→无处方的纯餐项 / 默认睡眠卫生)。
    from app.services.schedule_diet_sleep import (
        nutrition_prescription,
        sleep_prescription,
    )

    nutrition_rx = nutrition_prescription(db, user_id)
    sleep_rx = sleep_prescription(db, user_id)

    return schedule_from_medications(
        meds, profile=profile, forbidden_reasons=forbidden_reasons,
        ctx_overrides=overrides, workout_rx=rx,
        nutrition_rx=nutrition_rx, sleep_rx=sleep_rx,
    )
