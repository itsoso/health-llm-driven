import base64
import json
from io import BytesIO
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.config import settings
from app.models.food_nutrition import FoodItem, FoodNutrient
from app.models.daily_health import DietPhotoAsset, DietPhotoDraft, DietRecord
from app.models.user import User
from app.models.user_profile import UserProfile
from app.services.agent_executor import (
    AgentExecutor,
    _contextual_meal_consumed_fraction,
    _write_receipt_from_tool_result,
)
from app.services.dynamic_card_persistence import cards_for_persistence
from app.services import chat_utils


VALID_PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z/QAAAABJRU5ErkJggg=="


def _png_base64(color: tuple[int, int, int]) -> str:
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color=color).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def _food_result():
    return {
        "success": True,
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
    }


def _nutrition_label_food_result():
    return {
        "success": True,
        "foods": [{
            "name": "洽洽小黄袋每日坚果",
            "quantity": "每100g",
            "quantity_grams": 100,
            "label_basis_grams": 100,
            "calories": 655,
            "protein": 14.5,
            "carbs": 16,
            "fat": 59,
            "fiber": 7.5,
            "confidence": 0.95,
            "source": "nutrition_label",
            "nutrition_basis": "nutrition_label_per_100g",
        }],
        "total_calories": 655,
        "total_protein": 14.5,
        "total_carbs": 16,
        "total_fat": 59,
        "total_fiber": 7.5,
    }


def _stream_from(fake_call_llm):
    async def fake_call_llm_stream(messages, tools):
        result = await fake_call_llm(messages, tools)
        content = result.get("content") or ""
        if content:
            yield {"type": "content", "text": content}
        if result.get("tool_calls"):
            yield {"type": "tool_calls", "tool_calls": result["tool_calls"]}
        yield {"type": "finish", "finish_reason": result.get("finish_reason")}

    return fake_call_llm_stream


def _food_photo_executor(db, tmp_path, monkeypatch):
    from app.api import upload as upload_api

    user = User(
        username="agent_food_photo",
        email="agent-food-photo@example.com",
        hashed_password="hashed_password",
        name="Agent 食物照片用户",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(UserProfile(user_id=user.id, manual_timezone="America/New_York"))
    db.commit()
    monkeypatch.setattr(chat_utils, "_UPLOAD_DIR", str(tmp_path / "chat"))
    monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(tmp_path / "uploads"))
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_source_message_id = 888
    executor._current_turn_image_urls = [
        chat_utils.upload_chat_image(VALID_PNG_BASE64, user.id, "png")
    ]
    executor._agent_kernel_reference_now = lambda: datetime(2026, 7, 19, 16, 30, tzinfo=timezone.utc)
    return executor, user


@pytest.mark.asyncio
async def test_image_nutrition_label_auto_save_ignores_redundant_incomplete_write(
    db, tmp_path, monkeypatch
):
    from app.services.ai.food_recognition import food_recognition_service

    executor, user = _food_photo_executor(db, tmp_path, monkeypatch)
    llm_calls = 0

    async def recognize_food(*_args, **_kwargs):
        return _nutrition_label_food_result()

    async def fake_call_llm(messages, tools):
        nonlocal llm_calls
        llm_calls += 1
        if llm_calls == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [{
                    "id": "redundant-incomplete-diet-write",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps({
                            "record_type": "diet",
                            "data": {
                                "meal_type": "snack",
                                "food_items": "坚果 20g",
                            },
                        }, ensure_ascii=False),
                    },
                }],
            }
        return {
            "content": "已按营养成分表记录这餐。",
            "finish_reason": "stop",
        }

    monkeypatch.setattr(
        food_recognition_service,
        "recognize_food_from_base64",
        recognize_food,
    )
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr(
        "app.services.agent_executor.get_health_tools",
        lambda subset=None: [],
    )
    monkeypatch.setattr(executor, "_call_llm", fake_call_llm)
    monkeypatch.setattr(executor, "_call_llm_stream", _stream_from(fake_call_llm))

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="记录这餐 20 克坚果，并按营养成分表计算。",
            user_auth_token="test-token",
            images=[{"base64": VALID_PNG_BASE64, "type": "png"}],
            client_turn_id="turn-nutrition-label-auto-save",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    done = next(event for event in events if event.get("event") == "done")
    record = db.query(DietRecord).filter(DietRecord.user_id == user.id).one()
    photo = db.query(DietPhotoAsset).filter(
        DietPhotoAsset.user_id == user.id,
        DietPhotoAsset.diet_record_id == record.id,
    ).one()
    diet_cards = [
        card
        for card in done["data"].get("cards", [])
        if card.get("type") == "diet_draft"
    ]

    assert record.food_items == "洽洽小黄袋每日坚果 20g"
    assert record.calories == pytest.approx(131)
    assert record.protein == pytest.approx(2.9)
    assert photo.diet_record_id == record.id
    assert "这次没有写入" not in rendered
    assert "另有 1 项记录已完成并取得回执" not in rendered
    assert done["data"]["completion_status"] == "complete"
    assert len(done["data"]["write_receipts"]) == 1
    assert done["data"]["write_receipts"][0]["resource_id"] == str(record.id)
    assert len(diet_cards) == 1
    assert diet_cards[0]["data"]["record_id"] == record.id
    assert diet_cards[0]["data"]["photo_asset_id"] == photo.id


