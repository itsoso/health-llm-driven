"""工作日微运动自适应策略 —— 细粒度事件驱动运动计划的决策核心(纯函数,无 DB)。

给定 readiness 灯 × 触发情境(到岗/久坐/会议空档/午餐后/整点)× 用户偏好 →
产出「此刻该做的一个低摩擦微运动」。设计见
docs/plans/2026-06-17-workday-health-scheduler-watch-first-design.md §1。

铁律(自适应 > 固定整点):
- Green:标准力量微运动(俯卧撑/深蹲)。
- Yellow:降级到低冲击(上斜俯卧撑/步行/拉伸)。
- Red:**停止力量推动**,只站立/轻走/拉伸/观察恢复 —— 身体差时绝不硬推。
- gray(就绪度待同步):保守等同 Yellow,文案标注「数据待同步,先来个温和的」。
- 用药/补剂不在此列(按已确认方案,AI 不调剂量)。

纯函数:无副作用、无 DB,易单测。调度器/agenda/watch 消费它产出的动作。
"""
from typing import Any, Dict, Optional

# readiness 灯
GREEN, YELLOW, RED, GRAY = "green", "yellow", "red", "gray"

# 触发情境(事件驱动)
TRIGGER_ARRIVAL = "arrival_at_work"     # 到公司,启动一个低摩擦动作
TRIGGER_SEDENTARY = "sedentary_break"   # 久坐打断
TRIGGER_MEETING_GAP = "meeting_gap"     # 会议空档
TRIGGER_POST_LUNCH = "post_lunch"       # 午餐后
TRIGGER_HOURLY = "hourly"               # 整点(用户偏好驱动)

_VALID_TRIGGERS = {
    TRIGGER_ARRIVAL, TRIGGER_SEDENTARY, TRIGGER_MEETING_GAP, TRIGGER_POST_LUNCH, TRIGGER_HOURLY,
}

# 力量类动作(可被偏好放大;Red 下一律不出)。kind=strength。
_STRENGTH = {
    "pushup": {"title": "俯卧撑", "kind": "strength", "unit": "个"},
    "squat": {"title": "深蹲", "kind": "strength", "unit": "个"},
    "incline_pushup": {"title": "上斜俯卧撑", "kind": "strength", "unit": "个"},
}
# 低冲击/恢复类。kind=mobility/cardio。
_GENTLE = {
    "walk": {"title": "步行", "kind": "cardio", "unit": "分钟"},
    "stretch": {"title": "拉伸", "kind": "mobility", "unit": "分钟"},
    "stand": {"title": "起身站立活动", "kind": "mobility", "unit": "分钟"},
}


def _act(code: str, amount: int, *, intensity: str, rationale: str) -> Dict[str, Any]:
    spec = _STRENGTH.get(code) or _GENTLE.get(code)
    return {
        "action_code": code,
        "title": spec["title"],
        "kind": spec["kind"],
        "amount": amount,
        "unit": spec["unit"],
        "intensity": intensity,        # standard / low / recovery
        "rationale": rationale,
    }


def adapt_movement(
    light: Optional[str],
    *,
    trigger: str,
    prefers_pushups: bool = False,
) -> Dict[str, Any]:
    """按 (readiness 灯 × 触发情境) 产出此刻的微运动。

    返回单个动作 dict(action_code/title/kind/amount/unit/intensity/rationale)。
    Red 绝不返回力量类;未知 trigger → 退化为久坐打断的默认。
    """
    g = (light or GRAY).lower()
    if g not in (GREEN, YELLOW, RED, GRAY):
        g = GRAY
    if trigger not in _VALID_TRIGGERS:
        trigger = TRIGGER_SEDENTARY

    # RED:停止力量,只恢复。任何触发都不出力量类。
    if g == RED:
        return _act("stretch", 5, intensity="recovery",
                    rationale="今日就绪度偏低,先拉伸/轻走,别上力量。")

    # GREEN:标准力量(或按偏好的俯卧撑);午餐后偏步行。
    if g == GREEN:
        if trigger == TRIGGER_POST_LUNCH:
            return _act("walk", 10, intensity="standard", rationale="午餐后步行助消化、稳血糖。")
        if trigger == TRIGGER_ARRIVAL:
            return _act("pushup", 15, intensity="standard", rationale="到岗一个低摩擦启动动作,开启今日复利。")
        if prefers_pushups:
            return _act("pushup", 20, intensity="standard", rationale="就绪度好,按你偏好来组俯卧撑。")
        # 久坐/会议空档/整点:力量微运动
        return _act("squat", 15, intensity="standard", rationale="久坐打断:一组深蹲激活下肢。")

    # YELLOW / GRAY:降级低冲击(GRAY 文案标注待同步)。
    note = "数据待同步,先来个温和的:" if g == GRAY else "就绪度一般,降级低冲击:"
    if trigger == TRIGGER_POST_LUNCH:
        return _act("walk", 8, intensity="low", rationale=note + "午餐后慢走 8 分钟。")
    if trigger == TRIGGER_ARRIVAL:
        return _act("incline_pushup", 8, intensity="low", rationale=note + "到岗来组上斜俯卧撑(对手腕更友好)。")
    if prefers_pushups:
        return _act("incline_pushup", 8, intensity="low", rationale=note + "降级成上斜俯卧撑,保住坚持。")
    return _act("walk", 6, intensity="low", rationale=note + "起身走 6 分钟、顺手拉伸。")
