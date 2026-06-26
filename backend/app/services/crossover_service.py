"""R16 P4 交叉实验服务 —— 建实验 / 串入 on-off 相 / 重复感知裁决。

相 = 一个 InterventionCycle(on=干预期 / off=停用或洗脱期);该相的指标 level 取该 cycle 的
OutcomeMetric.latest_value(无则 baseline_value)。裁决由 crossover_verdict 算(治理护栏在那)。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.crossover_experiment import CrossoverExperiment
from app.models.intervention_cycle import OutcomeMetric
from app.services.crossover_verdict import replication_verdict

logger = logging.getLogger(__name__)

VALID_ARMS = {"on", "off"}


def _phase_level(db: Session, cycle_id: int, metric_code: str) -> Optional[float]:
    """取该 cycle 内该指标的代表 level:latest_value 优先,无则 baseline_value。"""
    om = (
        db.query(OutcomeMetric)
        .filter(OutcomeMetric.cycle_id == cycle_id, OutcomeMetric.metric_code == metric_code)
        .first()
    )
    if om is None:
        return None
    return om.latest_value if om.latest_value is not None else om.baseline_value


def _recompute(exp: CrossoverExperiment) -> None:
    v = replication_verdict(exp.phases or [], exp.metric_code, exp.direction or "down")
    exp.verdict = v["verdict"]
    exp.confidence = v["confidence"]


def create_experiment(
    db: Session, user_id: int, metric_code: str, direction: str = "down"
) -> CrossoverExperiment:
    exp = CrossoverExperiment(
        user_id=user_id, metric_code=metric_code,
        direction=direction if direction in ("down", "up") else "down",
        status="active", phases=[],
    )
    _recompute(exp)  # 空相 → insufficient
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def add_phase(db: Session, exp: CrossoverExperiment, cycle_id: int, arm: str) -> CrossoverExperiment:
    """把一个 cycle 作为 on/off 相串入,取其 level,重算裁决。arm 非法 → ValueError。"""
    if arm not in VALID_ARMS:
        raise ValueError(f"arm must be one of {VALID_ARMS}, got {arm!r}")
    level = _phase_level(db, cycle_id, exp.metric_code)
    phases = list(exp.phases or [])
    phases.append({"cycle_id": cycle_id, "arm": arm, "level": level})
    exp.phases = phases  # 重新赋值新 list,确保 SQLAlchemy 检测到 JSON 变更
    _recompute(exp)
    db.commit()
    db.refresh(exp)
    return exp


def serialize(exp: CrossoverExperiment) -> Dict[str, Any]:
    """前端友好序列化:含完整重复感知裁决细节(n_on/n_off/mean/attribution)。"""
    v = replication_verdict(exp.phases or [], exp.metric_code, exp.direction or "down")
    return {
        "id": exp.id,
        "metric_code": exp.metric_code,
        "direction": exp.direction,
        "status": exp.status,
        "phases": exp.phases or [],
        **v,  # verdict, confidence, requires_clinician, n_on, n_off, mean_on, mean_off, attribution
    }
