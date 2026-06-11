"""干预周期服务 — 起始 / 复查 / 查询 (PRD P2, G4).

闭环:
    start_metabolic_cycle(db, user_id, twin)   # 锁基线快照 + 基线 biomarker + 目标 → 建周期
    record_recheck(db, cycle, twin)            # 复查: 新快照 + 最新 biomarker → 算 delta/status
    get_active_cycle(db, user_id)

target_metrics 缺省由 default_metabolic_targets() 从当前异常代谢指标推导; 调用方可覆盖。
所有 baseline/latest 取自 BiomarkerObservation (标准化值), 快照绑定 TwinSnapshot。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.intervention_cycle import (
    InterventionCycle, OutcomeMetric, DEFAULT_STOP_CONDITIONS,
)

# code -> (默认目标值, 期望方向). 仅用于 default_metabolic_targets 兜底。
_DEFAULT_TARGET_RULES = {
    "lipid_ldl": (3.0, "down"),
    "lipid_tg": (1.7, "down"),
    "lipid_tc": (5.2, "down"),
    "UA": (380.0, "down"),
    "glucose_fasting": (6.1, "down"),
    "glucose_hba1c": (5.7, "down"),
    "ALT": (50.0, "down"),
    "GGT": (60.0, "down"),
    "lipid_hdl": (1.0, "up"),
}


def default_metabolic_targets(latest_obs: dict) -> list:
    """从最新观测里挑出"当前异常"的代谢/血脂/血糖/肝指标作为周期目标。

    latest_obs: {code: BiomarkerObservation} (来自 biomarker_service.latest_observations)
    """
    specs = []
    for code, (target, direction) in _DEFAULT_TARGET_RULES.items():
        obs = latest_obs.get(code)
        if obs is None:
            continue
        if getattr(obs, "abnormal", False):  # 聚焦需要改善的
            specs.append({"code": code, "target": target, "direction": direction})
    return specs


def _metric_status(om: OutcomeMetric) -> str:
    if om.baseline_value is None or om.latest_value is None:
        return "pending"
    desirable = om.direction or "down"
    if om.target_value is not None:
        if desirable == "down" and om.latest_value <= om.target_value:
            return "met"
        if desirable == "up" and om.latest_value >= om.target_value:
            return "met"
    if om.delta is None or abs(om.delta) < 1e-9:
        return "flat"
    moved_down = om.delta < 0
    improving = (desirable == "down" and moved_down) or (desirable == "up" and not moved_down)
    return "improving" if improving else "worsening"


def start_metabolic_cycle(
    db: Session,
    user_id: int,
    twin,
    *,
    target_specs: Optional[list] = None,
    days: int = 90,
    stop_conditions: Optional[list] = None,
    start_date: Optional[date] = None,
) -> InterventionCycle:
    """开启一个代谢干预周期: 锁基线 Twin 快照 + 基线 biomarker + 目标指标。"""
    from app.twin.snapshots import snapshot_twin
    from app.services.biomarker_service import latest_observations

    baseline = snapshot_twin(db, user_id, twin, purpose="cycle_baseline", dedupe=False)
    latest_obs = latest_observations(db, user_id)
    specs = target_specs if target_specs is not None else default_metabolic_targets(latest_obs)

    start = start_date or date.today()
    cycle = InterventionCycle(
        user_id=user_id,
        cycle_type="metabolic_90d",
        status="active",
        start_date=start,
        planned_end_date=start + timedelta(days=days),
        baseline_snapshot_id=baseline.id,
        target_metrics=specs,
        stop_conditions=stop_conditions if stop_conditions is not None else list(DEFAULT_STOP_CONDITIONS),
    )
    db.add(cycle)
    db.commit()
    db.refresh(cycle)

    for spec in specs:
        obs = latest_obs.get(spec["code"])
        db.add(OutcomeMetric(
            cycle_id=cycle.id,
            metric_code=spec["code"],
            unit=(obs.normalized_unit if obs else None),
            baseline_value=(obs.normalized_value if obs else None),
            target_value=spec.get("target"),
            direction=spec.get("direction", "down"),
            status="pending",
            baseline_observed_at=(obs.observed_at if obs else None),
        ))
    db.commit()
    db.refresh(cycle)
    return cycle


def record_recheck(db: Session, cycle: InterventionCycle, twin) -> InterventionCycle:
    """复查: 落最新 Twin 快照, 用最新 biomarker 计算每个目标的 delta/delta_pct/status。"""
    from app.twin.snapshots import snapshot_twin
    from app.services.biomarker_service import latest_observations

    latest_snap = snapshot_twin(db, cycle.user_id, twin, purpose="cycle_latest", dedupe=False)
    cycle.latest_snapshot_id = latest_snap.id

    latest_obs = latest_observations(db, cycle.user_id)
    for om in cycle.outcomes:
        obs = latest_obs.get(om.metric_code)
        if obs is None:
            continue
        om.latest_value = obs.normalized_value
        om.latest_observed_at = obs.observed_at
        if om.baseline_value is not None:
            om.delta = round(om.latest_value - om.baseline_value, 3)
            if abs(om.baseline_value) > 1e-9:
                om.delta_pct = round(om.delta / abs(om.baseline_value) * 100, 1)
        om.status = _metric_status(om)

    db.commit()
    db.refresh(cycle)
    return cycle


def refresh_cycle_targets(db: Session, cycle: InterventionCycle) -> InterventionCycle:
    """(重)计算周期目标 —— 修复"周期空目标"(根因:开周期时 biomarker_observations 为空)。

    用当前最新观测推导异常指标作目标,补齐 target_metrics + 缺失的 OutcomeMetric(基线快照)。
    幂等:已有的 metric_code 不重复建。前置应先 sync_indicators_to_biomarkers 打通归一层。
    """
    from app.services.biomarker_service import latest_observations

    latest_obs = latest_observations(db, cycle.user_id)
    specs = default_metabolic_targets(latest_obs)
    cycle.target_metrics = specs

    existing_codes = {om.metric_code for om in cycle.outcomes}
    for spec in specs:
        if spec["code"] in existing_codes:
            continue
        obs = latest_obs.get(spec["code"])
        db.add(OutcomeMetric(
            cycle_id=cycle.id,
            metric_code=spec["code"],
            unit=(obs.normalized_unit if obs else None),
            baseline_value=(obs.normalized_value if obs else None),
            target_value=spec.get("target"),
            direction=spec.get("direction", "down"),
            status="pending",
            baseline_observed_at=(obs.observed_at if obs else None),
        ))
    db.commit()
    db.refresh(cycle)
    return cycle


def get_active_cycle(db: Session, user_id: int) -> Optional[InterventionCycle]:
    return (
        db.query(InterventionCycle)
        .filter(InterventionCycle.user_id == user_id, InterventionCycle.status == "active")
        .order_by(InterventionCycle.start_date.desc())
        .first()
    )


def complete_cycle(db: Session, cycle: InterventionCycle, *, status: str = "completed") -> InterventionCycle:
    cycle.status = status if status in {"completed", "abandoned"} else "completed"
    db.commit()
    db.refresh(cycle)
    return cycle
