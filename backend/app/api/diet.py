"""饮食记录API"""
import os
import json
import logging
import fcntl
import threading
import uuid
from time import perf_counter
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
from typing import List, Optional
from datetime import date, timedelta, datetime, time, timezone

from app.database import get_db
from app.models.daily_health import DietPhotoAsset, DietPhotoDraft, DietRecord as DietRecordModel
from app.models.user import User
from app.api.deps import get_current_user_required
from app.schemas.diet import (
    MealType,
    DietRecordCreate,
    DietRecordUpdate,
    DietRecordResponse,
    DailyDietSummary,
    DietStats,
    FrequentFood,
    FoodRecognitionRequest,
    FoodRecognitionResponse,
    CreateDietFromImageRequest,
    VoiceFoodParseRequest,
    VoiceFoodParseResponse,
    DietPhotoDraftStatusResponse,
    DietPhotoAssetResponse,
)
from statistics import median
from app.services.ai.food_recognition import (
    food_recognition_service,
    sanitize_food_recognition_result,
)
from app.services.food_nutrition_lookup import calibrate_recognized_foods
from app.services.intake_intent_classifier import (
    classify_intake_intent,
    looks_like_food_ui_text,
)
from app.services.diet_media_storage import StoredDietPhoto, store_diet_image
# D1(garmin-sync 治理 Wave 3):图片 URL 签名抽到 utils 做单一真源,供 api 的
# _convert_to_response 与进程内 diet reader 共用(非确定性签名字段无法 parity-test,
# 必须共用同一函数对象防静默漂移)。保留同名以不动本模块调用点。
from app.utils.diet_image_url import diet_response_image_url as _diet_response_image_url

router = APIRouter()
logger = logging.getLogger(__name__)
PHOTO_DRAFT_TTL = timedelta(hours=24)
_ACTIVE_DIET_IMAGE_DELETION_GUARD = threading.Lock()
_ACTIVE_DIET_IMAGE_DELETIONS: set[str] = set()


def _diet_photo_idempotency_key(photo_draft_token: str | None) -> str | None:
    return f"diet-photo:{photo_draft_token}" if photo_draft_token else None


def _combined_diet_idempotency_key(
    idempotency_key: str | None,
    photo_draft_token: str | None,
) -> str | None:
    """Preserve both Runtime and photo-draft retry identities in one opaque field."""
    photo_key = _diet_photo_idempotency_key(photo_draft_token)
    if not idempotency_key:
        return photo_key
    if not photo_key or photo_key == idempotency_key:
        return idempotency_key
    combined = f"{idempotency_key}|{photo_key}"
    if len(combined) > 160:
        raise HTTPException(status_code=400, detail="组合幂等标识过长")
    return combined


def _find_idempotent_diet_record(
    db: Session,
    *,
    user_id: int,
    idempotency_key: str | None,
    photo_draft_token: str | None,
) -> DietRecordModel | None:
    conditions = []
    photo_key = _diet_photo_idempotency_key(photo_draft_token)
    if idempotency_key:
        conditions.extend([
            DietRecordModel.client_action_id == idempotency_key,
            DietRecordModel.client_action_id.startswith(
                f"{idempotency_key}|",
                autoescape=True,
            ),
        ])
    if photo_key:
        conditions.extend([
            DietRecordModel.client_action_id == photo_key,
            DietRecordModel.client_action_id.endswith(
                f"|{photo_key}",
                autoescape=True,
            ),
        ])
    if not conditions:
        return None
    return db.query(DietRecordModel).filter(
        DietRecordModel.user_id == user_id,
        or_(*conditions),
    ).first()


def _assert_diet_food_items_allowed(food_items: str) -> None:
    if looks_like_food_ui_text(food_items):
        raise HTTPException(
            status_code=400,
            detail="界面文案或按钮文字不能作为饮食记录写入，请填写真实食物名称和份量。",
        )
    intent = classify_intake_intent(food_items)
    if intent.kind == "diet_management":
        raise HTTPException(
            status_code=400,
            detail="查询、保存状态、删除、撤销或恢复饮食记录不能作为饮食记录写入，请使用饮食记录管理操作。",
        )
    if intent.kind in {"medication", "supplement"}:
        raise HTTPException(
            status_code=400,
            detail="药物或补剂摄入不能作为饮食记录写入，请使用用药或补剂记录。",
        )
    if intent.kind == "health_metric":
        raise HTTPException(
            status_code=400,
            detail="运动、睡眠、体重、血压或血糖不能作为饮食记录写入，请使用对应健康记录入口。",
        )


def _remove_diet_image_file(filepath: str | None) -> None:
    if not filepath:
        return
    try:
        os.remove(filepath)
    except FileNotFoundError:
        return


def _diet_image_file_path(image_url: str | None, owner_id: int) -> str | None:
    if not image_url:
        return None
    from app.api.upload import UPLOAD_DIR

    path = urlsplit(str(image_url)).path
    canonical_prefix = f"/api/v1/upload/files/diet/{int(owner_id)}/"
    legacy_prefix = "/api/v1/upload/files/diet/"
    if path.startswith(canonical_prefix):
        owner_root = os.path.realpath(os.path.join(UPLOAD_DIR, "diet", str(int(owner_id))))
        filename = os.path.basename(path.removeprefix(canonical_prefix))
    elif path.startswith(legacy_prefix):
        # Legacy files share a global directory and do not encode ownership in
        # their path. Keep them for the migration/cleanup job rather than risk
        # deleting another user's image from a forged or stale record.
        return None
    else:
        return None
    candidate = os.path.realpath(os.path.join(owner_root, filename))
    if not filename or not candidate.startswith(f"{owner_root}{os.sep}"):
        return None
    return candidate


def _assert_diet_user_access(user_id: int, current_user: User) -> None:
    if int(user_id) != int(current_user.id) and not bool(current_user.is_admin):
        raise HTTPException(status_code=403, detail="无权读取他人的饮食记录")


StagedDietImageDeletion = tuple[str, str, int]


def _release_staged_diet_image_lock(staged_deletion: StagedDietImageDeletion) -> None:
    _, staged, lock_fd = staged_deletion
    with _ACTIVE_DIET_IMAGE_DELETION_GUARD:
        _ACTIVE_DIET_IMAGE_DELETIONS.discard(staged)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(lock_fd)
    except OSError:
        pass


