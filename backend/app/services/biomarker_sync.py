"""medical_indicators → biomarker_observations 同步。

根因(盘点 P0③):归一化生物标志层(biomarker_observations)只从 MedicalExam.items
回填,但化验的统一存储是 medical_indicators(OCR/图片/手动/CSV 都写这)。两套数据源
没打通 → 很多用户 biomarker_observations 为空 → metabolic_90d 周期空目标、PhenoAge
喂不饱、结局判定无基线。本模块把 medical_indicators 归一后落 biomarker_observations,
打通断点。复用 normalize_observation(同一套 code 映射/单位换算/参考范围),不另造归一。
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.biomarkers.normalize import normalize_observation
from app.models.biomarker_observation import BiomarkerObservation
from app.models.user import User

logger = logging.getLogger(__name__)


def _as_date(v: Any) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def _user_sex_age(db: Session, user_id: int) -> tuple[Optional[str], Optional[int]]:
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        return None, None
    sex = None
    g = getattr(u, "gender", None)
    if g:
        sex = "male" if g in ("男", "male", "M") else ("female" if g in ("女", "female", "F") else None)
    age = None
    bd = getattr(u, "birth_date", None)
    if bd:
        t = date.today()
        age = t.year - bd.year - ((t.month, t.day) < (bd.month, bd.day))
    return sex, age


def sync_indicators_to_biomarkers(db: Session, user_id: int) -> dict[str, int]:
    """把 user 的 medical_indicators 归一并 upsert 到 biomarker_observations。

    幂等:按 (user_id, code, observed_at) 去重 —— 同指标同日期已有则更新,否则插入。
    返回 {scanned, recognized, written}。
    """
    sex, age = _user_sex_age(db, user_id)
    rows = db.execute(text(
        "SELECT name, value, unit, record_date FROM medical_indicators "
        "WHERE user_id = :uid AND value IS NOT NULL"
    ), {"uid": user_id}).fetchall()

    scanned = len(rows)
    recognized = 0
    written = 0
    for name, value, unit, rec_date in rows:
        d = _as_date(rec_date)
        if d is None:
            continue
        norm = normalize_observation(name, value, unit, sex=sex, age=age)
        if norm is None:  # 不在 definitions 里的指标 → 跳过(不臆造)
            continue
        recognized += 1
        observed_at = datetime(d.year, d.month, d.day)
        existing = (
            db.query(BiomarkerObservation)
            .filter(
                BiomarkerObservation.user_id == user_id,
                BiomarkerObservation.code == norm.code,
                BiomarkerObservation.observed_at == observed_at,
            )
            .first()
        )
        target = existing or BiomarkerObservation(user_id=user_id)
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
        target.observed_at = observed_at
        target.source = "indicator_sync"
        if existing is None:
            db.add(target)
        written += 1

    db.commit()
    logger.info(f"[biomarker_sync] user={user_id} scanned={scanned} recognized={recognized} written={written}")
    return {"scanned": scanned, "recognized": recognized, "written": written}
