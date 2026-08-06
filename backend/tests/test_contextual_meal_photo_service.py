"""Persistence contracts for contextual chat meal photos."""
import base64
import os
import threading
import time
from io import BytesIO
from datetime import datetime, timezone

import pytest
from PIL import Image
from sqlalchemy import event

from app.models.daily_health import DietPhotoAsset, DietPhotoDraft, DietRecord
from app.models.user import User
from app.services.contextual_meal_photo_policy import (
    MealPhotoCandidate,
    MealPhotoSemanticIntent,
    decide_contextual_meal_photo,
)
from app.services.contextual_meal_photo_service import (
    ContextualMealPhotoCapture,
    ContextualMealPhotoService,
    ContextualMealPhotoServiceError,
)
from app.services import chat_utils


VALID_PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z/QAAAABJRU5ErkJggg=="


@pytest.fixture
def test_user(db):
    user = User(
        username="contextual_meal_photo_user",
        email="contextual-meal-photo@example.com",
        hashed_password="hashed_password",
        name="餐食照片测试用户",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _decision(*, at: datetime, timezone_name: str = "America/New_York"):
    return decide_contextual_meal_photo(MealPhotoCandidate(
        origin="chat",
        semantic_intent=MealPhotoSemanticIntent.IMPLICIT_CAPTURE,
        classification="food",
        recognition_confidence=0.93,
        reference_now=at,
        timezone_name=timezone_name,
        idempotency_clear=True,
    ))


def _vision_result():
    return {
        "foods": [{
            "name": "鸡胸肉",
            "quantity": "约120g",
            "calories": 198,
            "protein": 37.0,
            "carbs": 0.0,
            "fat": 4.3,
            "fiber": 0.0,
            "confidence": 0.93,
        }],
        "total_calories": 198,
        "total_protein": 37.0,
        "total_carbs": 0.0,
        "total_fat": 4.3,
        "total_fiber": 0.0,
        "health_tips": "营养估算，仅供参考。",
    }


def _source_image(tmp_path, monkeypatch, user_id: int) -> str:
    from app.api import upload as upload_api

    monkeypatch.setattr(chat_utils, "_UPLOAD_DIR", str(tmp_path / "chat"))
    monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(tmp_path / "uploads"))
    return chat_utils.upload_chat_image(VALID_PNG_BASE64, user_id, "png")


def _source_image_variant(
    tmp_path,
    monkeypatch,
    user_id: int,
    *,
    color: tuple[int, int, int],
) -> str:
    from app.api import upload as upload_api

    monkeypatch.setattr(chat_utils, "_UPLOAD_DIR", str(tmp_path / "chat"))
    monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(tmp_path / "uploads"))
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color=color).save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode()
    return chat_utils.upload_chat_image(encoded, user_id, "png")


def _capture(
    *,
    user_id: int,
    message_id: int,
    source_url: str,
    ordinal: int,
    at: datetime,
    vision_result: dict | None = None,
    classification: str = "food",
) -> ContextualMealPhotoCapture:
    return ContextualMealPhotoCapture(
        user_id=user_id,
        source_message_id=message_id,
        source_image_url=source_url,
        source_image_index=ordinal,
        decision=_decision(at=at),
        vision_result=vision_result or _vision_result(),
        classification=classification,
    )


def test_auto_capture_copies_owned_chat_media_to_one_idempotent_diet_record(
    db, test_user, tmp_path, monkeypatch
):
    source_url = _source_image(tmp_path, monkeypatch, test_user.id)
    service = ContextualMealPhotoService(db)
    capture = ContextualMealPhotoCapture(
        user_id=test_user.id,
        source_message_id=701,
        source_image_url=source_url,
        source_image_index=0,
        decision=_decision(at=datetime(2026, 7, 19, 16, 30, tzinfo=timezone.utc)),
        vision_result=_vision_result(),
    )

    first = service.capture(capture)
    retry = service.capture(capture)

    assert first.record is not None
    assert retry.record is not None
    assert retry.record.id == first.record.id
    assert retry.replayed is True
    assert db.query(DietRecord).count() == 1
    asset = db.query(DietPhotoAsset).one()
    assert asset.user_id == test_user.id
    assert asset.diet_record_id == first.record.id
    assert asset.photo_draft_token is None
    assert asset.lifecycle == "attached"
    assert asset.storage_key.startswith(f"/api/v1/upload/files/diet/{test_user.id}/")
    assert "?" not in asset.storage_key
    assert first.record.image_url == asset.storage_key


