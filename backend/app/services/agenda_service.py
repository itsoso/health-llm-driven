"""统一健康议程投影(R1 第一刀)。

把分散来源投影成一条统一的 HealthAgendaItem 列表(item 引用 source object,不复制业务事实):
- HealthProtocol 今日待办(三域:饮水/用药/饮食 + 自定义)
- HealthProblem 到期/逾期复查(= 复查日历)
- 今日训练决策灯(green/yellow/red,只读建议项,来自 recovery_decision)
- 跨源数据质量提示(data_quality,设备读数冲突时,来自 Twin 回灌的 divergent_metrics)

后续 slice 再并入:DailyOperatingPlan 行动、用药 regimen。
只读投影,无副作用(完成/跳过仍走各自 source 的端点)。详见 docs/prd/reva-personal-health-os-prd.md §4 / R1。
"""
import logging
from datetime import date, timedelta
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.services import health_protocol_service as proto_svc
from app.services import health_problem_service as prob_svc
from app.services import agenda_contract
from app.services.daily_operating_plan import build_daily_operating_plan
from app.utils.timezone import get_china_today, get_user_today

logger = logging.getLogger(__name__)

# 时间窗排序(投影展示顺序)
_TW_ORDER = {"morning": 0, "noon": 1, "afternoon": 2, "evening": 3, "bedtime": 4, "anytime": 5}
_TERMINAL_STATUSES = agenda_contract.TERMINAL_ITEM_STATUSES


def _agenda_item(**kw) -> Dict[str, Any]:
    return kw


# 复查去重用器官/系统 token(ReviewSchedule.item_name × HealthProblem.problem_name 共现判同一复查)。
# 用多字消歧义(心脏/心血管 而非裸「心」—— 否则「心律」会误配「心理」;乳腺/胰腺/胆囊同理)。
_REVIEW_ORGAN_TOKENS = (
    "甲状腺", "前列腺", "骨密度", "血糖", "血脂", "血压", "尿酸", "甲功",
    "胃", "肺", "肝", "肾", "肠", "乳腺", "胰腺", "胆囊", "心脏", "心血管", "脑",
)


def _review_covered_by_problem(rs, existing_checkups: List[Dict[str, Any]], today: date) -> bool:
    """ReviewSchedule 是否被某条已加入的 HealthProblem 复查覆盖(**同器官 token** + ±30 天)。
    只认器官 token 共现 —— 不再用科室前缀(消化内科下「肠息肉随访」会误吞「胃镜复查」=漏检 under-alarm)。
    误判方向受控:仅抑制 ReviewSchedule 派生项,临床锚定的 HealthProblem 那条始终保留;
    宁可偶尔双重唠叨(器官不共现→两条都留)也不漏掉一个真复查。"""
    rs_name = rs.item_name or ""
    rs_date = rs.next_due_date
    for hp in existing_checkups:
        hp_title = hp.get("title") or ""           # "复查:胃溃疡(...)"
        nd = hp.get("next_due")
        try:
            hp_date = date.fromisoformat(str(nd)) if nd else None
        except (ValueError, TypeError):
            hp_date = None
        if hp_date is None or abs((rs_date - hp_date).days) > 30:
            continue
        if any(tok in rs_name and tok in hp_title for tok in _REVIEW_ORGAN_TOKENS):
            return True
    return False


def _project_course_reviews(db: Session, user_id: int, items: List[Dict[str, Any]], within_days: int) -> None:
    """到期 ReviewSchedule(药程结束复查等)投影成 checkup 项,与已加入的 HealthProblem 复查去重。
    只读;completion 不入 SUPPORTED_COMPLETE_TYPES(display/confirm-only,不进依从写路径)。"""
    try:
        from app.models.family_health import ReviewSchedule

        today = get_china_today()
        cutoff = today + timedelta(days=within_days)
        rows = (
            db.query(ReviewSchedule)
            .filter(
                ReviewSchedule.user_id == user_id,
                ReviewSchedule.status != "completed",
                ReviewSchedule.next_due_date <= cutoff,
            )
            .order_by(ReviewSchedule.next_due_date.asc())
            .all()
        )
        if not rows:
            return
        existing = [
            it for it in items
            if it.get("type") == "checkup"
            and (it.get("source") or {}).get("object_type") == "health_problem"
        ]
        for rs in rows:
            if _review_covered_by_problem(rs, existing, today):
                continue
            overdue = rs.next_due_date < today
            items.append(_agenda_item(
                type="checkup",
                title=f"复查:{rs.item_name}",
                status="overdue" if overdue else "due",
                time_window="anytime",
                priority=90 if (rs.priority in ("high", "urgent")) else 70,
                detail=(rs.department or None),
                responsible=rs.department,
                next_due=str(rs.next_due_date),
                source={"object_type": "review_schedule", "object_id": rs.id},
            ))
    except Exception as e:  # noqa: BLE001 — 投影增强失败不应破坏整条议程
        logger.warning("agenda: 药程复查投影失败,跳过: %s", e)


