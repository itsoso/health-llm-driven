"""Idempotent record-or-confirm flow for user-owned chat food photos."""
from __future__ import annotations

import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.daily_health import DietPhotoAsset, DietPhotoDraft, DietRecord
from app.services.ai.food_recognition import sanitize_food_recognition_result
from app.services.contextual_meal_photo_policy import MealPhotoDecision
from app.services.diet_media_storage import (
    StoredDietPhoto,
    copy_owned_chat_image_to_diet,
    remove_diet_image_file,
)
from app.services.intake_intent_classifier import classify_intake_intent, looks_like_food_ui_text


PHOTO_DRAFT_TTL = timedelta(hours=24)
logger = logging.getLogger(__name__)


class ContextualMealPhotoServiceError(ValueError):
    """Known safe failure for an image capture that was not persisted."""


@dataclass(frozen=True)
class ContextualMealPhotoCapture:
    user_id: int
    source_message_id: int
    source_image_url: str
    source_image_index: int
    decision: MealPhotoDecision
    vision_result: dict[str, Any]


@dataclass(frozen=True)
class ContextualMealPhotoCaptureResult:
    decision: MealPhotoDecision
    record: DietRecord | None = None
    photo_draft: DietPhotoDraft | None = None
    photo_asset: DietPhotoAsset | None = None
    replayed: bool = False