@pytest.mark.asyncio
async def test_structured_food_vision_does_not_save_label_basis_as_consumed_amount(
    db, tmp_path, monkeypatch
):
    from app.services.ai.food_recognition import food_recognition_service

    executor, user = _food_photo_executor(db, tmp_path, monkeypatch)

    async def recognize_food(*_args, **_kwargs):
        return _nutrition_label_food_result()

    monkeypatch.setattr(
        food_recognition_service,
        "recognize_food_from_base64",
        recognize_food,
    )

    context = await executor._analyze_food_images_with_structured_vision(
        "记录这餐坚果",
        [{"base64": VALID_PNG_BASE64, "type": "png"}],
    )

    assert db.query(DietRecord).filter(DietRecord.user_id == user.id).count() == 0
    assert context is not None
    assert "还缺少实际食用重量" in context
    assert "请补充你实际吃了多少克" in context


@pytest.mark.asyncio
async def test_structured_food_vision_scales_label_locally_from_user_amount(
    db, tmp_path, monkeypatch
):
    from app.services.ai.food_recognition import food_recognition_service

    executor, user = _food_photo_executor(db, tmp_path, monkeypatch)
    captured_kwargs = {}

    async def recognize_food(*_args, **kwargs):
        captured_kwargs.update(kwargs)
        return {
            "success": True,
            "foods": [{
                "name": "洽洽小黄袋每日坚果",
                "quantity": "每100g",
                "quantity_grams": 100,
                "label_basis_grams": 100,
                "calories": 655,
                "protein": 15,
                "carbs": 15,
                "fat": 60,
                "fiber": 7.5,
                "confidence": 0.95,
                "source": "nutrition_label",
                "nutrition_basis": "nutrition_label_per_100g",
            }],
        }

    monkeypatch.setattr(
        food_recognition_service,
        "recognize_food_from_base64",
        recognize_food,
    )

    context = await executor._analyze_food_images_with_structured_vision(
        "记录这餐，吃了 20 克坚果",
        [{"base64": VALID_PNG_BASE64, "type": "png"}],
    )

    record = db.query(DietRecord).filter(DietRecord.user_id == user.id).one()
    assert context is not None
    assert "user_context" not in captured_kwargs
    assert record.food_items == "洽洽小黄袋每日坚果 20g"
    assert record.calories == pytest.approx(131)
    assert record.protein == pytest.approx(3)
    assert record.carbs == pytest.approx(3)
    assert record.fat == pytest.approx(12)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("记录这餐，吃了三分之一", (1 / 3, "三分之一")),
        ("这份只吃了1/3", (1 / 3, "1/3")),
        ("这餐应该只吃三分之一吗？", None),
        ("这餐吃了1/2还是1/3", None),
        ("这餐吃了1/2，实际是1/3", None),
        ("这餐吃了1/2并不准确", None),
        ("这餐吃了1/2吗帮我记录", None),
        ("这餐吃了1/2，不要记录", None),
        ("这餐吃了1/2，取消记录", None),
        ("这餐吃了1/2，撤回记录", None),
        ("这餐吃了1/2，我反悔了", None),
        ("这餐吃了1/2，先不记录", None),
        ("这餐吃了1/2，不想记录", None),
        ("这餐吃了1/2，我没有让你记录", None),
        ("这餐吃了1/2，并非让你记录", None),
        ("这餐应该吃了1/2", None),
        ("这餐好像吃了1/2", None),
        ("这餐估计吃了1/2", None),
        ("这餐差不多吃了1/2", None),
        ("这餐吃了1/2吧", None),
        ("这餐吃了1/2，对吧", None),
        ("这餐吃了1/2，莫记录", None),
        ("假设这餐吃了1/2", None),
        ("这餐约吃了1/2", None),
        ("难道这餐吃了1/2", None),
        ("举例：这餐吃了1/2", None),
        ("这餐本来吃了1/2，后来全吃完了", None),
        ("这餐吃了1/2，勿记录", None),
        ("这餐吃了1/2，暂停记录", None),
        ("这餐吃了1/2，收回记录", None),
        ("这餐吃了1/2，撤掉记录", None),
        ("这餐吃了1/2，作罢", None),
        ("倘若这餐吃了1/2", None),
        ("这餐最多吃了1/2", None),
        ("这餐大致吃了1/2", None),
        ("这餐估摸吃了1/2", None),
        ("这餐吃了1/2，可否记录", None),
        ("谁说这餐吃了1/2", None),
        ("我否认这餐吃了1/2", None),
        ("演示：这餐吃了1/2", None),
        ("复述：这餐吃了1/2", None),
        ("小王说这餐吃了1/2", None),
        ("这餐打算只吃1/2", None),
        ("这餐计划只吃1/2", None),
        ("这餐准备只吃1/2", None),
        ("这餐想只吃1/2", None),
        ("记录这餐，吃了三分之一的蛋糕", None),
        ("吃了三分之一的蛋糕", None),
    ],
)
def test_contextual_meal_fraction_only_scales_an_explicit_whole_meal(
    message, expected
):
    parsed = _contextual_meal_consumed_fraction(message)
    if expected is None:
        assert parsed is None
    else:
        assert parsed is not None
        assert parsed[0] == pytest.approx(expected[0])
        assert parsed[1] == expected[1]


