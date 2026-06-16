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
from datetime import date
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.services import health_protocol_service as proto_svc
from app.services import health_problem_service as prob_svc
from app.utils.timezone import get_user_today

logger = logging.getLogger(__name__)

# 时间窗排序(投影展示顺序)
_TW_ORDER = {"morning": 0, "noon": 1, "afternoon": 2, "evening": 3, "bedtime": 4, "anytime": 5}


def _agenda_item(**kw) -> Dict[str, Any]:
    return kw


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


def _self_correction_items(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """协议自纠偏(R14)→ 只读建议项(不可完成)。失败降级。"""
    try:
        from app.services.protocol_self_correction import (
            detect_outcome_corrections,
            detect_self_corrections,
        )
        skip_corr = detect_self_corrections(db, user_id)
        outcome_corr = detect_outcome_corrections(db, user_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("agenda: 自纠偏计算失败,跳过: %s", e)
        return []

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
    return items


def today(db: Session, user_id: int, followup_within_days: int = 14) -> Dict[str, Any]:
    """今日统一议程:协议待办 + 近 N 天到期复查。按优先级(高在前)+ 时间窗排序。"""
    items: List[Dict[str, Any]] = []

    # 1) 协议今日待办(三域)
    for p in proto_svc.today_status(db, user_id):
        if not p.get("is_due_today"):
            continue
        items.append(_agenda_item(
            type=p["domain"],
            title=p["name"],
            status=p["today_status"],            # pending/completed/skipped
            time_window=p.get("time_window") or "anytime",
            priority=50,
            can_default_complete=p.get("can_default_complete"),
            source={"object_type": "health_protocol", "object_id": p["protocol_id"]},
        ))

    # 2) 今日训练决策灯(只读建议项)
    ti = _training_item(db, user_id)
    if ti is not None:
        items.append(ti)

    # 3) 跨源数据质量(设备读数冲突)→ data_quality 提示
    dq = _data_quality_item(db, user_id)
    if dq is not None:
        items.append(dq)

    # 4) 协议自纠偏(连续跳过)→ correction 提示(R14,非羞辱式)
    for c in _self_correction_items(db, user_id):
        items.append(c)

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

    items.sort(key=lambda x: (-x["priority"], _TW_ORDER.get(x.get("time_window"), 9)))
    return {
        "agenda_date": str(get_user_today(db, user_id)),
        "count": len(items),
        "items": items,
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


def complete_item(
    db: Session, user_id: int, object_type: str, object_id: int,
    track: str = "protocol", value: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """统一完成路由:按 agenda item 的 source.object_type 路由到对应 source 的完成。

    health_protocol → 双轨完成(写真实业务记录)。其余来源(复查/safety)后续接通;
    不支持的来源显式报错(不静默假装完成,守 Rule #1)。
    """
    if object_type == "health_protocol":
        ev = proto_svc.complete_protocol(db, object_id, user_id, track=track, value=value)
        if ev is None:
            raise ValueError("协议不存在")
        return {"object_type": object_type, "object_id": object_id,
                "status": ev.status, "track": ev.track}
    raise ValueError(f"不支持经议程完成的来源: {object_type}")