class ContextualMealPhotoService:
    """Single persistence path for qualified chat-origin meal photos."""

    def __init__(self, db: Session):
        self.db = db

    def capture(
        self,
        capture: ContextualMealPhotoCapture,
    ) -> ContextualMealPhotoCaptureResult:
        decision = capture.decision
        if decision.decision == "analyze_only":
            raise ContextualMealPhotoServiceError("contextual_meal_photo_not_write_eligible")
        if decision.decision not in {"auto_record", "confirm"}:
            raise ContextualMealPhotoServiceError("contextual_meal_photo_decision_invalid")

        existing = self._existing_capture(capture)
        if existing is not None:
            return existing

        record_data, snapshot = self._record_payload(capture.vision_result, decision)
        stored: StoredDietPhoto | None = None
        try:
            try:
                stored = copy_owned_chat_image_to_diet(
                    capture.source_image_url,
                    capture.user_id,
                )
            except ValueError as exc:
                raise ContextualMealPhotoServiceError(str(exc)) from exc

            asset = DietPhotoAsset(
                id=uuid.uuid4().hex,
                user_id=capture.user_id,
                storage_key=stored.storage_key,
                content_sha256=stored.content_sha256,
                media_type=stored.media_type,
                origin="chat",
                origin_message_id=capture.source_message_id,
                ordinal=capture.source_image_index,
                captured_at=decision.local_time,
                captured_timezone=decision.timezone_name,
                classification="food",
                recognition_confidence=record_data["ai_confidence"],
                intent_decision=decision.decision,
                recognition_snapshot=snapshot,
                lifecycle="pending",
            )

            if decision.decision == "auto_record":
                record = DietRecord(
                    user_id=capture.user_id,
                    record_date=decision.local_time.date(),
                    meal_type=decision.meal_type,
                    meal_time=decision.local_time.timetz().replace(tzinfo=None),
                    food_name=record_data["food_items"][:100],
                    food_items=record_data["food_items"],
                    source="chat_photo",
                    calories=record_data.get("calories"),
                    protein=record_data.get("protein"),
                    carbs=record_data.get("carbs"),
                    fat=record_data.get("fat"),
                    fiber=record_data.get("fiber"),
                    image_url=stored.storage_key,
                    client_action_id=self._record_idempotency_key(capture),
                    ai_recognized=True,
                    ai_confidence=record_data["ai_confidence"],
                    ai_raw_result=json.dumps(snapshot, ensure_ascii=False),
                    health_tips=record_data.get("health_tips"),
                )
                asset.diet_record = record
                asset.lifecycle = "attached"
                asset.attached_at = datetime.now(timezone.utc)
                self.db.add_all([record, asset])
                self.db.commit()
                self.db.refresh(record)
                self.db.refresh(asset)
                self._create_postmeal_protocol(record)
                return ContextualMealPhotoCaptureResult(
                    decision=decision,
                    record=record,
                    photo_asset=asset,
                )

            draft = DietPhotoDraft(
                token=secrets.token_urlsafe(32),
                user_id=capture.user_id,
                image_url=stored.storage_key,
                image_type=_image_type_from_media_type(stored.media_type),
                recognition_result=record_data,
                status="pending",
                expires_at=datetime.now(timezone.utc) + PHOTO_DRAFT_TTL,
            )
            asset.photo_draft_token = draft.token
            self.db.add_all([draft, asset])
            self.db.commit()
            self.db.refresh(draft)
            self.db.refresh(asset)
            return ContextualMealPhotoCaptureResult(
                decision=decision,
                photo_draft=draft,
                photo_asset=asset,
            )
        except IntegrityError:
            self.db.rollback()
            if stored is not None:
                remove_diet_image_file(stored.file_path)
            existing = self._existing_capture(capture)
            if existing is not None:
                return existing
            raise
        except Exception:
            self.db.rollback()
            if stored is not None:
                remove_diet_image_file(stored.file_path)
            raise

    def _existing_capture(
        self,
        capture: ContextualMealPhotoCapture,
    ) -> ContextualMealPhotoCaptureResult | None:
        asset = (
            self.db.query(DietPhotoAsset)
            .filter(
                DietPhotoAsset.user_id == capture.user_id,
                DietPhotoAsset.origin_message_id == capture.source_message_id,
                DietPhotoAsset.ordinal == capture.source_image_index,
            )
            .first()
        )
        if asset is None:
            return None
        if asset.diet_record_id:
            record = (
                self.db.query(DietRecord)
                .filter(
                    DietRecord.id == asset.diet_record_id,
                    DietRecord.user_id == capture.user_id,
                )
                .first()
            )
            if record is not None:
                return ContextualMealPhotoCaptureResult(
                    decision=capture.decision,
                    record=record,
                    photo_asset=asset,
                    replayed=True,
                )
        if asset.photo_draft_token:
            draft = (
                self.db.query(DietPhotoDraft)
                .filter(
                    DietPhotoDraft.token == asset.photo_draft_token,
                    DietPhotoDraft.user_id == capture.user_id,
                )
                .first()
            )
            if draft is not None:
                return ContextualMealPhotoCaptureResult(
                    decision=capture.decision,
                    photo_draft=draft,
                    photo_asset=asset,
                    replayed=True,
                )
        raise ContextualMealPhotoServiceError("contextual_meal_photo_existing_asset_invalid")

    def _record_payload(
        self,
        raw_vision_result: dict[str, Any],
        decision: MealPhotoDecision,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        vision_result = sanitize_food_recognition_result(raw_vision_result)
        foods = vision_result.get("foods") if isinstance(vision_result.get("foods"), list) else []
        if not vision_result.get("success") or not foods:
            raise ContextualMealPhotoServiceError("contextual_meal_photo_no_food")

        normalized_foods: list[dict[str, Any]] = []
        labels: list[str] = []
        confidences: list[float] = []
        for food in foods:
            if not isinstance(food, dict):
                continue
            name = str(food.get("name") or "").strip()
            if not name:
                continue
            quantity = str(food.get("quantity") or "").strip()
            labels.append(" ".join(part for part in (name, quantity) if part))
            normalized_foods.append({
                key: food[key]
                for key in (
                    "name", "quantity", "quantity_grams", "calories", "protein",
                    "carbs", "fat", "fiber", "confidence", "food_id", "source",
                    "nutrition_basis", "portion_basis", "portion_confidence",
                )
                if food.get(key) is not None
            })
            confidence = food.get("confidence")
            if isinstance(confidence, (int, float)):
                confidences.append(float(confidence))
        food_items = " + ".join(labels)
        if not food_items or looks_like_food_ui_text(food_items):
            raise ContextualMealPhotoServiceError("contextual_meal_photo_food_items_invalid")
        if classify_intake_intent(food_items).kind in {"diet_management", "medication", "supplement"}:
            raise ContextualMealPhotoServiceError("contextual_meal_photo_food_items_invalid")

        confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.0
        snapshot = {
            "recognition_version": "contextual_meal_photo_v1",
            "foods": normalized_foods,
            "policy": {
                "decision": decision.decision,
                "reason_codes": list(decision.reason_codes),
                "timezone": decision.timezone_name,
                "local_time": decision.local_time.isoformat(),
            },
        }
        payload = {
            "record_date": decision.local_time.date().isoformat(),
            "meal_type": decision.meal_type,
            "food_items": food_items,
            "calories": vision_result.get("total_calories"),
            "protein": vision_result.get("total_protein"),
            "carbs": vision_result.get("total_carbs"),
            "fat": vision_result.get("total_fat"),
            "fiber": vision_result.get("total_fiber"),
            "ai_recognized": 1,
            "ai_confidence": confidence,
            "ai_raw_result": snapshot,
            "health_tips": vision_result.get("health_tips"),
        }
        return payload, snapshot

    def _create_postmeal_protocol(self, record: DietRecord) -> None:
        """Mirror normal diet-record execution without weakening its receipt.

        DietRecord persistence is already committed before this best-effort
        execution projection. This matches the regular diet API: a protocol
        failure is observable in logs but never turns a successful receipt into
        a false failure or retries the photo write.
        """
        try:
            from app.services import health_protocol_service as protocol_service

            protocol_service.create_postmeal_walk_protocol(
                self.db,
                record.user_id,
                record_date=record.record_date,
                meal_type=record.meal_type,
                meal_time=record.meal_time,
                diet_record_id=record.id,
            )
        except Exception as exc:  # noqa: BLE001
            self.db.rollback()
            logger.warning(
                "contextual meal photo postmeal protocol failed: user_id=%s diet_record_id=%s error=%s",
                record.user_id,
                record.id,
                exc,
            )

    @staticmethod
    def _record_idempotency_key(capture: ContextualMealPhotoCapture) -> str:
        return f"contextual-meal-photo:{capture.source_message_id}:{capture.source_image_index}"


def _image_type_from_media_type(media_type: str) -> str:
    value = str(media_type or "image/jpeg").split("/", 1)[-1].lower()
    return "jpeg" if value == "jpg" else value