def _stage_diet_image_delete(
    image_url: str | None,
    owner_id: int,
) -> StagedDietImageDeletion | None:
    original = _diet_image_file_path(image_url, owner_id)
    if not original or not os.path.isfile(original):
        return None
    staged = f"{original}.deleting-{uuid.uuid4().hex}"
    lock_fd = os.open(original, os.O_RDONLY)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(lock_fd)
        return None
    with _ACTIVE_DIET_IMAGE_DELETION_GUARD:
        _ACTIVE_DIET_IMAGE_DELETIONS.add(staged)
    try:
        os.replace(original, staged)
    except Exception:
        _release_staged_diet_image_lock((original, staged, lock_fd))
        raise
    return original, staged, lock_fd


def _restore_staged_diet_image(staged_deletion: StagedDietImageDeletion) -> None:
    original, staged, _ = staged_deletion
    try:
        if os.path.exists(staged) and not os.path.exists(original):
            os.replace(staged, original)
    finally:
        _release_staged_diet_image_lock(staged_deletion)


def _finalize_staged_diet_image(staged_deletion: StagedDietImageDeletion) -> None:
    _, staged, _ = staged_deletion
    try:
        _remove_diet_image_file(staged)
    finally:
        _release_staged_diet_image_lock(staged_deletion)


def _stage_diet_image_deletions(
    image_urls: list[str | None],
    owner_id: int,
) -> list[StagedDietImageDeletion] | None:
    """Stage every distinct owner-owned photo before mutating its DB record.

    A diet record can now own a cover plus additional photo assets.  Deletion
    remains all-or-nothing at the DB boundary: if one image is busy, restore
    any images already staged and leave the record intact for a retry.
    """
    staged: list[StagedDietImageDeletion] = []
    seen_paths: set[str] = set()
    for image_url in image_urls:
        path = _diet_image_file_path(image_url, owner_id)
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        if not os.path.isfile(path):
            continue
        staged_image = _stage_diet_image_delete(image_url, owner_id)
        if staged_image is not None:
            staged.append(staged_image)
            continue
        for previous in reversed(staged):
            try:
                _restore_staged_diet_image(previous)
            except OSError as restore_error:
                logger.error("饮食记录删除取消后图片恢复失败: %s", restore_error)
        return None
    return staged


def _restore_staged_diet_images(staged_images: list[StagedDietImageDeletion]) -> None:
    for staged_image in reversed(staged_images):
        try:
            _restore_staged_diet_image(staged_image)
        except OSError as restore_error:
            logger.error("饮食记录删除失败后图片恢复失败: %s", restore_error)


def _finalize_staged_diet_images(staged_images: list[StagedDietImageDeletion]) -> None:
    for staged_image in staged_images:
        try:
            _finalize_staged_diet_image(staged_image)
        except OSError as cleanup_error:
            logger.error("饮食记录删除后图片清理失败: %s", cleanup_error)


def reconcile_staged_diet_image_deletions(db: Session) -> int:
    """Reconcile crash-safe image tombstones against owner-scoped DB references."""
    from app.api.upload import UPLOAD_DIR

    upload_root = os.path.realpath(os.path.join(UPLOAD_DIR, "diet"))
    if not os.path.isdir(upload_root):
        return 0
    candidates: list[str] = []
    for current_root, _directories, filenames in os.walk(upload_root, followlinks=False):
        for filename in filenames:
            if ".deleting-" in filename:
                candidates.append(os.path.join(current_root, filename))

    reconciled = 0
    failures: list[str] = []
    for path in candidates:
        candidate = os.path.realpath(path)
        if not candidate.startswith(f"{upload_root}{os.sep}"):
            continue
        with _ACTIVE_DIET_IMAGE_DELETION_GUARD:
            if candidate in _ACTIVE_DIET_IMAGE_DELETIONS:
                continue
        lock_fd = None
        try:
            lock_fd = os.open(candidate, os.O_RDONLY)
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            original = candidate.split(".deleting-", 1)[0]
            relative = os.path.relpath(original, upload_root).split(os.sep)
            if len(relative) != 2 or not relative[0].isdigit():
                continue
            owner_id = int(relative[0])
            image_url = f"/api/v1/upload/files/diet/{owner_id}/{os.path.basename(original)}"
            referenced = db.query(DietRecordModel.id).filter(
                DietRecordModel.user_id == owner_id,
                DietRecordModel.image_url == image_url,
            ).first() or db.query(DietPhotoDraft.token).filter(
                DietPhotoDraft.user_id == owner_id,
                DietPhotoDraft.image_url == image_url,
            ).first() or db.query(DietPhotoAsset.id).filter(
                DietPhotoAsset.user_id == owner_id,
                DietPhotoAsset.storage_key == image_url,
                DietPhotoAsset.lifecycle != "deleted",
            ).first()
            if referenced and not os.path.exists(original):
                os.replace(candidate, original)
            else:
                _remove_diet_image_file(candidate)
            reconciled += 1
        except FileNotFoundError:
            continue
        except BlockingIOError:
            continue
        except OSError as exc:
            failures.append(f"{candidate}:{exc}")
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except OSError:
                    pass
                try:
                    os.close(lock_fd)
                except OSError:
                    pass
    if failures:
        raise RuntimeError(
            "diet_image_tombstone_reconcile_failed: " + "; ".join(failures[:5])
        )
    return reconciled


def _is_photo_draft_expired(draft: DietPhotoDraft) -> bool:
    expires_at = draft.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def _new_diet_photo_asset(
    stored: StoredDietPhoto,
    *,
    user_id: int,
    origin: str,
    classification: str,
    intent_decision: str = "confirm",
    recognition_confidence: float | None = None,
    recognition_snapshot: dict | None = None,
    diet_record: DietRecordModel | None = None,
    photo_draft_token: str | None = None,
) -> DietPhotoAsset:
    """Build the canonical ledger row for every new diet image write.

    The legacy DietRecord.image_url remains a compatibility cover, but all new
    images must also have this owner-scoped asset row. A caller attaches it to
    either a record or a draft inside the same database transaction.
    """
    attached = diet_record is not None
    return DietPhotoAsset(
        id=uuid.uuid4().hex,
        user_id=user_id,
        diet_record=diet_record,
        photo_draft_token=photo_draft_token,
        storage_key=stored.storage_key,
        content_sha256=stored.content_sha256,
        media_type=stored.media_type,
        origin=origin,
        ordinal=0,
        classification=classification,
        recognition_confidence=recognition_confidence,
        intent_decision=intent_decision,
        recognition_snapshot=recognition_snapshot,
        lifecycle="attached" if attached else "pending",
        attached_at=datetime.now(timezone.utc) if attached else None,
    )