def _with_contract_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    """Attach additive cross-surface Agenda contract fields."""
    out = dict(item)
    status = out.get("status") or "pending"
    out["status_canonical"] = agenda_contract.canonical_item_status(status)
    out["is_terminal"] = agenda_contract.is_terminal_item_status(status)
    out["surface"] = out.get("surface") or agenda_contract.surface_contract_for_item(out)
    out["contract"] = agenda_contract.contract_metadata_for_item(out)
    return out


def _training_item(db: Session, user_id: int) -> Dict[str, Any] | None:
    """今日训练决策灯 → 议程项(只读建议,不可在议程内"完成")。

    防御性:无任何恢复信号(zone=unknown)且无训练负荷信号时返回 None ——
    不投一个凭空的黄灯(守 Rule #1,不假装有判断)。任何异常都吞掉只记日志,
    训练灯失败绝不拖垮整条议程。
    """
    try:
        from app.services.recovery_decision import training_decision
        d = training_decision(db, user_id)
    except Exception as e:  # noqa: BLE001 — 投影增强失败不应破坏议程
        logger.warning("agenda: 训练决策灯计算失败,跳过该项: %s", e)
        return None

    zone = d.get("zone")
    has_signal = (zone and zone != "unknown") or bool(d.get("acwr_zone"))
    if not has_signal:
        return None

    light = d.get("light", "yellow")
    # red 灯(建议休息)优先级抬到复查档,green/yellow 居协议之上
    priority = 90 if light == "red" else 80
    return _agenda_item(
        type="training",
        title=f"今日训练:{d.get('next_action') or '查看建议'}",
        status="info",                       # 建议项,非待办;前端不渲染 ✓
        time_window="morning",
        priority=priority,
        light=light,
        zone=zone,
        readiness_score=d.get("readiness_score"),
        confidence=d.get("confidence"),
        detail="；".join(d.get("reasons", []) or []),
        source={"object_type": "training_decision", "object_id": user_id},
    )


def _data_quality_item(db: Session, user_id: int) -> Dict[str, Any] | None:
    """跨源偏离 → data_quality 议程项(R3:冲突降置信不平均,暂以高优先级源为准)。

    从 Twin 读已回灌的 divergent_metrics(build_twin 算过,生产走 Redis 缓存→廉价)。
    无偏离 → None。只读建议项,不可完成。失败降级。
    """
    try:
        from app.twin.builder import build_twin
        twin = build_twin(db, user_id, use_cache=True)
        divs = twin.physiological.divergent_metrics or []
    except Exception as e:  # noqa: BLE001
        logger.warning("agenda: data_quality 计算失败,跳过: %s", e)
        return None
    if not divs:
        return None

    top = divs[0]
    extra = f"等 {len(divs)} 项指标" if len(divs) > 1 else ""
    return _agenda_item(
        type="data_quality",
        title=f"设备数据待核对:{top.label}{extra}",
        status="info",
        time_window="anytime",
        priority=70,
        detail=top.hint,
        divergent_metrics=[
            {"label": d.label, "trusted_source": d.trusted_source,
             "deviation_pct": d.deviation_pct, "hint": d.hint}
            for d in divs
        ],
        source={"object_type": "data_quality", "object_id": user_id},
    )