@pytest.mark.parametrize(
    "message",
    [
        "这餐吃了1/2，取消记录",
        "假设这餐吃了1/2",
        "这餐打算只吃1/2",
        "这餐吃了1/2，莫记录",
        "这餐50%",
        "这餐0.5",
        "这餐½",
        "这餐二分之一",
        "这餐吃了１／２，取消记录",
        "这餐吃了1／2，莫记录",
        "这餐百分之五十",
        "这餐五成",
        "这餐1比2",
        "这餐半",
        "这餐百分50",
        "这餐1:2",
        "这餐１：２",
        "晚餐吃了1÷2，取消修改",
        "晚餐吃了0点5，取消修改",
        "晚餐吃了百分之 50，取消修改",
        "晚餐吃了一比二，取消修改",
        "晚餐吃了1∶2，取消修改",
        "取消记录",
        "这餐莫记录",
        "这餐勿记录",
        "这餐别再记录",
        "这餐别帮我记录",
        "这餐不要给我记录",
        "这餐别把它记录下来",
        "这餐吃了1÷2，别帮我记录",
        "这餐0点5，不要给我记录",
    ],
)
def test_unsafe_photo_fraction_language_never_auto_captures(
    message, db, tmp_path, monkeypatch
):
    executor, _user = _food_photo_executor(db, tmp_path, monkeypatch)
    recognition = _food_result()

    result = executor._capture_contextual_meal_photo(
        message,
        recognition,
        image_index=0,
    )

    assert result is None
    assert db.query(DietRecord).count() == 0
    assert db.query(DietPhotoAsset).count() == 0
    assert db.query(DietPhotoDraft).count() == 0
    assert recognition["contextual_capture_write_blocked_reason"] in {
        "ambiguous_fraction",
        "cancelled",
    }
    assert executor._turn_contextual_diet_write_blocked_reason in {
        "ambiguous_fraction",
        "cancelled",
    }
    if any(token in message for token in ("取消", "莫", "勿", "别", "不要")):
        assert recognition["contextual_capture_write_blocked_reason"] == "cancelled"
    prompt_context = executor._format_food_recognition_for_agent(
        message,
        recognition,
        contextual_capture=result,
    )
    assert "严禁调用 health_record" in prompt_context
    assert (
        "没有通过明确事实校验" in prompt_context
        or "明确取消" in prompt_context
    )


@pytest.mark.asyncio
async def test_unsafe_photo_fraction_closes_model_diet_write_adapter(
    db, tmp_path, monkeypatch
):
    executor, _user = _food_photo_executor(db, tmp_path, monkeypatch)
    recognition = _food_result()
    executor._capture_contextual_meal_photo(
        "这餐吃了1/2，取消记录",
        recognition,
        image_index=0,
    )
    post = AsyncMock()
    monkeypatch.setattr(executor, "_api_post_json", post)

    result = await executor._exec_health_record("http://test", {}, {
        "record_type": "diet",
        "data": {
            "meal_type": "dinner",
            "food_items": "鸡胸肉",
            "calories": 198,
        },
    })

    assert "contextual_diet_write_blocked" in result
    post.assert_not_awaited()
    assert db.query(DietRecord).count() == 0

    manage_result = await executor._exec_health_manage("http://test", {}, {
        "record_type": "diet",
        "operation": "update",
        "record_id": 123,
        "data": {
            "meal_type": "dinner",
            "food_items": "鸡胸肉",
            "calories": 198,
        },
    })

    assert "contextual_diet_write_blocked" in manage_result
    post.assert_not_awaited()
    assert db.query(DietRecord).count() == 0