def test_auto_capture_creates_the_same_postmeal_protocol_once(
    db, test_user, tmp_path, monkeypatch
):
    source_url = _source_image(tmp_path, monkeypatch, test_user.id)
    calls = []

    def create_protocol(db_session, user_id, **kwargs):
        calls.append((db_session, user_id, kwargs))
        return None

    monkeypatch.setattr(
        "app.services.health_protocol_service.create_postmeal_walk_protocol",
        create_protocol,
    )
    service = ContextualMealPhotoService(db)
    capture = ContextualMealPhotoCapture(
        user_id=test_user.id,
        source_message_id=704,
        source_image_url=source_url,
        source_image_index=0,
        decision=_decision(at=datetime(2026, 7, 19, 16, 30, tzinfo=timezone.utc)),
        vision_result=_vision_result(),
    )

    first = service.capture(capture)
    retry = service.capture(capture)

    assert first.record is not None
    assert retry.replayed is True
    assert calls == [(
        db,
        test_user.id,
        {
            "record_date": first.record.record_date,
            "meal_type": "lunch",
            "meal_time": first.record.meal_time,
            "diet_record_id": first.record.id,
        },
    )]


def test_food_photo_outside_auto_window_creates_owner_bound_confirmation_draft(
    db, test_user, tmp_path, monkeypatch
):
    source_url = _source_image(tmp_path, monkeypatch, test_user.id)
    service = ContextualMealPhotoService(db)
    capture = ContextualMealPhotoCapture(
        user_id=test_user.id,
        source_message_id=702,
        source_image_url=source_url,
        source_image_index=0,
        decision=_decision(at=datetime(2026, 7, 20, 3, 30, tzinfo=timezone.utc)),
        vision_result=_vision_result(),
    )

    result = service.capture(capture)

    assert result.record is None
    assert result.photo_draft is not None
    assert db.query(DietRecord).count() == 0
    draft = db.query(DietPhotoDraft).one()
    asset = db.query(DietPhotoAsset).one()
    assert draft.token == result.photo_draft.token
    assert asset.photo_draft_token == draft.token
    assert asset.diet_record_id is None
    assert asset.lifecycle == "pending"


def test_confirmation_draft_parent_is_inserted_before_photo_assets(
    db, test_user, tmp_path, monkeypatch
):
    """Keep PostgreSQL's immediate FK check safe without ORM relationships."""
    source_url = _source_image(tmp_path, monkeypatch, test_user.id)
    insert_order: list[str] = []

    def capture_insert_order(_conn, _cursor, statement, _params, _ctx, _many):
        normalized = statement.lstrip().lower()
        if normalized.startswith("insert into diet_photo_drafts"):
            insert_order.append("draft")
        elif normalized.startswith("insert into diet_photo_assets"):
            insert_order.append("asset")

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", capture_insert_order)
    try:
        result = ContextualMealPhotoService(db).capture(ContextualMealPhotoCapture(
            user_id=test_user.id,
            source_message_id=703,
            source_image_url=source_url,
            source_image_index=0,
            decision=_decision(
                at=datetime(2026, 7, 20, 3, 30, tzinfo=timezone.utc),
            ),
            vision_result=_vision_result(),
        ))
    finally:
        event.remove(engine, "before_cursor_execute", capture_insert_order)

    assert result.photo_draft is not None
    assert insert_order == ["draft", "asset"]


def test_same_message_photos_attach_to_one_auto_record(
    db, test_user, tmp_path, monkeypatch
):
    first_url = _source_image_variant(
        tmp_path, monkeypatch, test_user.id, color=(220, 30, 30),
    )
    second_url = _source_image_variant(
        tmp_path, monkeypatch, test_user.id, color=(30, 180, 80),
    )
    at = datetime(2026, 7, 19, 16, 30, tzinfo=timezone.utc)
    service = ContextualMealPhotoService(db)

    result = service.capture_session([
        _capture(
            user_id=test_user.id,
            message_id=708,
            source_url=first_url,
            ordinal=0,
            at=at,
        ),
        _capture(
            user_id=test_user.id,
            message_id=708,
            source_url=second_url,
            ordinal=1,
            at=at,
        ),
    ])

    records = db.query(DietRecord).filter(DietRecord.user_id == test_user.id).all()
    assets = (
        db.query(DietPhotoAsset)
        .filter(DietPhotoAsset.user_id == test_user.id)
        .order_by(DietPhotoAsset.ordinal.asc())
        .all()
    )
    assert len(records) == 1
    assert result.record is not None
    assert result.record.id == records[0].id
    assert result.record.client_action_id == "contextual-meal-photo:708"
    assert [asset.ordinal for asset in assets] == [0, 1]
    assert {asset.diet_record_id for asset in assets} == {records[0].id}
    assert [asset.id for asset in result.photo_assets] == [asset.id for asset in assets]
    # The structured vision result describes the whole session. Adding an
    # alternate angle must not double-count its nutrition.
    assert result.record.calories == 198


