"""补剂审计服务层 — 最小 CRUD + 状态机"""
import logging
from datetime import UTC, datetime
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import case, func
from sqlalchemy.orm import Session, selectinload

from app.models.supplement_audit import SupplementAudit, SupplementAuditItem
from app.schemas.supplement_audit import (
    SupplementAuditCreate,
    SupplementAuditItemUpdate,
)

logger = logging.getLogger(__name__)

VALID_ITEM_STATUS = {"pending", "accepted", "rejected", "completed", "superseded"}
VALID_ACTION_TYPES = {"keep", "add", "upgrade", "remove", "monitor", "warning"}


class SupplementAuditService:

    def list_audits(self, db: Session, user_id: int, limit: int = 20) -> List[dict]:
        """返回用户的审计列表（含 items 统计）"""
        audits = (
            db.query(SupplementAudit)
            .filter(SupplementAudit.user_id == user_id)
            .order_by(SupplementAudit.version.desc())
            .limit(limit)
            .all()
        )

        # 一次查出 items 统计，避免 N+1
        if not audits:
            return []
        audit_ids = [a.id for a in audits]
        stats_rows = (
            db.query(
                SupplementAuditItem.audit_id,
                func.count().label("items_count"),
                func.sum(
                    case((SupplementAuditItem.status == "pending", 1), else_=0)
                ).label("pending_count"),
            )
            .filter(SupplementAuditItem.audit_id.in_(audit_ids))
            .group_by(SupplementAuditItem.audit_id)
            .all()
        )
        stats_map = {row.audit_id: (row.items_count, row.pending_count or 0) for row in stats_rows}

        result = []
        for a in audits:
            items_count, pending_count = stats_map.get(a.id, (0, 0))
            result.append({
                "id": a.id,
                "user_id": a.user_id,
                "version": a.version,
                "title": a.title,
                "status": a.status,
                "triggered_by": a.triggered_by,
                "summary": a.summary,
                "data_period_start": a.data_period_start,
                "data_period_end": a.data_period_end,
                "next_review_at": a.next_review_at,
                "created_at": a.created_at,
                "items_count": items_count,
                "pending_count": pending_count,
            })
        return result

    def get_active_audit(self, db: Session, user_id: int) -> Optional[SupplementAudit]:
        return (
            db.query(SupplementAudit)
            .options(selectinload(SupplementAudit.items))
            .filter(SupplementAudit.user_id == user_id, SupplementAudit.status == "active")
            .order_by(SupplementAudit.version.desc())
            .first()
        )

    def get_audit_by_id(self, db: Session, user_id: int, audit_id: int) -> SupplementAudit:
        audit = (
            db.query(SupplementAudit)
            .options(selectinload(SupplementAudit.items))
            .filter(SupplementAudit.id == audit_id, SupplementAudit.user_id == user_id)
            .first()
        )
        if not audit:
            raise HTTPException(status_code=404, detail="审计不存在")
        return audit

    def create_audit(self, db: Session, user_id: int, payload: SupplementAuditCreate) -> SupplementAudit:
        # 下一个 version
        max_version = (
            db.query(func.max(SupplementAudit.version))
            .filter(SupplementAudit.user_id == user_id)
            .scalar()
        ) or 0
        next_version = max_version + 1

        # 把旧 active 置为 superseded
        db.query(SupplementAudit).filter(
            SupplementAudit.user_id == user_id, SupplementAudit.status == "active"
        ).update({"status": "superseded", "updated_at": datetime.now(UTC)})

        audit = SupplementAudit(
            user_id=user_id,
            version=next_version,
            triggered_by=payload.triggered_by,
            parent_audit_id=payload.parent_audit_id,
            data_period_start=payload.data_period_start,
            data_period_end=payload.data_period_end,
            title=payload.title,
            input_snapshot=payload.input_snapshot or {},
            rationale_markdown=payload.rationale_markdown,
            summary=payload.summary,
            status="active",
            next_review_at=payload.next_review_at,
            generated_by=payload.generated_by,
            llm_model=payload.llm_model,
        )
        db.add(audit)
        db.flush()

        for item_payload in payload.items:
            if item_payload.action_type not in VALID_ACTION_TYPES:
                raise HTTPException(status_code=400, detail=f"非法 action_type: {item_payload.action_type}")
            db.add(SupplementAuditItem(
                audit_id=audit.id,
                user_id=user_id,
                action_type=item_payload.action_type,
                priority=item_payload.priority,
                title=item_payload.title,
                product_id=item_payload.product_id,
                supplement_definition_id=item_payload.supplement_definition_id,
                target_metric=item_payload.target_metric,
                rationale_markdown=item_payload.rationale_markdown,
                evidence_refs=item_payload.evidence_refs or [],
                warnings=item_payload.warnings or [],
                status="pending",
            ))

        db.commit()
        db.refresh(audit)
        logger.info(f"[审计] 创建成功 user={user_id} audit_id={audit.id} v={audit.version}")
        return audit

    def update_item(
        self,
        db: Session,
        user_id: int,
        item_id: int,
        payload: SupplementAuditItemUpdate,
    ) -> SupplementAuditItem:
        item = (
            db.query(SupplementAuditItem)
            .filter(SupplementAuditItem.id == item_id, SupplementAuditItem.user_id == user_id)
            .first()
        )
        if not item:
            raise HTTPException(status_code=404, detail="审计建议不存在")

        if payload.status is not None:
            if payload.status not in VALID_ITEM_STATUS:
                raise HTTPException(status_code=400, detail=f"非法 status: {payload.status}")
            item.status = payload.status
            now = datetime.now(UTC)
            if payload.status == "accepted":
                item.accepted_at = now
            elif payload.status == "completed":
                item.completed_at = now
                if not item.accepted_at:
                    item.accepted_at = now
            elif payload.status == "rejected":
                item.rejected_reason = payload.rejected_reason

        if payload.user_note is not None:
            item.user_note = payload.user_note

        item.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(item)
        return item


supplement_audit_service = SupplementAuditService()
