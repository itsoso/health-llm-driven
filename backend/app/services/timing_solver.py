"""每日时点约束求解器 —— 把六域的项排上一条满足全部硬约束的时间轴(纯函数,无 DB)。

这是 docs/design/health-os/planning-methodology.md §5「约束求解器」与
docs/design/health-os/os-design.md「Write 层 timing-solver」点名的**唯一真缺**的决策核心。

输入一组归一化 Item(药/补剂/饮食/运动/睡眠/复查)+ 当日上下文(餐/作息/运动/就绪度/静默窗),
输出:scheduled(排上时间轴的项)/ rejected(硬禁忌·走告警通道非排程)/ deferred(被静默窗或复查配额顺延)。

铁律(methodology §5 的 8 层冲突消解优先级,高→低):
  1. 安全限幅       —— 硬禁忌(DDI/DSI/PGx)、Red+力量、急性病 → 不可排,剔除走告警
  2. 越界写保护     —— 调用方负责(剂量/诊断/复查间隔下限),求解器不接收此类项
  3. 处方因果裁决禁令 —— 调用方负责(降级 clinician_review)
  4. 药代螯合间隔    —— 钙×铁≥2h、钙/铁×左甲状腺素≥4h…多间隔冲突取「更长者优先」
  5. 餐锚定 + 昼夜相位 —— 空腹/餐前30/随含脂餐/睡前 落对应真实窗;锚点缺失按默认但标降级
  6. 恢复/状态门控    —— readiness 灯(Red 已在第1层剔力量)
  7. 通知预算 + 静默窗 —— quiet_hours、每日复查≤N 条按 severity 排占
  8. 用户偏好        —— 最低,冲突时让步

红线:求解器只排「时点/间隔/提醒」,绝不生成/调整剂量(R4)。剂量来自医生处方,
prescribed 项的 fixed_time(reminder_times)优先于锚点启发式。纯函数:无副作用、易单测。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ── 锚点类型(methodology §5)──────────────────────────────────────────────
ANCHOR_EMPTY_STOMACH = "empty_stomach"      # 晨起空腹(左甲状腺素/铁剂)
ANCHOR_BEFORE_MEAL_30 = "before_meal_30"    # 餐前 30(–60)min(PPI)
ANCHOR_WITH_MEAL = "with_meal"              # 随含脂正餐(脂溶维生素/Omega-3)
ANCHOR_AFTER_MEAL = "after_meal"            # 餐后(午餐后步行)
ANCHOR_BEDTIME = "bedtime"                  # 睡前(镁)
ANCHOR_PERI_WORKOUT_PRE = "peri_workout_pre"   # 训练前 1–2h(碳水)
ANCHOR_PERI_WORKOUT_POST = "peri_workout_post"  # 训练后(碳水+蛋白)
ANCHOR_ANYTIME = "anytime"                  # 灵活,填空隙

_VALID_ANCHORS = {
    ANCHOR_EMPTY_STOMACH, ANCHOR_BEFORE_MEAL_30, ANCHOR_WITH_MEAL, ANCHOR_AFTER_MEAL,
    ANCHOR_BEDTIME, ANCHOR_PERI_WORKOUT_PRE, ANCHOR_PERI_WORKOUT_POST, ANCHOR_ANYTIME,
}

# readiness 灯(与 movement_strategy 对齐)
GREEN, YELLOW, RED, GRAY = "green", "yellow", "red", "gray"

# ── 数据流 ────────────────────────────────────────────────────────────────
@dataclass
class Item:
    """一个待排程项(已归一化;medication/supplement→Item 的 adapter 是下一刀)。"""
    id: str
    domain: str                                  # medication/supplement/diet/movement/sleep/checkup
    title: str
    anchor: str = ANCHOR_ANYTIME
    anchor_ref: Optional[str] = None             # breakfast/lunch/dinner/workout(配合锚点)
    interval_constraints: List[Tuple[str, float]] = field(default_factory=list)  # (other_id, min_gap_h)
    severity: int = 50                           # 0–100,越高越重要(决定冲突时谁让步、复查配额)
    hard_forbidden: bool = False                 # DDI/DSI/PGx 硬禁忌 → 不可排,走告警
    forbidden_reason: Optional[str] = None
    requires_strength: bool = False              # 力量类运动项(Red 下剔除)
    deferrable: bool = True                      # 能否顺延(prescribed 固定项通常 False)
    preference_weight: float = 0.0               # 偏好加权(仅在不违反硬约束时生效)
    fixed_time: Optional[str] = None             # 医嘱固定时点 "HH:MM"(优先于锚点启发式)


@dataclass
class DayContext:
    meals: Dict[str, str] = field(default_factory=lambda: {
        "breakfast": "07:30", "lunch": "12:00", "dinner": "18:30"})
    wake: str = "07:00"
    sleep: str = "22:30"
    workout_start: Optional[str] = None
    readiness: str = GRAY
    quiet_hours: Tuple[str, str] = ("22:00", "08:30")
    daily_recheck_cap: int = 2
    anchors_degraded: bool = False               # 餐点是默认值(无真实打卡)→ 文案标降级
    work_start: Optional[str] = None             # 上班 "09:00"(None=未设;不约束)
    work_end: Optional[str] = None               # 下班 "18:00"
    is_workday: bool = True                       # 今天是否工作日(周末/休假→不避工作窗)


# ── 时间工具(分钟制,跨午夜安全)───────────────────────────────────────────
def _to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _to_hhmm(minutes: int) -> str:
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _in_quiet(minutes: int, quiet: Tuple[str, str]) -> bool:
    """静默窗(可跨午夜,如 22:00–08:30)。"""
    start, end = _to_min(quiet[0]), _to_min(quiet[1])
    minutes %= 24 * 60
    if start <= end:
        return start <= minutes < end
    return minutes >= start or minutes < end  # 跨午夜


def _in_work(minutes: int, ctx: DayContext) -> bool:
    """是否落在工作窗内(仅工作日且上下班都已设;常规白班,不约束夜班/异常)。"""
    if not ctx.is_workday or not ctx.work_start or not ctx.work_end:
        return False
    ws, we = _to_min(ctx.work_start), _to_min(ctx.work_end)
    if ws >= we:  # 跨午夜/异常 → 不约束(避免误把全天当工作窗)
        return False
    return ws <= (minutes % (24 * 60)) < we


# ── 锚点落桩(Step 1)─────────────────────────────────────────────────────
def _anchor_minutes(item: Item, ctx: DayContext) -> Optional[int]:
    """把锚点解析成目标时刻(分钟)。fixed_time 优先;anytime → None(后填)。"""
    if item.fixed_time:
        return _to_min(item.fixed_time)
    a = item.anchor
    if a == ANCHOR_ANYTIME:
        return None
    if a == ANCHOR_EMPTY_STOMACH:
        # 晨起空腹:起床后 ~15min,且早餐前
        return min(_to_min(ctx.wake) + 15, _meal(ctx, "breakfast") - 30)
    if a == ANCHOR_BEFORE_MEAL_30:
        return _meal(ctx, item.anchor_ref or "breakfast") - 30
    if a == ANCHOR_WITH_MEAL:
        return _meal(ctx, item.anchor_ref or "breakfast")
    if a == ANCHOR_AFTER_MEAL:
        return _meal(ctx, item.anchor_ref or "lunch") + 20
    if a == ANCHOR_BEDTIME:
        return _to_min(ctx.sleep) - 45
    if a == ANCHOR_PERI_WORKOUT_PRE:
        return (_to_min(ctx.workout_start) - 90) if ctx.workout_start else None
    if a == ANCHOR_PERI_WORKOUT_POST:
        return (_to_min(ctx.workout_start) + 60) if ctx.workout_start else None
    return None


def _meal(ctx: DayContext, ref: str) -> int:
    return _to_min(ctx.meals.get(ref, ctx.meals.get("breakfast", "07:30")))


# ── 主求解(纯函数)────────────────────────────────────────────────────────
def solve_day_schedule(items: List[Item], ctx: DayContext) -> Dict[str, list]:
    """求解当日时间轴。返回 {scheduled, rejected, deferred},均为可审计 dict 列表。

    确定性:同输入同输出(排序 key 含 id,无随机)。
    """
    rejected: List[dict] = []
    survivors: List[Item] = []

    # ── Step 0 安全剪枝(第 1 层:硬禁忌 / Red+力量)──────────────────────
    for it in items:
        if it.hard_forbidden:
            rejected.append({"id": it.id, "title": it.title, "domain": it.domain,
                             "reason": it.forbidden_reason or "硬禁忌(DDI/DSI/PGx)→ 走告警通道,不排程"})
            continue
        if it.requires_strength and ctx.readiness == RED:
            rejected.append({"id": it.id, "title": it.title, "domain": it.domain,
                             "reason": "Red 恢复不足:不排力量,改拉伸/休息"})
            continue
        if it.anchor not in _VALID_ANCHORS:
            it.anchor = ANCHOR_ANYTIME
        survivors.append(it)

    # ── Step 1 锚点落桩 ────────────────────────────────────────────────
    placed: Dict[str, Optional[int]] = {it.id: _anchor_minutes(it, ctx) for it in survivors}

    # ── Step 4(间隔)螯合约束满足:更长间隔优先,低优先项让步 ─────────────
    # 优先级:severity 高 + 不可顺延者占位;偏好权重最低。tier_key 越小越「占着不动」。
    def tier_key(it: Item) -> tuple:
        return (-it.severity, 0 if not it.deferrable else 1, -it.preference_weight, it.id)

    order = sorted(survivors, key=tier_key)
    by_id = {it.id: it for it in survivors}

    # 收集所有间隔约束(对称化)
    constraints: List[Tuple[str, str, float]] = []
    for it in survivors:
        for other_id, gap_h in it.interval_constraints:
            if other_id in by_id:
                constraints.append((it.id, other_id, gap_h * 60))
    # 更长间隔先满足
    constraints.sort(key=lambda c: -c[2])

    def _satisfy_intervals() -> None:
        """迭代收敛间隔约束(钙×铁≥2h、钙/铁×左甲状腺素≥4h…)。让步方=tier 更低者后移。
        仅对已落桩(非 None)的项生效 —— 故 anytime 项须先在 fill 里拿到时点再跑本函数。"""
        for _pass in range(4):  # 迭代收敛(项数小,固定几轮足够)
            moved = False
            for a_id, b_id, gap_min in constraints:
                ta, tb = placed.get(a_id), placed.get(b_id)
                if ta is None or tb is None:
                    continue
                if abs(ta - tb) >= gap_min:
                    continue
                # 违反:让「让步方」后移。让步方 = tier 更低(severity 低/可顺延/偏好)者
                ia, ib = by_id[a_id], by_id[b_id]
                yielder, fixed = (ia, tb) if tier_key(ia) > tier_key(ib) else (ib, ta)
                if not yielder.deferrable:
                    # 两个都不可顺延且冲突 → 标记冲突(让步给安全侧:把可调的那个尽量推)
                    other = ib if yielder is ia else ia
                    if other.deferrable:
                        yielder = other
                    else:
                        continue  # 双固定冲突:留给上层(医嘱)处理,不强行改
                # 把让步方推到「远侧」:本就在 fixed 之后→further after;在之前→further before
                placed[yielder.id] = (fixed + int(gap_min)) if placed[yielder.id] >= fixed else (fixed - int(gap_min))
                moved = True
            if not moved:
                break

    _satisfy_intervals()  # 第一轮:已落桩的锚点/固定项之间的间隔

    # ── anytime 项填空隙(锚点为 None 的)—— 从「起床+1h 或静默窗结束」较晚者起,错开 ──
    # 工作日避开工作窗:浮动主动 nudge 落在上班时段 → 顺延到下班后(不打扰工作);
    # 上班前的空档(起床~上班)仍可用。锚点项(空腹/餐前/睡前/医嘱固定)不受此约束。
    fallback = max(_to_min(ctx.wake) + 60, _to_min(ctx.quiet_hours[1]))
    work_end_min = _to_min(ctx.work_end) if (ctx.work_end and ctx.is_workday) else None
    for it in order:
        if placed[it.id] is None:
            if work_end_min is not None and _in_work(fallback, ctx):
                fallback = work_end_min  # 落在上班时段 → 挪到下班后
            placed[it.id] = fallback
            fallback += 30  # 错开,避免堆叠

    # 第二轮:anytime 项已落桩 → 补跑间隔约束,让两个「随时」螯合项(钙×铁)也守 ≥2h
    # (此前都是 None 被第一轮跳过,只在 fill 里 +30 错开)。螯合间隔(layer 4)优先级高于
    # 工作窗回避(layer 8),故被推动的 anytime 项即便落回工作时段也以安全间隔为先。
    _satisfy_intervals()

    # ── Step 7 静默窗 + 复查配额 ───────────────────────────────────────
    scheduled: List[dict] = []
    deferred: List[dict] = []
    qend = _to_min(ctx.quiet_hours[1])

    for it in order:
        t = placed[it.id]
        # 静默窗只约束「无生活锚点的浮动主动 nudge」(anchor=anytime 且可顺延)。
        # 生活锚点项(空腹/餐前/睡前/围训练)与 prescribed 固定项是医嘱/作息必达,
        # 即使落在静默窗也保留原时点 —— 绝不把处方剂量或晨起空腹药丢到次日(R4:不漏给药)。
        if it.anchor == ANCHOR_ANYTIME and it.deferrable and _in_quiet(t, ctx.quiet_hours):
            t = qend  # 浮动 nudge 顺延到静默窗结束
        scheduled.append({"id": it.id, "title": it.title, "domain": it.domain,
                          "time": _to_hhmm(t), "_min": t, "anchor": it.anchor,
                          "severity": it.severity, "degraded": ctx.anchors_degraded})

    # 复查配额:checkup 域按 severity 取前 N,其余顺延
    checkups = sorted([s for s in scheduled if s["domain"] == "checkup"],
                      key=lambda s: -s["severity"])
    for extra in checkups[ctx.daily_recheck_cap:]:
        scheduled.remove(extra)
        deferred.append({"id": extra["id"], "title": extra["title"], "domain": "checkup",
                         "reason": f"超每日复查配额({ctx.daily_recheck_cap}条)→ 顺延"})

    scheduled.sort(key=lambda s: (s["_min"], s["id"]))
    for s in scheduled:
        s.pop("_min", None)
        s.pop("severity", None)

    return {"scheduled": scheduled, "rejected": rejected, "deferred": deferred}
