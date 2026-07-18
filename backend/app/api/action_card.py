"""
ActionCard API —— 对话固化到首页。

- GET    /action-cards/me              获取当前用户的活跃卡片
- POST   /action-cards                 创建卡片
- POST   /action-cards/from-message    从 AI 消息一键固化（自动提取标题）
- PATCH  /action-cards/{id}            更新状态/标题
- DELETE /action-cards/{id}            归档
"""

import logging
import re
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.action_card import ActionCard
from app.models.user import User
from app.services.outcome_safety import (
    clinician_review_grading_note,
    is_efficacy_score_eligible_card,
    user_facing_efficacy_fields,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/action-cards", tags=["action-cards"])


# ─────────────────────── Schemas ────────────────────────


ActionMetricKey = Literal["sleep_score", "hrv", "rhr", "weight", "bp", "spo2_odi", "custom"]

# 信任循环支持的化验项 metric_key (在 outcome_grader._fetch_metric 里实现)
LAB_METRIC_KEYS = {
    "alt", "ast", "ggt", "alp", "creatinine", "uric_acid", "urea",
    "hba1c", "tsh", "ft3", "ft4", "vitamin_d", "b12", "ferritin",
    "crp", "esr", "wbc", "rbc", "hgb", "plt", "lp_a", "apo_b",
    "ldl", "hdl", "tc", "tg", "fasting_glucose", "blood_glucose",
    "systolic_bp", "diastolic_bp", "bmi", "body_fat",
}
ALLOWED_METRIC_KEYS = {"sleep_score", "hrv", "rhr", "weight", "bp",
                       "spo2_odi", "custom",
                       "phenotypic_age", "biological_age",
                       "vo2max", "fitness_age"} | LAB_METRIC_KEYS


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _effective_expires_at(card: ActionCard) -> datetime | None:
    expires_at = _as_utc(card.expires_at)
    if expires_at is not None:
        return expires_at
    if card.source_type == "weekly_advisor" and card.created_at is not None:
        created_at = _as_utc(card.created_at)
        if created_at is not None:
            return created_at + timedelta(days=14)
    return None


def _archive_expired_cards(db: Session, *, user_id: int) -> int:
    now = datetime.now(timezone.utc)
    cards = (
        db.query(ActionCard)
        .filter(
            ActionCard.user_id == user_id,
            ActionCard.status == "active",
            ActionCard.is_visible == True,  # noqa: E712
        )
        .all()
    )
    archived = 0
    for card in cards:
        expires_at = _effective_expires_at(card)
        if expires_at is not None and expires_at <= now:
            card.status = "archived"
            card.is_visible = False
            card.updated_at = now
            archived += 1
    if archived:
        db.commit()
    return archived


class ChecklistItem(BaseModel):
    item: str = Field(..., min_length=1, max_length=200)
    done: bool = False


class ActionCardCreate(BaseModel):
    title: str = Field(..., max_length=200)
    content: str
    card_type: str = "note"
    color: Optional[str] = None
    source_type: str = "manual"
    source_id: Optional[str] = None
    priority: int = 0
    expires_at: Optional[datetime] = None
    metric_key: Optional[str] = Field(None, max_length=50)
    baseline_value: Optional[str] = Field(None, max_length=100)
    target_value: Optional[str] = Field(None, max_length=100)
    verification_days: Optional[int] = Field(None, ge=1, le=90)
    checklist: list[ChecklistItem] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    # Only explicit, user-confirmed creation flows set this. Keeping the default
    # false preserves draft/pending behavior for every existing caller.
    accepted: bool = False
    # 信任循环字段
    creator_specialist: Optional[str] = Field(None, max_length=64)
    check_back_date: Optional[datetime] = None

    @field_validator("metric_key")
    @classmethod
    def _validate_metric_key(cls, v):
        if v is not None and v not in ALLOWED_METRIC_KEYS:
            raise ValueError(f"未知 metric_key: {v}. 支持: {sorted(ALLOWED_METRIC_KEYS)}")
        return v

    @field_validator("evidence_refs")
    @classmethod
    def _validate_evidence_refs(cls, refs):
        out = []
        seen = set()
        for ref in refs or []:
            value = str(ref).strip()
            if not value.startswith("claim:") or value in seen:
                continue
            seen.add(value)
            out.append(value)
        return out


class ActionCardFromMessage(BaseModel):
    content: str = Field(..., description="AI 消息的完整内容（markdown）")
    source_id: Optional[str] = None
    card_type: str = "plan"
    creator_specialist: Optional[str] = Field(None, max_length=64,
        description="若由 specialist 触发, 标注 specialist 名 (recovery_coach 等)")


class ActionCardUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None  # active / completed / archived
    priority: Optional[int] = None
    is_visible: Optional[bool] = None
    color: Optional[str] = None


class LatestAssessmentInput(BaseModel):
    score: Optional[int] = Field(None, ge=0, le=10)
    summary: str = Field(..., max_length=1000)
    evidence: list[str] = Field(default_factory=list)


class ActionCardReview(BaseModel):
    status: Literal["active", "completed", "archived"] = "completed"
    outcome_status: Literal["met", "not_met", "inconclusive", "pending"]
    actual_value: Optional[str] = Field(None, max_length=100)
    latest_assessment: LatestAssessmentInput


# ─────────────────────── 工具 ────────────────────────


def _extract_title(content: str, max_len: int = 60) -> str:
    """从 markdown 内容自动提取标题。"""
    # 尝试取第一个 # 标题
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("#"):
            title = re.sub(r"^#+\s*", "", line).strip()
            if title:
                return title[:max_len]

    # 尝试取第一个加粗文本
    bold = re.search(r"\*\*(.+?)\*\*", content)
    if bold:
        return bold.group(1)[:max_len]

    # 取第一行非空文本
    for line in content.split("\n"):
        line = line.strip()
        if line and not line.startswith("```") and not line.startswith("---"):
            return line[:max_len]

    return "行动卡片"


def _accepted_create_key(*, user_id: int, body: ActionCardCreate) -> str:
    source_identity = body.source_id or datetime.now(UTC).date().isoformat()
    raw = "|".join(
        [
            str(user_id),
            body.source_type.strip().lower(),
            source_identity.strip(),
            body.title.strip(),
        ]
    )
    return sha256(raw.encode("utf-8")).hexdigest()


def _accepted_action_domain(title: str, content: str) -> str:
    text = f"{title} {content}".lower()
    try:
        from app.services.drug_lexicon import contains_medication_reference

        has_medication_reference = contains_medication_reference(text)
    except Exception as exc:
        logger.exception("Accepted action medication classifier unavailable")
        raise HTTPException(
            status_code=422,
            detail={"code": "advice_guard_contract_invalid", "message": "健康行动安全分类暂不可用"},
        ) from exc

    if has_medication_reference or any(marker in text for marker in ("用药", "服药", "服用", "停药", "停止服用", "不再服用", "换药", "剂量", "处方", "药物", "药品")):
        return "medication"
    if any(marker in text for marker in ("补剂", "补充剂", "维生素", "益生菌", "鱼油", "辅酶", "镁")):
        return "supplement"
    if any(marker in text for marker in ("睡眠", "入睡", "起床", "熬夜", "午睡")):
        return "sleep"
    if any(marker in text for marker in ("运动", "训练", "跑步", "散步", "步行", "拉伸", "太极", "八段锦")):
        return "movement"
    if any(marker in text for marker in ("饮食", "早餐", "午餐", "晚餐", "蛋白质", "热量", "血糖")):
        return "metabolic"
    return "recovery"


def _guard_accepted_action(
    db: Session,
    *,
    user_id: int,
    body: ActionCardCreate,
    accepted_key: str,
) -> None:
    from app.services.advice_guard import AdviceCandidate, AdviceGuardError, guard_and_record_advice

    domain = _accepted_action_domain(body.title, body.content)
    candidate = AdviceCandidate(
        user_id=user_id,
        source="action_card_explicit_accept",
        source_id=f"action-card:{accepted_key[:24]}",
        domain=domain,
        title=body.title,
        body=body.content,
        metric_key=body.metric_key,
        target_value=body.target_value or f"action:{sha256(body.title.encode('utf-8')).hexdigest()[:16]}",
        evidence_tier="knowledge_claim" if body.evidence_refs else "model_inference",
        confidence="medium",
        claim_boundary="这是健康管理行动建议，不替代医生诊断、处方或治疗。",
        evidence_refs=body.evidence_refs,
        verification_metric=body.metric_key or "self_report",
        verification_window_days=body.verification_days or 1,
        risk_level="high" if domain in {"medication", "supplement"} else "low",
        valid_for_date=datetime.now(UTC).date(),
    )
    try:
        decision = guard_and_record_advice(db, candidate)
    except AdviceGuardError as exc:
        logger.warning(
            "Accepted ActionCard contract rejected - user_id=%s source_type=%s reason=%s",
            user_id,
            body.source_type,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=422,
            detail={"code": "advice_guard_contract_invalid", "message": "这条行动缺少必要的安全信息，暂不能加入今天。"},
        ) from exc
    if not decision.allowed:
        logger.warning(
            "Accepted ActionCard blocked by AdviceGuard - user_id=%s source_type=%s reason=%s",
            user_id,
            body.source_type,
            decision.reason,
        )
        raise HTTPException(
            status_code=422,
            detail={"code": "advice_guard_blocked", "message": "这条行动涉及医疗安全边界，暂不能直接加入今天。"},
        )


# ─────────────────────── 端点 ────────────────────────


@router.get("/me")
def get_my_cards(
    status: str = Query("active", description="active / completed / archived / all"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """获取当前用户的行动卡片。"""
    if status in {"active", "all"}:
        _archive_expired_cards(db, user_id=current_user.id)

    q = db.query(ActionCard).filter(
        ActionCard.user_id == current_user.id,
        ActionCard.is_visible == True,  # noqa: E712
    )
    if status != "all":
        q = q.filter(ActionCard.status == status)
    cards = q.order_by(desc(ActionCard.priority), desc(ActionCard.created_at)).limit(limit).all()

    return [_card_to_dict(c) for c in cards]


@router.post("")
def create_card(
    body: ActionCardCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """手动创建卡片。"""
    # 复盘窗口和生命周期是两套语义。verification_days 只决定何时回看，
    # 不能把行动在同一时刻自动归档；只有调用方显式给 expires_at 才过期。
    expires_at = body.expires_at

    # 自动推算 check_back_date: 显式给 > verification_days > 默认 7 天 (有 metric_key 才设)
    check_back = body.check_back_date
    if check_back is None and body.metric_key:
        days = body.verification_days or 7
        check_back = datetime.now(UTC) + timedelta(days=days)

    accepted_key = _accepted_create_key(user_id=current_user.id, body=body) if body.accepted else None

    # Chat 的确认按钮可能因网络重试或连续点击重复提交。相同消息中的同名
    # accepted 行动视为同一次用户决定，直接回放已有资源。
    if accepted_key:
        existing = (
            db.query(ActionCard)
            .filter(
                ActionCard.user_id == current_user.id,
                ActionCard.accepted_create_key == accepted_key,
            )
            .order_by(desc(ActionCard.created_at))
            .first()
        )
        if existing is None and body.source_id:
            existing = (
                db.query(ActionCard)
                .filter(
                    ActionCard.user_id == current_user.id,
                    ActionCard.source_type == body.source_type,
                    ActionCard.source_id == body.source_id,
                    ActionCard.title == body.title,
                    ActionCard.user_decision.in_(["accepted", "adjusted"]),
                )
                .order_by(desc(ActionCard.created_at))
                .first()
            )
        if existing is not None:
            logger.info(
                "ActionCard accepted create replayed - user_id=%s source_type=%s source_id=%s card_id=%s",
                current_user.id,
                body.source_type,
                body.source_id,
                existing.id,
            )
            return _card_to_dict(existing)

        _guard_accepted_action(
            db,
            user_id=current_user.id,
            body=body,
            accepted_key=accepted_key,
        )

    decided_at = datetime.now(UTC) if body.accepted else None
    card = ActionCard(
        user_id=current_user.id,
        title=body.title,
        content=body.content,
        card_type=body.card_type,
        color=body.color,
        source_type=body.source_type,
        source_id=body.source_id,
        accepted_create_key=accepted_key,
        priority=body.priority,
        expires_at=expires_at,
        metric_key=body.metric_key,
        baseline_value=body.baseline_value,
        target_value=body.target_value,
        verification_days=body.verification_days,
        checklist=[item.model_dump() for item in body.checklist],
        evidence_refs=body.evidence_refs,
        creator_specialist=body.creator_specialist,
        check_back_date=check_back,
        user_decision="accepted" if body.accepted else None,
        decided_at=decided_at,
        decision_reason="explicit_create_confirmation" if body.accepted else None,
    )
    db.add(card)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if accepted_key:
            existing = (
                db.query(ActionCard)
                .filter(
                    ActionCard.user_id == current_user.id,
                    ActionCard.accepted_create_key == accepted_key,
                )
                .first()
            )
            if existing is not None:
                return _card_to_dict(existing)
        raise
    db.refresh(card)
    return _card_to_dict(card)


@router.post("/from-message")
def create_from_message(
    body: ActionCardFromMessage,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """
    从 AI 消息一键固化。自动提取标题。

    前端传 AI 回答的完整 markdown 内容，后端自动：
    1. 提取标题（第一个 # 标题 / 加粗文本 / 首行）
    2. **best-effort LLM 抽取信任循环字段** (metric_key / target_value / verification_days)
       — 抽到了卡片自动进 outcome_grader 队列, 抽不到退化为普通卡 (与历史行为一致).
    3. 创建卡片
    """
    title = _extract_title(body.content)

    # Trust loop: best-effort 抽取 metric_key / target / verification_days.
    # 抽取失败 (LLM 挂 / JSON 错 / 没指标) → 全 None, 卡片仍创建, 只是不进 grader.
    from app.services.action_card_extractor import extract_from_content
    extracted = extract_from_content(
        content=body.content, title=title, user_id=current_user.id
    )

    check_back = None
    if extracted.metric_key:
        days = extracted.verification_days or 7
        check_back = datetime.now(UTC) + timedelta(days=days)

    card = ActionCard(
        user_id=current_user.id,
        title=title,
        content=body.content,
        card_type=body.card_type,
        source_type="conversation",
        source_id=body.source_id,
        priority=10,  # 从对话固化的默认优先级高
        creator_specialist=body.creator_specialist,
        # Trust loop fields (None if 没抽到 — 行为与原版一致)
        metric_key=extracted.metric_key,
        baseline_value=extracted.baseline_value,
        target_value=extracted.target_value,
        verification_days=extracted.verification_days,
        check_back_date=check_back,
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    if extracted.metric_key:
        logger.info(
            f"[ActionCard] 用户 {current_user.id} 从对话固化 (信任循环): "
            f"{title!r} metric={extracted.metric_key} target={extracted.target_value} "
            f"check_back={check_back.date() if check_back else None}"
        )
    else:
        logger.info(f"[ActionCard] 用户 {current_user.id} 从对话固化: {title}")
    return _card_to_dict(card)


@router.get("/{card_id}")
def get_card(
    card_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """单卡详情 — mobile /card/[id] 用. 比走 list filter 可靠 (closed/verifying
    等所有 status 都能拿)."""
    card = db.query(ActionCard).filter(
        ActionCard.id == card_id,
        ActionCard.user_id == current_user.id,
    ).first()
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    return _card_to_dict(card)


@router.patch("/{card_id}")
def update_card(
    card_id: int,
    body: ActionCardUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """更新卡片状态/标题/优先级。"""
    card = db.query(ActionCard).filter(
        ActionCard.id == card_id,
        ActionCard.user_id == current_user.id,
    ).first()
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")

    if body.title is not None:
        card.title = body.title
    if body.status is not None:
        card.status = body.status
        if body.status == "completed":
            card.completed_at = datetime.now(UTC)
        elif body.status == "active":
            # P8 (2026-05-04): 撤销完成 — 用户点"已完成" 后悔了, status 改回 active
            # 必须清 completed_at, 否则 grader / outcome view 仍把它当 completed
            card.completed_at = None
    if body.priority is not None:
        card.priority = body.priority
    if body.is_visible is not None:
        card.is_visible = body.is_visible
    if body.color is not None:
        card.color = body.color

    db.commit()
    db.refresh(card)
    return _card_to_dict(card)


class ActionCardAdherence(BaseModel):
    """用户/系统设置这张卡的执行依从度."""
    kind: Literal["self_reported", "device", "proxy"] = "self_reported"
    confidence: int = Field(..., ge=0, le=100, description="0-100, 0=完全没做, 100=完全做到")


@router.post("/{card_id}/adherence")
def set_card_adherence(
    card_id: int,
    body: ActionCardAdherence,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """标注执行依从度. outcome_grader 评分时会 accuracy × adherence_confidence.

    kind:
      - self_reported: 用户自报 (confidence 上限通常应 ≤ 70)
      - device: 设备数据证实 (Garmin 步数/HR/sleep_time 等)
      - proxy: 间接信号 (早餐打卡频率 / 用药 log 等)
    """
    card = db.query(ActionCard).filter(
        ActionCard.id == card_id,
        ActionCard.user_id == current_user.id,
    ).first()
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")

    # self_reported 信号置信度软上限 70 — 防止用户一律勾 100
    if body.kind == "self_reported" and body.confidence > 70:
        body_confidence = 70
    else:
        body_confidence = body.confidence

    card.adherence_kind = body.kind
    card.adherence_confidence = body_confidence
    db.commit()
    db.refresh(card)
    logger.info(
        f"[ActionCard] 用户 {current_user.id} 标注依从度: card_id={card_id}, "
        f"kind={body.kind}, confidence={body_confidence}"
    )
    return _card_to_dict(card)


@router.post("/{card_id}/review")
def review_card(
    card_id: int,
    body: ActionCardReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """写入行动卡片复盘结果。"""
    card = db.query(ActionCard).filter(
        ActionCard.id == card_id,
        ActionCard.user_id == current_user.id,
    ).first()
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")

    card.status = body.status
    if body.status == "completed":
        card.completed_at = datetime.now(UTC)
    card.latest_assessment = {
        **body.latest_assessment.model_dump(),
        "outcome_status": body.outcome_status,
        "actual_value": body.actual_value,
    }
    card.last_assessed_at = datetime.now(UTC)
    card.assessment_count = (card.assessment_count or 0) + 1

    db.commit()
    db.refresh(card)
    logger.info(f"[ActionCard] 用户 {current_user.id} 复盘行动卡片: card_id={card_id}, outcome={body.outcome_status}")
    return _card_to_dict(card)


@router.delete("/{card_id}")
def archive_card(
    card_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """归档卡片（软删除）。"""
    card = db.query(ActionCard).filter(
        ActionCard.id == card_id,
        ActionCard.user_id == current_user.id,
    ).first()
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    card.status = "archived"
    card.is_visible = False
    db.commit()
    return {"message": "已归档", "id": card_id}


# ─────────────────────── WSCLA 生命周期 (Phase 1) ────────────────────────

_VALID_DECISIONS = {"accepted", "adjusted", "declined", "dismissed", "false_positive"}


class CardDecisionBody(BaseModel):
    decision: str
    reason: Optional[str] = None
    adjusted_payload: Optional[Dict[str, Any]] = None


@router.post("/{card_id}/decision")
def record_card_decision(
    card_id: int,
    body: CardDecisionBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """用户对卡片做决策 — accepted / adjusted / declined / dismissed / false_positive.

    幂等: 同 decision 重复调用只更新 reason, 不刷新 decided_at;
          换 decision 会更新 decided_at + decision_reason.
    """
    if body.decision not in _VALID_DECISIONS:
        raise HTTPException(
            status_code=400,
            detail=f"decision 必须是 {sorted(_VALID_DECISIONS)} 之一",
        )

    card = db.query(ActionCard).filter(
        ActionCard.id == card_id,
        ActionCard.user_id == current_user.id,
    ).first()
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")

    now = datetime.now(timezone.utc)

    if card.user_decision != body.decision:
        card.user_decision = body.decision
        card.decided_at = now
    card.decision_reason = body.reason

    # declined / dismissed / false_positive → status='archived' + is_visible=False (从首页消失但留库)
    if body.decision in {"declined", "dismissed", "false_positive"}:
        card.status = "archived"
        card.is_visible = False

    # adjusted 时把用户调整后的 payload 保留进 latest_assessment 便于后续 review
    if body.decision == "adjusted" and body.adjusted_payload:
        meta = dict(card.latest_assessment or {})
        meta["adjusted_payload"] = body.adjusted_payload
        meta["adjusted_at"] = now.isoformat()
        card.latest_assessment = meta

    db.commit()
    db.refresh(card)
    logger.info(
        f"[ActionCard] user={current_user.id} card={card_id} decision={body.decision}"
    )
    return _card_to_dict(card)


@router.post("/{card_id}/click")
def record_card_push_click(
    card_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """通知点击回写 — 客户端打开 health://card/{id} 深链时调.

    幂等: 已 stamp 过 push_clicked_at 不再覆盖. seen_at 同时盖 (用户打开了卡片).
    """
    card = db.query(ActionCard).filter(
        ActionCard.id == card_id,
        ActionCard.user_id == current_user.id,
    ).first()
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")

    now = datetime.now(timezone.utc)
    changed = False
    if card.push_clicked_at is None:
        card.push_clicked_at = now
        changed = True
    if card.seen_at is None:
        card.seen_at = now
        changed = True
    if changed:
        db.commit()
    return {
        "id": card_id,
        "push_clicked_at": card.push_clicked_at.isoformat() if card.push_clicked_at else None,
    }


# ─────────────────────── 序列化 ────────────────────────


def _card_to_dict(card: ActionCard) -> dict:
    efficacy_score_eligible = is_efficacy_score_eligible_card(card)
    efficacy_fields = user_facing_efficacy_fields(card)
    return {
        "id": card.id,
        "title": card.title,
        "content": card.content,
        "card_type": card.card_type,
        "color": card.color,
        "source_type": card.source_type,
        "source_id": card.source_id,
        "status": card.status,
        "priority": card.priority,
        "expires_at": card.expires_at.isoformat() if card.expires_at else None,
        "completed_at": card.completed_at.isoformat() if card.completed_at else None,
        "created_at": card.created_at.isoformat() if card.created_at else None,
        "checklist": card.checklist or [],
        "latest_assessment": card.latest_assessment,
        "metric_key": card.metric_key,
        "baseline_value": card.baseline_value,
        "target_value": card.target_value,
        "verification_days": card.verification_days,
        "creator_specialist": card.creator_specialist,
        "check_back_date": card.check_back_date.isoformat() if card.check_back_date else None,
        "actual_value": card.actual_value,
        **efficacy_fields,
        "graded_at": card.graded_at.isoformat() if card.graded_at else None,
        "grading_notes": (
            card.grading_notes
            if efficacy_score_eligible
            else clinician_review_grading_note(card.metric_key)
        ),
        "adherence_kind": card.adherence_kind,
        "adherence_confidence": card.adherence_confidence,
        # WSCLA 生命周期 (Phase 0/1)
        "severity": card.severity,
        "evidence_level": card.evidence_level,
        "evidence_refs": card.evidence_refs or [],
        "user_decision": card.user_decision,
        "decided_at": card.decided_at.isoformat() if card.decided_at else None,
        "decision_reason": card.decision_reason,
        "seen_at": card.seen_at.isoformat() if card.seen_at else None,
        "push_sent_at": card.push_sent_at.isoformat() if card.push_sent_at else None,
        "push_delivered_at": card.push_delivered_at.isoformat() if card.push_delivered_at else None,
        "push_clicked_at": card.push_clicked_at.isoformat() if card.push_clicked_at else None,
    }


# ─────────────────────── G-W5 用户进度看板 ────────────────────────


@router.get("/me/progress", summary="我的执行监测进度 (用户视角 WSCLA)")
def get_my_progress(
    days: int = Query(30, ge=7, le=180, description="时间窗口天数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """用户视角的执行监测看板 — Mobile /my-progress 用.

    返回:
      window: {since, until, days}
      stats:
        - total_surfaced: 窗口内 AI 给出的建议总数
        - accepted: 用户接受数
        - declined: 用户拒绝数
        - pending: 还没决策数
        - completed: accepted 且执行完成 (completed_at)
        - graded: 已自动评估 (graded_at)
        - improved / unchanged / worsened / inconclusive: outcome 分布
        - acceptance_rate / verification_rate / improvement_rate
      closed_cards: [近 N 条已闭环的卡, 带 metric 旅程]
      verifying_cards: [accepted 但未 graded 的卡, 显示等待中的 metric]
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    base = db.query(ActionCard).filter(
        ActionCard.user_id == current_user.id,
        ActionCard.created_at >= cutoff,
    )

    total_surfaced = base.count()
    accepted = base.filter(ActionCard.user_decision == "accepted").count()
    declined = base.filter(
        ActionCard.user_decision.in_(["declined", "dismissed", "false_positive"])
    ).count()
    pending = base.filter(ActionCard.user_decision.is_(None)).count()
    completed = base.filter(
        ActionCard.user_decision == "accepted",
        ActionCard.completed_at.isnot(None),
    ).count()
    graded = base.filter(ActionCard.graded_at.isnot(None)).count()
    improved = base.filter(ActionCard.outcome == "improved").count()
    unchanged = base.filter(ActionCard.outcome == "unchanged").count()
    worsened = base.filter(ActionCard.outcome == "worsened").count()
    inconclusive = base.filter(ActionCard.outcome == "inconclusive").count()

    decided = accepted + declined
    accept_rate = round(accepted / decided, 4) if decided > 0 else None
    verify_rate = round(graded / completed, 4) if completed > 0 else None
    safe_closed = improved + unchanged
    improvement_rate = round(improved / graded, 4) if graded > 0 else None

    # 已闭环列表 (按 graded_at 倒序)
    closed = (
        base.filter(ActionCard.graded_at.isnot(None))
        .order_by(desc(ActionCard.graded_at))
        .limit(20)
        .all()
    )
    closed_dicts = [_card_to_dict(c) for c in closed]

    # 验证中: accepted, completed_at 已写, graded_at 未写
    verifying = (
        base.filter(
            ActionCard.user_decision == "accepted",
            ActionCard.completed_at.isnot(None),
            ActionCard.graded_at.is_(None),
        )
        .order_by(desc(ActionCard.completed_at))
        .limit(10)
        .all()
    )
    verifying_dicts = [_card_to_dict(c) for c in verifying]

    return {
        "window": {
            "since": cutoff.isoformat(),
            "until": datetime.now(timezone.utc).isoformat(),
            "days": days,
        },
        "stats": {
            "total_surfaced": total_surfaced,
            "accepted": accepted,
            "declined": declined,
            "pending": pending,
            "completed": completed,
            "graded": graded,
            "improved": improved,
            "unchanged": unchanged,
            "worsened": worsened,
            "inconclusive": inconclusive,
            "safe_closed": safe_closed,
            "acceptance_rate": accept_rate,
            "verification_rate": verify_rate,
            "improvement_rate": improvement_rate,
        },
        "closed_cards": closed_dicts,
        "verifying_cards": verifying_dicts,
    }