def _wearable_router_quality_items(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """Wearable Router stale/conflict issues → data_quality agenda items."""
    try:
        from app.services import wearable_router

        issues = wearable_router.data_quality_issues(db, user_id, max_items=3)
    except Exception as e:  # noqa: BLE001
        logger.warning("agenda: wearable router data_quality 计算失败,跳过: %s", e)
        return []

    items: List[Dict[str, Any]] = []
    for issue in issues:
        items.append(_agenda_item(
            type="data_quality",
            title=issue.get("title") or "可穿戴数据待核对",
            status="info",
            time_window="anytime",
            priority=73 if issue.get("kind") == "conflict" else 68,
            detail=issue.get("message"),
            metric=issue.get("metric"),
            issue_kind=issue.get("kind"),
            severity=issue.get("severity"),
            wearable_router_issue=issue,
            source={"object_type": "wearable_router", "object_id": user_id},
        ))
    return items


def _self_correction_items(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """协议自纠偏(R14)→ 只读建议项(不可完成)。失败降级。"""
    try:
        from app.services.protocol_self_correction import (
            detect_outcome_corrections,
            detect_self_corrections,
            suggest_protocol_adjustments,
        )
        skip_corr = detect_self_corrections(db, user_id)
        outcome_corr = detect_outcome_corrections(db, user_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("agenda: 自纠偏计算失败,跳过: %s", e)
        return []

    # P6 学习闭环调参建议(SUGGEST-ONLY,carry field_delta)。独立降级:失败不拖垮其余项。
    adjustments: List[Dict[str, Any]] = []
    try:
        adjustments = suggest_protocol_adjustments(db, user_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("agenda: 学习闭环调参建议计算失败,跳过: %s", e)

    items = [
        _agenda_item(
            type="correction",
            title=f"协议待调整:{c['name']}",
            status="info",
            time_window="anytime",
            priority=72,
            detail=c["message"],
            suggestion=c["suggestion"],
            skip_count=c["skip_count"],
            source={"object_type": "health_protocol", "object_id": c["protocol_id"]},
        )
        for c in skip_corr
    ]
    items += [
        _agenda_item(
            type="correction",
            title=c["name"],
            status="info",
            time_window="anytime",
            priority=74,                      # 结果趋势纠偏略高于协议跳过纠偏
            detail=c["message"],
            suggestion=c["suggestion"],
            source={"object_type": "outcome_correction", "object_id": user_id},
        )
        for c in outcome_corr
    ]
    # P6:人体工学调参建议作 correction 项,携带 field_delta(用户点 apply 才生效)。
    items += [
        _agenda_item(
            type="correction",
            title=f"提醒可调整:{d['name']}",
            status="info",
            time_window="anytime",
            priority=71,                      # 略低于结果趋势/跳过纠偏(人体工学非急)
            detail=d["message"],
            suggestion=d["message"],
            field_delta=d,                    # {protocol_id, field, from, to, confidence, ...}
            source={"object_type": "health_protocol", "object_id": d["protocol_id"]},
        )
        for d in adjustments
    ]
    return items


def _bucket(hhmm: str | None) -> str:
    """HH:MM → 时间窗桶(对齐 _TW_ORDER)。"""
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


def _day_schedule_workout_item(db: Session, user_id: int) -> Dict[str, Any] | None:
    """timing-solver 当日锻炼块投影成 agenda 项(cut 6)。

    锻炼是 solver 独有产出(非 HealthProtocol),投影到 agenda 不重复 source:
    - 排上 → pending movement 项(带 solver 求解的精确 `time`)。
    - readiness=Red 被剔 → info 「改拉伸/休息」项(带 reason)。
    仅当用户设了 workout_pref_window 才求解(省掉无偏好用户的整次 solve)。
    """
    from app.models.user_profile import UserProfile

    pref = (
        db.query(UserProfile.workout_pref_window)
        .filter(UserProfile.user_id == user_id)
        .scalar()
    )
    if not pref:
        return None
    try:
        from app.services.day_schedule_service import build_day_schedule
        sched = build_day_schedule(db, user_id)
    except Exception:  # 排程失败不应清空整条 agenda;记日志,锻炼项缺省
        logger.warning("agenda: day-schedule build failed for user %s", user_id, exc_info=True)
        return None

    w = next((s for s in sched.get("scheduled", []) if s.get("id") == "workout:today"), None)
    if w:
        item = _agenda_item(
            type="movement",
            title=w.get("title") or "锻炼",
            status="pending",
            time=w.get("time"),
            time_window=_bucket(w.get("time")),
            priority=55,
            source={"object_type": "day_schedule_workout", "object_id": user_id},
        )
        if w.get("prescription"):
            item["prescription"] = w["prescription"]  # cut A:结构化处方,各端渲染
        return item
    r = next((x for x in sched.get("rejected", []) if x.get("id") == "workout:today"), None)
    if r:
        return _agenda_item(
            type="movement",
            title=r.get("title") or "锻炼",
            status="info",
            detail=r.get("reason"),
            time_window="anytime",
            priority=40,
            source={"object_type": "day_schedule_workout", "object_id": user_id},
        )
    return None


def today(db: Session, user_id: int, followup_within_days: int = 14) -> Dict[str, Any]:
    """今日统一议程:协议待办 + 近 N 天到期复查。按优先级(高在前)+ 时间窗排序。"""
    from app.services import workout_chain_service as wcs

    items: List[Dict[str, Any]] = []

    # 0) P4 锻炼链(opt-in):链 ON → 先幂等物化链协议(commit),再由下方 today_status 投影。
    chain_on = wcs.is_workout_chain_enabled(db, user_id)
    if chain_on:
        wcs.maybe_materialize_workout_chain(db, user_id)

    # 1) 协议今日待办(链协议也走这条:它们就是 HealthProtocol,自动流入)
    for p in proto_svc.today_status(db, user_id):
        if not p.get("is_due_today"):
            continue
        iq = p.get("implied_quantity") or {}
        # 链指针(additive,仅链协议带;非链协议这些键缺省 None → 行为零变化)。
        chain_kw = {}
        if isinstance(iq, dict) and iq.get("chain_id"):
            chain_kw = {
                "chain_id": iq.get("chain_id"),
                "chain_step": iq.get("chain_step"),
                "chain_role": iq.get("chain_role"),
                "prev_protocol_id": iq.get("prev_protocol_id"),
                "next_protocol_id": iq.get("next_protocol_id"),
            }
        items.append(_agenda_item(
            type=p["domain"],
            title=p["name"],
            status=p["today_status"],            # pending/completed/skipped
            time_window=p.get("time_window") or "anytime",
            priority=50,
            cadence=p.get("cadence"),            # 透传给时间线 driver 派生(纯展示,不影响调度)
            can_default_complete=p.get("can_default_complete"),
            # 完成落库的目标业务表(权威);供 _to_smart_item 派生 voice_actionable —— 比 domain
            # 更可靠地判「含糊语音确认会不会写医疗级依从(MedicationLog/SupplementRecord)」。
            source_model=p.get("source_model"),
            source={"object_type": "health_protocol", "object_id": p["protocol_id"]},
            **chain_kw,
        ))

    # 2) 今日训练决策灯(只读建议项)
    ti = _training_item(db, user_id)
    if ti is not None:
        items.append(ti)

    # 2.5) timing-solver 当日锻炼块(cut 6)→ 带精确时点的 movement 项 / Red 休息项。
    # 链 ON 时跳过:锻炼已展开成链协议(上方 today_status 已投影),不再叠加旧单锻炼项(避免双份)。
    if not chain_on:
        wk = _day_schedule_workout_item(db, user_id)
        if wk is not None:
            items.append(wk)

    # 3) 跨源数据质量(设备读数冲突)→ data_quality 提示
    dq = _data_quality_item(db, user_id)
    if dq is not None:
        items.append(dq)
    for wq in _wearable_router_quality_items(db, user_id):
        items.append(wq)

    # 4) 协议自纠偏(连续跳过)→ correction 提示(R14,非羞辱式)
    for c in _self_correction_items(db, user_id):
        items.append(c)

    # 4.5) 个人基线漂移哨兵(R18 王牌③:RHR z-score 偏离)→ 归因候选 advisory
    # 哨兵"加层不减层":急性 RHR 也自身产带就医出口的 advisory 兜底(不再依赖
    # SafetyGuardian 接管——后者 rhr_tachycardia/bradycardia 仅 Severity.MEDIUM,
    # 且与哨兵 latest 语义不一致,数据不同步时两路可能全漏)。
    # import 放函数内避免与本模块被 watch_summary 等 import 形成循环。
    from app.services import baseline_deviation_sentinel
    for it in baseline_deviation_sentinel.deviation_advisories(db, user_id):
        items.append(it)

    # 5) 到期复查(HealthProblem follow_up)→ 复查日历项
    for f in prob_svc.due_followups(db, user_id, within_days=followup_within_days):
        items.append(_agenda_item(
            type="checkup",
            title=f"复查:{f['name']}",
            status="overdue" if f["overdue"] else "due",
            time_window="anytime",
            priority=95 if (f.get("risk_level") in ("P0", "P1")) else 75,
            detail=f.get("what_to_check"),
            responsible=f.get("responsible"),
            next_due=f.get("next_due"),
            source={"object_type": "health_problem", "object_id": f["problem_id"]},
        ))

    # 6) 药程结束复查(ReviewSchedule)→ 复查项;与上面 HealthProblem 复查去重
    #    (同器官/科室 + ±30 天 → HealthProblem 临床锚定胜,抑制本条,避免同一复查双重唠叨)
    _project_course_reviews(db, user_id, items, within_days=followup_within_days)

    items.sort(key=lambda x: (-x["priority"], _TW_ORDER.get(x.get("time_window"), 9)))
    items = [_with_contract_metadata(item) for item in items]
    return {
        "agenda_date": str(get_user_today(db, user_id)),
        "count": len(items),
        "items": items,
    }


def _when_bucket(when: str | None) -> str:
    """Daily Plan 的 when 字段 → 议程时间窗。"""
    mapping = {
        "morning": "morning",
        "breakfast": "morning",
        "noon": "noon",
        "lunch": "noon",
        "afternoon": "afternoon",
        "daytime": "afternoon",
        "meals": "noon",
        "evening": "evening",
        "dinner": "evening",
        "bedtime": "bedtime",
        "sleep": "bedtime",
        "today": "anytime",
        "in_progress": "anytime",
    }
    return mapping.get(str(when or "").strip().lower(), "anytime")


def _surface_for(item: Dict[str, Any]) -> Dict[str, Any]:
    return agenda_contract.surface_contract_for_item(item)


def _smart_id(item: Dict[str, Any]) -> str:
    source = item.get("source") or {}
    object_type = source.get("object_type") or item.get("type") or "item"
    object_id = source.get("object_id") or item.get("action_key") or item.get("title") or "unknown"
    return f"smart_{object_type}_{object_id}"


def _rank_score(item: Dict[str, Any]) -> int:
    source_type = (item.get("source") or {}).get("object_type")
    score = int(item.get("priority") or 0)
    score += {
        "overdue": 40,
        "due": 25,
        "pending": 10,
        "info": 5,
    }.get(str(item.get("status") or ""), 0)
    score += {
        "health_problem": 20,
        "daily_plan_action": 10,
        "health_protocol": 5,
        "training_decision": 5,
    }.get(str(source_type or ""), 0)
    return score


def _why_now(item: Dict[str, Any]) -> str:
    status = item.get("status")
    detail = item.get("detail")
    if status == "overdue":
        return f"已逾期，需要优先处理。{detail or ''}".strip()
    if status == "due":
        return f"复查到期，需要安排检查或确认已完成。{detail or ''}".strip()
    if item.get("why"):
        return str(item["why"])
    typ = item.get("type")
    if typ == "training":
        return detail or "恢复状态提示今天需要调整训练安排。"
    if typ == "data_quality":
        return detail or "设备数据存在偏离，需要先核对后再做健康判断。"
    if typ == "correction":
        return detail or "近期执行结果提示需要调整原计划。"
    return detail or "今天的健康议程项，适合在当前时间窗处理。"


def _do_now(item: Dict[str, Any]) -> str:
    title = item.get("title") or "这项行动"
    typ = item.get("type")
    if typ == "checkup":
        return f"安排/确认: {title}"
    if typ in {"data_quality", "correction", "training"}:
        return f"查看并确认: {title}"
    return f"执行: {title}"


def _verify_by(item: Dict[str, Any], fallback_verification: Dict[str, Any] | None = None) -> Dict[str, Any]:
    verification = item.get("verification")
    if isinstance(verification, dict) and verification:
        return dict(verification)
    metric_key = item.get("metric_key")
    if metric_key:
        return {
            "metrics": [metric_key],
            "target_value": item.get("target_value"),
            "window_days": 1 if item.get("when") in {"morning", "today"} else 7,
        }
    if item.get("type") == "checkup":
        return {"metrics": ["follow_up_completed"], "window_days": 14}
    if fallback_verification:
        return dict(fallback_verification)
    return {"metrics": ["completion_event"], "window_days": 1}


def _replan_policy(item: Dict[str, Any]) -> Dict[str, str]:
    if item.get("type") == "checkup":
        return {
            "on_skip": "capture_reason_then_reschedule",
            "on_miss": "escalate_next_business_day",
            "on_complete": "refresh_followup_cycle",
        }
    return {
        "on_skip": "capture_reason_then_reschedule",
        "on_miss": "move_to_next_available_window",
        "on_complete": "observe_metric_change",
    }


def _daily_plan_action_items(db: Session, user_id: int) -> tuple[List[Dict[str, Any]], Dict[str, Any] | None]:
    try:
        plan = build_daily_operating_plan(db, user_id, plan_date=get_user_today(db, user_id))
    except Exception as e:  # noqa: BLE001
        logger.warning("agenda: Daily Operating Plan 生成失败, smart agenda 跳过行动项: %s", e)
        return [], None

    plan_verification = plan.get("verification") if isinstance(plan, dict) else None
    actions = plan.get("actions") if isinstance(plan, dict) else []
    items: List[Dict[str, Any]] = []
    for action in actions or []:
        if not isinstance(action, dict):
            continue
        action_key = str(action.get("action_key") or action.get("title") or "unknown")
        domain = action.get("domain") or "daily_plan"
        items.append(_agenda_item(
            type=domain,
            title=action.get("title") or action_key,
            status="pending",
            time_window=_when_bucket(action.get("when")),
            priority=65,
            why=action.get("why"),
            when=action.get("when"),
            metric_key=action.get("metric_key"),
            target_value=action.get("target_value"),
            evidence_level=action.get("evidence_level"),
            evidence_tier=action.get("evidence_tier"),
            confidence=action.get("confidence"),
            claim_boundary=action.get("claim_boundary"),
            verification=action.get("verification"),
            action_key=action_key,
            source={"object_type": "daily_plan_action", "object_id": action_key},
        ))
    return items, plan_verification if isinstance(plan_verification, dict) else None


# 完成时写「医疗级依从事实」的目标业务表 —— 这类协议**永不**可由一句含糊语音("确认")
# 自动写(R4 / under-alarm 防御:依从数据喂 DDI/PGx,误写后果严重)。权威来源是协议的
# source_model(_write_domain_record 据它分派),不是 domain —— 二者结构上可漂移
# (如 hydration-domain 协议带 source_model=medication_logs)。
_MEDICAL_GRADE_SOURCE_MODELS = frozenset({"medication_logs", "supplement_records"})
# 复查/随访 domain 协议(source_model 多为 None)也排除:确认复查须用户在手机上显式操作。
_NON_VOICE_DOMAINS = frozenset({"checkup", "follow_up", "followup"})


def _is_voice_actionable(item: Dict[str, Any]) -> bool:
    """该议程项能否被「一句含糊语音」安全自动完成(R4 安全裁决的权威落点)。

    True 仅当:完成它**不会**写医疗级依从记录,且不是复查项。判定从协议 `source_model`
    (完成实际落哪张表)派生,而非 domain —— 这把安全决定放在权威真相处,消除客户端
    domain 白名单与后端写表分派两份清单的漂移风险。

    非协议来源(复查 health_problem / Daily Plan 行动 / 训练灯等)一律 False。
    autonomy_tier / 各动作 can_* 能力门由调用方(客户端)另判,不在此重复。
    """
    source = item.get("source") or {}
    if source.get("object_type") != "health_protocol":
        return False
    # 仅真实「待办」协议项可语音执行。协议自纠偏建议(_self_correction_items)也挂
    # object_type=health_protocol,但 status="info" 且无 source_model —— 它不是依从待办,
    # 一句"跳过/稍后"不得动它背后的协议(老 domain 白名单恰好挡住了它,本门必须显式保住)。
    if (item.get("status") or "") not in {"pending", "due", "overdue"}:
        return False
    if (item.get("type") or "") in _NON_VOICE_DOMAINS:
        return False
    if item.get("source_model") in _MEDICAL_GRADE_SOURCE_MODELS:
        return False
    return True


def _to_smart_item(
    item: Dict[str, Any],
    *,
    fallback_verification: Dict[str, Any] | None,
) -> Dict[str, Any]:
    score = _rank_score(item)
    status = item.get("status") or "pending"
    status_canonical = agenda_contract.canonical_item_status(status)
    return {
        "id": _smart_id(item),
        "type": item.get("type"),
        "title": item.get("title"),
        "status": status,
        "status_canonical": status_canonical,
        "is_terminal": agenda_contract.is_terminal_item_status(status),
        "time": item.get("time"),
        "time_window": item.get("time_window") or "anytime",
        "priority": item.get("priority") or 0,
        "rank_score": score,
        "rank_reason": {
            "status": status,
            "priority": item.get("priority") or 0,
            "source": (item.get("source") or {}).get("object_type"),
        },
        "source": item.get("source") or {},
        "why_now": _why_now(item),
        "do_now": _do_now(item),
        "verify_by": _verify_by(item, fallback_verification),
        "replan_policy": _replan_policy(item),
        "surface": _surface_for(item),
        "contract": agenda_contract.contract_metadata_for_item(item),
        "autonomy_tier": "confirm" if item.get("type") == "checkup" else "suggest",
        "can_complete": status in {"pending", "due", "overdue"},
        "can_snooze": status in {"pending", "due", "overdue", "info"},
        "can_skip": status in {"pending", "info"},
        # 含糊语音(Rokid "确认/跳过")可否安全自动完成 —— 权威安全门,从 source_model 派生
        # (排除 medication_logs/supplement_records 与复查)。客户端据此 gate,domain 白名单
        # 仅作旧后端缺该字段时的兜底。见 mobile/services/rokidVoiceAgenda.ts。
        "voice_actionable": _is_voice_actionable(item),
        "confidence": item.get("confidence"),
        "claim_boundary": item.get("claim_boundary"),
    }


def smart_today(
    db: Session,
    user_id: int,
    followup_within_days: int = 14,
    max_items: int = 3,
) -> Dict[str, Any]:
    """智能今日议程:普通 agenda + Daily Plan 行动 → 可执行、可验证、可重排的 top list。"""
    base = today(db, user_id, followup_within_days=followup_within_days)
    base_items = list(base.get("items") or [])
    daily_items, plan_verification = _daily_plan_action_items(db, user_id)
    candidates = base_items + daily_items
    smart_items = [
        _to_smart_item(item, fallback_verification=plan_verification)
        for item in candidates
        if not agenda_contract.is_terminal_item_status(item.get("status"))
    ]
    smart_items.sort(key=lambda item: (
        -int(item.get("rank_score") or 0),
        _TW_ORDER.get(item.get("time_window"), 9),
        str(item.get("title") or ""),
    ))
    max_items = max(1, min(int(max_items or 3), 10))
    top_items = smart_items[:max_items]
    return {
        "agenda_date": base.get("agenda_date") or str(get_user_today(db, user_id)),
        "mode": "smart",
        "source_count": len(candidates),
        "count": len(top_items),
        "items": base_items,
        "smart": {
            "generated_by": "deterministic_smart_agenda_v1",
            "ranking": "priority_status_source_v1",
            "top_items": top_items,
        },
    }


def range_view(db: Session, user_id: int, days: int = 7) -> Dict[str, Any]:
    """周/区间视图:常驻每日协议 + 窗口内按到期日排布的复查。"""
    today_d = get_user_today(db, user_id)
    recurring = [
        {"protocol_id": p["protocol_id"], "domain": p["domain"],
         "name": p["name"], "cadence": p["cadence"]}
        for p in proto_svc.today_status(db, user_id)
        if (p.get("cadence") or "daily") == "daily"
    ]
    scheduled = [
        {"date": f["next_due"], "type": "checkup", "title": f"复查:{f['name']}",
         "overdue": f["overdue"], "what_to_check": f.get("what_to_check"),
         "source": {"object_type": "health_problem", "object_id": f["problem_id"]}}
        for f in prob_svc.due_followups(db, user_id, within_days=days)
    ]
    scheduled.sort(key=lambda x: x["date"])
    from datetime import timedelta
    return {
        "start": str(today_d), "end": str(today_d + timedelta(days=days)),
        "recurring_protocols": recurring,
        "scheduled": scheduled,
    }


# 经议程统一完成路由支持的来源(供上游 complete_by_ref 在物化前先验,避免给
# 不支持的来源凭空物化一条议程 HealthEvent)。新增 source 完成路径时同步扩这里。
SUPPORTED_COMPLETE_TYPES = ("health_protocol", "medication", "supplement")


def ensure_source_exists(db: Session, user_id: int, object_type: str, object_id: int) -> None:
    """物化前先验来源所有权/存在性(F1:done 与 skip 同标准)。

    - 不支持的来源 → ValueError(端点转 400,不给它凭空物化议程行)。
    - 来源不存在 / 非本人 → LookupError(端点转 404,守跨用户隔离)。

    不写任何记录,纯校验。complete_by_ref 在懒物化前调它,确保 skip 也不会给
    外人/不存在/不支持的 ref 物化幻影议程 HealthEvent。
    """
    if object_type == "health_protocol":
        if proto_svc.get_protocol(db, object_id, user_id) is None:
            raise LookupError("协议不存在")
        return
    if object_type in ("medication", "supplement"):
        from app.services.medication_service import medication_service
        if medication_service.get_medication(db, object_id, user_id) is None:
            raise LookupError("medication not found")
        return
    raise ValueError(f"不支持经议程完成的来源: {object_type}")


def complete_item(
    db: Session, user_id: int, object_type: str, object_id: int,
    track: str = "protocol", value: Dict[str, Any] | None = None,
    taken_time: str | None = None,
    status: str = "done",
    skip_reason: str | None = None,
) -> Dict[str, Any]:
    """统一完成/跳过路由:按 agenda item 的 source.object_type 路由到对应 source。

    done 与 skipped **共用同一写路径**(不 fork),只是落库的 status/track 不同:
    - health_protocol:done → complete_protocol(双轨写真实业务记录);
      skipped → skip_protocol(写 HealthProtocolEvent status=skipped,单行 uq_hpe_protocol_date)。
    - med/supplement:done → MedicationLog(taken);skipped → MedicationLog(skipped)。
      两者落同一 uq_medlog_med_date_time 槽(status-agnostic 唯一约束)→ 先跳后服可
      **supersede**(更新同槽行 skipped→taken),不撞约束、不落第二条。

    不支持的来源显式报错(不静默假装完成,守 Rule #1)。

    taken_time(可选,med/supplement 用):由调用方给确定性服药时点槽(如议程项 scheduled_for
    的 "HH:MM"),让 uq_medlog_med_date_time 在重复完成时真兜底;缺省回退中国时区 now。
    """
    if status not in ("done", "skipped"):
        raise ValueError(f"未知 status: {status}(应为 done|skipped)")

    if object_type == "health_protocol":
        if status == "skipped":
            ev = proto_svc.skip_protocol(db, object_id, user_id, reason=skip_reason)
            if ev is None:
                raise LookupError("协议不存在")
            return {"object_type": object_type, "object_id": object_id,
                    "status": ev.status, "wrote": False}
        ev = proto_svc.complete_protocol(db, object_id, user_id, track=track, value=value)
        if ev is None:
            # 协议不存在 / 非本人 → LookupError(端点转 404,与 med/supplement 一致)。
            raise LookupError("协议不存在")
        return {"object_type": object_type, "object_id": object_id,
                "status": ev.status, "track": ev.track, "wrote": True}
    if object_type in ("medication", "supplement"):
        # 药与补剂同存 medications 表;object_id 即 medication_id,无独立补剂写路径。
        # done/skipped 都经 medication_service 写同一 uq_medlog 槽(commit=False 把领域写并入
        # 调用方单次事务,与 complete_protocol 用药分支同款,不 fork 写路径)。
        from app.services.medication_service import medication_service
        from app.utils.timezone import get_china_now
        med = medication_service.get_medication(db, object_id, user_id)
        if med is None:
            # 资源不存在 / 非本人 → LookupError(端点转 404,守跨用户隔离)。
            raise LookupError("medication not found")
        # 确定性服药时点槽(议程项 scheduled_for):同项重复完成落同一 uq_medlog 槽 → DB 兜底去重。
        slot = taken_time or get_china_now().strftime("%H:%M")
        if status == "skipped":
            # 漏服事实:落 MedicationLog(skipped)。同槽 supersede 让「先服后跳」也能改写。
            log = medication_service.upsert_medication_log(
                db, user_id, object_id, taken_time=slot,
                status="skipped", skip_reason=skip_reason, commit=False,
            )
            return {"object_type": object_type, "object_id": object_id,
                    "wrote": False, "log_id": log.id}
        # 手工轨可带用户实际剂量(actual_dosage):记的是「用户报告实际服了多少」这一依从事实,
        # 不是处方/调量(R4)。缺省 None → 按医嘱默认记录。
        actual_dosage = (value or {}).get("actual_dosage")
        # supersede:先跳后服 → 把同槽 skipped 行翻成 taken(uq_medlog 是 status-agnostic,
        # 不能再 INSERT 第二条;同时也兜住「先服后服」幂等)。
        log = medication_service.upsert_medication_log(
            db, user_id, object_id, taken_time=slot,
            status="taken", actual_dosage=actual_dosage, commit=False,
        )
        return {"object_type": object_type, "object_id": object_id,
                "wrote": True, "log_id": log.id}
    raise ValueError(f"不支持经议程完成的来源: {object_type}")
