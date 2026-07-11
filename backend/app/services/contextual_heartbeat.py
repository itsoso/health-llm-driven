# -*- coding: utf-8 -*-
"""情境心跳 —— 确定性触发器(Slice 2, v1 零 LLM)。

对标 OpenClaw 的 30min heartbeat「该为用户做点什么吗」,但**不偷** LLM 自检:
每 tick 读 Twin(缓存,绝不重建)→ 跑一组**纯确定性**触发规则,命中 → 候选提示。
候选是否真推由 task 层过既有 `interruption_budget` / `proactive_coordinator` 硬闸决定;
本模块只判「该不该提醒」,不发推送、不写库(R4:心跳只提示,永不写健康数据)。

设计取舍:
- 规则全是**纯函数**(输入 = 已从 Twin/DB 摘出的原语),无副作用、无 DB —— 单测可穷举正反例。
- `evaluate_heartbeat` 逐规则 try/except:**单条规则抛错计入 failed_rules 并 logger.error**
  (fail-loud,不静默),其余规则照跑,绝不让一条坏规则挂掉整个 tick。
- 每条规则至多产出 1 个候选(最紧迫的那个),避免一 tick 刷屏。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 常量(白天窗 / 各规则阈值)────────────────────────────────────────────
DAY_START_HOUR = 8          # 白天 tick 窗 [08:00, 22:00) —— 夜间不 tick
DAY_END_HOUR = 22

HYDRATION_AFTER_HOUR = 15   # 下午 15:00 后才提醒补水(上午落后是正常节奏)
HYDRATION_MIN_PCT = 40.0    # 进度 < 40% 目标 才提醒

MED_GRACE_MIN = 30          # 用药窗过点 > 30min 且今日未记录 → 错过

WORK_START_HOUR = 10        # 久坐仅在工作时段判定 [10:00, 18:00)
WORK_END_HOUR = 18
SEDENTARY_STEP_DELTA = 100  # 近 ~2h 新增步数 < 100 → 久坐
SEDENTARY_LOOKBACK_MIN_HOURS = 1.5   # 参照样本年龄须落在 [1.5h, 3h]
SEDENTARY_LOOKBACK_MAX_HOURS = 3.0   # (太新=还没到 2h;太旧=跨越太多不可比)

HEARTBEAT_TIER = "P1"       # 心跳提示统一 P1:可忽略、静默时段不推、受全局周预算封顶


def is_daytime(hour: int) -> bool:
    """当前用户本地小时是否落在白天 tick 窗 [08:00, 22:00)。夜间返回 False → 不 tick。"""
    return DAY_START_HOUR <= hour < DAY_END_HOUR


@dataclass
class HeartbeatCandidate:
    """一条候选提示(尚未过打扰预算)。"""

    rule_id: str        # hydration_gap / medication_missed / recheck_due / sedentary
    metric: str         # 埋点 metric 字段
    reason: str         # 打扰契约:为什么现在提醒
    action: str         # 打扰契约:建议动作
    title: str          # push 标题
    body: str           # push 正文(锁屏可见 → 不得含药名等 §5 敏感属性)
    tier: str = HEARTBEAT_TIER
    # 仅进 push data payload(App 内可用,不上锁屏):如 medication_name
    push_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HeartbeatInputs:
    """一次 tick 已从 Twin/DB 摘出的所有规则原语(task 层组装,规则层只读)。"""

    hour: int
    today: date
    now_minutes: int                       # 本地 HH*60+MM
    water_ml_today: int = 0
    water_goal_ml: int = 0
    water_progress_pct: float = 0.0
    active_meds: List[Dict[str, Any]] = field(default_factory=list)
    active_cycles: List[Dict[str, Any]] = field(default_factory=list)  # {id, cycle_type, planned_end_date}
    steps_now: Optional[int] = None
    steps_prior: Optional[int] = None      # ~2h 前的 steps_today(来自上一批心跳快照)
    prior_age_hours: Optional[float] = None


@dataclass
class HeartbeatResult:
    candidates: List[HeartbeatCandidate]
    considered: int
    failed_rules: int
    failed_rule_ids: List[str]


# ── 规则(纯函数,无副作用)────────────────────────────────────────────────


def rule_hydration_gap(
    *, hour: int, water_ml_today: int, water_goal_ml: int, water_progress_pct: float
) -> Optional[HeartbeatCandidate]:
    """下午 15:00 后、已在记录饮水但进度 < 40% 目标 → 补水提示。

    仅当 ``water_ml_today > 0`` 才触发:0 无法区分「没喝」与「没记录」,不骚扰不记饮水的用户。
    """
    if hour < HYDRATION_AFTER_HOUR:
        return None
    if water_goal_ml <= 0 or water_ml_today <= 0:
        return None
    if water_progress_pct >= HYDRATION_MIN_PCT:
        return None
    remaining = max(water_goal_ml - water_ml_today, 0)
    return HeartbeatCandidate(
        rule_id="hydration_gap",
        metric="water",
        reason=f"{hour} 点了,今日饮水仅 {water_progress_pct:.0f}% 目标",
        action="接一杯水喝掉",
        title="补点水吧",
        body=(
            f"今天喝了 {water_ml_today}ml,离目标还差约 {remaining}ml。"
            f"现在补一杯,别等到口渴。"
        ),
    )


def _hhmm_to_minutes(hhmm: Any) -> Optional[int]:
    try:
        h, m = str(hhmm).strip().split(":")
        return int(h) * 60 + int(m)
    except Exception:  # noqa: BLE001 — 脏 reminder_time 跳过该窗,不崩
        # fail-loud(安全评审 #2):静默剔除 = 该药窗悄悄退出漏服判定(under-alarm),
        # 留可观测痕迹让数据质量问题能被发现。
        logger.warning("[heartbeat] 无法解析 reminder_time=%r,该用药窗跳过漏服判定", hhmm)
        return None


def rule_medication_missed(
    *, now_minutes: int, active_meds: List[Dict[str, Any]]
) -> Optional[HeartbeatCandidate]:
    """今日某个用药提醒窗过点 > 30min 且未被 taken 记录覆盖 → 最早未覆盖窗的温和提示。

    覆盖判定用 ``taken_count``:一天多个提醒时段,已服 N 次视为覆盖最早 N 个到点窗
    (不做精确窗-记录配对,避免过报;宁可漏也不误报)。**不含任何剂量/是否补服的处方指令**,
    补服与否明确让位「按医嘱」(R4:AI 不开药、不给用药决策)。
    """
    worst: Optional[tuple] = None  # (earliest_uncovered_minute, med_dict)
    for med in active_meds or []:
        reminder_times = med.get("reminder_times") or []
        try:
            taken_count = int(med.get("taken_count") or 0)
        except (TypeError, ValueError):
            taken_count = 0
        due = sorted(
            mm
            for mm in (_hhmm_to_minutes(t) for t in reminder_times)
            if mm is not None and now_minutes >= mm + MED_GRACE_MIN
        )
        if len(due) > taken_count:
            first_uncovered = due[taken_count]
            if worst is None or first_uncovered < worst[0]:
                worst = (first_uncovered, med)
    if worst is None:
        return None
    med = worst[1]
    name = str(med.get("name") or "用药")
    return HeartbeatCandidate(
        rule_id="medication_missed",
        metric="medication",
        reason=f"{name} 的用药窗已过 30 分钟仍无今日记录",
        action="已服请打卡;是否补服按医嘱",
        title="用药提醒",
        # 隐私(安全评审 #1):锁屏可见的 body 不带药名(药名≈诊断,§5 Tier 敏感);
        # 药名走 push_data 只进 App 内。reason 不持久化不进 push,保留药名供预算门上下文。
        body=(
            "有一项用药到点超过半小时还没记录。已经服了就点一下打卡;"
            "忘了的话,是否补服请按医嘱决定。"
        ),
        push_data={"medication_name": name},
    )


def rule_recheck_due(
    *, today: date, active_cycles: List[Dict[str, Any]]
) -> Optional[HeartbeatCandidate]:
    """在飞干预周期已到/过复查节点(``planned_end_date <= today``)→ 复查提示。

    与 Wave-1 recheck 排程共用同一候选出口(此处只提示复测,不建卡、不改周期)。
    """
    due = [
        c
        for c in (active_cycles or [])
        if c.get("planned_end_date") is not None and c["planned_end_date"] <= today
    ]
    if not due:
        return None
    top = min(due, key=lambda c: (c["planned_end_date"], c.get("id") or 0))
    overdue_days = (today - top["planned_end_date"]).days
    when = "今天" if overdue_days <= 0 else f"已过 {overdue_days} 天"
    return HeartbeatCandidate(
        rule_id="recheck_due",
        metric="recheck",
        reason=f"干预周期到复查节点({when})",
        action="安排一次指标复测",
        title="该复查了",
        body=(
            "你的干预周期到了复查节点。安排一次指标复测,"
            "好和基线对照看看这一程的效果。"
        ),
    )


def rule_sedentary(
    *,
    hour: int,
    steps_now: Optional[int],
    steps_prior: Optional[int],
    prior_age_hours: Optional[float],
) -> Optional[HeartbeatCandidate]:
    """工作时段近 ~2h 步数几乎无增量 → 起身走动提示。

    需要一个 ~2h 前的参照步数(来自上一批心跳快照);无参照 / 参照不在 [1.5h,3h] 窗内
    / 步数回退(跨日归零、换设备)→ 不触发(欠报是安全方向,别误报)。
    """
    if not (WORK_START_HOUR <= hour < WORK_END_HOUR):
        return None
    if steps_now is None or steps_prior is None or prior_age_hours is None:
        return None
    if not (SEDENTARY_LOOKBACK_MIN_HOURS <= prior_age_hours <= SEDENTARY_LOOKBACK_MAX_HOURS):
        return None
    delta = steps_now - steps_prior
    if delta < 0:
        return None
    if delta >= SEDENTARY_STEP_DELTA:
        return None
    return HeartbeatCandidate(
        rule_id="sedentary",
        metric="steps",
        reason=f"工作时段近 2 小时步数几乎没动(+{delta} 步)",
        action="起身走动两三分钟",
        title="起来动一动",
        body=(
            "过去两个小时几乎没走动。方便的话起身接杯水、走两圈,"
            "让身体重新启动一下。"
        ),
    )


# ── 编排(逐规则 fail-loud)──────────────────────────────────────────────


def evaluate_heartbeat(inp: HeartbeatInputs) -> HeartbeatResult:
    """跑全部规则,汇总候选。单条规则抛错 → 计入 failed_rules + logger.error,其余照跑。"""
    candidates: List[HeartbeatCandidate] = []
    failed = 0
    failed_ids: List[str] = []

    rule_calls = (
        (
            "hydration_gap",
            lambda: rule_hydration_gap(
                hour=inp.hour,
                water_ml_today=inp.water_ml_today,
                water_goal_ml=inp.water_goal_ml,
                water_progress_pct=inp.water_progress_pct,
            ),
        ),
        (
            "medication_missed",
            lambda: rule_medication_missed(
                now_minutes=inp.now_minutes, active_meds=inp.active_meds
            ),
        ),
        (
            "recheck_due",
            lambda: rule_recheck_due(today=inp.today, active_cycles=inp.active_cycles),
        ),
        (
            "sedentary",
            lambda: rule_sedentary(
                hour=inp.hour,
                steps_now=inp.steps_now,
                steps_prior=inp.steps_prior,
                prior_age_hours=inp.prior_age_hours,
            ),
        ),
    )

    for rule_id, call in rule_calls:
        try:
            out = call()
        except Exception as e:  # noqa: BLE001 — fail-loud:计数 + 告警,绝不吞、不挂整 tick
            failed += 1
            failed_ids.append(rule_id)
            logger.error(
                "[heartbeat] 规则 %s 抛错(计入 failed_rules,其余规则照跑): %s",
                rule_id,
                e,
            )
            continue
        if out is not None:
            candidates.append(out)

    return HeartbeatResult(
        candidates=candidates,
        considered=len(candidates),
        failed_rules=failed,
        failed_rule_ids=failed_ids,
    )