def test_same_message_photos_attach_to_one_confirmation_draft(
    db, test_user, tmp_path, monkeypatch
):
    first_url = _source_image_variant(
        tmp_path, monkeypatch, test_user.id, color=(20, 80, 220),
    )
    second_url = _source_image_variant(
        tmp_path, monkeypatch, test_user.id, color=(220, 180, 20),
    )
    at = datetime(2026, 7, 20, 3, 30, tzinfo=timezone.utc)
    service = ContextualMealPhotoService(db)

    result = service.capture_session([
        _capture(
            user_id=test_user.id,
            message_id=709,
            source_url=first_url,
            ordinal=0,
            at=at,
        ),
        _capture(
            user_id=test_user.id,
            message_id=709,
            source_url=second_url,
            ordinal=1,
            at=at,
        ),
    ])

    drafts = db.query(DietPhotoDraft).filter(
        DietPhotoDraft.user_id == test_user.id,
    ).all()
    assets = (
        db.query(DietPhotoAsset)
        .filter(DietPhotoAsset.user_id == test_user.id)
        .order_by(DietPhotoAsset.ordinal.asc())
        .all()
    )
    assert len(drafts) == 1
    assert result.photo_draft is not None
    assert result.photo_draft.token == drafts[0].token
    assert [asset.ordinal for asset in assets] == [0, 1]
    assert {asset.photo_draft_token for asset in assets} == {drafts[0].token}
    assert [asset.id for asset in result.photo_assets] == [asset.id for asset in assets]


def test_same_message_duplicate_photo_content_is_stored_once(
    db, test_user, tmp_path, monkeypatch
):
    source_url = _source_image(tmp_path, monkeypatch, test_user.id)
    at = datetime(2026, 7, 19, 16, 30, tzinfo=timezone.utc)
    service = ContextualMealPhotoService(db)

    result = service.capture_session([
        _capture(
            user_id=test_user.id,
            message_id=710,
            source_url=source_url,
            ordinal=0,
            at=at,
        ),
        _capture(
            user_id=test_user.id,
            message_id=710,
            source_url=source_url,
            ordinal=1,
            at=at,
        ),
    ])

    assert result.record is not None
    assert db.query(DietRecord).count() == 1
    assert db.query(DietPhotoAsset).count() == 1
    assert len(result.photo_assets) == 1


def test_postgres_capture_session_uses_transaction_advisory_lock(
    db, test_user, tmp_path, monkeypatch
):
    source_url = _source_image(tmp_path, monkeypatch, test_user.id)
    real_execute = db.execute
    statements: list[str] = []

    monkeypatch.setattr(db.get_bind().dialect, "name", "postgresql")

    def capture_execute(statement, params=None, *args, **kwargs):
        sql = str(statement)
        if "pg_advisory_xact_lock" in sql:
            statements.append(sql)
            return None
        return real_execute(statement, params, *args, **kwargs)

    monkeypatch.setattr(db, "execute", capture_execute)

    result = ContextualMealPhotoService(db).capture(_capture(
        user_id=test_user.id,
        message_id=711,
        source_url=source_url,
        ordinal=0,
        at=datetime(2026, 7, 19, 16, 30, tzinfo=timezone.utc),
    ))

    assert result.record is not None
    assert len(statements) == 1
    assert "pg_advisory_xact_lock" in statements[0]


