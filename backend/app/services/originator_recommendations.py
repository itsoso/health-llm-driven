"""原研药推荐(抑制感知)。

基于用户**在用药**(medications.is_active)匹配原研药精选表,给出"可换原研"建议;
已采纳(adopted)/已忽略(dismissed)的不再出现在待推荐里 → 对话不重复打扰。
用户主动要求时调 reset() 把状态清回 suggested 即可重新推荐。
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.medication import Medication
from app.models.originator_recommendation import OriginatorRecommendation
from app.services.originator_drugs import _normalize, find_originator

logger = logging.getLogger(__name__)


def _status_map(db: Session, user_id: int) -> dict[str, str]:
    rows = db.query(OriginatorRecommendation).filter(
        OriginatorRecommendation.user_id == user_id
    ).all()
    return {r.generic_name: r.status for r in rows}


def pending_originator_recs(db: Session, user_id: int) -> list[dict[str, Any]]:
    """用户在用药里"有原研药且未采纳/未忽略"的建议列表(去重到通用名)。"""
    meds = db.query(Medication).filter(
        Medication.user_id == user_id, Medication.is_active == True  # noqa: E712
    ).all()
    statuses = _status_map(db, user_id)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in meds:
        orig = find_originator(m.name or "")
        if not orig:
            continue
        key = _normalize(orig["generic"])
        if key in seen:
            continue
        # 已采纳/忽略 → 抑制
        if statuses.get(key) in ("adopted", "dismissed"):
            continue
        seen.add(key)
        out.append({
            "med_name": m.name,
            "generic_name": orig["generic"],
            "generic_key": key,
            "brand": orig["brand"],
            "manufacturer": orig["manufacturer"],
        })
    return out


def originator_recs_prompt_blob(db: Session, user_id: int) -> str:
    """注入 agent 的紧凑文本。无待推荐 → 空串(不占 prompt)。"""
    recs = pending_originator_recs(db, user_id)
    if not recs:
        return ""
    lines = [f"- {r['med_name']}(通用名{r['generic_name']})→ 原研药「{r['brand']}」/{r['manufacturer']}" for r in recs]
    return (
        "【原研药可换建议(仅在与用药/换药相关时自然提及一次,勿强行插入;"
        "用户采纳或拒绝后本列表会自动移除,勿重复推荐)】\n" + "\n".join(lines)
    )


def set_status(
    db: Session, user_id: int, generic_key: str, status: str,
    *, brand: str | None = None, manufacturer: str | None = None, source: str = "chat",
) -> OriginatorRecommendation:
    """upsert 某药的推荐状态(suggested/adopted/dismissed)。"""
    rec = db.query(OriginatorRecommendation).filter(
        OriginatorRecommendation.user_id == user_id,
        OriginatorRecommendation.generic_name == generic_key,
    ).first()
    if rec is None:
        rec = OriginatorRecommendation(
            user_id=user_id, generic_name=generic_key, brand=brand,
            manufacturer=manufacturer, status=status, source=source,
        )
        db.add(rec)
    else:
        rec.status = status
        if brand:
            rec.brand = brand
        if manufacturer:
            rec.manufacturer = manufacturer
    db.commit()
    db.refresh(rec)
    return rec
