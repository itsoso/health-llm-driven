"""medical_indicators → biomarker_observations 同步 + 统一回填入口。

根因(盘点 P0③):归一化生物标志层(biomarker_observations)只从 MedicalExam.items
回填,但化验的统一存储是 medical_indicators(OCR/图片/手动/CSV 都写这)。两套数据源
没打通 → 很多用户 biomarker_observations 为空 → metabolic_90d 周期空目标(目标列表
为空 + OutcomeMetric 基线全 None)。本模块把 medical_indicators 归一后落
biomarker_observations,并提供 ensure_biomarkers() 统一入口(exam + indicators),
供干预周期等在"读 observation 前"自愈式调用。复用 normalize_observation
(同一套 code 映射/单位换算/参考范围),不另造归一。

跨源去重:exam 路径(biomarker_service)按 source_exam_item_id 去重、observed_at 可能
带时间;本模块按"同 user+code+同一日历日"去重,且**遇到已有的非本源(如 exam)观测
就跳过**——结构化的体检项优先,绝不写重复行、不覆盖更可信的来源。
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

_SYNC_SOURCE = "indicator_sync"


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


def _same_day_observation(
    db: Session, user_id: int, code: str, day: date
) -> Optional[BiomarkerObservation]:
    """查同一日历日、同 code 的已有观测(无论 observed_at 是 date 还是带时间的 datetime)。

    在 Python 侧按日历日比对,避开 SQLite 把 date 与 datetime 存成不同字符串
    导致 SQL 范围查询漏匹配的坑(exam 路径常把 observed_at 存成纯 date)。
    单 user+code 行数极少,全取无压力。
    """
    rows = (
        db.query(BiomarkerObservation)
        .filter(
            BiomarkerObservation.user_id == user_id,
            BiomarkerObservation.code == code,
        )
        .all()
    )
    for r in rows:
        if _as_date(r.observed_at) == day:
            return r
    return None


def sync_indicators_to_biomarkers(db: Session, user_id: int) -> dict[str, int]:
    """把 user 的 medical_indicators 归一并 upsert 到 biomarker_observations。

    幂等 + 跨源安全:
      - 同日同 code 已有"非本源"观测(如 exam)→ skipped(结构化来源优先,不写重复)
      - 同日同 code 已有本源(indicator_sync)观测 → 更新(允许后续修正)
      - 否则插入
    返回 {scanned, recognized, written, skipped}。
    """
    sex, age = _user_sex_age(db, user_id)
    rows = db.execute(text(
        "SELECT name, value, unit, record_date FROM medical_indicators "
        "WHERE user_id = :uid AND value IS NOT NULL"
    ), {"uid": user_id}).fetchall()

    scanned = len(rows)
    recognized = 0
    written = 0
    skipped = 0
    for name, value, unit, rec_date in rows:
        d = _as_date(rec_date)
        if d is None:
            continue
        norm = normalize_observation(name, value, unit, sex=sex, age=age)
        if norm is None:  # 不在 definitions 里的指标 → 跳过(不臆造)
            continue
        recognized += 1

        existing = _same_day_observation(db, user_id, norm.code, d)
        if existing is not None and existing.source != _SYNC_SOURCE:
            skipped += 1  # 已有更结构化的来源(如体检项),让位
            continue

        observed_at = datetime(d.year, d.month, d.day)
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
        target.source = _SYNC_SOURCE
        if existing is None:
            db.add(target)
        written += 1

    db.commit()
    logger.info(
        f"[biomarker_sync] user={user_id} scanned={scanned} "
        f"recognized={recognized} written={written} skipped={skipped}"
    )
    return {"scanned": scanned, "recognized": recognized, "written": written, "skipped": skipped}


def ensure_biomarkers(db: Session, user_id: int) -> dict[str, int]:
    """统一入口:回填体检(exam)+ 同步化验指标(indicators)→ biomarker_observations。

    幂等、可重跑、跨源去重。供干预周期 / 结局基线等在"读 observation 之前"调用,
    使 biomarker_observations 自愈式补齐,避免空目标 / 空基线。

    返回 {exam_observations, scanned, recognized, written, skipped}。
    """
    # 延迟导入避免与 biomarker_service 潜在循环依赖
    from app.services.biomarker_service import backfill_user

    exam_n = backfill_user(db, user_id)
    sync = sync_indicators_to_biomarkers(db, user_id)
    return {"exam_observations": exam_n, **sync}
