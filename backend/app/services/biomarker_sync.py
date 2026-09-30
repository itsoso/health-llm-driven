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
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.biomarkers.normalize import normalize_observation
from app.models.biomarker_observation import BiomarkerObservation
from app.models.user import User
from app.services.biomarker_service import SYNC_SOURCE, as_date, backfill_user, fill_observation

logger = logging.getLogger(__name__)

__all__ = ["SYNC_SOURCE", "sync_indicators_to_biomarkers"]


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
    """把 user 的体检与 medical_indicators 对账进 biomarker_observations。幂等、自愈。

    1. 先把 user 的每张 exam 归一化落库 (exam 路径, 按 source_exam_item_id 幂等) —— 体检入库
       API 曾漏接 ingest_exam, 这里兜底。
    2. 全部指标 (含挂 exam 的) 归一后派生 indicator_sync 行, 以 (code, 日历日, 值) 为一次测量:
       同一次测量已有 exam 等更结构化来源的行 → 不写并删掉本源行 (exam 优先); 同日不同值是另一次测量,
       保留。写入期被改名的标签 (尿肌酐 →「肌酐」mg/g、MCH →「血红蛋白」pg) 由归一化的单位闸门拒收。
    3. 对账而非追加: 每次测量至多一行本源行; 本源旧行若已不对应任何指标 (旧映射写错的 CREA/LDL 行、
       指标被改值或删除) → 删除。旧实现逐条查「第一个同日候选」, autoflush=False 下同批新增行不可见
       → 同日多行, 且后写覆盖先写。observed_at 可能是 date/datetime/字符串 —— 日历日在 Python 侧比对。

    返回 {scanned, recognized, written, skipped, deleted, exam_observations}。
    """
    exam_observations = backfill_user(db, user_id)

    sex, age = _user_sex_age(db, user_id)
    rows = db.execute(text(
        "SELECT name, value, unit, record_date FROM medical_indicators "
        "WHERE user_id = :uid AND value IS NOT NULL ORDER BY id"
    ), {"uid": user_id}).fetchall()

    scanned = len(rows)
    recognized = 0
    desired: dict[tuple, object] = {}  # (code, 日, 值) → 归一结果
    for name, value, unit, rec_date in rows:
        d = as_date(rec_date)
        if d is None:
            continue
        norm = normalize_observation(name, value, unit, sex=sex, age=age)
        if norm is None:  # 不在 definitions 里 / 单位量纲不符 / 数值不合理 → 跳过(不臆造)
            continue
        recognized += 1
        desired[(norm.code, d, norm.normalized_value)] = norm

    existing = (
        db.query(BiomarkerObservation)
        .filter(BiomarkerObservation.user_id == user_id)
        .order_by(BiomarkerObservation.id)
        .all()
    )
    structured = {
        (o.code, as_date(o.observed_at), o.normalized_value) for o in existing if o.source != SYNC_SOURCE
    }
    own: dict[tuple, list[BiomarkerObservation]] = {}
    for o in existing:
        if o.source == SYNC_SOURCE:
            own.setdefault((o.code, as_date(o.observed_at), o.normalized_value), []).append(o)

    written = skipped = deleted = 0
    for key, norm in desired.items():
        if key in structured:  # 同一次测量已由 exam 等更结构化来源落库,绝不重复
            skipped += 1
            continue
        mine = own.pop(key, [])
        target = mine[0] if mine else BiomarkerObservation(user_id=user_id)
        for extra in mine[1:]:
            db.delete(extra)
            deleted += 1
        day = key[1]
        fill_observation(target, norm, datetime(day.year, day.month, day.day), SYNC_SOURCE)
        if not mine:
            db.add(target)
        written += 1

    for stale in own.values():  # 与 exam 重复 / 指标已不存在或改值 / 旧映射写错
        for o in stale:
            db.delete(o)
            deleted += 1

    db.commit()
    logger.info(
        f"[biomarker_sync] user={user_id} exam_observations={exam_observations} scanned={scanned} "
        f"recognized={recognized} written={written} skipped={skipped} deleted={deleted}"
    )
    return {
        "scanned": scanned,
        "recognized": recognized,
        "written": written,
        "skipped": skipped,
        "deleted": deleted,
        "exam_observations": exam_observations,
    }