def test_agent_auto_captures_empty_high_confidence_lunch_photo_with_receipt(
    db, tmp_path, monkeypatch
):
    executor, user = _food_photo_executor(db, tmp_path, monkeypatch)

    result = executor._capture_contextual_meal_photo("", _food_result(), image_index=0)

    assert result is not None
    assert result.record is not None
    assert result.record.user_id == user.id
    assert db.query(DietRecord).count() == 1
    assert executor._turn_contextual_diet_receipts == [{
        "operation_id": f"contextual_meal_photo:{result.record.id}",
        "status": "verified",
        "resource_type": "diet_record",
        "resource_id": str(result.record.id),
        "date": result.record.record_date.isoformat(),
        "verified": True,
    }]
    card = executor._turn_contextual_diet_cards[0]
    assert card["type"] == "diet_draft"
    assert card["data"]["recorded"] is True
    assert card["data"]["record_id"] == result.record.id
    adjust_action = card["actions"][0]
    assert adjust_action["action"] == "ui.inline.expand"
    assert adjust_action["label"] == "调整记录"
    assert adjust_action["payload"]["target"] == "adjust_record"
    assert adjust_action["payload"]["patch"]["adjust_record"] == {
        "record_id": result.record.id,
        "meal_type": "lunch",
        "food_items": result.record.food_items,
        "calories": result.record.calories,
        "protein": result.record.protein,
        "carbs": result.record.carbs,
        "fat": result.record.fat,
    }
    assert "photo_url" not in cards_for_persistence([card])[0]["data"]


def test_agent_analysis_intent_never_auto_captures_food_photo(db, tmp_path, monkeypatch):
    executor, _user = _food_photo_executor(db, tmp_path, monkeypatch)

    result = executor._capture_contextual_meal_photo("请分析这张图片", _food_result(), image_index=0)

    assert result is None
    assert db.query(DietRecord).count() == 0
    prompt_context = executor._format_food_recognition_for_agent(
        "请分析这张图片", _food_result(), contextual_capture=result,
    )
    assert "严禁调用 health_record" in prompt_context


def test_agent_creates_owner_bound_confirmation_card_outside_meal_window(
    db, tmp_path, monkeypatch
):
    executor, _user = _food_photo_executor(db, tmp_path, monkeypatch)
    executor._agent_kernel_reference_now = lambda: datetime(2026, 7, 20, 3, 30, tzinfo=timezone.utc)

    result = executor._capture_contextual_meal_photo("", _food_result(), image_index=0)

    assert result is not None
    assert result.record is None
    assert result.photo_draft is not None
    card = executor._turn_contextual_diet_cards[0]
    assert card["type"] == "diet_draft"
    assert card["data"]["photo_asset_id"]
    assert "signature=" in card["data"]["photo_url"]
    # Dynamic-card data is user-facing. Keep its number representation aligned
    # with the product display contract, while the action payload keeps raw data.
    assert isinstance(card["data"]["protein"], int)
    assert card["data"]["protein"] == 37
    assert isinstance(card["data"]["fiber"], int)
    assert card["data"]["fiber"] == 0
    action = card["actions"][0]
    assert action["action"] == "diet_record.create"
    assert action["payload"]["record"]["protein"] == 37.0
    assert action["payload"]["record"]["source"] == "chat_photo"
    assert action["payload"]["record"]["photo_draft_token"] == result.photo_draft.token
    assert "photo_url" not in cards_for_persistence([card])[0]["data"]


def test_agent_explicit_food_photo_write_records_outside_meal_window(
    db, tmp_path, monkeypatch
):
    executor, user = _food_photo_executor(db, tmp_path, monkeypatch)
    executor._agent_kernel_reference_now = lambda: datetime(2026, 7, 20, 3, 30, tzinfo=timezone.utc)

    result = executor._capture_contextual_meal_photo("记录这餐", _food_result(), image_index=0)

    assert result is not None
    assert result.record is not None
    assert result.record.user_id == user.id
    assert result.record.meal_type == "snack"
    assert db.query(DietRecord).count() == 1
    assert executor._turn_contextual_diet_receipts == [{
        "operation_id": f"contextual_meal_photo:{result.record.id}",
        "status": "verified",
        "resource_type": "diet_record",
        "resource_id": str(result.record.id),
        "date": result.record.record_date.isoformat(),
        "verified": True,
    }]
    card = executor._turn_contextual_diet_cards[0]
    assert card["data"]["recorded"] is True
    assert card["actions"][0]["action"] == "ui.inline.expand"