def _recognition_confidence(recognition_result: dict) -> float | None:
    values = [
        float(food["confidence"])
        for food in recognition_result.get("foods", [])
        if isinstance(food, dict) and isinstance(food.get("confidence"), (int, float))
    ]
    return round(sum(values) / len(values), 3) if values else None


def _create_diet_photo_draft(
    db: Session,
    user_id: int,
    image_base64: str,
    image_type: str,
    recognition_result: dict,
) -> DietPhotoDraft:
    stored = store_diet_image(image_base64, image_type, user_id)
    draft = DietPhotoDraft(
        token=uuid.uuid4().hex,
        user_id=user_id,
        image_url=stored.storage_key,
        image_type=image_type,
        recognition_result=recognition_result,
        status="pending",
        expires_at=datetime.now(timezone.utc) + PHOTO_DRAFT_TTL,
    )
    asset = _new_diet_photo_asset(
        stored,
        user_id=user_id,
        origin="diet_recognition",
        classification="food" if recognition_result.get("foods") else "unknown",
        recognition_confidence=_recognition_confidence(recognition_result),
        recognition_snapshot=recognition_result,
        photo_draft_token=draft.token,
    )
    try:
        db.add_all([draft, asset])
        db.commit()
        db.refresh(draft)
    except Exception:
        db.rollback()
        _remove_diet_image_file(stored.file_path)
        raise
    return draft


def _expire_photo_draft(db: Session, draft: DietPhotoDraft) -> None:
    assets = db.query(DietPhotoAsset).filter(
        DietPhotoAsset.user_id == draft.user_id,
        DietPhotoAsset.photo_draft_token == draft.token,
    ).with_for_update().all()
    image_paths = {
        _diet_image_file_path(image_url, draft.user_id)
        for image_url in [draft.image_url, *(asset.storage_key for asset in assets)]
    }
    draft.status = "expired"
    draft.recognition_result = {}
    db.flush()
    try:
        for image_path in image_paths:
            _remove_diet_image_file(image_path)
    except OSError:
        # Persist the scrubbed retry row before surfacing the cleanup failure.
        db.commit()
        raise
    for asset in assets:
        db.delete(asset)
    db.delete(draft)
    db.commit()


def purge_expired_diet_photo_drafts(
    db: Session,
    *,
    now: datetime | None = None,
) -> int:
    """Expire abandoned drafts and retry private-image deletion until cleared."""
    cutoff = now or datetime.now(timezone.utc)
    drafts = db.query(DietPhotoDraft).filter(
        or_(
            (
                (DietPhotoDraft.status == "pending")
                & (DietPhotoDraft.expires_at <= cutoff)
            ),
            (
                DietPhotoDraft.status.in_(("expired", "cancelled"))
            ),
        )
    ).with_for_update(skip_locked=True).all()
    if not drafts:
        return 0

    for draft in drafts:
        if draft.status == "pending":
            draft.status = "expired"
        draft.recognition_result = {}
    db.flush()

    purged = 0
    failures: list[str] = []
    for draft in drafts:
        assets = db.query(DietPhotoAsset).filter(
            DietPhotoAsset.user_id == draft.user_id,
            DietPhotoAsset.photo_draft_token == draft.token,
        ).all()
        image_paths = {
            _diet_image_file_path(image_url, draft.user_id)
            for image_url in [draft.image_url, *(asset.storage_key for asset in assets)]
        }
        try:
            for image_path in image_paths:
                _remove_diet_image_file(image_path)
            for asset in assets:
                db.delete(asset)
            db.delete(draft)
            purged += 1
        except OSError as exc:
            failures.append(f"{draft.token}:{exc}")
    db.commit()
    if failures:
        raise RuntimeError(
            "diet_photo_draft_image_purge_failed: " + "; ".join(failures[:5])
        )
    return purged


@router.post("/records", response_model=DietRecordResponse)
def create_diet_record(
    record: DietRecordCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    idempotency_key: Optional[str] = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=8,
        max_length=160,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
):
    """Create a diet record, serializing confirmation with photo auto-capture."""
    if record.photo_draft_token:
        photo_draft = db.query(DietPhotoDraft).filter(
            DietPhotoDraft.token == record.photo_draft_token,
            DietPhotoDraft.user_id == current_user.id,
        ).first()
        if photo_draft is not None and photo_draft.source_message_id is not None:
            from app.services.contextual_meal_photo_service import (
                ContextualMealPhotoService,
            )

            service = ContextualMealPhotoService(db)
            with service._capture_session_lock(  # noqa: SLF001 - shared write boundary
                current_user.id,
                photo_draft.source_message_id,
            ):
                return _create_diet_record_locked(
                    record,
                    current_user=current_user,
                    db=db,
                    idempotency_key=idempotency_key,
                )
    return _create_diet_record_locked(
        record,
        current_user=current_user,
        db=db,
        idempotency_key=idempotency_key,
    )


