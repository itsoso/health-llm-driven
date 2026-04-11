"""健康咨询服务层

核心能力:
- create_consultation: 批量创建一次咨询 + 所有 items (供 ClaudeCode 或 LLM 直接调用)
- list / get / update_item: 基础 CRUD
- verify_predictions: 自动对比 garmin_data / medical_indicators 验证 predictions (回测引擎)
"""
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import case, func
from sqlalchemy.orm import Session, selectinload

from app.models.daily_health import GarminData
from app.models.family_health import MedicalIndicator
from app.models.health_consultation import ConsultationItem, HealthConsultation
from app.schemas.health_consultation import (
    ConsultationItemUpdate,
    HealthConsultationCreate,
)

logger = logging.getLogger(__name__)

VALID_ITEM_TYPES = {"hypothesis", "action", "prediction", "red_flag", "note"}

# 不同 item_type 允许的 status 集合
ALLOWED_STATUS_BY_TYPE = {
    "hypothesis": {"pending", "confirmed", "refuted", "inconclusive"},
    "action": {"pending", "in_progress", "completed", "skipped", "deferred"},
    "prediction": {"pending", "met", "not_met", "partial", "inconclusive"},
    "red_flag": {"watching", "triggered", "resolved"},
    "note": {"pending", "resolved"},
}