def test_agent_missing_any_food_confidence_requires_confirmation(
    db, tmp_path, monkeypatch
):
    executor, _user = _food_photo_executor(db, tmp_path, monkeypatch)
    recognition = _food_result()
    recognition["foods"].append({
        "name": "青菜",
        "quantity": "约100g",
        "calories": 20,
        "protein": 2,
        "carbs": 3,
        "fat": 0,
        "fiber": 2,
        "confidence": None,
    })

    result = executor._capture_contextual_meal_photo(
        "记录这餐",
        recognition,
        image_index=0,
    )

    assert result is not None
    assert result.record is None
    assert result.photo_draft is not None
    assert db.query(DietRecord).count() == 0


def test_agent_photo_persistence_failure_never_falls_back_to_unverified_write(
    db, tmp_path, monkeypatch
):
    from app.services.contextual_meal_photo_service import (
        ContextualMealPhotoService,
    )

    executor, _user = _food_photo_executor(db, tmp_path, monkeypatch)

    def fail_capture(*_args, **_kwargs):
        raise OSError("simulated private image storage failure")

    monkeypatch.setattr(ContextualMealPhotoService, "capture_session", fail_capture)
    recognition = _food_result()

    capture = executor._capture_contextual_meal_photo(
        "记录这餐",
        recognition,
        image_index=0,
    )
    context = executor._format_food_recognition_for_agent(
        "记录这餐",
        recognition,
        contextual_capture=capture,
    )

    assert capture is None
    assert db.query(DietRecord).count() == 0
    assert "严禁调用 health_record" in context
    assert "请调用 health_record" not in context


@pytest.mark.asyncio
async def test_agent_applies_consumed_fraction_before_contextual_photo_write(
    db, tmp_path, monkeypatch
):
    from app.services.ai.food_recognition import food_recognition_service

    executor, user = _food_photo_executor(db, tmp_path, monkeypatch)

    async def recognize(*_args, **_kwargs):
        return _food_result()

    monkeypatch.setattr(
        food_recognition_service,
        "recognize_food_from_base64",
        recognize,
    )

    context = await executor._analyze_food_images_with_structured_vision(
        "记录这餐，吃了三分之一",
        [{"base64": VALID_PNG_BASE64, "type": "png"}],
    )

    records = db.query(DietRecord).filter(DietRecord.user_id == user.id).all()
    assert len(records) == 1
    record = records[0]
    assert record.calories == pytest.approx(66)
    assert record.protein == pytest.approx(12.3)
    assert record.fat == pytest.approx(1.4)
    assert "按实际食用三分之一计" in record.food_items
    assert executor._turn_contextual_diet_consumed_fraction == pytest.approx(1 / 3)
    assert len(executor._turn_contextual_diet_receipts) == 1
    assert len(executor._turn_contextual_diet_cards) == 1
    assert context is not None
    assert "份量已在首次写入中按三分之一修正" in context
    assert "不要再次调用 health_record 或 health_manage 写入" in context


@pytest.mark.asyncio
async def test_multi_image_turn_persists_once_and_emits_one_multi_photo_card(
    db, tmp_path, monkeypatch
):
    from app.services.ai.food_recognition import food_recognition_service

    executor, user = _food_photo_executor(db, tmp_path, monkeypatch)
    second_image = _png_base64((20, 160, 80))
    executor._current_turn_image_urls.append(
        chat_utils.upload_chat_image(second_image, user.id, "png"),
    )
    results = [
        _food_result(),
        {
            "success": True,
            "foods": [{
                "name": "西兰花",
                "quantity": "约150g",
                "calories": 50,
                "protein": 4,
                "carbs": 8,
                "fat": 0.5,
                "fiber": 4,
                "confidence": 0.9,
            }],
        },
    ]

    async def recognize(*_args, **_kwargs):
        return results.pop(0)

    monkeypatch.setattr(
        food_recognition_service,
        "recognize_food_from_base64",
        recognize,
    )

    context = await executor._analyze_food_images_with_structured_vision(
        "记录这餐",
        [
            {"base64": VALID_PNG_BASE64, "type": "png"},
            {"base64": second_image, "type": "png"},
        ],
    )

    records = db.query(DietRecord).filter(DietRecord.user_id == user.id).all()
    assets = (
        db.query(DietPhotoAsset)
        .filter(DietPhotoAsset.user_id == user.id)
        .order_by(DietPhotoAsset.ordinal.asc())
        .all()
    )
    assert len(records) == 1
    assert records[0].calories == 248
    assert len(assets) == 2
    assert {asset.diet_record_id for asset in assets} == {records[0].id}
    assert len(executor._turn_contextual_diet_receipts) == 1
    assert len(executor._turn_contextual_diet_cards) == 1
    card = executor._turn_contextual_diet_cards[0]
    expected_capture_session_id = f"meal-photo:{assets[0].origin_message_id}"
    assert card["data"]["card_id"] == (
        f"diet-capture:{expected_capture_session_id}"
    )
    assert card["data"]["capture_session_id"] == expected_capture_session_id
    assert card["data"]["photo_asset_ids"] == [asset.id for asset in assets]
    assert len(card["data"]["photo_urls"]) == 2
    assert context is not None
    assert "不要再次调用 health_record" in context