def _create_diet_record_locked(
    record: DietRecordCreate,
    *,
    current_user: User,
    db: Session,
    idempotency_key: Optional[str],
) -> DietRecordResponse:
    """创建饮食记录（需要登录）"""
    _assert_diet_food_items_allowed(record.food_items)
    effective_idempotency_key = _combined_diet_idempotency_key(
        idempotency_key,
        record.photo_draft_token,
    )
    if effective_idempotency_key:
        existing = _find_idempotent_diet_record(
            db,
            user_id=current_user.id,
            idempotency_key=idempotency_key,
            photo_draft_token=record.photo_draft_token,
        )
        if existing:
            return _convert_to_response(existing)
    created_image_path: str | None = None
    try:
        logger.info(
            "用户 %s 创建饮食记录: meal_type=%s",
            current_user.id,
            record.meal_type,
        )

        # 转换meal_time为字符串
        record_dict = record.model_dump()
        if record_dict.get('meal_time'):
            record_dict['meal_time'] = record_dict['meal_time'].strftime('%H:%M')

        photo_draft: DietPhotoDraft | None = None
        if record.photo_draft_token:
            photo_draft = db.query(DietPhotoDraft).filter(
                DietPhotoDraft.token == record.photo_draft_token,
                DietPhotoDraft.user_id == current_user.id,
            ).with_for_update().first()
            if photo_draft is None:
                existing = _find_idempotent_diet_record(
                    db,
                    user_id=current_user.id,
                    idempotency_key=idempotency_key,
                    photo_draft_token=record.photo_draft_token,
                )
                if existing:
                    return _convert_to_response(existing)
                raise HTTPException(status_code=404, detail="饮食照片草稿不存在或无权访问")
            if photo_draft.status == "consumed" and photo_draft.consumed_record_id:
                existing = db.query(DietRecordModel).filter(
                    DietRecordModel.id == photo_draft.consumed_record_id,
                    DietRecordModel.user_id == current_user.id,
                ).first()
                if existing:
                    return _convert_to_response(existing)
            if photo_draft.status != "pending":
                raise HTTPException(status_code=409, detail="饮食照片草稿已不可用")
            if _is_photo_draft_expired(photo_draft):
                _expire_photo_draft(db, photo_draft)
                raise HTTPException(status_code=410, detail="饮食照片草稿已过期，请重新拍照")
            image_url = photo_draft.image_url
        else:
            image_url = None

        stored_direct_image: StoredDietPhoto | None = None
        if record_dict.get('image_base64') and photo_draft is None:
            stored_direct_image = store_diet_image(
                record_dict['image_base64'],
                record_dict.get('image_type'),
                current_user.id,
            )
            image_url = stored_direct_image.storage_key
            created_image_path = stored_direct_image.file_path
            logger.info("饮食图片已保存: user_id=%s", current_user.id)

        # 确保 meal_type 是字符串
        meal_type_value = record_dict['meal_type']
        if isinstance(meal_type_value, MealType):
            meal_type_value = meal_type_value.value

        # food_name 使用 food_items 的值（数据库要求 NOT NULL）
        food_name = record_dict['food_items']
        if food_name and len(food_name) > 100:
            food_name = food_name[:100]  # 截断过长的名称
        ai_raw_result = record_dict.get('ai_raw_result')
        if ai_raw_result is not None and not isinstance(ai_raw_result, str):
            ai_raw_result = json.dumps(ai_raw_result, ensure_ascii=False)

        db_record = DietRecordModel(
            user_id=current_user.id,
            record_date=record_dict['record_date'],
            meal_type=meal_type_value,
            food_name=food_name,  # 必填字段
            food_items=record_dict['food_items'],
            food_id=record_dict.get('food_id'),
            source=record_dict.get('source'),
            calories=record_dict.get('calories'),
            protein=record_dict.get('protein'),
            carbs=record_dict.get('carbs'),
            fat=record_dict.get('fat'),
            fiber=record_dict.get('fiber'),
            alcohol_units=record_dict.get('alcohol_units'),
            notes=record_dict.get('notes'),
            image_url=image_url,
            client_action_id=effective_idempotency_key,
            ai_recognized=bool(record_dict.get('ai_recognized')),
            ai_confidence=record_dict.get('ai_confidence'),
            ai_raw_result=ai_raw_result,
            health_tips=record_dict.get('health_tips'),
        )
        db.add(db_record)
        if stored_direct_image is not None:
            db.add(_new_diet_photo_asset(
                stored_direct_image,
                user_id=current_user.id,
                origin="diet_api",
                classification="unknown",
                recognition_confidence=record_dict.get("ai_confidence"),
                recognition_snapshot=(
                    record_dict.get("ai_raw_result")
                    if isinstance(record_dict.get("ai_raw_result"), dict)
                    else None
                ),
                diet_record=db_record,
            ))
        try:
            db.flush()
            if photo_draft is not None:
                pending_assets = (
                    db.query(DietPhotoAsset)
                    .filter(
                        DietPhotoAsset.user_id == current_user.id,
                        DietPhotoAsset.photo_draft_token == photo_draft.token,
                        DietPhotoAsset.lifecycle == "pending",
                    )
                    .with_for_update()
                    .order_by(DietPhotoAsset.ordinal)
                    .all()
                )
                for asset in pending_assets:
                    asset.diet_record_id = db_record.id
                    asset.photo_draft_token = None
                    asset.lifecycle = "attached"
                    asset.attached_at = datetime.now(timezone.utc)
                if pending_assets and not db_record.image_url:
                    db_record.image_url = pending_assets[0].storage_key
                # The record now owns the private image. Remove the short-lived
                # recognition payload in the same transaction; idempotent retries
                # are resolved by DietRecord.client_action_id.
                db.delete(photo_draft)
            db.commit()
        except IntegrityError:
            db.rollback()
            if effective_idempotency_key:
                existing = _find_idempotent_diet_record(
                    db,
                    user_id=current_user.id,
                    idempotency_key=idempotency_key,
                    photo_draft_token=record.photo_draft_token,
                )
                if existing:
                    _remove_diet_image_file(created_image_path)
                    created_image_path = None
                    return _convert_to_response(existing)
            raise
        created_image_path = None
        db.refresh(db_record)

        logger.info(f"饮食记录创建成功: id={db_record.id}")
        try:
            from app.services import health_protocol_service as protocol_service

            protocol_service.create_postmeal_walk_protocol(
                db,
                current_user.id,
                record_date=db_record.record_date,
                meal_type=meal_type_value,
                meal_time=record.meal_time,
                diet_record_id=db_record.id,
            )
        except Exception as e:  # noqa: BLE001
            db.rollback()
            logger.warning(
                "餐后散步协议创建失败,不阻塞饮食记录: user_id=%s diet_record_id=%s error=%s",
                current_user.id,
                db_record.id,
                e,
            )
        return _convert_to_response(db_record)

    except HTTPException:
        db.rollback()
        try:
            _remove_diet_image_file(created_image_path)
        except OSError as cleanup_error:
            logger.error("饮食图片失败回滚清理失败: %s", cleanup_error)
        raise
    except Exception as e:
        logger.error(f"创建饮食记录失败: {e}", exc_info=True)
        db.rollback()
        try:
            _remove_diet_image_file(created_image_path)
        except OSError as cleanup_error:
            logger.error("饮食图片失败回滚清理失败: %s", cleanup_error)
        raise HTTPException(status_code=500, detail=f"创建记录失败: {str(e)}")


