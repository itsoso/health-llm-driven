"""P4 锻炼链:把单锻炼块展开成链式议程(预检→锻炼→拉伸→淋浴→按摩→餐→复盘)。

设计(复用完成闭环,**不 fork**):链 = N 条互相串联的 HealthProtocol,每步一条。
- 为何不是新链对象 / 不是 solver-only Item:完成闭环只让 HealthProtocol(+药/补剂)可完成;
  solver 的 `workout:today` 是 movement Item,没有完成路径。每步落成 HealthProtocol → 每步白嫖
  既有 `/agenda/complete` 闭环(distinct protocol_id → distinct complete_ref → distinct HealthEvent,
  互不碰撞)。
- 链指针存在 `HealthProtocol.implied_quantity` JSONB(无迁移、无新列):
  {chain_id, chain_step, chain_role, prev_protocol_id, next_protocol_id, downgraded_from?, optional?}。

R4(医疗边界):锻炼步逐字复用 movement_coach 处方(训练参数,非医疗剂量);拉伸/淋浴/按摩只带
通用对冲措辞("10 分钟拉伸""温水淋浴"),无量化处方、无 LLM 编造动作要领。降级只会降强度
(RED→拉伸/休息),绝不上调处方 —— 降级由 movement_coach/recovery_coach 的确定性 rx 决定,LLM 不参与。

R15(通知预算):本模块只产 HealthProtocol(经议程投影成 agenda 项),**绝不直接 push**。
是否推送由既有 event_reminders/proactive_coordinator 预算层决定:协议到点轻推恒走 `protocol` tier=P1
(绝不消耗 P0);time_window=anytime 的步(拉伸/淋浴/按摩/餐/复盘)无固定到点 → 根本不推
(等效 P2,纯 log)。只有预检/锻炼落在固定时间窗 → P1 到点轻推。

幂等:议程每次刷新都会跑 ensure_workout_chain_protocols → 必须按 (user, chain_id, chain_step) 去重,
否则每次刷新都重建一批协议。
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.health_protocol import HealthProtocol
from app.services.timing_solver import _to_hhmm, _to_min
from app.utils.timezone import get_china_today

logger = logging.getLogger(__name__)

# 链步角色(固定顺序)→ (域, 默认名)。域全部在 PROTOCOL_DOMAINS 内,无迁移。
#   pre_check=measurement(测量类:开练前自检),workout=exercise,stretch=exercise,
#   shower=activity,massage=activity,meal=diet,review=measurement(复盘:回看完成情况)。
_ROLE_DOMAIN: Dict[str, str] = {
    "pre_check": "measurement",
    "workout": "exercise",
    "stretch": "exercise",
    "shower": "activity",
    "massage": "activity",
    "meal": "diet",
    "review": "measurement",
}

# 链步默认文案(R4:拉伸/淋浴/按摩只通用对冲措辞,无动作要领、无量化处方)。
_ROLE_NAME: Dict[str, str] = {
    "pre_check": "锻炼前自检(身体状态/补水)",
    "workout": "锻炼",
    "stretch": "10 分钟拉伸放松",
    "shower": "温水淋浴",
    "massage": "放松按摩/筋膜放松",
    "meal": "训练后恢复餐",
    "review": "锻炼复盘(回看完成情况)",
}

# 链步相对锚点的偏移(分钟)。负=锻炼开始前;正=锻炼结束后。
_PRE_CHECK_LEAD_MIN = 15          # 预检 = 锻炼开始前 15min
_STRETCH_OFFSET_MIN = 5           # 拉伸 = 锻炼结束 +5min
_SHOWER_OFFSET_MIN = 20          # 淋浴 = 锻炼结束 +20min
_MASSAGE_OFFSET_MIN = 30         # 按摩 = 锻炼结束 +30min
_MEAL_OFFSET_MIN = 45            # 恢复餐 = 锻炼结束 +45min(蛋白/碳水窗中段)
_REVIEW_OFFSET_MIN = 120         # 复盘 = 锻炼结束 +2h(更晚,纯回看)


def _bucket(hhmm: Optional[str]) -> str:
    """HH:MM → 时间窗桶(对齐 agenda 的 _TW_ORDER / event_reminders 的到点表)。

    只有落入 morning/noon/afternoon/evening/bedtime 的步会被 event_reminders 到点轻推(P1);
    None / 越界 → anytime(无固定到点 → 不推,等效纯 log,R15)。
    """
    if not hhmm:
        return "anytime"
    try:
        h = int(hhmm.split(":")[0])
    except (ValueError, AttributeError):
        return "anytime"
    if h < 11:
        return "morning"
    if h < 13:
        return "noon"
    if h < 17:
        return "afternoon"
    if h < 21:
        return "evening"
    return "bedtime"


def build_workout_chain(
    rx: Optional[dict],
    ctx,
    *,
    workout_minutes: int,
) -> List[Dict[str, Any]]:
    """据已算好的 movement 处方 rx + 已对齐的 DayContext → 有序链步描述符。

    **不重算 readiness / 不再 build_twin**:rx 已由 day_schedule_service.workout_prescription
    算好(ACWR×readiness×ACTN3 + 急性休息门控),ctx.workout_start 已由 _maybe_workout_item 落桩。

    降级(R4,LLM 不参与):rx.intensity == "rest"(RED / 急性)→ **不建锻炼步**,只建拉伸
    (+ 可选淋浴),并标 downgraded_from="workout"。降级永远只降强度。

    返回每步:{role, domain, name, time_window, fixed_time?, implied_quantity_extra,
              can_default_complete, optional}。fixed_time 可为 None(anytime,无到点 → 不推)。
    """
    steps: List[Dict[str, Any]] = []
    workout_start = getattr(ctx, "workout_start", None)
    is_rest = bool(rx and rx.get("intensity") == "rest")

    if is_rest:
        # ── 降级路径:RED / 急性 → 不排锻炼,只排主动恢复(拉伸 + 可选淋浴)──────────
        # 拉伸不带具体训练参数(非锻炼步),只通用对冲措辞;标 downgraded_from。
        steps.append({
            "role": "stretch",
            "domain": _ROLE_DOMAIN["stretch"],
            "name": "主动恢复:轻度拉伸/放松",
            "time_window": _bucket(workout_start) if workout_start else "anytime",
            "fixed_time": workout_start,
            "implied_quantity_extra": {
                "downgraded_from": "workout",
                "guidance": rx.get("guidance") if rx else "今日建议恢复,做些轻度拉伸即可。",
            },
            "can_default_complete": False,
            "optional": False,
        })
        steps.append({
            "role": "shower",
            "domain": _ROLE_DOMAIN["shower"],
            "name": _ROLE_NAME["shower"],
            "time_window": "anytime",
            "fixed_time": None,
            "implied_quantity_extra": {"downgraded_from": "workout"},
            "can_default_complete": False,
            "optional": True,
        })
        return steps

    # ── 正常链:预检 → 锻炼 → 拉伸 → 淋浴 → 按摩 → 餐 → 复盘 ─────────────────────
    end_min = (_to_min(workout_start) + workout_minutes) if workout_start else None

    def _offset_time(base_min: Optional[int], delta: int) -> Optional[str]:
        if base_min is None:
            return None
        return _to_hhmm(base_min + delta)

    # pre_check:锻炼开始前 15min
    pre_time = _offset_time(_to_min(workout_start), -_PRE_CHECK_LEAD_MIN) if workout_start else None
    steps.append({
        "role": "pre_check",
        "domain": _ROLE_DOMAIN["pre_check"],
        "name": _ROLE_NAME["pre_check"],
        "time_window": _bucket(pre_time),
        "fixed_time": pre_time,
        "implied_quantity_extra": {},
        "can_default_complete": False,
        "optional": False,
    })

    # workout:逐字复用 movement_coach 处方(rx),落进 implied_quantity(训练参数,非医疗剂量)。
    steps.append({
        "role": "workout",
        "domain": _ROLE_DOMAIN["workout"],
        "name": _workout_name(rx, workout_minutes),
        "time_window": _bucket(workout_start),
        "fixed_time": workout_start,
        "implied_quantity_extra": _workout_implied(rx, workout_minutes),
        "can_default_complete": False,
        "optional": False,
    })

    # 锻炼后链(拉伸/淋浴/按摩/餐/复盘):时点 = 锻炼结束 + 各自偏移。
    # time_window 用 _bucket → 多落 anytime(无固定到点),只产协议、不主动推(R15)。
    post = [
        ("stretch", _STRETCH_OFFSET_MIN, False, False),
        ("shower", _SHOWER_OFFSET_MIN, True, False),
        ("massage", _MASSAGE_OFFSET_MIN, True, True),     # 按摩可选
        ("meal", _MEAL_OFFSET_MIN, False, False),
        ("review", _REVIEW_OFFSET_MIN, False, False),
    ]
    for role, offset, optional, _ in post:
        t = _offset_time(end_min, offset)
        # 锻炼后链全部 time_window=anytime:不主动到点推送(等效 P2 log-only,R15);
        # fixed_time 仍保留供各端排序/渲染,但不进 event_reminders 的到点表。
        steps.append({
            "role": role,
            "domain": _ROLE_DOMAIN[role],
            "name": _ROLE_NAME[role],
            "time_window": "anytime",
            "fixed_time": t,
            "implied_quantity_extra": _post_implied(role),
            "can_default_complete": False,
            "optional": optional,
        })
    return steps


def _workout_name(rx: Optional[dict], minutes: int) -> str:
    label = {
        "high": "高强度训练", "moderate": "Z2 有氧", "low": "轻有氧",
    }.get((rx or {}).get("intensity"))
    return f"{label} {minutes} 分钟" if label else f"锻炼 {minutes} 分钟"


def _workout_implied(rx: Optional[dict], minutes: int) -> Dict[str, Any]:
    """锻炼步 implied_quantity:复用 rx 训练参数 + 落 ExerciseRecord 需要的字段。"""
    extra: Dict[str, Any] = {
        "exercise_type": (rx or {}).get("type") or "general",
        "duration_min": (rx or {}).get("duration_min") or minutes,
        "intensity": (rx or {}).get("intensity") or "moderate",
    }
    if rx:
        for k in ("rpe", "guidance", "gene_note"):
            if rx.get(k):
                extra[k] = rx[k]
        # 整份处方也留底,供各端渲染(R4 已清:训练参数非医疗剂量)。
        extra["prescription"] = rx
    return extra


def _post_implied(role: str) -> Dict[str, Any]:
    """锻炼后链 implied_quantity:只通用对冲措辞,无量化处方(R4)。"""
    if role == "stretch":
        return {"exercise_type": "stretch", "duration_min": 10, "intensity": "easy",
                "guidance": "锻炼后做约 10 分钟拉伸放松,缓解肌肉紧张(非硬性指标)。"}
    if role == "shower":
        return {"guidance": "锻炼后温水淋浴,帮助放松(注意水温适中)。"}
    if role == "massage":
        return {"guidance": "如有条件可做放松按摩/筋膜放松,缓解酸痛(可选)。"}
    if role == "meal":
        return {"meal_type": "加餐",
                "guidance": "训练后那一餐适当补充优质蛋白与碳水,帮助恢复(非克数处方)。"}
    if role == "review":
        return {"guidance": "回看今天锻炼链的完成情况。"}
    return {}


# ── 协议物化(幂等)─────────────────────────────────────────────────────────
def ensure_workout_chain_protocols(
    db: Session,
    user_id: int,
    *,
    chain_id: str,
    steps: List[Dict[str, Any]],
    chain_date: Optional[date] = None,
) -> List[HealthProtocol]:
    """把链步幂等物化成 N 条互相串联的 HealthProtocol。模仿 create_postmeal_walk_protocol。

    幂等(双层):
      ① 应用层:先按 (user_id, chain_id, chain_step) 查既有 active 协议,命中则复用(不重建)。
      ② DB 层 backstop:每步带 chain_key="{chain_id}:{chain_step}",配 partial unique index
         uq_health_protocols_user_chain_key(user_id, chain_key)。并发两次 GET /agenda 同时
         物化同一步 → 第二条 INSERT 撞唯一约束 IntegrityError → 回滚重读那一行(对齐
         _claim_today_event 模式),不靠应用层读-检查-写裸竞态(守依从写回幂等必须 DB 兜底的教训)。

    两遍:① 逐步建缺失行(撞约束即重读)② UPDATE prev/next_protocol_id 链接。
    用户隔离:创建与查询都按 user_id 过滤(对齐 create_postmeal_walk_protocol)。
    """
    # trigger_date 必须与 _is_due_today 的 today 基准一致(get_china_today,UTC+8 硬编码):
    # _is_due_today 对 event_triggered 协议判 trigger_date == today.isoformat();今日协议查询
    # 已统一到 get_china_today。若这里用 date.today()(OS 时区,CI=UTC)在午夜边界会比中国日早
    # 一天 → 链协议 is_due_today=False → 整条链不投影进议程(链静默丢失)。
    chain_date = chain_date or get_china_today()
    trigger_date = chain_date.isoformat()

    # 既有同链协议(按 chain_key 索引)——一次性查,避免每步 N+1。
    existing_by_step: Dict[int, HealthProtocol] = {}
    candidates = (
        db.query(HealthProtocol)
        .filter(
            HealthProtocol.user_id == user_id,
            HealthProtocol.status == "active",
            HealthProtocol.chain_key.isnot(None),
        )
        .all()
    )
    for p in candidates:
        iq = p.implied_quantity or {}
        if iq.get("chain_id") == chain_id and isinstance(iq.get("chain_step"), int):
            existing_by_step[int(iq["chain_step"])] = p

    # ── Pass 1:逐步建缺失行(prev/next 先留 None,Pass 2 回填)──────────────────
    ordered: List[HealthProtocol] = []
    for step_idx, step in enumerate(steps):
        existing = existing_by_step.get(step_idx)
        if existing is not None:
            ordered.append(existing)
            continue
        ordered.append(
            _create_chain_step(db, user_id, chain_id, step_idx, step, trigger_date)
        )

    db.flush()  # 拿到新建行的 id 供 Pass 2 串联

    # ── Pass 2:回填 prev/next_protocol_id 链接(只在缺失/不一致时写)──────────
    changed = False
    for i, p in enumerate(ordered):
        prev_id = ordered[i - 1].id if i > 0 else None
        next_id = ordered[i + 1].id if i < len(ordered) - 1 else None
        iq = dict(p.implied_quantity or {})
        if iq.get("prev_protocol_id") != prev_id or iq.get("next_protocol_id") != next_id:
            iq["prev_protocol_id"] = prev_id
            iq["next_protocol_id"] = next_id
            p.implied_quantity = iq
            changed = True

    if changed or any(p.id is None for p in ordered):
        db.commit()
        for p in ordered:
            db.refresh(p)
    return ordered


def _create_chain_step(
    db: Session, user_id: int, chain_id: str, step_idx: int,
    step: Dict[str, Any], trigger_date: str,
) -> HealthProtocol:
    """建单条链步协议;撞 partial unique index → 回滚 savepoint 重读已存在行(并发 backstop)。

    用 begin_nested()(SAVEPOINT)包住单步 INSERT:IntegrityError 只回滚本步,前面已建步不丢。
    重读用 chain_key 精确定位那一行(并发里另一请求刚建的同步)。
    """
    chain_key = f"{chain_id}:{step_idx}"
    implied = {
        "chain_id": chain_id,
        "chain_step": step_idx,
        "chain_role": step["role"],
        "prev_protocol_id": None,
        "next_protocol_id": None,
        "trigger_date": trigger_date,
    }
    if step.get("optional"):
        implied["optional"] = True
    implied.update(step.get("implied_quantity_extra") or {})

    source_model, source_id = _source_for_role(step["role"])
    p = HealthProtocol(
        user_id=user_id,
        domain=step["domain"],
        name=step["name"],
        mechanism="pre_commit",
        implied_quantity=implied,
        cadence="event_triggered",      # 一次性(当日触发),完成后掉出,不每天复现
        time_window=step.get("time_window") or "anytime",
        completion_mode="one_tap",
        can_default_complete=bool(step.get("can_default_complete")),
        manual_track_allowed=True,
        source_model=source_model,
        source_id=source_id,
        chain_key=chain_key,
        status="active",
    )
    db.add(p)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        # 并发请求已建同一 (user_id, chain_key) → savepoint 已回滚本步,重读那一行。
        existing = (
            db.query(HealthProtocol)
            .filter(
                HealthProtocol.user_id == user_id,
                HealthProtocol.chain_key == chain_key,
            )
            .first()
        )
        if existing is None:  # 约束撞了却查不到,理论不至于 → fail loud(不静默假成功)
            raise
        return existing
    return p


# ── 议程入口(opt-in 门 + 物化触发)────────────────────────────────────────
def is_workout_chain_enabled(db: Session, user_id: int) -> bool:
    """P4 锻炼链 opt-in:UserProfile.workout_chain_enabled=True 才展开链。

    须同时有 workout_pref_window(否则无锻炼起点,链无意义)。缺任一 → False(走旧单项,无回归)。
    """
    from app.models.user_profile import UserProfile

    row = (
        db.query(UserProfile.workout_chain_enabled, UserProfile.workout_pref_window)
        .filter(UserProfile.user_id == user_id)
        .first()
    )
    return bool(row and row[0] and row[1])


def maybe_materialize_workout_chain(db: Session, user_id: int) -> None:
    """链 ON 时:幂等物化锻炼链协议(commit,THEN 由 today_status 投影)。

    必须在读 today_status **之前** commit(链协议要先入库才能被投影);幂等去重保证每次刷新不重建。
    失败只记 warning,绝不拖垮整条议程(链是增强,不是主路径)。
    """
    try:
        from app.services.day_schedule_service import build_workout_chain_steps

        plan = build_workout_chain_steps(db, user_id)
        if not plan:
            return
        ensure_workout_chain_protocols(
            db, user_id, chain_id=plan["chain_id"], steps=plan["steps"],
        )
    except Exception:  # noqa: BLE001 — 链物化失败不应清空议程;记日志,退化为无链
        # 必须 rollback:DB 级错误(commit 撞约束 / autoflush / 连接断)会把 session 置入
        # PendingRollbackError 终态;不回滚则 agenda_service.today() 紧接着的 today_status()
        # autoflush 会再次抛 → 整条 /agenda/today 500(链是增强不该拖垮主路径)。见安全评审 B1。
        db.rollback()
        logger.warning(
            "workout chain materialize failed for user %s", user_id, exc_info=True
        )


def _source_for_role(role: str) -> tuple[Optional[str], Optional[int]]:
    """链步角色 → 完成落到哪张业务表(走既有 _write_domain_record 适配器)。

    - workout/stretch:exercise_records(完成 → 真落 ExerciseRecord,不假完成)。
    - meal:diet_records(完成 → DietRecord)。
    - pre_check/shower/massage/review:无业务表;协议自身事件即记录(source_model=None)。
    """
    if role in ("workout", "stretch"):
        return "exercise_records", None
    if role == "meal":
        return "diet_records", None
    return None, None