@pytest.mark.asyncio
async def test_multi_image_partial_recognition_forces_one_confirmation_batch(
    db, tmp_path, monkeypatch
):
    from app.services.ai.food_recognition import food_recognition_service

    executor, user = _food_photo_executor(db, tmp_path, monkeypatch)
    second_image = _png_base64((180, 80, 40))
    executor._current_turn_image_urls.append(
        chat_utils.upload_chat_image(second_image, user.id, "png"),
    )
    results = [
        _food_result(),
        {"success": False, "error": "vision provider timeout"},
    ]

    async def recognize(*_args, **_kwargs):
        return results.pop(0)

    monkeypatch.setattr(
        food_recognition_service,
        "recognize_food_from_base64",
        recognize,
    )

    context = await executor._analyze_food_images_with_structured_vision(
        "记录这餐",
        [
            {"base64": VALID_PNG_BASE64, "type": "png"},
            {"base64": second_image, "type": "png"},
        ],
    )

    assets = (
        db.query(DietPhotoAsset)
        .filter(DietPhotoAsset.user_id == user.id)
        .order_by(DietPhotoAsset.ordinal.asc())
        .all()
    )
    assert db.query(DietRecord).filter(DietRecord.user_id == user.id).count() == 0
    assert db.query(DietPhotoDraft).filter(DietPhotoDraft.user_id == user.id).count() == 1
    assert [asset.classification for asset in assets] == ["food", "unknown"]
    assert {asset.photo_draft_token for asset in assets} == {
        db.query(DietPhotoDraft).filter(DietPhotoDraft.user_id == user.id).one().token
    }
    assert len(executor._turn_contextual_diet_receipts) == 0
    assert len(executor._turn_contextual_diet_cards) == 1
    card = executor._turn_contextual_diet_cards[0]
    assert card["data"]["media_stage"] == "pending_confirmation"
    assert card["data"]["capture_session_id"] == (
        f"meal-photo:{assets[0].origin_message_id}"
    )
    assert context is not None
    assert "确认" in context


@pytest.mark.asyncio
async def test_more_than_three_images_never_partially_records(
    db, tmp_path, monkeypatch
):
    from app.services.ai.food_recognition import food_recognition_service

    executor, _user = _food_photo_executor(db, tmp_path, monkeypatch)

    async def unexpected_recognition(*_args, **_kwargs):
        raise AssertionError("over-limit input must not call vision")

    monkeypatch.setattr(
        food_recognition_service,
        "recognize_food_from_base64",
        unexpected_recognition,
    )
    response = await executor._analyze_food_images_with_structured_vision(
        "记录这餐",
        [
            {"base64": f"image-{index}", "type": "png"}
            for index in range(4)
        ],
    )

    assert response is not None
    assert "超过 3 张" in response
    assert "没有写入" in response
    assert db.query(DietRecord).count() == 0


@pytest.mark.asyncio
async def test_contextual_fraction_update_replays_receipt_without_second_write(
    db, tmp_path, monkeypatch
):
    executor, _user = _food_photo_executor(db, tmp_path, monkeypatch)
    capture = executor._capture_contextual_meal_photo(
        "记录这餐",
        _food_result(),
        image_index=0,
    )
    assert capture is not None
    assert capture.record is not None
    executor._turn_contextual_diet_consumed_fraction = 1 / 3

    async def unexpected_put(*_args, **_kwargs):
        raise AssertionError("same-turn contextual diet update must not reach the API")

    monkeypatch.setattr(executor, "_api_put", unexpected_put)

    update_args = {
        "record_type": "diet",
        "operation": "update",
        "record_id": capture.record.id,
        "data": {"calories": 22},
    }
    result = await executor._exec_health_manage(
        "https://health.example.test",
        {"Authorization": "Bearer test"},
        update_args,
    )

    payload = json.loads(result)
    assert payload == {
        "id": capture.record.id,
        "record_id": capture.record.id,
        "resource_type": "diet_record",
        "record_date": capture.record.record_date.isoformat(),
        "operation_id": f"contextual_meal_photo:{capture.record.id}",
        "status": "recorded",
        "replayed": True,
        "portion_adjustment_applied": True,
    }
    receipt = _write_receipt_from_tool_result(
        "health_manage",
        update_args,
        result,
    )
    assert receipt is not None
    assert receipt["operation_id"] == (
        f"contextual_meal_photo:{capture.record.id}"
    )
    assert receipt["status"] == "verified"
    assert receipt["date"] == capture.record.record_date.isoformat()
    db.refresh(capture.record)
    assert capture.record.calories == pytest.approx(198)


