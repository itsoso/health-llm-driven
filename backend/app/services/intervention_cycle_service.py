"""干预周期服务 — 起始 / 复查 / 查询 (PRD P2, G4).

闭环:
    start_metabolic_cycle(db, user_id, twin)   # 锁基线快照 + 基线 biomarker + 目标 → 建周期
    record_recheck(db, cycle, twin)            # 复查: 新快照 + 最新 biomarker → 算 delta/status
    get_active_cycle(db, user_id)

target_metrics 缺省由 default_metabolic_targets() 从当前异常代谢指标推导; 调用方可覆盖。
所有 baseline/latest 取自 BiomarkerObservation (标准化值), 快照绑定 TwinSnapshot。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.intervention_cycle import (
    InterventionCycle, OutcomeMetric, DEFAULT_STOP_CONDITIONS,
)

logger = logging.getLogger(__name__)

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


def _floor_confidence(conf, smoothing_method, ma_lag_divergent) -> Optional[str]:
    """R16 P2:稀疏(未平滑)或近期剧烈波动 → 置信度封 low(只降不升,不臆造/不静默高置信)。"""
    if smoothing_method == "none" or ma_lag_divergent:
        return "low"
    return conf


def _metric_status(
    om: OutcomeMetric,
    *,
    smoothed_delta_pct: Optional[float] = None,
    smoothing_method: Optional[str] = None,
    ma_lag_divergent: bool = False,
) -> str:
    """R16 去噪:目标达成 → met;变化未超 RCV(噪声带内)→ flat;超噪声 → improving/worsening。

    副作用:写 om.significant / om.confidence。**P2**:有 smoothed_delta_pct(端点去噪后)则用它判
    显著/方向(单点噪声不再冒充信号);稀疏/MA-lag 背离 → 置信度封 low。不传(legacy / 其它调用方)
    → 退回原始单点 delta_pct,行为与改前**逐字节一致**。
    """
    from app.services.intervention_significance import classify_change

    if om.baseline_value is None or om.latest_value is None:
        om.significant, om.confidence = None, None
        return "pending"
    eval_delta_pct = smoothed_delta_pct if smoothed_delta_pct is not None else om.delta_pct
    desirable = om.direction or "down"
    if om.target_value is not None:
        if (desirable == "down" and om.latest_value <= om.target_value) or \
           (desirable == "up" and om.latest_value >= om.target_value):
            # 达标即达标,但仍标注本次变化的统计置信度
            _, conf = classify_change(eval_delta_pct, om.metric_code)
            om.significant = True
            om.confidence = _floor_confidence(conf, smoothing_method, ma_lag_divergent)
            return "met"

    significant, confidence = classify_change(eval_delta_pct, om.metric_code)
    om.significant = significant
    om.confidence = _floor_confidence(confidence, smoothing_method, ma_lag_divergent)
    if not significant:
        return "flat"   # 落在噪声带内(未超 RCV)—— 不臆断见效
    moved_down = (eval_delta_pct or 0) < 0
    improving = (desirable == "down" and moved_down) or (desirable == "up" and not moved_down)
    return "improving" if improving else "worsening"


def _apply_washout_attribution(db: Session, cycle: InterventionCycle, om: OutcomeMetric) -> None:
    """R16 P3:判跨周期洗脱期归因,写 om.attribution_state / washout_until;washout_pending → 置信度封 low。

    严格 demote-only(只降不升);attribution_for_metric 内部已 fail-closed(异常→washout_pending),
    本层再兜一道:写归因字段出错也 fail-closed 到 washout_pending + low(绝不留 attributable 假绿)。
    """
    from app.services import washout_guard

    try:
        state, washout_until = washout_guard.attribution_for_metric(
            db, cycle.user_id, cycle, om.metric_code, om.baseline_observed_at
        )
        om.attribution_state = state
        om.washout_until = washout_until
        if state == washout_guard.WASHOUT_PENDING:
            om.confidence = "low"  # 归因待定 → 不自信(只降不升;不改测得的方向/status)
    except Exception as e:  # noqa: BLE001 — fail-closed:出错宁可 washout_pending,绝不默认 attributable
        logger.warning("[washout] 归因写入失败,fail-closed: metric=%s err=%s", om.metric_code, e)
        om.attribution_state = washout_guard.WASHOUT_PENDING
        om.confidence = "low"


def _denoised_status(db: Session, cycle: InterventionCycle, om: OutcomeMetric) -> str:
    """R16 P2 去噪 + P3 洗脱期归因:取观测序列做端点去噪喂 _metric_status,再叠加跨周期洗脱期归因。

    密集(两端各 ≥3 点)→ 7 天均值平滑端点;稀疏(化验)→ 不平滑 + 置信度封 low(不臆造趋势)。
    去噪异常 → fail-soft 退回原始单点。随后 P3 跨周期洗脱期归因(washout_pending → 再封 low,只降不升)。
    """
    from app.services import intervention_denoise as dn
    from app.services.biomarker_service import observation_series

    try:
        series = [
            (o.observed_at, o.normalized_value)
            for o in observation_series(db, cycle.user_id, om.metric_code)
        ]
        d = dn.denoise_endpoints(
            series, om.baseline_observed_at, om.baseline_value,
            om.latest_observed_at, om.latest_value,
        )
        om.smoothing_method = d["method"]
        om.sample_n = d["sample_n"]
        status = _metric_status(
            om,
            smoothed_delta_pct=dn.smoothed_delta_pct(d),
            smoothing_method=d["method"],
            ma_lag_divergent=d["ma_lag_divergent"],
        )
    except Exception:  # noqa: BLE001 — 去噪失败绝不臆造,退回原始单点 delta(legacy 行为)
        logger.warning("[Cycle] 端点去噪失败,退回原始单点 delta: metric=%s", om.metric_code)
        om.smoothing_method = None
        status = _metric_status(om)

    _apply_washout_attribution(db, cycle, om)  # P3:叠加跨周期洗脱期归因(只降置信度,不改 status)
    return status


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
        om.status = _denoised_status(db, cycle, om)

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


def intervention_proposal_prompt_blob(db: Session, user_id: int) -> str:
    """轻量主动提议: 用户有明确异常代谢杠杆 + 无 active 周期时, 提示 agent 可提议开 N-of-1 周期。

    返回空串表示不提议 (已有周期 / 无异常杠杆 / 任何异常)。措辞要求 agent "只提议 + 要确认",
    避免刷屏。**只读**, 失败静默返回空 (system prompt 注入是旁路, 不应影响主链路)。
    """
    try:
        if get_active_cycle(db, user_id) is not None:
            return ""  # 已有周期, 不提议

        from app.services.biomarker_service import latest_observations
        latest_obs = latest_observations(db, user_id)
        specs = default_metabolic_targets(latest_obs)
        if not specs:
            return ""  # 无明确异常代谢杠杆

        from app.biomarkers import get_definition
        names = []
        for spec in specs[:4]:
            defn = get_definition(spec["code"])
            names.append(defn.display if defn else spec["code"])
        levers = ", ".join(names)
        return (
            "## 干预闭环主动提议 (克制使用, 只提议 + 要确认)\n"
            f"- 用户当前有偏高的代谢指标: {levers}, 且没有进行中的干预周期。\n"
            "- 在合适时机 (用户聊到这些指标 / 想改善代谢 / 问'我该怎么调理') 可**提议**开一个 "
            "N-of-1 干预周期, 用 ta 自己的复查数据验证某个干预是否真的有效 (产品核心: 验证闭环)。\n"
            "- 调用 intervention_cycle(action='start') 走确认流程, 不要一句话就建周期, 也不要每轮都提。\n"
            "- 措辞: 非医疗诊断, 是自我管理实验; 重大调整建议结合医生。不要诱导, 用户没兴趣就放下。"
        )
    except Exception:  # noqa: BLE001 — prompt 注入旁路, 失败不应影响对话
        return ""


def complete_cycle(db: Session, cycle: InterventionCycle, *, status: str = "completed") -> InterventionCycle:
    cycle.status = status if status in {"completed", "abandoned"} else "completed"
    db.commit()
    db.refresh(cycle)
    return cycle