class HealthConsultationService:

    # ---------- list / get ----------

    def list_consultations(self, db: Session, user_id: int, limit: int = 20) -> List[dict]:
        consults = (
            db.query(HealthConsultation)
            .filter(HealthConsultation.user_id == user_id)
            .order_by(HealthConsultation.version.desc())
            .limit(limit)
            .all()
        )
        if not consults:
            return []

        consult_ids = [c.id for c in consults]
        stats_rows = (
            db.query(
                ConsultationItem.consultation_id,
                func.count().label("total"),
                func.sum(case((ConsultationItem.item_type == "hypothesis", 1), else_=0)).label("hypo"),
                func.sum(case((ConsultationItem.item_type == "action", 1), else_=0)).label("action"),
                func.sum(case((ConsultationItem.item_type == "prediction", 1), else_=0)).label("pred"),
                func.sum(case((ConsultationItem.item_type == "red_flag", 1), else_=0)).label("red"),
                func.sum(case((ConsultationItem.status == "pending", 1), else_=0)).label("pending"),
            )
            .filter(ConsultationItem.consultation_id.in_(consult_ids))
            .group_by(ConsultationItem.consultation_id)
            .all()
        )
        stats_map = {
            row.consultation_id: {
                "total_items": row.total or 0,
                "hypothesis_count": row.hypo or 0,
                "action_count": row.action or 0,
                "prediction_count": row.pred or 0,
                "red_flag_count": row.red or 0,
                "pending_count": row.pending or 0,
            }
            for row in stats_rows
        }

        result = []
        for c in consults:
            s = stats_map.get(c.id, {})
            result.append({
                "id": c.id,
                "user_id": c.user_id,
                "version": c.version,
                "title": c.title,
                "topic": c.topic,
                "consultation_type": c.consultation_type,
                "triggered_by": c.triggered_by,
                "status": c.status,
                "summary": c.summary,
                "verification_scheduled_at": c.verification_scheduled_at,
                "created_at": c.created_at,
                **s,
            })
        return result

    def get_active(self, db: Session, user_id: int) -> Optional[HealthConsultation]:
        return (
            db.query(HealthConsultation)
            .options(selectinload(HealthConsultation.items))
            .filter(HealthConsultation.user_id == user_id, HealthConsultation.status == "active")
            .order_by(HealthConsultation.version.desc())
            .first()
        )

    def get_by_id(self, db: Session, user_id: int, consultation_id: int) -> HealthConsultation:
        c = (
            db.query(HealthConsultation)
            .options(selectinload(HealthConsultation.items))
            .filter(HealthConsultation.id == consultation_id, HealthConsultation.user_id == user_id)
            .first()
        )
        if not c:
            raise HTTPException(status_code=404, detail="咨询不存在")
        return c

    # ---------- create ----------

    def create(self, db: Session, user_id: int, payload: HealthConsultationCreate) -> HealthConsultation:
        max_version = (
            db.query(func.max(HealthConsultation.version))
            .filter(HealthConsultation.user_id == user_id)
            .scalar()
        ) or 0
        next_version = max_version + 1

        c = HealthConsultation(
            user_id=user_id,
            version=next_version,
            parent_consultation_id=payload.parent_consultation_id,
            title=payload.title,
            topic=payload.topic,
            consultation_type=payload.consultation_type,
            triggered_by=payload.triggered_by,
            chief_complaint=payload.chief_complaint,
            input_snapshot=payload.input_snapshot or {},
            rationale_markdown=payload.rationale_markdown,
            summary=payload.summary,
            status="active",
            verification_scheduled_at=payload.verification_scheduled_at,
            generated_by=payload.generated_by,
            llm_model=payload.llm_model,
        )
        db.add(c)
        db.flush()

        for item_payload in payload.items:
            if item_payload.item_type not in VALID_ITEM_TYPES:
                raise HTTPException(status_code=400, detail=f"非法 item_type: {item_payload.item_type}")
            default_status = "watching" if item_payload.item_type == "red_flag" else "pending"
            db.add(ConsultationItem(
                consultation_id=c.id,
                user_id=user_id,
                item_type=item_payload.item_type,
                item_code=item_payload.item_code,
                priority=item_payload.priority,
                title=item_payload.title,
                content_markdown=item_payload.content_markdown,
                meta=item_payload.meta or {},
                due_date=item_payload.due_date,
                status=default_status,
            ))

        db.commit()
        db.refresh(c)
        logger.info(f"[咨询] 创建成功 user={user_id} id={c.id} v={c.version} items={len(payload.items)}")
        return c

    # ---------- update item ----------

    def update_item(
        self,
        db: Session,
        user_id: int,
        item_id: int,
        payload: ConsultationItemUpdate,
    ) -> ConsultationItem:
        item = (
            db.query(ConsultationItem)
            .filter(ConsultationItem.id == item_id, ConsultationItem.user_id == user_id)
            .first()
        )
        if not item:
            raise HTTPException(status_code=404, detail="咨询条目不存在")

        if payload.status is not None:
            allowed = ALLOWED_STATUS_BY_TYPE.get(item.item_type, set())
            if payload.status not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=f"item_type={item.item_type} 不允许 status={payload.status}, 允许: {sorted(allowed)}"
                )
            item.status = payload.status
            now = datetime.now(UTC)
            if payload.status in ("completed", "confirmed", "met", "not_met", "triggered", "resolved", "refuted"):
                item.verified_at = now
            if payload.status == "completed":
                item.completed_at = now

        if payload.user_note is not None:
            item.user_note = payload.user_note
        if payload.outcome is not None:
            item.outcome = payload.outcome
        if payload.actual_value is not None:
            item.actual_value = payload.actual_value
        if payload.meta_patch:
            merged = dict(item.meta or {})
            merged.update(payload.meta_patch)
            item.meta = merged

        item.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(item)
        return item

    # ---------- verification engine ----------

    def verify_predictions(self, db: Session, user_id: int, consultation_id: int) -> List[Dict[str, Any]]:
        """自动回测所有 pending predictions - 对比 garmin_data / medical_indicators 的实际值

        返回每条 prediction 的验证结果(不自动写库, 让前端/用户确认)
        """
        consult = self.get_by_id(db, user_id, consultation_id)
        results = []

        for item in consult.items:
            if item.item_type != "prediction" or item.status != "pending":
                continue

            meta = item.meta or {}
            data_source = meta.get("data_source", "")
            metric_name = meta.get("metric_name") or meta.get("metric")
            target = meta.get("target", "")
            check_after_days = meta.get("check_after_days", 28)

            consultation_start = consult.created_at.date() if consult.created_at else date.today()
            check_since = consultation_start + timedelta(days=max(1, check_after_days - 7))

            actual = None
            note = ""

            # 1. Garmin 数据源
            if data_source.startswith("garmin_data."):
                field = data_source.split(".", 1)[1]
                if hasattr(GarminData, field):
                    col = getattr(GarminData, field)
                    avg_val = (
                        db.query(func.avg(col))
                        .filter(
                            GarminData.user_id == user_id,
                            GarminData.record_date >= check_since,
                            col.isnot(None),
                        )
                        .scalar()
                    )
                    if avg_val is not None:
                        actual = round(float(avg_val), 2)
                        note = f"garmin_data.{field} 从 {check_since} 起均值"

            # 2. 医学指标数据源
            elif data_source.startswith("medical_indicator."):
                ind_name = data_source.split(".", 1)[1]
                latest = (
                    db.query(MedicalIndicator)
                    .filter(
                        MedicalIndicator.user_id == user_id,
                        MedicalIndicator.name == ind_name,
                        MedicalIndicator.record_date >= check_since,
                    )
                    .order_by(MedicalIndicator.record_date.desc())
                    .first()
                )
                if latest:
                    actual = latest.value
                    note = f"medical_indicator.{ind_name} 最近值 ({latest.record_date})"

            results.append({
                "item_id": item.id,
                "item_code": item.item_code,
                "title": item.title,
                "metric_name": metric_name,
                "target": target,
                "baseline": meta.get("baseline"),
                "actual_value": actual,
                "note": note,
                "suggested_status": self._suggest_status(actual, target, meta.get("baseline")),
                "data_source": data_source,
            })

        return results

    @staticmethod
    def _suggest_status(actual: Any, target: str, baseline: Any) -> str:
        """轻量的 target 评估. 不强求, 让用户/LLM 做最终判断."""
        if actual is None or actual == "":
            return "pending"  # 无数据
        try:
            actual_f = float(actual)
            t = str(target).strip()
            # 支持 ">=90", ">50", "<30", "[50, 80]" 等简单格式
            if t.startswith(">="):
                return "met" if actual_f >= float(t[2:]) else "not_met"
            if t.startswith("<="):
                return "met" if actual_f <= float(t[2:]) else "not_met"
            if t.startswith(">"):
                return "met" if actual_f > float(t[1:]) else "not_met"
            if t.startswith("<"):
                return "met" if actual_f < float(t[1:]) else "not_met"
        except (ValueError, TypeError):
            pass
        return "inconclusive"


health_consultation_service = HealthConsultationService()