@pytest.mark.asyncio
async def test_contextual_meal_update_replays_receipt_without_portion_adjustment(
    db, tmp_path, monkeypatch
):
    executor, _user = _food_photo_executor(db, tmp_path, monkeypatch)
    capture = executor._capture_contextual_meal_photo(
        "记录这餐",
        _food_result(),
        image_index=0,
    )
    assert capture is not None
    assert capture.record is not None
    assert executor._turn_contextual_diet_consumed_fraction is None

    async def unexpected_put(*_args, **_kwargs):
        raise AssertionError("same-turn contextual diet update must not reach the API")

    monkeypatch.setattr(executor, "_api_put", unexpected_put)

    result = await executor._exec_health_manage(
        "https://health.example.test",
        {"Authorization": "Bearer test"},
        {
            "record_type": "diet",
            "operation": "update",
            "record_id": capture.record.id,
            "data": {"food_items": "模型重复整理的同一餐"},
        },
    )

    assert json.loads(result) == {
        "id": capture.record.id,
        "record_id": capture.record.id,
        "resource_type": "diet_record",
        "record_date": capture.record.record_date.isoformat(),
        "operation_id": f"contextual_meal_photo:{capture.record.id}",
        "status": "recorded",
        "replayed": True,
    }


@pytest.mark.asyncio
async def test_contextual_meal_update_never_mutates_a_different_historical_record(
    db, tmp_path, monkeypatch
):
    executor, user = _food_photo_executor(db, tmp_path, monkeypatch)
    capture = executor._capture_contextual_meal_photo(
        "记录这餐",
        _food_result(),
        image_index=0,
    )
    assert capture is not None
    assert capture.record is not None

    historical = DietRecord(
        user_id=user.id,
        record_date=capture.record.record_date,
        meal_type="breakfast",
        food_items="历史早餐",
        calories=500,
    )
    db.add(historical)
    db.commit()
    db.refresh(historical)

    async def unexpected_put(*_args, **_kwargs):
        raise AssertionError("contextual meal turn must not update an older record")

    monkeypatch.setattr(executor, "_api_put", unexpected_put)

    result = await executor._exec_health_manage(
        "https://health.example.test",
        {"Authorization": "Bearer test"},
        {
            "record_type": "diet",
            "operation": "update",
            "record_id": historical.id,
            "data": {"calories": 22},
        },
    )

    payload = json.loads(result)
    assert payload["record_id"] == capture.record.id
    assert payload["operation_id"] == (
        f"contextual_meal_photo:{capture.record.id}"
    )
    assert payload["replayed"] is True
    db.refresh(historical)
    assert historical.calories == pytest.approx(500)


def test_contextual_meal_capture_replays_after_executor_restart(
    db, tmp_path, monkeypatch
):
    executor, user = _food_photo_executor(db, tmp_path, monkeypatch)
    first = executor._capture_contextual_meal_photo(
        "记录这餐",
        _food_result(),
        image_index=0,
    )
    assert first is not None
    assert first.record is not None

    restarted = AgentExecutor(db)
    restarted._current_user_id = user.id
    restarted._current_turn_source_message_id = (
        executor._current_turn_source_message_id
    )
    restarted._current_turn_image_urls = list(
        executor._current_turn_image_urls
    )
    restarted._agent_kernel_reference_now = (
        executor._agent_kernel_reference_now
    )

    replay = restarted._capture_contextual_meal_photo(
        "记录这餐",
        _food_result(),
        image_index=0,
    )

    assert replay is not None
    assert replay.replayed is True
    assert replay.record is not None
    assert replay.record.id == first.record.id
    assert db.query(DietRecord).filter(DietRecord.user_id == user.id).count() == 1
    assert restarted._turn_contextual_diet_receipts == [{
        "operation_id": f"contextual_meal_photo:{first.record.id}",
        "status": "verified",
        "resource_type": "diet_record",
        "resource_id": str(first.record.id),
        "date": first.record.record_date.isoformat(),
        "verified": True,
    }]
    assert len(restarted._turn_contextual_diet_cards) == 1