def _convert_to_response(record) -> DietRecordResponse:
    """转换为响应模型"""
    meal_time = None
    if hasattr(record, 'meal_time') and record.meal_time:
        if isinstance(record.meal_time, str):
            try:
                meal_time = datetime.strptime(record.meal_time, '%H:%M').time()
            except (ValueError, TypeError):
                meal_time = None
        elif isinstance(record.meal_time, time):
            meal_time = record.meal_time

    photo_assets = []
    for asset in sorted(
        (
            asset for asset in (getattr(record, "photo_assets", None) or [])
            if asset.lifecycle == "attached"
        ),
        key=lambda asset: (asset.ordinal, asset.created_at or datetime.min.replace(tzinfo=timezone.utc)),
    ):
        signed_url = _diet_response_image_url(asset.storage_key, record.user_id)
        if not signed_url:
            logger.warning(
                "忽略无效饮食照片资产: asset_id=%s user_id=%s",
                asset.id,
                record.user_id,
            )
            continue
        photo_assets.append(DietPhotoAssetResponse(
            id=asset.id,
            url=signed_url,
            ordinal=asset.ordinal,
            captured_at=asset.captured_at,
            origin=asset.origin,
        ))

    legacy_image_url = _diet_response_image_url(
        getattr(record, 'image_url', None),
        record.user_id,
    )
    image_urls = [asset.url for asset in photo_assets]
    if not image_urls and legacy_image_url:
        image_urls.append(legacy_image_url)

    return DietRecordResponse(
        id=record.id,
        user_id=record.user_id,
        record_date=record.record_date,
        meal_type=MealType(record.meal_type) if record.meal_type else MealType.EXTRA,
        meal_time=meal_time,
        food_items=record.food_items or '',
        food_id=getattr(record, 'food_id', None),
        source=getattr(record, 'source', None),
        calories=record.calories,
        protein=record.protein,
        carbs=record.carbs,
        fat=record.fat,
        fiber=record.fiber,
        notes=record.notes,
        image_url=image_urls[0] if image_urls else legacy_image_url,
        image_urls=image_urls,
        photo_assets=photo_assets,
        ai_recognized=getattr(record, 'ai_recognized', 0),
        ai_confidence=getattr(record, 'ai_confidence', None),
        health_tips=getattr(record, 'health_tips', None),
        created_at=record.created_at,
        updated_at=record.updated_at if hasattr(record, 'updated_at') else None,
    )