def test_sqlite_capture_session_lock_serializes_same_source_message(db):
    active = 0
    max_active = 0
    state_lock = threading.Lock()

    def enter_guard():
        nonlocal active, max_active
        service = ContextualMealPhotoService(db)
        with service._capture_session_lock(9, 712):
            with state_lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.04)
            with state_lock:
                active -= 1

    threads = [threading.Thread(target=enter_guard) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert all(not thread.is_alive() for thread in threads)
    assert max_active == 1


def test_mixed_recognition_batch_cannot_auto_record_failed_image_as_food(
    db, test_user, tmp_path, monkeypatch
):
    first_url = _source_image_variant(
        tmp_path, monkeypatch, test_user.id, color=(220, 30, 30),
    )
    second_url = _source_image_variant(
        tmp_path, monkeypatch, test_user.id, color=(30, 180, 80),
    )
    at = datetime(2026, 7, 19, 16, 30, tzinfo=timezone.utc)

    with pytest.raises(
        ContextualMealPhotoServiceError,
        match="contextual_meal_photo_incomplete_batch_requires_confirmation",
    ):
        ContextualMealPhotoService(db).capture_session([
            _capture(
                user_id=test_user.id,
                message_id=713,
                source_url=first_url,
                ordinal=0,
                at=at,
            ),
            _capture(
                user_id=test_user.id,
                message_id=713,
                source_url=second_url,
                ordinal=1,
                at=at,
                classification="unknown",
            ),
        ])

    assert db.query(DietRecord).count() == 0
    assert db.query(DietPhotoAsset).count() == 0


def test_appending_photo_updates_record_aggregate_inside_session(
    db, test_user, tmp_path, monkeypatch
):
    first_url = _source_image_variant(
        tmp_path, monkeypatch, test_user.id, color=(220, 30, 30),
    )
    second_url = _source_image_variant(
        tmp_path, monkeypatch, test_user.id, color=(30, 180, 80),
    )
    at = datetime(2026, 7, 19, 16, 30, tzinfo=timezone.utc)
    service = ContextualMealPhotoService(db)
    first_capture = _capture(
        user_id=test_user.id,
        message_id=714,
        source_url=first_url,
        ordinal=0,
        at=at,
    )
    first = service.capture(first_capture)
    aggregate = {
        "foods": [
            *_vision_result()["foods"],
            {
                "name": "西兰花",
                "quantity": "约150g",
                "calories": 50,
                "protein": 4,
                "carbs": 8,
                "fat": 0.5,
                "fiber": 4,
                "confidence": 0.9,
            },
        ],
        "total_calories": 248,
        "total_protein": 41,
        "total_carbs": 8,
        "total_fat": 4.8,
        "total_fiber": 4,
        "health_tips": "补图后的完整估算。",
    }

    updated = service.capture_session([
        _capture(
            user_id=test_user.id,
            message_id=714,
            source_url=first_url,
            ordinal=0,
            at=at,
            vision_result=aggregate,
        ),
        _capture(
            user_id=test_user.id,
            message_id=714,
            source_url=second_url,
            ordinal=1,
            at=at,
            vision_result=aggregate,
        ),
    ])

    assert first.record is not None
    assert updated.record is not None
    assert updated.record.id == first.record.id
    assert updated.record.calories == 248
    assert updated.record.food_items == "鸡胸肉 约120g + 西兰花 约150g"
    assert updated.record.health_tips == "补图后的完整估算。"
    assert len(updated.photo_assets) == 2


def test_appending_photo_updates_draft_aggregate_inside_session(
    db, test_user, tmp_path, monkeypatch
):
    first_url = _source_image_variant(
        tmp_path, monkeypatch, test_user.id, color=(20, 80, 220),
    )
    second_url = _source_image_variant(
        tmp_path, monkeypatch, test_user.id, color=(220, 180, 20),
    )
    at = datetime(2026, 7, 20, 3, 30, tzinfo=timezone.utc)
    service = ContextualMealPhotoService(db)
    first = service.capture(_capture(
        user_id=test_user.id,
        message_id=715,
        source_url=first_url,
        ordinal=0,
        at=at,
    ))
    aggregate = {
        **_vision_result(),
        "foods": [{
            **_vision_result()["foods"][0],
            "calories": 260,
        }],
        "total_calories": 260,
        "health_tips": "补图后的草稿估算。",
    }

    updated = service.capture_session([
        _capture(
            user_id=test_user.id,
            message_id=715,
            source_url=first_url,
            ordinal=0,
            at=at,
            vision_result=aggregate,
        ),
        _capture(
            user_id=test_user.id,
            message_id=715,
            source_url=second_url,
            ordinal=1,
            at=at,
            vision_result=aggregate,
        ),
    ])

    assert first.photo_draft is not None
    assert updated.photo_draft is not None
    assert updated.photo_draft.token == first.photo_draft.token
    assert updated.photo_draft.recognition_result["calories"] == 260
    assert updated.photo_draft.recognition_result["health_tips"] == "补图后的草稿估算。"
    assert len(updated.photo_assets) == 2


def test_auto_capture_write_failure_falls_back_to_owner_bound_confirmation_draft(
    db, test_user, tmp_path, monkeypatch
):
    """A failed automatic write must remain recoverable in the current chat."""
    source_url = _source_image(tmp_path, monkeypatch, test_user.id)
    real_commit = db.commit
    commits = 0

    def fail_first_capture_commit():
        nonlocal commits
        commits += 1
        if commits == 1:
            raise RuntimeError("simulated automatic record write failure")
        return real_commit()

    monkeypatch.setattr(db, "commit", fail_first_capture_commit)
    service = ContextualMealPhotoService(db)
    capture = ContextualMealPhotoCapture(
        user_id=test_user.id,
        source_message_id=705,
        source_image_url=source_url,
        source_image_index=0,
        decision=_decision(at=datetime(2026, 7, 19, 16, 30, tzinfo=timezone.utc)),
        vision_result=_vision_result(),
    )

    result = service.capture(capture)

    assert result.record is None
    assert result.photo_draft is not None
    assert result.fallback_from_auto is True
    assert db.query(DietRecord).count() == 0
    asset = db.query(DietPhotoAsset).one()
    assert asset.photo_draft_token == result.photo_draft.token
    assert asset.diet_record_id is None
    assert asset.lifecycle == "pending"


def test_auto_capture_ambiguous_commit_keeps_the_committed_photo_asset(
    db, test_user, tmp_path, monkeypatch
):
    """A driver error after commit must not delete the committed image copy."""
    source_url = _source_image(tmp_path, monkeypatch, test_user.id)
    real_commit = db.commit
    commits = 0

    def commit_then_report_failure():
        nonlocal commits
        commits += 1
        if commits == 1:
            real_commit()
            raise RuntimeError("simulated commit acknowledgement failure")
        return real_commit()

    monkeypatch.setattr(db, "commit", commit_then_report_failure)
    service = ContextualMealPhotoService(db)
    capture = ContextualMealPhotoCapture(
        user_id=test_user.id,
        source_message_id=706,
        source_image_url=source_url,
        source_image_index=0,
        decision=_decision(at=datetime(2026, 7, 19, 16, 30, tzinfo=timezone.utc)),
        vision_result=_vision_result(),
    )

    result = service.capture(capture)

    assert result.record is not None
    assert result.replayed is True
    asset = db.query(DietPhotoAsset).one()
    from app.api import upload as upload_api

    relative_path = asset.storage_key.split("/files/", 1)[1]
    assert os.path.exists(os.path.join(upload_api.UPLOAD_DIR, relative_path))


def test_auto_capture_fallback_ambiguous_commit_keeps_the_pending_draft(
    db, test_user, tmp_path, monkeypatch
):
    """The recovery draft is equally protected from post-commit errors."""
    source_url = _source_image(tmp_path, monkeypatch, test_user.id)
    real_commit = db.commit
    commits = 0

    def auto_then_draft_commit_failure():
        nonlocal commits
        commits += 1
        if commits == 1:
            raise RuntimeError("automatic write failed")
        if commits == 2:
            real_commit()
            raise RuntimeError("draft commit acknowledgement failure")
        return real_commit()

    monkeypatch.setattr(db, "commit", auto_then_draft_commit_failure)
    service = ContextualMealPhotoService(db)
    capture = ContextualMealPhotoCapture(
        user_id=test_user.id,
        source_message_id=707,
        source_image_url=source_url,
        source_image_index=0,
        decision=_decision(at=datetime(2026, 7, 19, 16, 30, tzinfo=timezone.utc)),
        vision_result=_vision_result(),
    )

    result = service.capture(capture)

    assert result.photo_draft is not None
    assert result.replayed is True
    asset = db.query(DietPhotoAsset).one()
    from app.api import upload as upload_api

    relative_path = asset.storage_key.split("/files/", 1)[1]
    assert os.path.exists(os.path.join(upload_api.UPLOAD_DIR, relative_path))


def test_capture_rejects_a_chat_image_not_owned_by_the_target_user(
    db, test_user, tmp_path, monkeypatch
):
    source_url = _source_image(tmp_path, monkeypatch, test_user.id + 99)
    service = ContextualMealPhotoService(db)
    capture = ContextualMealPhotoCapture(
        user_id=test_user.id,
        source_message_id=703,
        source_image_url=source_url,
        source_image_index=0,
        decision=_decision(at=datetime(2026, 7, 19, 16, 30, tzinfo=timezone.utc)),
        vision_result=_vision_result(),
    )

    with pytest.raises(ContextualMealPhotoServiceError, match="owned_chat_image"):
        service.capture(capture)

    assert db.query(DietRecord).count() == 0
    assert db.query(DietPhotoAsset).count() == 0