def test_agent_auto_capture_failure_surfaces_the_recoverable_confirmation_card(
    db, tmp_path, monkeypatch
):
    executor, _user = _food_photo_executor(db, tmp_path, monkeypatch)
    real_commit = db.commit
    commits = 0

    def fail_first_capture_commit():
        nonlocal commits
        commits += 1
        if commits == 1:
            raise RuntimeError("simulated automatic record write failure")
        return real_commit()

    monkeypatch.setattr(db, "commit", fail_first_capture_commit)
    result = executor._capture_contextual_meal_photo("", _food_result(), image_index=0)

    assert result is not None
    assert result.record is None
    assert result.photo_draft is not None
    card = executor._turn_contextual_diet_cards[0]
    assert card["type"] == "diet_draft"
    assert card["data"]["auto_save_fallback"] is True
    assert card["actions"][0]["action"] == "diet_record.create"


@pytest.mark.asyncio
async def test_structured_food_vision_calibrates_before_building_agent_context(
    db, monkeypatch
):
    from app.services.ai.food_recognition import food_recognition_service

    db.add(FoodItem(
        food_id="cfc:chicken_breast",
        canonical_name="鸡胸肉",
        aliases=["鸡肉"],
        calibration_names=["鸡胸肉"],
        locale="zh-CN",
        source="china_food_composition",
        source_ref="test-fixture",
    ))
    db.add(FoodNutrient(
        food_id="cfc:chicken_breast",
        kcal_per_100g=165.0,
        protein_g_per_100g=31.0,
        carbs_g_per_100g=0.0,
        fat_g_per_100g=3.6,
        fiber_g_per_100g=0.0,
        source="china_food_composition",
        source_ref="test-fixture",
    ))
    db.commit()

    async def recognize(*_args, **_kwargs):
        return {
            "success": True,
            "foods": [{
                "name": "鸡胸肉",
                "quantity": "200g",
                "calories": 999,
                "protein": 1,
                "carbs": 50,
                "fat": 40,
                "fiber": 8,
                "confidence": 0.9,
            }],
            "total_calories": 999,
            "total_protein": 1,
            "total_carbs": 50,
            "total_fat": 40,
            "total_fiber": 8,
        }

    monkeypatch.setattr(food_recognition_service, "recognize_food_from_base64", recognize)

    context = await AgentExecutor(db)._analyze_food_images_with_structured_vision(
        "记录午餐",
        [{"base64": "ZmFrZQ==", "type": "jpeg"}],
    )

    assert context is not None
    assert "鸡胸肉 200g 约330kcal" in context
    assert '"food_id": "cfc:chicken_breast"' in context
    assert '"source": "china_food_composition"' in context
    assert '"ai_recognized": 1' in context


@pytest.mark.asyncio
async def test_generic_vision_fallback_does_not_repeat_structured_recognition(
    db, monkeypatch
):
    executor = AgentExecutor(db)
    calls = 0

    async def no_structured_result(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return None

    class FailedResponse:
        status_code = 503
        text = "unavailable"

    class FakeHttpClient:
        async def post(self, *_args, **_kwargs):
            return FailedResponse()

    monkeypatch.setattr(executor, "_analyze_food_images_with_structured_vision", no_structured_result)
    monkeypatch.setattr(settings, "llm_vision_base_url", "https://vision.example.test")
    monkeypatch.setattr(settings, "llm_vision_api_key", "test-key")
    executor._http_client = FakeHttpClient()

    result = await executor._analyze_image_with_vision(
        "帮我看看",
        [{"base64": "ZmFrZQ==", "type": "jpeg"}],
    )

    assert result is None
    assert calls == 1


def test_commercial_multimodal_food_photos_still_use_structured_preprocessing(
    db, monkeypatch
):
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_should_send_raw_images_to_primary_model", lambda _user_id: True)

    assert executor._should_preprocess_attached_images(1, "记录这张午餐照片") is True
    assert executor._should_preprocess_attached_images(1, "请分析这些图片") is True
    assert executor._should_preprocess_attached_images(1, "帮我记一下") is True
    assert executor._should_preprocess_attached_images(1, "拍照记餐") is True
    assert executor._should_preprocess_attached_images(1, "看看这张风景照片") is False


def test_explicit_aigc_photo_request_never_enters_food_preprocessing(db, monkeypatch):
    """A creative request must not turn an attached image into a diet candidate."""
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_should_send_raw_images_to_primary_model", lambda _user_id: False)

    assert executor._should_preprocess_attached_images(
        1,
        "基于这张照片生成今天活动的短视频，以此照片为开头。",
    ) is False
