"""
训练负荷安全规则 —— ACWR (Acute:Chronic Workload Ratio)。

来源：Gabbett 2016, "The training-injury prevention paradox"
  - ACWR 0.8-1.3: 最佳区间（sweet spot）
  - ACWR < 0.8: undertraining，体能流失
  - ACWR > 1.5: 伤病风险显著升高（高于 1.5 的一周，下一周伤病率可达 +50%）
"""

from typing import Optional

from app.agents.safety_guardian.engine import register
from app.agents.safety_guardian.schema import Alert, Severity
from app.twin.schema import HealthTwin

ACWR_RULE_IDS = frozenset(
    {
        "training.acwr_overload",
        "training.acwr_undertraining",
    }
)


@register
def training_acwr_overload(twin: HealthTwin) -> Optional[Alert]:
    """ACWR > 1.5 —— 过载风险。"""
    acwr = twin.behavioral.acute_chronic_ratio
    if acwr is None:
        return None
    if twin.behavioral.acwr_reliable is not True:
        return None
    # Defensive consistency guard: a ratio cannot indicate acute overload when
    # the same Twin explicitly says the recent load is zero. This also prevents
    # a stale cached ratio from surviving a later activity resync.
    if (
        twin.behavioral.training_load_7d is not None
        and twin.behavioral.training_load_7d <= 0
    ):
        return None
    if acwr <= 1.5:
        return None

    severity = Severity.HIGH if acwr > 2.0 else Severity.MEDIUM

    return Alert(
        rule_id="training.acwr_overload",
        category="training_load",
        severity=severity,
        title=f"训练负荷过载 (ACWR={acwr:.2f})",
        message=(
            f"你的急慢性负荷比 (ACWR) = {acwr:.2f}，超过 Gabbett 模型安全阈值 1.5。"
            "高 ACWR 是未来 1-2 周软组织伤病和过度疲劳的强预测因子。"
        ),
        action=(
            "接下来 5-7 天降低训练强度 20-30%，增加恢复（充足睡眠、补液、软组织放松）；"
            "观察是否有持续性肌腱酸痛、静息心率上升、睡眠恶化等过训练信号。"
        ),
        data_citation={"acwr": acwr, "acwr_zone": twin.behavioral.acwr_zone},
        references=[
            "https://bjsm.bmj.com/content/50/5/273",
        ],
    )


@register
def training_acwr_undertraining(twin: HealthTwin) -> Optional[Alert]:
    """ACWR < 0.8 + 本周运动次数少 —— undertraining，体能流失。"""
    acwr = twin.behavioral.acute_chronic_ratio
    if acwr is None:
        return None
    if twin.behavioral.acwr_reliable is not True:
        return None
    if acwr >= 0.8:
        return None

    workouts_this_week = twin.behavioral.workouts_this_week or 0

    # 完全没运动是另一件事，不通过这条规则
    if workouts_this_week == 0:
        return None

    return Alert(
        rule_id="training.acwr_undertraining",
        category="training_load",
        severity=Severity.LOW,
        title=f"训练负荷偏低 (ACWR={acwr:.2f})",
        message=(
            f"你的 ACWR = {acwr:.2f}，低于最佳区间下限 0.8。"
            f"本周运动 {workouts_this_week} 次。长期偏低会损失有氧基础和肌肉质量。"
        ),
        action=(
            "下周尝试增加 1-2 次 Z2 有氧（40-60 分钟慢跑/骑行/快走），"
            "每周 2 次力量训练（大肌群复合动作）。缓慢提升，不要一次拉回 ACWR。"
        ),
        data_citation={
            "acwr": acwr,
            "workouts_this_week": workouts_this_week,
            "training_load_7d": twin.behavioral.training_load_7d,
        },
    )


@register
def training_complete_inactivity(twin: HealthTwin) -> Optional[Alert]:
    """一周完全没运动 —— 独立于 ACWR 的信息提示。"""
    w = twin.behavioral.workouts_this_week or 0
    if w > 0:
        return None

    # 如果连 Twin 都没有训练负荷数据，就不触发（可能是数据未同步）
    if twin.behavioral.training_load_7d is None and twin.behavioral.acute_chronic_ratio is None:
        return None

    return Alert(
        rule_id="training.complete_inactivity",
        category="training_load",
        severity=Severity.LOW,
        title="本周零运动",
        message=(
            "过去 7 天没有有记录的训练。久坐与全因死亡风险直接相关；"
            "WHO 建议成人每周至少 150 分钟中等强度或 75 分钟高强度有氧 + 2 次力量训练。"
        ),
        action="今天先走 20 分钟快走（不需要装备、不需要换衣服）；本周目标 3 次 30 分钟任意形式的运动。",
        data_citation={"workouts_this_week": w},
    )
