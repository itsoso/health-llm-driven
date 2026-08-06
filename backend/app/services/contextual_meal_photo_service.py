"""Idempotent record-or-confirm flow for user-owned chat food photos."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import secrets
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from sqlalchemy import text
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
    classification: str = "food"


@dataclass(frozen=True)
class ContextualMealPhotoCaptureResult:
    decision: MealPhotoDecision
    record: DietRecord | None = None
    photo_draft: DietPhotoDraft | None = None
    photo_asset: DietPhotoAsset | None = None
    photo_assets: tuple[DietPhotoAsset, ...] = ()
    replayed: bool = False
    # Automatic capture is allowed to degrade to the same owner-bound manual
    # confirmation protocol.  This retains the analyzed photo and gives every
    # client a real recovery action instead of silently losing the meal.
    fallback_from_auto: bool = False


class ContextualMealPhotoService:
    """Single persistence path for qualified chat-origin meal photos."""

    _SQLITE_LOCK_STRIPES = tuple(threading.RLock() for _ in range(128))

    def __init__(self, db: Session):
        self.db = db

    def capture(
        self,
        capture: ContextualMealPhotoCapture,
    ) -> ContextualMealPhotoCaptureResult:
        """Compatibility entry point for a one-photo capture session."""
        return self.capture_session([capture])

    def capture_session(
        self,
        captures: list[ContextualMealPhotoCapture],
        *,
        _conflict_retried: bool = False,
    ) -> ContextualMealPhotoCaptureResult:
        normalized = self._validate_session(captures)
        first_capture = normalized[0]
        with self._capture_session_lock(
            first_capture.user_id,
            first_capture.source_message_id,
        ):
            return self._capture_session_locked(
                normalized,
                _conflict_retried=_conflict_retried,
            )

    def _capture_session_locked(
        self,
        captures: list[ContextualMealPhotoCapture],
        *,
        _conflict_retried: bool = False,
    ) -> ContextualMealPhotoCaptureResult:
        """Persist one user-message worth of meal photos as one transaction.

        ``source_message_id`` is the business idempotency boundary. Photo
        ordinals identify media inside that session; they never create another
        diet record or confirmation draft.
        """
        normalized = self._validate_session(captures)
        first_capture = normalized[0]
        decision = first_capture.decision
        logger.info(
            "meal_capture_session_started user_id=%s source_message_id=%s "
            "image_count=%s decision=%s",
            first_capture.user_id,
            first_capture.source_message_id,
            len(normalized),
            decision.decision,
        )
        if decision.decision == "analyze_only":
            raise ContextualMealPhotoServiceError("contextual_meal_photo_not_write_eligible")
        if decision.decision not in {"auto_record", "confirm"}:
            raise ContextualMealPhotoServiceError("contextual_meal_photo_decision_invalid")

        exact_assets = self._existing_assets_by_ordinal(first_capture)
        existing = self._existing_session(first_capture)
        missing = [
            capture
            for capture in normalized
            if capture.source_image_index not in exact_assets
        ]
        if existing is not None and not missing:
            self._log_result("replayed", first_capture, existing)
            return self._with_replayed(existing)

        record_data, snapshot = self._record_payload(
            first_capture.vision_result,
            decision,
        )
        stored_items: list[tuple[ContextualMealPhotoCapture, StoredDietPhoto]] = []
        try:
            try:
                stored_items = self._copy_unique_session_media(
                    missing if existing is not None else normalized,
                    existing=existing,
                )
            except ValueError as exc:
                raise ContextualMealPhotoServiceError(str(exc)) from exc

            if existing is not None:
                if not stored_items:
                    self._log_result("replayed", first_capture, existing)
                    return self._with_replayed(existing)
                return self._attach_session_media(
                    existing,
                    stored_items,
                    record_data,
                    snapshot,
                    provided_ordinals={
                        capture.source_image_index for capture in normalized
                    },
                )

            if not stored_items:
                raise ContextualMealPhotoServiceError(
                    "contextual_meal_photo_no_unique_media",
                )

            if decision.decision == "auto_record":
                try:
                    return self._persist_auto_record(
                        first_capture,
                        decision,
                        record_data,
                        snapshot,
                        stored_items,
                    )
                except Exception as auto_error:  # noqa: BLE001 - recovery is part of this write protocol
                    self.db.rollback()
                    self._acquire_postgres_session_lock(
                        first_capture.user_id,
                        first_capture.source_message_id,
                    )
                    winner = self._existing_session(first_capture)
                    if winner is not None and self._result_references_all_stored(
                        winner,
                        stored_items,
                    ):
                        if winner.record is not None:
                            self._create_postmeal_protocol(winner.record)
                        return self._with_replayed(winner)
                    if winner is not None:
                        return self._attach_session_media(
                            winner,
                            stored_items,
                            record_data,
                            snapshot,
                            provided_ordinals={
                                capture.source_image_index for capture in normalized
                            },
                        )
                    logger.warning(
                        "contextual meal photo auto-record failed; preserving confirmation draft: "
                        "user_id=%s source_message_id=%s error=%s",
                        first_capture.user_id,
                        first_capture.source_message_id,
                        type(auto_error).__name__,
                    )
                    try:
                        return self._persist_confirmation_draft(
                            first_capture,
                            decision,
                            record_data,
                            snapshot,
                            stored_items,
                            fallback_from_auto=True,
                        )
                    except Exception:
                        self.db.rollback()
                        self._acquire_postgres_session_lock(
                            first_capture.user_id,
                            first_capture.source_message_id,
                        )
                        winner = self._existing_session(first_capture)
                        if winner is not None and self._result_references_all_stored(
                            winner,
                            stored_items,
                        ):
                            return self._with_replayed(winner)
                        self._remove_unreferenced_copies(stored_items, winner)
                        raise

            return self._persist_confirmation_draft(
                first_capture,
                decision,
                record_data,
                snapshot,
                stored_items,
            )
        except IntegrityError:
            self.db.rollback()
            self._acquire_postgres_session_lock(
                first_capture.user_id,
                first_capture.source_message_id,
            )
            winner = self._existing_session(first_capture)
            self._remove_unreferenced_copies(stored_items, winner)
            if winner is not None and not _conflict_retried:
                return self.capture_session(
                    normalized,
                    _conflict_retried=True,
                )
            if winner is not None:
                return self._with_replayed(winner)
            raise
        except Exception:
            self.db.rollback()
            self._acquire_postgres_session_lock(
                first_capture.user_id,
                first_capture.source_message_id,
            )
            winner = self._existing_session(first_capture)
            if winner is not None and self._result_references_all_stored(
                winner,
                stored_items,
            ):
                return self._with_replayed(winner)
            self._remove_unreferenced_copies(stored_items, winner)
            raise

    @contextmanager
    def _capture_session_lock(
        self,
        user_id: int,
        source_message_id: int,
    ) -> Iterator[None]:
        """Serialize a capture session before reading either possible parent.

        PostgreSQL uses a transaction-scoped advisory lock, which coordinates
        every application process. SQLite is test/development-only here, so a
        bounded process-local stripe prevents thread races without pretending
        to provide cross-process locking.
        """
        if self.db.get_bind().dialect.name == "postgresql":
            self._acquire_postgres_session_lock(user_id, source_message_id)
            try:
                yield
            finally:
                # Replays and ambiguous-commit recovery perform read queries
                # after the last write commit. End that transaction here so a
                # transaction-scoped advisory lock never leaks into later work
                # performed with this Session.
                if self.db.in_transaction():
                    self.db.rollback()
            return
        lock_key = self._capture_session_lock_key(user_id, source_message_id)
        lock = self._SQLITE_LOCK_STRIPES[lock_key % len(self._SQLITE_LOCK_STRIPES)]
        with lock:
            try:
                yield
            finally:
                # Keep SQLite tests behaviorally aligned with production and
                # avoid returning a Session with an implicit read transaction.
                if self.db.in_transaction():
                    self.db.rollback()

    def _acquire_postgres_session_lock(
        self,
        user_id: int,
        source_message_id: int,
    ) -> None:
        if self.db.get_bind().dialect.name != "postgresql":
            return
        self.db.execute(
            text("SELECT pg_advisory_xact_lock(:capture_session_key)"),
            {
                "capture_session_key": self._capture_session_lock_key(
                    user_id,
                    source_message_id,
                ),
            },
        )

    @staticmethod
    def _capture_session_lock_key(user_id: int, source_message_id: int) -> int:
        digest = hashlib.blake2b(
            f"diet-photo:{int(user_id)}:{int(source_message_id)}".encode(),
            digest_size=8,
        ).digest()
        unsigned = int.from_bytes(digest, byteorder="big", signed=False)
        return unsigned if unsigned < 2**63 else unsigned - 2**64

    @staticmethod
    def _validate_session(
        captures: list[ContextualMealPhotoCapture],
    ) -> list[ContextualMealPhotoCapture]:
        if not captures:
            raise ContextualMealPhotoServiceError("contextual_meal_photo_session_empty")
        if len(captures) > 8:
            raise ContextualMealPhotoServiceError("contextual_meal_photo_session_too_large")
        ordered = sorted(captures, key=lambda item: item.source_image_index)
        first = ordered[0]
        seen_ordinals: set[int] = set()
        for capture in ordered:
            if (
                capture.user_id != first.user_id
                or capture.source_message_id != first.source_message_id
            ):
                raise ContextualMealPhotoServiceError(
                    "contextual_meal_photo_session_identity_mismatch",
                )
            if capture.decision != first.decision:
                raise ContextualMealPhotoServiceError(
                    "contextual_meal_photo_session_decision_mismatch",
                )
            if capture.source_image_index < 0:
                raise ContextualMealPhotoServiceError(
                    "contextual_meal_photo_session_ordinal_invalid",
                )
            if capture.source_image_index in seen_ordinals:
                raise ContextualMealPhotoServiceError(
                    "contextual_meal_photo_session_ordinal_duplicate",
                )
            if capture.classification not in {"food", "non_food", "unknown"}:
                raise ContextualMealPhotoServiceError(
                    "contextual_meal_photo_classification_invalid",
                )
            seen_ordinals.add(capture.source_image_index)
        if (
            first.decision.decision == "auto_record"
            and any(capture.classification != "food" for capture in ordered)
        ):
            raise ContextualMealPhotoServiceError(
                "contextual_meal_photo_incomplete_batch_requires_confirmation",
            )
        return ordered

    def _copy_unique_session_media(
        self,
        captures: list[ContextualMealPhotoCapture],
        *,
        existing: ContextualMealPhotoCaptureResult | None,
    ) -> list[tuple[ContextualMealPhotoCapture, StoredDietPhoto]]:
        existing_hashes = {
            asset.content_sha256
            for asset in (existing.photo_assets if existing is not None else ())
        }
        seen_hashes = set(existing_hashes)
        stored_items: list[tuple[ContextualMealPhotoCapture, StoredDietPhoto]] = []
        try:
            for capture in captures:
                stored = copy_owned_chat_image_to_diet(
                    capture.source_image_url,
                    capture.user_id,
                )
                if stored.content_sha256 in seen_hashes:
                    remove_diet_image_file(stored.file_path)
                    continue
                seen_hashes.add(stored.content_sha256)
                stored_items.append((capture, stored))
            return stored_items
        except Exception:
            for _capture, stored in stored_items:
                remove_diet_image_file(stored.file_path)
            raise

    @staticmethod
    def _result_references_all_stored(
        result: ContextualMealPhotoCaptureResult,
        stored_items: list[tuple[ContextualMealPhotoCapture, StoredDietPhoto]],
    ) -> bool:
        referenced = {asset.storage_key for asset in result.photo_assets}
        return bool(stored_items) and all(
            stored.storage_key in referenced
            for _capture, stored in stored_items
        )

    @staticmethod
    def _remove_unreferenced_copies(
        stored_items: list[tuple[ContextualMealPhotoCapture, StoredDietPhoto]],
        existing: ContextualMealPhotoCaptureResult | None,
    ) -> None:
        referenced = {
            asset.storage_key
            for asset in (existing.photo_assets if existing is not None else ())
        }
        for _capture, stored in stored_items:
            if stored.storage_key not in referenced:
                remove_diet_image_file(stored.file_path)

    def _persist_auto_record(
        self,
        capture: ContextualMealPhotoCapture,
        decision: MealPhotoDecision,
        record_data: dict[str, Any],
        snapshot: dict[str, Any],
        stored_items: list[tuple[ContextualMealPhotoCapture, StoredDietPhoto]],
    ) -> ContextualMealPhotoCaptureResult:
        assets = [
            self._new_asset(
                media_capture,
                decision,
                record_data,
                snapshot,
                stored,
            )
            for media_capture, stored in stored_items
        ]
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
            image_url=stored_items[0][1].storage_key,
            client_action_id=self._record_idempotency_key(capture),
            ai_recognized=True,
            ai_confidence=record_data["ai_confidence"],
            ai_raw_result=json.dumps(snapshot, ensure_ascii=False),
            health_tips=record_data.get("health_tips"),
        )
        attached_at = datetime.now(timezone.utc)
        for asset in assets:
            asset.diet_record = record
            asset.lifecycle = "attached"
            asset.attached_at = attached_at
        self.db.add_all([record, *assets])
        self.db.commit()
        self.db.refresh(record)
        for asset in assets:
            self.db.refresh(asset)
        self._create_postmeal_protocol(record)
        result = ContextualMealPhotoCaptureResult(
            decision=decision,
            record=record,
            photo_asset=assets[0],
            photo_assets=tuple(assets),
        )
        self._log_result("committed", capture, result)
        return result

    def _persist_confirmation_draft(
        self,
        capture: ContextualMealPhotoCapture,
        decision: MealPhotoDecision,
        record_data: dict[str, Any],
        snapshot: dict[str, Any],
        stored_items: list[tuple[ContextualMealPhotoCapture, StoredDietPhoto]],
        *,
        fallback_from_auto: bool = False,
    ) -> ContextualMealPhotoCaptureResult:
        assets = [
            self._new_asset(
                media_capture,
                decision,
                record_data,
                snapshot,
                stored,
            )
            for media_capture, stored in stored_items
        ]
        draft = DietPhotoDraft(
            token=secrets.token_urlsafe(32),
            user_id=capture.user_id,
            source_message_id=capture.source_message_id,
            image_url=stored_items[0][1].storage_key,
            image_type=_image_type_from_media_type(stored_items[0][1].media_type),
            recognition_result=record_data,
            status="pending",
            expires_at=datetime.now(timezone.utc) + PHOTO_DRAFT_TTL,
        )
        for asset in assets:
            asset.photo_draft_token = draft.token
        # ``DietPhotoAsset`` intentionally has no ORM relationship to its
        # draft parent. Flush the parent explicitly so PostgreSQL's immediate
        # FK check never observes an asset before ``DietPhotoDraft`` exists.
        self.db.add(draft)
        self.db.flush()
        self.db.add_all(assets)
        self.db.commit()
        self.db.refresh(draft)
        for asset in assets:
            self.db.refresh(asset)
        result = ContextualMealPhotoCaptureResult(
            decision=decision,
            photo_draft=draft,
            photo_asset=assets[0],
            photo_assets=tuple(assets),
            fallback_from_auto=fallback_from_auto,
        )
        self._log_result(
            "fallback_draft" if fallback_from_auto else "confirmation_draft",
            capture,
            result,
        )
        return result

    def _attach_session_media(
        self,
        existing: ContextualMealPhotoCaptureResult,
        stored_items: list[tuple[ContextualMealPhotoCapture, StoredDietPhoto]],
        record_data: dict[str, Any],
        snapshot: dict[str, Any],
        *,
        provided_ordinals: set[int],
    ) -> ContextualMealPhotoCaptureResult:
        assets = [
            self._new_asset(
                capture,
                existing.decision,
                record_data,
                snapshot,
                stored,
            )
            for capture, stored in stored_items
        ]
        if existing.record is not None:
            attached_at = datetime.now(timezone.utc)
            for asset in assets:
                asset.diet_record_id = existing.record.id
                asset.lifecycle = "attached"
                asset.attached_at = attached_at
        elif existing.photo_draft is not None:
            for asset in assets:
                asset.photo_draft_token = existing.photo_draft.token
        else:
            raise ContextualMealPhotoServiceError(
                "contextual_meal_photo_session_parent_missing",
            )
        self._refresh_parent_aggregate(
            existing,
            assets,
            record_data,
            snapshot,
            provided_ordinals=provided_ordinals,
        )
        self.db.add_all(assets)
        self.db.commit()
        result = self._existing_session(stored_items[0][0], replayed=False) or existing
        self._log_result("media_attached", stored_items[0][0], result)
        return result

    @staticmethod
    def _refresh_parent_aggregate(
        existing: ContextualMealPhotoCaptureResult,
        new_assets: list[DietPhotoAsset],
        record_data: dict[str, Any],
        snapshot: dict[str, Any],
        *,
        provided_ordinals: set[int],
    ) -> None:
        """Replace the parent projection with the complete session snapshot.

        The caller holds the capture-session lock. A partial snapshot must not
        overwrite an already persisted whole-meal aggregate.
        """
        all_assets = sorted(
            (*existing.photo_assets, *new_assets),
            key=lambda asset: (int(asset.ordinal), str(asset.id)),
        )
        declared_count = snapshot.get("source_image_count")
        if declared_count is not None:
            try:
                declared_count = int(declared_count)
            except (TypeError, ValueError) as exc:
                raise ContextualMealPhotoServiceError(
                    "contextual_meal_photo_session_snapshot_invalid",
                ) from exc
            if declared_count < len(all_assets):
                raise ContextualMealPhotoServiceError(
                    "contextual_meal_photo_session_snapshot_incomplete",
                )
        elif not {
            int(asset.ordinal) for asset in existing.photo_assets
        }.issubset(provided_ordinals):
            raise ContextualMealPhotoServiceError(
                "contextual_meal_photo_session_snapshot_incomplete",
            )

        for asset in all_assets:
            asset.recognition_snapshot = snapshot
            if asset.classification == "food":
                asset.recognition_confidence = record_data["ai_confidence"]

        first_storage_key = all_assets[0].storage_key
        if existing.record is not None:
            record = existing.record
            record.record_date = existing.decision.local_time.date()
            record.meal_type = existing.decision.meal_type
            record.meal_time = existing.decision.local_time.timetz().replace(tzinfo=None)
            record.food_name = record_data["food_items"][:100]
            record.food_items = record_data["food_items"]
            record.source = "chat_photo"
            record.calories = record_data.get("calories")
            record.protein = record_data.get("protein")
            record.carbs = record_data.get("carbs")
            record.fat = record_data.get("fat")
            record.fiber = record_data.get("fiber")
            record.image_url = first_storage_key
            record.ai_recognized = True
            record.ai_confidence = record_data["ai_confidence"]
            record.ai_raw_result = json.dumps(snapshot, ensure_ascii=False)
            record.health_tips = record_data.get("health_tips")
            return
        if existing.photo_draft is not None:
            existing.photo_draft.image_url = first_storage_key
            existing.photo_draft.image_type = _image_type_from_media_type(
                all_assets[0].media_type,
            )
            existing.photo_draft.recognition_result = record_data
            return
        raise ContextualMealPhotoServiceError(
            "contextual_meal_photo_session_parent_missing",
        )

    @staticmethod
    def _log_result(
        stage: str,
        capture: ContextualMealPhotoCapture,
        result: ContextualMealPhotoCaptureResult,
    ) -> None:
        logger.info(
            "meal_capture_session_finished stage=%s user_id=%s "
            "source_message_id=%s parent_type=%s parent_id=%s asset_count=%s replayed=%s",
            stage,
            capture.user_id,
            capture.source_message_id,
            "diet_record" if result.record is not None else "diet_photo_draft",
            result.record.id if result.record is not None else "redacted",
            len(result.photo_assets),
            result.replayed,
        )

    @staticmethod
    def _new_asset(
        capture: ContextualMealPhotoCapture,
        decision: MealPhotoDecision,
        record_data: dict[str, Any],
        snapshot: dict[str, Any],
        stored: StoredDietPhoto,
    ) -> DietPhotoAsset:
        return DietPhotoAsset(
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
            classification=capture.classification,
            recognition_confidence=(
                record_data["ai_confidence"]
                if capture.classification == "food"
                else None
            ),
            intent_decision=decision.decision,
            recognition_snapshot=snapshot,
            lifecycle="pending",
        )

    def _existing_capture(
        self,
        capture: ContextualMealPhotoCapture,
    ) -> ContextualMealPhotoCaptureResult | None:
        asset = self._existing_assets_by_ordinal(capture).get(
            capture.source_image_index,
        )
        if asset is None:
            return None
        return self._result_for_session_assets(
            capture,
            self._session_assets(capture),
            replayed=True,
        )

    def _existing_assets_by_ordinal(
        self,
        capture: ContextualMealPhotoCapture,
    ) -> dict[int, DietPhotoAsset]:
        assets = (
            self.db.query(DietPhotoAsset)
            .filter(
                DietPhotoAsset.user_id == capture.user_id,
                DietPhotoAsset.origin_message_id == capture.source_message_id,
                DietPhotoAsset.lifecycle != "deleted",
            )
            .order_by(DietPhotoAsset.ordinal.asc(), DietPhotoAsset.created_at.asc())
            .all()
        )
        return {int(asset.ordinal): asset for asset in assets}

    def _session_assets(
        self,
        capture: ContextualMealPhotoCapture,
    ) -> tuple[DietPhotoAsset, ...]:
        return tuple(self._existing_assets_by_ordinal(capture).values())

    def _existing_session(
        self,
        capture: ContextualMealPhotoCapture,
        *,
        replayed: bool = True,
    ) -> ContextualMealPhotoCaptureResult | None:
        assets = self._session_assets(capture)
        if not assets:
            return None
        return self._result_for_session_assets(
            capture,
            assets,
            replayed=replayed,
        )

    def _result_for_session_assets(
        self,
        capture: ContextualMealPhotoCapture,
        assets: tuple[DietPhotoAsset, ...],
        *,
        replayed: bool,
    ) -> ContextualMealPhotoCaptureResult:
        record_ids = {asset.diet_record_id for asset in assets if asset.diet_record_id}
        draft_tokens = {
            asset.photo_draft_token
            for asset in assets
            if asset.photo_draft_token
        }
        if len(record_ids) + len(draft_tokens) != 1:
            raise ContextualMealPhotoServiceError(
                "contextual_meal_photo_session_parent_conflict",
            )
        first_asset = assets[0]
        if record_ids:
            record_id = next(iter(record_ids))
            if any(
                asset.diet_record_id != record_id or asset.photo_draft_token
                for asset in assets
            ):
                raise ContextualMealPhotoServiceError(
                    "contextual_meal_photo_session_parent_conflict",
                )
            record = (
                self.db.query(DietRecord)
                .filter(
                    DietRecord.id == record_id,
                    DietRecord.user_id == capture.user_id,
                )
                .first()
            )
            if record is not None:
                return ContextualMealPhotoCaptureResult(
                    decision=capture.decision,
                    record=record,
                    photo_asset=first_asset,
                    photo_assets=assets,
                    replayed=replayed,
                )
        if draft_tokens:
            draft_token = next(iter(draft_tokens))
            if any(
                asset.photo_draft_token != draft_token or asset.diet_record_id
                for asset in assets
            ):
                raise ContextualMealPhotoServiceError(
                    "contextual_meal_photo_session_parent_conflict",
                )
            draft = (
                self.db.query(DietPhotoDraft)
                .filter(
                    DietPhotoDraft.token == draft_token,
                    DietPhotoDraft.user_id == capture.user_id,
                )
                .first()
            )
            if draft is not None:
                return ContextualMealPhotoCaptureResult(
                    decision=capture.decision,
                    photo_draft=draft,
                    photo_asset=first_asset,
                    photo_assets=assets,
                    replayed=replayed,
                    fallback_from_auto=first_asset.intent_decision == "auto_record",
                )
        raise ContextualMealPhotoServiceError("contextual_meal_photo_existing_asset_invalid")

    @staticmethod
    def _with_replayed(
        result: ContextualMealPhotoCaptureResult,
    ) -> ContextualMealPhotoCaptureResult:
        return ContextualMealPhotoCaptureResult(
            decision=result.decision,
            record=result.record,
            photo_draft=result.photo_draft,
            photo_asset=result.photo_asset,
            photo_assets=result.photo_assets,
            replayed=True,
            fallback_from_auto=result.fallback_from_auto,
        )

    def _record_payload(
        self,
        raw_vision_result: dict[str, Any],
        decision: MealPhotoDecision,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        consumed_fraction = raw_vision_result.get("consumed_fraction")
        if (
            not isinstance(consumed_fraction, (int, float))
            or isinstance(consumed_fraction, bool)
            or not math.isfinite(float(consumed_fraction))
            or not 0 < float(consumed_fraction) < 1
        ):
            consumed_fraction = None
        consumed_fraction_label = str(
            raw_vision_result.get("consumed_fraction_label") or ""
        ).strip()[:20]
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
                    "name", "quantity", "quantity_grams", "label_basis_grams",
                    "calories", "protein", "carbs", "fat", "fiber",
                    "confidence", "food_id", "source", "nutrition_basis",
                    "portion_basis", "portion_confidence",
                )
                if food.get(key) is not None
            })
            confidence = food.get("confidence")
            if isinstance(confidence, (int, float)):
                confidences.append(float(confidence))
        food_items = " + ".join(labels)
        if consumed_fraction is not None and consumed_fraction_label:
            food_items = (
                f"{food_items}（按实际食用{consumed_fraction_label}计）"
            )
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
        source_image_count = raw_vision_result.get("source_image_count")
        if isinstance(source_image_count, int) and not isinstance(source_image_count, bool):
            snapshot["source_image_count"] = max(0, source_image_count)
        if raw_vision_result.get("multi_photo_incomplete"):
            snapshot["multi_photo_incomplete"] = True
            failed_indexes = raw_vision_result.get("failed_image_indexes")
            if isinstance(failed_indexes, list):
                snapshot["failed_image_indexes"] = [
                    int(index)
                    for index in failed_indexes
                    if isinstance(index, int) and not isinstance(index, bool) and index >= 0
                ]
        if consumed_fraction is not None:
            snapshot["consumed_fraction"] = float(consumed_fraction)
            snapshot["consumed_fraction_label"] = consumed_fraction_label
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
        return f"contextual-meal-photo:{capture.source_message_id}"


def _image_type_from_media_type(media_type: str) -> str:
    value = str(media_type or "image/jpeg").split("/", 1)[-1].lower()
    return "jpeg" if value == "jpg" else value
