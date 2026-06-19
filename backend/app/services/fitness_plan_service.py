"""C1 周健身计划服务 —— T2 自治(系统起草 → 用户一键确认 → 排程)。

数据流:
    build_twin(use_cache=True) ──▶ movement_coach ACWR×readiness 决策矩阵 + ACTN3 基因偏好
                                    │  (复用 coach._resolve_training_status / _today_intensity / _gene_bias)
                                    ▼
        本周 day_type 分配(hard/easy/rest)──▶ 7 天结构化 days[] ──▶ FitnessPlan(status=proposed)
                                    │
                       用户确认(POST /confirm)
                                    ▼
        原子 UPDATE...WHERE status='proposed' 的 rowcount 门(确认幂等,确认两次不重复排程)
                                    │
                                    ▼
        每个非 rest 日建一条 SmartReminder(确认产物)→ 落到 day timeline / 提醒通道

确定性优先:day_type 由 movement_coach 矩阵驱动(不另造启发式);rationale 是确定性文本
(引用健康指标处标注「相关非因果」);不出处方剂量、不出医疗裁决(R4)。disclaimer 含伤病先就医。

幂等三层(沿用项目既有模式):
  ① 一周一行(UniqueConstraint user+week_start),generate 同周已有则返回既有(不重复提议);
  ② confirm 走原子 UPDATE...WHERE status='proposed' 的 rowcount 门(并发双击只有一路 claim);
  ③ 每条排程 SmartReminder 建前按 (plan_id, date) 去重(belt-and-suspenders)。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.fitness_plan import FitnessPlan
from app.models.smart_reminder import SmartReminder
from app.utils.timezone import get_china_today

logger = logging.getLogger(__name__)

_WEEKDAY_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# C2 exercise_key 对接:day_type 主题 → 推荐动作(命中 C2 的 key 才填 exercise_key,否则空串)。
# 上肢力量给 pushup(也是 C3 Rokid 示例),下肢力量给 squat,核心给 plank。
_WORKOUT_THEMES = {
    "upper_strength": {"name": "上肢力量", "exercise_key": "pushup"},
    "lower_strength": {"name": "下肢力量", "exercise_key": "squat"},
    "core": {"name": "核心稳定", "exercise_key": "plank"},
    "aerobic": {"name": "有氧耐力", "exercise_key": ""},
    "easy_aerobic": {"name": "轻有氧 / 活动度", "exercise_key": ""},
}

# 默认时长(分钟,整数 —— 绝不 float,422 教训)。hard/easy 各给保守值。
_DURATION = {"hard": 45, "easy": 30}

_DISCLAIMER = (
    "这是基于你近期训练负荷与恢复信号生成的一般性健身安排,不是医疗或处方建议。"
    "请量力而行,循序渐进;有伤病、慢性病或身体不适请先就医,经医生评估后再训练。"
)


# ───────────────────────── 周锚点 ─────────────────────────


def _week_start(today: Optional[date] = None) -> date:
    """目标周的周一(Asia/Shanghai)。"""
    d = today or get_china_today()
    return d - timedelta(days=d.weekday())


# ───────────────────────── 目标推断 ─────────────────────────


def _infer_goal(twin) -> str:
    """从 twin goals 推断健身目标标签(增肌/减脂/心肺/维持)。

    描述性文案,非临床裁决。无法判断 → 「维持」兜底。
    """
    try:
        goals = (getattr(twin.goals, "active_goals", None) or [])
    except Exception:
        goals = []
    for g in goals:
        gtype = (g.get("goal_type") or "").lower()
        title = (g.get("title") or "")
        if gtype == "weight" or any(k in title for k in ("减脂", "减重", "瘦")):
            return "减脂"
        if any(k in title for k in ("增肌", "肌肉", "力量", "增重")):
            return "增肌"
        if any(k in title for k in ("心肺", "有氧", "耐力", "跑")):
            return "心肺"
    return "维持"


# ───────────────────────── day_type 分配 ─────────────────────────


def _day_type_plan(intensity: str, acwr: Optional[float]) -> List[str]:
    """movement_coach intensity_code(+ACWR)→ 一周 7 天的 day_type 序列(周一→周日)。

    intensity_code ∈ {high, moderate, low, rest, unknown}。
    高 ACWR / 低恢复(low/rest) → 更多 rest/easy;均衡(high/moderate) → 2-3 个 hard。
    全部确定性,不随机。
    """
    if intensity in ("rest",) or (acwr is not None and acwr > 1.5):
        # 过载窗口:本周以恢复为主,只 2 个 easy,其余 rest
        return ["easy", "rest", "rest", "easy", "rest", "rest", "rest"]
    if intensity == "low":
        # 恢复偏低:1 hard + 2 easy
        return ["hard", "rest", "easy", "rest", "easy", "rest", "rest"]
    if intensity == "moderate":
        # 均衡:2 hard + 2 easy
        return ["hard", "rest", "easy", "hard", "rest", "easy", "rest"]
    if intensity == "high":
        # 状态好:3 hard + 2 easy
        return ["hard", "easy", "hard", "rest", "hard", "easy", "rest"]
    # unknown / 兜底:保守均衡,2 hard
    return ["hard", "rest", "easy", "hard", "rest", "easy", "rest"]


# hard 日按工作日序号轮换动作主题(确定性:周内不同 hard 日练不同部位)。
_HARD_ROTATION = ["upper_strength", "lower_strength", "core"]


def _build_days(
    week_start: date,
    day_types: List[str],
    goal: str,
    acwr: Optional[float],
    gene_tip: Optional[str],
) -> List[Dict[str, Any]]:
    days: List[Dict[str, Any]] = []
    hard_idx = 0
    acwr_note = ""
    if acwr is not None:
        acwr_note = f"(近期负荷 ACWR≈{acwr:.2f},相关非因果)"
    for i in range(7):
        d = week_start + timedelta(days=i)
        dt = day_types[i]
        workout: Optional[Dict[str, Any]] = None
        if dt == "rest":
            rationale = "安排休息恢复,让身体适应与修复;睡眠和补水也是训练的一部分。"
        elif dt == "easy":
            theme = _WORKOUT_THEMES["easy_aerobic"]
            workout = {
                "name": theme["name"],
                "exercise_key": theme["exercise_key"],
                "duration_min": int(_DURATION["easy"]),
                "intensity_note": "低强度,能正常说话的节奏即可,不必追求大汗。",
            }
            rationale = f"轻量活动日,促进恢复、维持习惯,不增加额外负荷 {acwr_note}".strip()
        else:  # hard
            theme = _WORKOUT_THEMES[_HARD_ROTATION[hard_idx % len(_HARD_ROTATION)]]
            hard_idx += 1
            note = "中等到较高强度,量力而行,动作质量优先于次数。"
            if gene_tip:
                note = f"{note} 基因偏好提示:{gene_tip}(仅供参考,相关非因果)"
            workout = {
                "name": theme["name"],
                "exercise_key": theme["exercise_key"],
                "duration_min": int(_DURATION["hard"]),
                "intensity_note": note,
            }
            rationale = f"训练日,围绕「{goal}」目标安排;留意热身与动作幅度 {acwr_note}".strip()
        days.append({
            "date": d.isoformat(),
            "weekday": _WEEKDAY_ZH[i],
            "day_type": dt,
            "workout": workout,
            "rationale": rationale,
        })
    return days


def _readiness_note(intensity: str, acwr: Optional[float]) -> str:
    if intensity == "rest" or (acwr is not None and acwr > 1.5):
        return "近期负荷偏高,本周安排较多恢复日,优先把状态调回来(相关非因果)。"
    if intensity == "low":
        return "恢复信号偏弱,本周以低强度为主,循序渐进(相关非因果)。"
    if intensity == "high":
        return "近期恢复状态不错,本周可以安排 3 个训练日,注意动作质量。"
    if intensity == "unknown":
        return "训练数据还不足,先按保守的均衡安排;多同步几天活动数据后会更贴合你。"
    return "本周训练与恢复均衡安排,留意身体反馈随时调整。"


# ───────────────────────── 生成提议 ─────────────────────────


def _twin_signals(db: Session, user_id: int) -> Dict[str, Any]:
    """跑 movement_coach 矩阵函数取 intensity / acwr / gene_tip / goal。fail-soft。

    复用 coach._resolve_training_status / _today_intensity / _gene_bias —— 不重实现。
    任一步失败 → 退化到 unknown(仍能生成保守计划,不静默吞为绿灯)。
    """
    out: Dict[str, Any] = {"intensity": "unknown", "acwr": None, "gene_tip": None, "goal": "维持"}
    try:
        from app.twin.builder import build_twin
        from app.agents.movement_coach import coach as mc
        try:
            from app.agents.recovery_coach import compute_readiness
        except Exception:
            compute_readiness = None  # type: ignore

        twin = build_twin(db, user_id, use_cache=True)
        out["goal"] = _infer_goal(twin)
        out["acwr"] = mc._safe(twin.behavioral.acute_chronic_ratio)
        status, _src = mc._resolve_training_status(twin)
        zone = None
        if compute_readiness is not None:
            try:
                zone = compute_readiness(twin).zone
            except Exception:
                zone = None
        intensity, _guidance = mc._today_intensity(status, zone)
        # 急性不适/生病门控:与 movement_coach 同源 → 强制 rest 主题的周计划。
        acute = getattr(twin, "acute", None)
        if bool(getattr(acute, "should_rest_from_training", False)):
            intensity = "rest"
        out["intensity"] = intensity
        gene = mc._gene_bias(twin) or {}
        out["gene_tip"] = gene.get("tip") if isinstance(gene, dict) else None
    except Exception:
        logger.warning("fitness_plan: twin signals failed for user %s", user_id, exc_info=True)
    return out


def _view(plan: FitnessPlan) -> Dict[str, Any]:
    return {
        "plan_id": plan.id,
        "status": plan.status,
        "week_start": plan.week_start.isoformat() if plan.week_start else None,
        "goal": plan.goal or "维持",
        "acwr": plan.acwr,
        "readiness_note": plan.readiness_note or "",
        "days": plan.days or [],
        "disclaimer": _DISCLAIMER,
    }


def get_or_generate_weekly_plan(db: Session, user_id: int) -> Dict[str, Any]:
    """本周已有计划(proposed/confirmed)→ 返回;否则生成新提议(proposed)。

    dismissed 的计划视为「不要本周计划」,不再自动重生(避免反复 nag);用户可下周再要,
    或显式重新触发(本期不放开重生端点)。
    """
    ws = _week_start()
    existing = (
        db.query(FitnessPlan)
        .filter(FitnessPlan.user_id == user_id, FitnessPlan.week_start == ws)
        .first()
    )
    if existing is not None:
        return _view(existing)

    sig = _twin_signals(db, user_id)
    intensity = sig["intensity"]
    acwr = sig["acwr"]
    goal = sig["goal"]
    day_types = _day_type_plan(intensity, acwr)
    days = _build_days(ws, day_types, goal, acwr, sig["gene_tip"])
    readiness_note = _readiness_note(intensity, acwr)

    plan = FitnessPlan(
        user_id=user_id,
        week_start=ws,
        status="proposed",
        goal=goal,
        acwr=acwr,
        readiness_note=readiness_note,
        days=days,
    )
    db.add(plan)
    try:
        db.commit()
        db.refresh(plan)
    except IntegrityError:
        # 并发:另一路同周先插了 → 收敛到既有行(uq_fitness_plan_user_week)
        db.rollback()
        existing = (
            db.query(FitnessPlan)
            .filter(FitnessPlan.user_id == user_id, FitnessPlan.week_start == ws)
            .first()
        )
        if existing is None:  # 撞约束却查不到 → 反常,fail loud
            raise
        return _view(existing)
    return _view(plan)


# ───────────────────────── 确认(T2) ─────────────────────────


def _remind_at_for_day(day_iso: str) -> datetime:
    """该训练日的提醒时点:当地 18:00 → 存 UTC。日期解析失败 → fail loud(不静默兜默认日)。"""
    d = date.fromisoformat(day_iso)
    beijing = timezone(timedelta(hours=8))
    local = datetime(d.year, d.month, d.day, 18, 0, tzinfo=beijing)
    return local.astimezone(timezone.utc)


def _plan_reminders(db: Session, plan: FitnessPlan) -> List[SmartReminder]:
    """该 plan 已建的 fitness_plan SmartReminder(按 extra_data.fitness_plan_id 过滤)。

    不用 JSON-path SQL 比较(SQLite 的 JSON_EXTRACT 数值/字符串强转跨方言不可靠,
    曾导致 count 误返 0)。该用户 fitness_plan 提醒量极小(≤7/周),用 Python 精确过滤,
    完全可移植(PG/SQLite 同行为)。
    """
    rows = (
        db.query(SmartReminder)
        .filter(
            SmartReminder.user_id == plan.user_id,
            SmartReminder.source == "fitness_plan",
        )
        .all()
    )
    return [r for r in rows if (r.extra_data or {}).get("fitness_plan_id") == plan.id]


def _schedule_workouts(db: Session, plan: FitnessPlan) -> int:
    """为 plan 的非 rest 日建 SmartReminder(确认产物)。逐日按 (plan_id, date) 去重(幂等)。

    内层只 flush,提交由 confirm 外层统一负责(同事务,失败整体回滚,不假装成功)。
    """
    existing_dates = {
        (r.extra_data or {}).get("date") for r in _plan_reminders(db, plan)
    }
    scheduled = 0
    for day in (plan.days or []):
        if day.get("day_type") == "rest" or not day.get("workout"):
            continue
        day_iso = day["date"]
        # 幂等:该 plan 该天已建过 → 跳过(防确认两次双排程)
        if day_iso in existing_dates:
            continue
        w = day["workout"]
        rem = SmartReminder(
            user_id=plan.user_id,
            title=f"{day['weekday']} 训练:{w.get('name')}",
            message=w.get("intensity_note") or "今天的训练安排,量力而行。",
            remind_at=_remind_at_for_day(day_iso),
            priority="normal",
            status="pending",
            source="fitness_plan",
            extra_data={
                "fitness_plan_id": plan.id,
                "date": day_iso,
                "day_type": day.get("day_type"),
                "exercise_key": w.get("exercise_key") or None,
                "kind": "fitness_workout",
            },
        )
        db.add(rem)
        scheduled += 1
    db.flush()
    return scheduled


def confirm_weekly_plan(db: Session, user_id: int, plan_id: int) -> Dict[str, Any]:
    """T2 一键确认 → 排程。原子门防双确认;排程失败整体回滚(状态退回 proposed,fail loud)。

    幂等:已 confirmed → 直接返回既有排程数,不重复建。
    """
    plan = (
        db.query(FitnessPlan)
        .filter(FitnessPlan.id == plan_id, FitnessPlan.user_id == user_id)
        .first()
    )
    if plan is None:
        raise LookupError("fitness_plan not found")  # 端点 → 404(含 IDOR)
    if plan.status == "confirmed":
        # 幂等:已确认 → 返回当前已排程数(按来源标签精确计数,不重复建)
        count = _count_scheduled(db, plan)
        return {"confirmed": True, "plan_id": plan.id, "scheduled_count": count}
    if plan.status != "proposed":
        # dismissed 等不可确认 → fail loud(别静默假装成功)
        raise ValueError(f"cannot confirm plan in status={plan.status}")

    affected = (
        db.query(FitnessPlan)
        .filter(
            FitnessPlan.id == plan_id,
            FitnessPlan.user_id == user_id,
            FitnessPlan.status == "proposed",
        )
        .update(
            {"status": "confirmed", "confirmed_at": datetime.now(timezone.utc)},
            synchronize_session=False,
        )
    )
    if affected != 1:
        # 并发双确认:别人先 claim 了 → 收敛到既有排程数,不重复排程
        db.rollback()
        db.refresh(plan)
        count = _count_scheduled(db, plan)
        return {"confirmed": True, "plan_id": plan.id, "scheduled_count": count}

    try:
        scheduled = _schedule_workouts(db, plan)
    except Exception:
        db.rollback()  # 撤销 status=confirmed,回到 proposed,不假装成功
        raise
    db.commit()
    return {"confirmed": True, "plan_id": plan.id, "scheduled_count": scheduled}


def _count_scheduled(db: Session, plan: FitnessPlan) -> int:
    return len(_plan_reminders(db, plan))


def dismiss_weekly_plan(db: Session, user_id: int, plan_id: int) -> Dict[str, Any]:
    plan = (
        db.query(FitnessPlan)
        .filter(FitnessPlan.id == plan_id, FitnessPlan.user_id == user_id)
        .first()
    )
    if plan is None:
        raise LookupError("fitness_plan not found")
    if plan.status == "proposed":
        plan.status = "dismissed"
        db.commit()
    return {"dismissed": True}
