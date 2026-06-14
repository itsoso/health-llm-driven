"""用药方案实例化 + 引入即 DDI 预检闸门。

把「医生开的复杂方案」一键变成可执行的带时点药品 —— 但引入新药前**强制**跑安全检查
(用户可能已在吃十几种药),CRITICAL 相互作用阻断、不写库。这是 Rule #1(不假装成功)
在用药场景的硬约束:不能默默把会撞药的方案录进去还说「记好了」。

定位:执行/录入工具,非开方工具。方案来自医生(模板脚手架 / OCR / 手填)。
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.agents.safety_guardian.engine import evaluate_rules  # import 即触发规则注册(engine.py 末尾)
from app.agents.safety_guardian.schema import Alert, Severity
from app.models.medication import Medication, MedicationRegimen, medication_timing_label
from app.services import regimen_templates

logger = logging.getLogger(__name__)


def _safety_twin(db: Session, user_id: int):
    """构一个只填「药物分区」的轻量 Twin,用传入的 db(请求事务)。

    不用 build_twin:它在内部 SessionLocal() 自开连接(真库)、忽略传入 db,
    既看不到请求事务里的数据,又在测试/事务边界失真。这里直接复用 builder 的
    _fill_medication(它用传入 db),只填 DDI 需要的药物列表。
    """
    from app.twin import builder as twin_builder
    from app.twin.schema import HealthTwin, TwinMeta

    twin = HealthTwin(meta=TwinMeta(user_id=user_id, generated_at=datetime.now(UTC)))
    twin_builder._fill_medication(db, user_id, twin, set())
    return twin


def precheck_interactions(
    db: Session,
    user_id: int,
    candidate_names: List[str],
) -> List[Alert]:
    """引入 candidate_names 这些新药会**新触发**哪些安全告警(delta 法)。

    先对现状跑一遍规则得 baseline,再把候选药塞进 Twin 的 active_meds 跑一遍,
    返回新增的 Alert(即「就是这些新药引入的」)。按 rule_id 去重。

    覆盖范围:当前用轻量 twin(药物分区),主要捕获 **药×药 DDI**(本场景真实风险:
    克拉霉素 CYP3A4 抑制 × 他汀/华法林等)。PGx(需基因)/DSI(需补剂)的引入即校验
    待接全量 twin 后补 —— 不在此处假装已覆盖。
    """
    if not candidate_names:
        return []

    twin = _safety_twin(db, user_id)
    before_ids = {a.rule_id for a in evaluate_rules(twin)}

    # 把候选新药追加进 medication 分区(只用得到 name;DDI 规则按药名匹配)
    if twin.medication.active_meds is None:
        twin.medication.active_meds = []
    for nm in candidate_names:
        twin.medication.active_meds.append({"name": nm})
    twin.medication.has_any = True

    after = evaluate_rules(twin)
    delta = [a for a in after if a.rule_id not in before_ids]
    # 按严重度降序,CRITICAL 在前
    delta.sort(key=lambda a: int(a.severity), reverse=True)
    return delta


def _audit_introduction(
    db: Session,
    user_id: int,
    regimen_name: str,
    candidate_names: List[str],
    alerts: List[Alert],
    decision: str,  # blocked / override / clean
) -> None:
    """把一次「引入即 DDI 校验」的结果写进 Agent 审计(旁路,失败不影响主流程)。

    被阻断 / 被 override 的高危录入尝试**最该留痕**(知情同意 / 纠纷 / 复盘)。
    """
    try:
        from app.agents.audit import log_safety_evaluation

        log_safety_evaluation(
            db,
            user_id=user_id,
            alerts_count=len(alerts),
            result_summary=f"regimen_introduce:{decision} 「{regimen_name}」",
            twin_build_ms=0,
            evaluate_ms=0,
            twin_sources=["medication"],
            result_detail={
                "kind": "medication_regimen_introduce",
                "decision": decision,
                "candidates": candidate_names,
                "triggered_rules": [a.rule_id for a in alerts],
            },
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[Regimen] 审计写入失败(旁路): {e}")


def _resolve_phases(
    template_id: Optional[str],
    phases: Optional[List[Dict[str, Any]]],
) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """从模板或自定义 phases 解析出 (phases, template_meta)。"""
    if template_id:
        tpl = regimen_templates.get_template(template_id)
        if not tpl:
            raise ValueError(f"未知方案模板: {template_id}")
        return tpl["phases"], tpl
    if phases:
        return phases, None
    raise ValueError("必须提供 template_id 或 phases")


def instantiate_regimen(
    db: Session,
    user_id: int,
    *,
    template_id: Optional[str] = None,
    phases: Optional[List[Dict[str, Any]]] = None,
    name: Optional[str] = None,
    start_on: Optional[date] = None,
    override_safety: bool = False,
) -> Dict[str, Any]:
    """实例化一个用药方案。

    流程:解析 phases → 对**当前阶段(phase 0)**的药跑 DDI 预检 →
    若有「需阻断」相互作用(severity≥HIGH 或 requires_medical_attention)且 override_safety=False
    → 阻断(不写库,返回 blocked=True)→ 否则建 MedicationRegimen + phase 0 的 Medication 行(带 timing)。
    阻断 / override / clean 三种结局都写 Agent 审计(旁路)。

    返回 {blocked, safety_alerts, disclaimer, regimen}。blocked=True 时 regimen=None。
    """
    resolved_phases, tpl = _resolve_phases(template_id, phases)
    regimen_name = name or (tpl["name"] if tpl else "用药方案")
    review_note = tpl.get("review_on_complete") if tpl else None
    source = f"template:{template_id}" if template_id else "manual"

    # ── 引入即 DDI 预检(硬闸门)──────────────────────────────
    candidate_names = regimen_templates.phase_med_names(resolved_phases, 0)
    alerts = precheck_interactions(db, user_id, candidate_names)
    alerts_json = [a.model_dump_for_api() for a in alerts]

    # 阻断阈值:severity≥HIGH **或** 规则标了「需就医」。
    # 一键自动录入是主动动作,不是被动观察现状,应更保守 —— 本场景的克拉霉素×阿托伐他汀
    # 只评 MEDIUM 却 requires_medical_attention=True(横纹肌溶解风险),必须拦,不能只"提示"。
    blocking = [a for a in alerts if a.severity >= Severity.HIGH or a.requires_medical_attention]

    if blocking and not override_safety:
        logger.warning(
            f"[Regimen] user={user_id} 方案 {regimen_name} 被 DDI 闸门阻断: "
            f"{[a.rule_id for a in blocking]}"
        )
        _audit_introduction(db, user_id, regimen_name, candidate_names, alerts, "blocked")
        return {
            "blocked": True,
            "safety_alerts": alerts_json,
            "disclaimer": regimen_templates.TEMPLATE_DISCLAIMER,
            "regimen": None,
        }
    if blocking:  # override_safety=True 才走到这:知情强录,留痕
        logger.warning(
            f"[Regimen] user={user_id} 方案 {regimen_name} 知情强行录入(override): "
            f"{[a.rule_id for a in blocking]}"
        )
        _audit_introduction(db, user_id, regimen_name, candidate_names, alerts, "override")
    else:
        _audit_introduction(db, user_id, regimen_name, candidate_names, alerts, "clean")

    # ── 写库:疗程 + 当前阶段药品 ───────────────────────────
    start = start_on or date.today()
    total_days = sum(int(p.get("duration_days") or 0) for p in resolved_phases)
    expected_end = start + timedelta(days=total_days) if total_days else None

    regimen = MedicationRegimen(
        user_id=user_id,
        name=regimen_name,
        source=source,
        template_id=template_id,
        status="active",
        current_phase=0,
        phases=resolved_phases,
        review_on_complete=review_note,
        started_on=start,
        expected_end_on=expected_end,
    )
    db.add(regimen)
    db.flush()  # 拿 regimen.id 给药品挂

    phase0 = resolved_phases[0] if resolved_phases else {"meds": []}
    phase_end = start + timedelta(days=int(phase0.get("duration_days") or 0))
    for m in phase0.get("meds") or []:
        db.add(Medication(
            user_id=user_id,
            name=m["name"],
            dosage=m.get("dosage"),
            frequency=m.get("frequency"),
            times_per_day=m.get("times_per_day", 1),
            reminder_times=m.get("reminder_times"),
            timing_relation=m.get("timing_relation"),
            meal_anchor=m.get("meal_anchor"),
            category="处方药",
            purpose=regimen_name,
            regimen_id=regimen.id,
            start_date=start,
            end_date=phase_end,
            is_active=True,
        ))
    db.commit()
    db.refresh(regimen)
    logger.info(f"[Regimen] user={user_id} 方案已实例化: id={regimen.id} 阶段药 {len(phase0.get('meds') or [])} 种")

    return {
        "blocked": False,
        "safety_alerts": alerts_json,  # 非 CRITICAL 的提示仍带回(让用户知情)
        "disclaimer": regimen_templates.TEMPLATE_DISCLAIMER,
        "regimen": serialize_regimen(regimen),
    }


def list_regimens(db: Session, user_id: int, active_only: bool = True) -> List[Dict[str, Any]]:
    q = db.query(MedicationRegimen).filter(MedicationRegimen.user_id == user_id)
    if active_only:
        q = q.filter(MedicationRegimen.status == "active")
    return [serialize_regimen(r) for r in q.order_by(MedicationRegimen.created_at.desc()).all()]


def serialize_regimen(r: MedicationRegimen) -> Dict[str, Any]:
    phases = r.phases or []
    cur = r.current_phase or 0
    # 给每个阶段的药补中文时点标签,前端直接显示
    phases_view = []
    for p in phases:
        meds = []
        for m in p.get("meds") or []:
            meds.append({**m, "timing_label": medication_timing_label(m.get("timing_relation"), m.get("meal_anchor"))})
        phases_view.append({**p, "meds": meds})
    return {
        "id": r.id,
        "name": r.name,
        "source": r.source,
        "template_id": r.template_id,
        "status": r.status,
        "current_phase": cur,
        "current_phase_name": phases[cur].get("name") if cur < len(phases) else None,
        "phases": phases_view,
        "review_on_complete": r.review_on_complete,
        "started_on": str(r.started_on) if r.started_on else None,
        "expected_end_on": str(r.expected_end_on) if r.expected_end_on else None,
    }
