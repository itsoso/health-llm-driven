"""Biomarker 服务 — 把 MedicalExamItem 归一化落库为 BiomarkerObservation, 并提供查询 (PRD P1, G3).

核心:
    observe_exam_item(db, user_id, item, sex, age, observed_at)  # 单项归一化落库
    ingest_exam(db, exam)                                        # 整张体检 → observations
    latest_observations(db, user_id)                             # 每个 code 的最新观测
    observation_series(db, user_id, code)                        # 单指标趋势
    backfill_user(db, user_id)                                   # 回填历史体检
    ingest_exam_safely(db, exam)                                 # 体检入库后的旁路调用

旁路: 体检入库路径在自身 commit 之后调用 ingest_exam_safely —— 归一化失败不拖垮导入,
但会回滚会话并记 error 日志 (返回 False)。所有体检入库 API 都必须调用它 (2026-09-30 事故:
确认导入 / PDF / 图片 / 单项校正都漏接, 整张体检在归一化层零行)。
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.biomarkers.definitions import name_conflicts_with_code, resolve_code
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


# medical_indicators 同步写入的 source; exam 行 (source=item.source) 优先于它
SYNC_SOURCE = "indicator_sync"


def as_date(v: Any) -> Optional[date]:
    """observed_at/record_date 可能是 date/datetime/字符串; 统一成日历日在 Python 侧比对。"""
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


def fill_observation(target: BiomarkerObservation, norm, observed_at, source: Optional[str]) -> None:
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
    target.source = source


def _normalize_item(item, sex: Optional[str], age: Optional[int]):
    """按项目名归一; 名字不认识时退回 item_code 提示 (「Alanine aminotransferase」+ ALT), 除非名字与之冲突。"""
    name = getattr(item, "item_name", None)
    code_hint = getattr(item, "item_code", None)
    value = getattr(item, "value", None)
    unit = getattr(item, "unit", None)
    if value is None or not (name or code_hint):
        return None
    norm = normalize_observation(name or code_hint, value, unit, sex=sex, age=age)
    if norm is None and name and code_hint and resolve_code(name) is None:
        hinted = resolve_code(code_hint)
        if hinted is not None and not name_conflicts_with_code(name, hinted):
            norm = normalize_observation(hinted, value, unit, sex=sex, age=age)
    return norm


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
    """把一个 MedicalExamItem 归一化并落库 (幂等: 同 source_item 已存在则更新)。

    识别不到 / 无数值 → None, 且删除该 item 此前落下的行 —— 旧映射写错的行 (VLDL 曾被当 LDL)
    不能因为「现在识别不到」就永远留在标准序列里。
    """
    norm = _normalize_item(item, sex, age)
    item_id = getattr(item, "id", None)
    existing = None
    if item_id is not None:
        existing = (
            db.query(BiomarkerObservation)
            .filter(
                BiomarkerObservation.user_id == user_id,
                BiomarkerObservation.source_exam_item_id == item_id,
            )
            .first()
        )
    if norm is None:
        if existing is not None:
            db.delete(existing)
            if commit:
                db.commit()
        return None

    target = existing or BiomarkerObservation(user_id=user_id, source_exam_item_id=item_id)
    fill_observation(target, norm, observed_at or datetime.utcnow(), getattr(item, "source", None))
    if existing is None:
        db.add(target)
    if commit:
        db.commit()
        db.refresh(target)
    return target


def ingest_exam(db: Session, exam, *, user_id: Optional[int] = None) -> list:
    """把一张 MedicalExam 的所有项目归一化为 observations。返回本次落库/更新的 observation 列表。

    幂等且自愈:
      - 按 source_exam_item_id 更新; item 已识别不到 → 删除它的旧行。
      - 同一次测量已由另一张 exam 落库 (同 code、同日、同值; 同一报告被重复导入)
        → 不新增, 本 item 已有的重复行也删除 (对账后每次测量一行; 另一张 exam 的行保留)。
      - exam 优先: 同 (code, 日, 值) 的 indicator_sync 行是同一次测量 → 删除; 值不同的是另一次测量, 保留。
    单项归一是纯函数; 任何异常都让整张体检失败 (调用方 ingest_exam_safely 回滚并记 error), 不报部分成功。
    """
    uid = user_id or getattr(exam, "user_id", None)
    if uid is None:
        return []
    sex = _norm_sex(getattr(exam, "patient_gender", None))
    age = getattr(exam, "patient_age", None)
    observed_at = getattr(exam, "exam_date", None)
    obs_day = as_date(observed_at)
    items = list(getattr(exam, "items", None) or [])
    item_ids = {getattr(i, "id", None) for i in items} - {None}

    rows = db.query(BiomarkerObservation).filter(BiomarkerObservation.user_id == uid).all()
    mine = {r.source_exam_item_id: r for r in rows if r.source_exam_item_id in item_ids}
    others_same_day = [
        r for r in rows
        if r.source_exam_item_id not in item_ids and obs_day is not None and as_date(r.observed_at) == obs_day
    ]
    seen = {(r.code, r.normalized_value) for r in others_same_day if r.source != SYNC_SOURCE}

    out = []
    for item in items:
        norm = _normalize_item(item, sex, age)
        row = mine.get(getattr(item, "id", None))
        if norm is None:
            if row is not None:
                db.delete(row)
            continue
        if (norm.code, norm.normalized_value) in seen:
            # 同一次测量已由另一张 exam 落库 → 不新增; 旧 backfill 已落的重复行也收敛掉
            if row is not None:
                db.delete(row)
            continue
        if row is None:
            row = BiomarkerObservation(user_id=uid, source_exam_item_id=getattr(item, "id", None))
            db.add(row)
        fill_observation(row, norm, observed_at or datetime.utcnow(), getattr(item, "source", None))
        seen.add((norm.code, norm.normalized_value))
        out.append(row)

    for r in others_same_day:  # exam 优先: 只删同 (code, 日, 值) 的 indicator_sync 行
        if r.source == SYNC_SOURCE and (r.code, r.normalized_value) in seen:
            db.delete(r)
    db.commit()
    for o in out:
        db.refresh(o)
    return out


def ingest_exam_safely(db: Session, exam, *, same_day: bool = False) -> bool:
    """体检已提交后的旁路归一化。失败: 回滚会话 (调用方还要序列化 exam) + error 日志, 返回 False。

    same_day=True (单项校正后): 同用户同日的全部体检按 id 顺序重新归一 —— 校正可能解除跨 exam 的
    同值去重 (A 改值后, B 那条同值测量要重新落库)。
    不吞成功假象: 调用方拿到 False, 日志带 exam/user 与异常类型; 数据由下次对账
    (biomarker_sync / scripts/reconcile_biomarkers.py) 补齐。
    """
    try:
        exams = [exam]
        if same_day:
            from app.models.medical_exam import MedicalExam
            exams = (
                db.query(MedicalExam)
                .filter(MedicalExam.user_id == exam.user_id, MedicalExam.exam_date == exam.exam_date)
                .order_by(MedicalExam.id)
                .all()
            )
        for e in exams:
            ingest_exam(db, e)
        return True
    except Exception as e:  # noqa: BLE001 — 旁路; 失败可见 (返回值 + error 日志), 不影响已提交的导入
        db.rollback()
        logger.error(
            "biomarker ingest failed exam=%s user=%s error=%s",
            getattr(exam, "id", "?"), getattr(exam, "user_id", "?"), type(e).__name__,
        )
        return False


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

    exams = db.query(MedicalExam).filter(MedicalExam.user_id == user_id).order_by(MedicalExam.id).all()
    n = 0
    for exam in exams:
        n += len(ingest_exam(db, exam, user_id=user_id))
    return n