@router.get("/records/user/{user_id}", response_model=List[DietRecordResponse])
def get_user_diet_records(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    meal_type: Optional[str] = None,
    limit: int = Query(default=50, le=500),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取用户饮食记录"""
    _assert_diet_user_access(user_id, current_user)
    query = db.query(DietRecordModel).filter(DietRecordModel.user_id == user_id)

    if start_date:
        query = query.filter(DietRecordModel.record_date >= start_date)
    if end_date:
        query = query.filter(DietRecordModel.record_date <= end_date)
    if meal_type:
        query = query.filter(DietRecordModel.meal_type == meal_type)

    records = query.order_by(
        desc(DietRecordModel.record_date),
        desc(DietRecordModel.created_at),
        desc(DietRecordModel.id),
    ).limit(limit).all()
    return [_convert_to_response(r) for r in records]


@router.get("/records/user/{user_id}/date/{record_date}", response_model=DailyDietSummary)
def get_daily_diet_summary(
    user_id: int,
    record_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取某日饮食汇总"""
    _assert_diet_user_access(user_id, current_user)
    records = db.query(DietRecordModel).filter(
        DietRecordModel.user_id == user_id,
        DietRecordModel.record_date == record_date
    ).order_by(DietRecordModel.created_at).all()

    total_calories = sum(r.calories or 0 for r in records)
    total_protein = sum(r.protein or 0 for r in records)
    total_carbs = sum(r.carbs or 0 for r in records)
    total_fat = sum(r.fat or 0 for r in records)
    total_fiber = sum(r.fiber or 0 for r in records)

    return DailyDietSummary(
        record_date=record_date,
        total_calories=total_calories,
        total_protein=round(total_protein, 1),
        total_carbs=round(total_carbs, 1),
        total_fat=round(total_fat, 1),
        total_fiber=round(total_fiber, 1),
        meals_count=len(records),
        meals=[_convert_to_response(r) for r in records]
    )


@router.get("/records/user/{user_id}/stats", response_model=DietStats)
def get_diet_stats(
    user_id: int,
    days: int = Query(default=7, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取饮食统计"""
    _assert_diet_user_access(user_id, current_user)
    start_date = date.today() - timedelta(days=days)

    records = db.query(DietRecordModel).filter(
        DietRecordModel.user_id == user_id,
        DietRecordModel.record_date >= start_date
    ).all()

    if not records:
        return DietStats(total_records=0, days_recorded=0)

    # 按日期分组统计
    daily_data = {}
    for r in records:
        d = str(r.record_date)
        if d not in daily_data:
            daily_data[d] = {'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0}
        daily_data[d]['calories'] += r.calories or 0
        daily_data[d]['protein'] += r.protein or 0
        daily_data[d]['carbs'] += r.carbs or 0
        daily_data[d]['fat'] += r.fat or 0

    days_count = len(daily_data)

    return DietStats(
        average_daily_calories=round(sum(d['calories'] for d in daily_data.values()) / days_count, 0) if days_count else None,
        average_daily_protein=round(sum(d['protein'] for d in daily_data.values()) / days_count, 1) if days_count else None,
        average_daily_carbs=round(sum(d['carbs'] for d in daily_data.values()) / days_count, 1) if days_count else None,
        average_daily_fat=round(sum(d['fat'] for d in daily_data.values()) / days_count, 1) if days_count else None,
        total_records=len(records),
        days_recorded=days_count
    )


# ========== /me 端点 ==========

@router.get("/records/me", response_model=List[DietRecordResponse])
def get_my_diet_records(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    meal_type: Optional[str] = None,
    limit: int = Query(default=50, le=500),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户饮食记录（需要登录）"""
    query = db.query(DietRecordModel).filter(DietRecordModel.user_id == current_user.id)

    if start_date:
        query = query.filter(DietRecordModel.record_date >= start_date)
    if end_date:
        query = query.filter(DietRecordModel.record_date <= end_date)
    if meal_type:
        query = query.filter(DietRecordModel.meal_type == meal_type)

    records = query.order_by(
        desc(DietRecordModel.record_date),
        desc(DietRecordModel.created_at),
        desc(DietRecordModel.id),
    ).limit(limit).all()
    return [_convert_to_response(r) for r in records]


@router.get("/records/me/date/{record_date}", response_model=DailyDietSummary)
def get_my_daily_diet_summary(
    record_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户某日饮食汇总（需要登录）"""
    records = db.query(DietRecordModel).filter(
        DietRecordModel.user_id == current_user.id,
        DietRecordModel.record_date == record_date
    ).order_by(DietRecordModel.created_at).all()

    total_calories = sum(r.calories or 0 for r in records)
    total_protein = sum(r.protein or 0 for r in records)
    total_carbs = sum(r.carbs or 0 for r in records)
    total_fat = sum(r.fat or 0 for r in records)
    total_fiber = sum(r.fiber or 0 for r in records)

    return DailyDietSummary(
        record_date=record_date,
        total_calories=total_calories,
        total_protein=round(total_protein, 1),
        total_carbs=round(total_carbs, 1),
        total_fat=round(total_fat, 1),
        total_fiber=round(total_fiber, 1),
        meals_count=len(records),
        meals=[_convert_to_response(r) for r in records]
    )


@router.get("/records/me/stats", response_model=DietStats)
def get_my_diet_stats(
    days: int = Query(default=7, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户饮食统计（需要登录）"""
    start_date = date.today() - timedelta(days=days)

    records = db.query(DietRecordModel).filter(
        DietRecordModel.user_id == current_user.id,
        DietRecordModel.record_date >= start_date
    ).all()

    if not records:
        return DietStats(total_records=0, days_recorded=0)

    # 按日期分组统计
    daily_data = {}
    for r in records:
        d = str(r.record_date)
        if d not in daily_data:
            daily_data[d] = {'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0}
        daily_data[d]['calories'] += r.calories or 0
        daily_data[d]['protein'] += r.protein or 0
        daily_data[d]['carbs'] += r.carbs or 0
        daily_data[d]['fat'] += r.fat or 0

    days_count = len(daily_data)

    return DietStats(
        average_daily_calories=round(sum(d['calories'] for d in daily_data.values()) / days_count, 0) if days_count else None,
        average_daily_protein=round(sum(d['protein'] for d in daily_data.values()) / days_count, 1) if days_count else None,
        average_daily_carbs=round(sum(d['carbs'] for d in daily_data.values()) / days_count, 1) if days_count else None,
        average_daily_fat=round(sum(d['fat'] for d in daily_data.values()) / days_count, 1) if days_count else None,
        total_records=len(records),
        days_recorded=days_count
    )


def _median_or_none(values: List[float]) -> Optional[float]:
    """对非空数值取中位数, 全空返回 None (诚实表达"无历史营养数据")."""
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return round(float(median(nums)), 1)


@router.get("/records/me/frequent", response_model=List[FrequentFood])
def get_my_frequent_foods(
    days: int = Query(default=30, ge=7, le=180),
    limit: int = Query(default=8, ge=1, le=30),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """当前用户最近 N 天的"常吃"食物, 按出现频次倒序 (供一键复用).

    按 food_items (去空白后) 分组; 同名食物的营养素取历次中位数, meal_type 取众数.
    无历史营养数据的项营养素返回 null —— 不编造数值 (rule#1).
    """
    start_date = date.today() - timedelta(days=days)
    records = db.query(DietRecordModel).filter(
        DietRecordModel.user_id == current_user.id,
        DietRecordModel.record_date >= start_date,
    ).all()

    # 按归一化 food_items 分组
    groups: dict[str, list] = {}
    for r in records:
        key = (r.food_items or "").strip()
        if not key:
            continue
        groups.setdefault(key, []).append(r)

    items: List[FrequentFood] = []
    for food, rs in groups.items():
        # meal_type 众数 (并列时取最近一次)
        meal_counts: dict[str, int] = {}
        for r in rs:
            mt = r.meal_type or "extra"
            meal_counts[mt] = meal_counts.get(mt, 0) + 1
        top_meal = max(meal_counts.items(), key=lambda kv: kv[1])[0]
        items.append(FrequentFood(
            food_items=food,
            meal_type=MealType(top_meal) if top_meal in MealType._value2member_map_ else MealType.EXTRA,
            count=len(rs),
            calories=_median_or_none([r.calories for r in rs]),
            protein=_median_or_none([r.protein for r in rs]),
            carbs=_median_or_none([r.carbs for r in rs]),
            fat=_median_or_none([r.fat for r in rs]),
        ))

    # 频次倒序, 同频次按字母稳定排序
    items.sort(key=lambda f: (-f.count, f.food_items))
    return items[:limit]


@router.put("/records/{record_id}", response_model=DietRecordResponse)
def update_diet_record(
    record_id: int,
    update_data: DietRecordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """更新饮食记录（需登录，且只能更新自己的记录）"""
    record = db.query(DietRecordModel).filter(
        DietRecordModel.id == record_id
    ).with_for_update().first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权更新他人的饮食记录")

    update_dict = update_data.model_dump(exclude_unset=True)
    if update_dict.get("food_items") is not None:
        _assert_diet_food_items_allowed(update_dict["food_items"])
    food_changed = (
        "food_items" in update_dict
        and " ".join(str(update_dict["food_items"] or "").split())
        != " ".join(str(record.food_items or "").split())
    )
    nutrient_fields = ("calories", "protein", "carbs", "fat", "fiber")
    nutrition_changed = any(
        key in update_dict and update_dict[key] != getattr(record, key)
        for key in nutrient_fields
    )
    preserve_explicit_nutrients = (
        update_dict.get("source") == "agent_portion_correction"
    )
    if food_changed:
        update_dict["food_id"] = None
        for key in nutrient_fields:
            if (
                key not in update_dict
                or (
                    not preserve_explicit_nutrients
                    and update_dict[key] == getattr(record, key)
                )
            ):
                update_dict[key] = None
    if food_changed or nutrition_changed:
        update_dict["source"] = "user_corrected"
        update_dict["ai_recognized"] = 0
        update_dict["ai_confidence"] = None
        update_dict["ai_raw_result"] = None
        update_dict["health_tips"] = None
    if 'meal_type' in update_dict and update_dict['meal_type']:
        update_dict['meal_type'] = update_dict['meal_type'].value
    if 'meal_time' in update_dict and update_dict['meal_time']:
        update_dict['meal_time'] = update_dict['meal_time'].strftime('%H:%M')
    if update_dict.get("ai_raw_result") is not None and not isinstance(
        update_dict["ai_raw_result"], str
    ):
        update_dict["ai_raw_result"] = json.dumps(
            update_dict["ai_raw_result"], ensure_ascii=False
        )

    for key, value in update_dict.items():
        setattr(record, key, value)

    db.commit()
    db.refresh(record)
    return _convert_to_response(record)


@router.delete("/records/{record_id}")
def delete_diet_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """删除饮食记录（需登录，且只能删除自己的记录）"""
    record = db.query(DietRecordModel).filter(
        DietRecordModel.id == record_id
    ).with_for_update().first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除他人的饮食记录")

    assets = db.query(DietPhotoAsset).filter(
        DietPhotoAsset.user_id == current_user.id,
        DietPhotoAsset.diet_record_id == record.id,
    ).with_for_update().all()
    staged_images = _stage_diet_image_deletions(
        [record.image_url, *(asset.storage_key for asset in assets)],
        current_user.id,
    )
    if staged_images is None:
        raise HTTPException(status_code=409, detail="饮食图片正在处理中，请稍后重试删除")
    try:
        for asset in assets:
            db.delete(asset)
        db.delete(record)
        db.commit()
    except Exception:
        db.rollback()
        _restore_staged_diet_images(staged_images)
        raise
    _finalize_staged_diet_images(staged_images)
    return {
        "message": "Record deleted successfully",
        "id": record_id,
        "record_id": record_id,
        "resource_type": "diet_record",
    }


# ========== AI食物识别端点 ==========

@router.post("/voice/parse", response_model=VoiceFoodParseResponse)
async def parse_voice_food_endpoint(
    request: VoiceFoodParseRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """语音转写文本 → 结构化食物草稿(Apple Watch Companion / R5)。

    只解析不写库;客户端确认后再 POST /diet/records。分层:规则(餐次/风险标签)+
    记忆(常吃中位营养)+ LLM(自由文本→结构化)。LLM 不可用则降级 + 标 needs_confirmation。
    """
    from app.services.diet_voice_parser import parse_voice_food
    from app.services.ambient_wearables import create_audio_input_event

    _assert_diet_food_items_allowed(request.raw_text)
    result = await parse_voice_food(db, current_user.id, request.raw_text, request.meal_type)
    create_audio_input_event(
        db,
        current_user.id,
        intent="food",
        transcript=request.raw_text,
        source=request.source or "voice",
        device_type=request.device_type or "unknown",
        confidence=result.get("confidence"),
        status="pending_confirmation",
        target_type="diet_voice_draft",
        meta={
            "meal_type": result.get("meal_type"),
            "risk_tags": result.get("risk_tags") or [],
            "parser_version": result.get("parser_version"),
            "needs_confirmation": result.get("needs_confirmation"),
        },
    )
    db.commit()
    return result


@router.post("/recognize", response_model=FoodRecognitionResponse)
async def recognize_food(
    request: FoodRecognitionRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    AI识别食物图片

    上传Base64编码的图片，AI会识别出食物并估算营养信息
    """
    if not food_recognition_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="智能食物识别服务不可用"
        )

    request_started = perf_counter()
    vision_ms = 0
    calibration_ms = 0
    photo_draft_ms = 0
    try:
        vision_started = perf_counter()
        result = await food_recognition_service.recognize_food_from_base64(
            request.image_base64,
            request.image_type
        )
        vision_ms = round((perf_counter() - vision_started) * 1000)
        result = sanitize_food_recognition_result(result)

        if not result.get("success"):
            total_ms = round((perf_counter() - request_started) * 1000)
            return FoodRecognitionResponse(
                success=False,
                error=result.get("error", "识别失败"),
                foods=[],
                timing_ms={"vision": vision_ms, "total": total_ms},
            )

        calibration_started = perf_counter()
        calibrate_recognized_foods(db, result.get("foods", []))
        result = sanitize_food_recognition_result(result)
        calibration_ms = round((perf_counter() - calibration_started) * 1000)
        photo_draft_token = None
        if request.create_photo_draft:
            photo_draft_started = perf_counter()
            photo_draft = _create_diet_photo_draft(
                db,
                current_user.id,
                request.image_base64,
                request.image_type,
                result,
            )
            photo_draft_token = photo_draft.token
            photo_draft_ms = round((perf_counter() - photo_draft_started) * 1000)
        total_ms = round((perf_counter() - request_started) * 1000)
        logger.info(
            "[diet_photo] recognition completed user_id=%s foods=%s vision_ms=%s "
            "calibration_ms=%s draft_ms=%s total_ms=%s",
            current_user.id,
            len(result.get("foods", [])),
            vision_ms,
            calibration_ms,
            photo_draft_ms,
            total_ms,
        )

        return FoodRecognitionResponse(
            success=True,
            foods=result.get("foods", []),
            meal_description=result.get("meal_description"),
            health_tips=result.get("health_tips"),
            total_calories=result.get("total_calories"),
            total_protein=result.get("total_protein"),
            total_carbs=result.get("total_carbs"),
            total_fat=result.get("total_fat"),
            total_fiber=result.get("total_fiber"),
            photo_draft_token=photo_draft_token,
            timing_ms={
                "vision": vision_ms,
                "calibration": calibration_ms,
                "photo_draft": photo_draft_ms,
                "total": total_ms,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "食物识别失败: %s total_ms=%s",
            e,
            round((perf_counter() - request_started) * 1000),
        )
        raise HTTPException(status_code=500, detail=f"识别失败: {str(e)}")


@router.get(
    "/photo-drafts/{token}/status",
    response_model=DietPhotoDraftStatusResponse,
)
def get_photo_draft_status(
    token: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    draft = db.query(DietPhotoDraft).filter(
        DietPhotoDraft.token == token,
        DietPhotoDraft.user_id == current_user.id,
    ).with_for_update().first()
    if draft is None:
        raise HTTPException(status_code=404, detail="饮食照片草稿不存在或无权访问")
    if draft.status != "pending" or _is_photo_draft_expired(draft):
        if draft.status == "pending":
            _expire_photo_draft(db, draft)
        raise HTTPException(status_code=410, detail="饮食照片草稿已失效")
    return DietPhotoDraftStatusResponse(
        status=draft.status,
        expires_at=draft.expires_at,
    )


@router.delete("/photo-drafts/{token}", status_code=204)
def discard_photo_draft(
    token: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    draft = db.query(DietPhotoDraft).filter(
        DietPhotoDraft.token == token,
        DietPhotoDraft.user_id == current_user.id,
    ).with_for_update().first()
    if draft is None:
        confirmed = db.query(DietRecordModel).filter(
            DietRecordModel.user_id == current_user.id,
            DietRecordModel.client_action_id == f"diet-photo:{token}",
        ).first()
        if confirmed is not None:
            raise HTTPException(status_code=409, detail="已确认的饮食照片不能取消")
        raise HTTPException(status_code=404, detail="饮食照片草稿不存在或无权访问")
    if draft.status == "consumed":
        raise HTTPException(status_code=409, detail="已确认的饮食照片不能取消")
    if draft.status == "pending":
        draft.status = "cancelled"
        draft.recognition_result = {}
    if draft.status not in {"cancelled", "expired"}:
        raise HTTPException(status_code=409, detail="饮食照片草稿已不可用")
    draft.recognition_result = {}
    db.flush()
    assets = db.query(DietPhotoAsset).filter(
        DietPhotoAsset.user_id == current_user.id,
        DietPhotoAsset.photo_draft_token == draft.token,
    ).with_for_update().all()
    image_paths = {
        _diet_image_file_path(image_url, current_user.id)
        for image_url in [draft.image_url, *(asset.storage_key for asset in assets)]
    }
    try:
        for image_path in image_paths:
            _remove_diet_image_file(image_path)
    except OSError as exc:
        db.commit()
        logger.error(
            "饮食照片草稿取消后图片清理失败: user=%s asset_count=%s error_type=%s",
            current_user.id,
            len(assets),
            type(exc).__name__,
        )
        raise HTTPException(status_code=500, detail="草稿已取消，图片清理将在后台重试") from exc
    for asset in assets:
        db.delete(asset)
    db.delete(draft)
    db.commit()
    return None


@router.post("/recognize-and-save", response_model=DietRecordResponse)
async def recognize_and_save_diet(
    request: CreateDietFromImageRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    AI识别食物图片并直接保存为饮食记录

    一键拍照 -> AI识别 -> 保存记录
    """
    if not food_recognition_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="智能食物识别服务不可用"
        )

    created_image_path: str | None = None
    try:
        # AI识别
        result = await food_recognition_service.recognize_food_from_base64(
            request.image_base64,
            request.image_type
        )
        result = sanitize_food_recognition_result(result)

        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "智能识别失败")
            )

        foods = result.get("foods", [])
        if not foods:
            raise HTTPException(
                status_code=400,
                detail="未识别到任何食物，请重新拍照"
            )

        calibrate_recognized_foods(db, foods)
        result = sanitize_food_recognition_result(result)
        foods = result.get("foods", [])

        # 组合食物名称
        food_names = [f.get("name", "") for f in foods if f.get("name")]
        food_items = ", ".join([f.get("name", "") + (f" ({f.get('quantity', '')})" if f.get('quantity') else "") for f in foods])
        _assert_diet_food_items_allowed(food_items)

        # 取第一个食物名称作为主名称（兼容旧字段）
        primary_food_name = food_names[0] if food_names else "智能识别食物"

        # 计算平均置信度
        confidences = [f.get("confidence", 0) for f in foods if f.get("confidence")]
        avg_confidence = sum(confidences) / len(confidences) if confidences else None

        # 保存图片（如果有）
        image_url = None
        stored_image: StoredDietPhoto | None = None
        if request.image_base64:
            stored_image = store_diet_image(
                request.image_base64,
                request.image_type,
                current_user.id,
            )
            image_url = stored_image.storage_key
            created_image_path = stored_image.file_path
            logger.info("饮食图片已保存: user_id=%s", current_user.id)

        # 创建饮食记录
        db_record = DietRecordModel(
            user_id=current_user.id,
            record_date=request.record_date,
            meal_type=request.meal_type.value,
            food_name=primary_food_name,  # 必填字段
            food_items=food_items,
            calories=result.get("total_calories"),
            protein=result.get("total_protein"),
            carbs=result.get("total_carbs"),
            fat=result.get("total_fat"),
            notes=request.notes,
            image_url=image_url,  # 保存图片URL
            ai_recognized=True,  # 布尔类型，不是整数
            ai_confidence=avg_confidence,
            ai_raw_result=json.dumps(result, ensure_ascii=False),
            health_tips=result.get("health_tips")
        )

        db.add(db_record)
        if stored_image is not None:
            db.add(_new_diet_photo_asset(
                stored_image,
                user_id=current_user.id,
                origin="diet_recognize_and_save",
                classification="food",
                recognition_confidence=avg_confidence,
                recognition_snapshot=result,
                diet_record=db_record,
            ))
        db.commit()
        created_image_path = None
        db.refresh(db_record)

        logger.info(
            "用户 %s 通过 AI 识别创建饮食记录: record_id=%s food_count=%s",
            current_user.id,
            db_record.id,
            len(foods),
        )

        return _convert_to_response(db_record)

    except HTTPException:
        db.rollback()
        try:
            _remove_diet_image_file(created_image_path)
        except OSError as cleanup_error:
            logger.error("AI 饮食图片失败回滚清理失败: %s", cleanup_error)
        raise
    except Exception as e:
        db.rollback()
        try:
            _remove_diet_image_file(created_image_path)
        except OSError as cleanup_error:
            logger.error("AI 饮食图片失败回滚清理失败: %s", cleanup_error)
        logger.error(f"AI识别并保存失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@router.post("/estimate-nutrition", response_model=FoodRecognitionResponse)
async def estimate_nutrition_from_text(
    food_description: str = Query(..., description="食物描述文字"),
    current_user: User = Depends(get_current_user_required)
):
    """
    根据文字描述估算营养信息（不需要图片）

    例如: "两个鸡蛋，一碗米饭，炒青菜"
    """
    if not food_recognition_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="智能服务不可用"
        )

    try:
        result = food_recognition_service.estimate_nutrition_from_text(food_description)

        if not result.get("success"):
            return FoodRecognitionResponse(
                success=False,
                error=result.get("error", "估算失败"),
                foods=[]
            )

        return FoodRecognitionResponse(
            success=True,
            foods=result.get("foods", []),
            health_tips=result.get("health_tips"),
            total_calories=result.get("total_calories"),
            total_protein=result.get("total_protein"),
            total_carbs=result.get("total_carbs"),
            total_fat=result.get("total_fat")
        )

    except Exception as e:
        logger.error(f"营养估算失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
