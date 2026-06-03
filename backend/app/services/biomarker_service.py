"""Biomarker 服务 — 把 MedicalExamItem 归一化落库为 BiomarkerObservation, 并提供查询 (PRD P1, G3).

核心:
    observe_exam_item(db, user_id, item, sex, age, observed_at)  # 单项归一化落库
    ingest_exam(db, exam)                                        # 整张体检 → observations
    latest_observations(db, user_id)                             # 每个 code 的最新观测
    observation_series(db, user_id, code)                        # 单指标趋势
    backfill_user(db, user_id)                                   # 回填历史体检

设计为旁路: 失败不抛给上游 (体检入库不应被归一化拖垮), 只 log。
暂不挂进既有 import 流程 (保持改动可评审); 由调用方在导入后显式调用 ingest_exam。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.biomarkers.normalize import normalize_observation
from app.models.biomarker_observation import BiomarkerObservation

logger = logging.getLogger(__name__)


def _norm_sex(g) -> Optional[str]:
    if not g:
        return None
    s = str(g).strip().lower()
    if s in ("male", "m", "男"):
        return "male"
    if s in ("female", "f", "女"):
        return "female"
    return None


def observe_exam_item(
    db: Session,
    user_id: int,
    item,
    *,
    sex: Optional[str] = None,
    age: Optional[int] = None,
    observed_at: Optional[datetime] = None,
    commit: bool = True,
) -> Optional[BiomarkerObservation]:
    """把一个 MedicalExamItem 归一化并落库。识别不到 / 无数值 → None (幂等: 同 source_item 已存在则更新)。"""
    raw_name = getattr(item, "item_name", None) or getattr(item, "item_code", None)
    value = getattr(item, "value", None)
    unit = getattr(item, "unit", None)
    if raw_name is None or value is None:
        return None

    norm = normalize_observation(raw_name, value, unit, sex=sex, age=age)
    if norm is None:
        return None

    item_id = getattr(item, "id", None)
    src = getattr(item, "source", None)
    obs_at = observed_at or datetime.utcnow()

    existing = None
    if item_id is not None:
        existing = (
            db.query(BiomarkerObservation)
            .filter(BiomarkerObservation.source_exam_item_id == item_id)
            .first()
        )

    target = existing or BiomarkerObservation(user_id=user_id, source_exam_item_id=item_id)
    target.code = norm.code
    target.domain = norm.domain
    target.value = norm.value
    target.unit = norm.unit
    target.normalized_value = norm.normalized_value
    target.normalized_unit = norm.normalized_unit
    target.ref_low = norm.ref_low
    target.ref_high = norm.ref_high
    target.flag = norm.flag
    target.abnormal = norm.abnormal
    target.is_risk = norm.is_risk
    target.confidence = norm.confidence
    target.observed_at = obs_at
    target.source = src

    if existing is None:
        db.add(target)
    if commit:
        db.commit()
        db.refresh(target)
    return target


def ingest_exam(db: Session, exam, *, user_id: Optional[int] = None) -> list:
    """把一张 MedicalExam 的所有项目归一化为 observations。返回成功落库的 observation 列表。"""
    uid = user_id or getattr(exam, "user_id", None)
    if uid is None:
        return []
    sex = _norm_sex(getattr(exam, "patient_gender", None))
    age = getattr(exam, "patient_age", None)
    observed_at = getattr(exam, "exam_date", None)
    items = getattr(exam, "items", None) or []

    out = []
    for item in items:
        try:
            obs = observe_exam_item(
                db, uid, item, sex=sex, age=age, observed_at=observed_at, commit=False
            )
            if obs is not None:
                out.append(obs)
        except Exception as e:  # 旁路: 单项失败不影响其它项
            logger.warning("biomarker ingest failed for item %s: %s", getattr(item, "id", "?"), e)
    if out:
        db.commit()
        for o in out:
            db.refresh(o)
    return out


def latest_observations(db: Session, user_id: int) -> dict:
    """每个 code 的最新一条观测 {code: BiomarkerObservation}。"""
    rows = (
        db.query(BiomarkerObservation)
        .filter(BiomarkerObservation.user_id == user_id)
        .order_by(BiomarkerObservation.observed_at.desc())
        .all()
    )
    out: dict = {}
    for r in rows:
        if r.code not in out:
            out[r.code] = r
    return out


def observation_series(db: Session, user_id: int, code: str) -> list:
    """单指标按时间升序的观测序列 (趋势用)。"""
    return (
        db.query(BiomarkerObservation)
        .filter(BiomarkerObservation.user_id == user_id, BiomarkerObservation.code == code)
        .order_by(BiomarkerObservation.observed_at.asc())
        .all()
    )


def backfill_user(db: Session, user_id: int) -> int:
    """回填某用户所有历史体检的 observations。返回落库条数。"""
    from app.models.medical_exam import MedicalExam

    exams = db.query(MedicalExam).filter(MedicalExam.user_id == user_id).all()
    n = 0
    for exam in exams:
        n += len(ingest_exam(db, exam, user_id=user_id))
    return n
