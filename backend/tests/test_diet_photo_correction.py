"""Synthetic photo-to-editor proposals never authorize automatic record writes."""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.diet_photo_correction import save_recognition, build_correction_proposal

NOW = datetime(2031, 4, 4, 5, tzinfo=timezone.utc)
REQUEST = "基于识别的这一餐来修改今天午餐记录"


@pytest.fixture
def context(db, auth_user_and_headers):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.models.daily_health import DietRecord
    user, _ = auth_user_and_headers
    conv = AgentConversation(user_id=user.id)
    db.add(conv)
    db.flush()
    source = AgentMessage(conversation_id=conv.id, role="user", content="分析这张照片",
                          image_url='["/synthetic/owned-photo.jpg"]')
    db.add(source)
    db.flush()
    assert save_recognition(db, user.id, source.id, "牛肉面 约1碗", NOW)
    db.add(AgentMessage(conversation_id=conv.id, role="assistant", content="识别结果",
                       meta={"client_turn_finalized": True, "completion_status": "complete"}))
    db.flush()
    current = AgentMessage(conversation_id=conv.id, role="user", content=REQUEST)
    target = DietRecord(user_id=user.id, record_date=NOW.date(), meal_type="lunch",
                        food_items="汤一碗", calories=100, protein=5, carbs=10, fat=4)
    db.add_all([current, target])
    db.commit()
    return user, conv, source, current, target


def proposal(db, context, text=REQUEST, now=NOW):
    user, conv, _, current, _ = context
    return build_correction_proposal(db, user.id, conv.id, current.id, text, now, "Asia/Shanghai")


def test_photo_reference_proposes_unique_owned_meal_without_changing_it(db, context):
    result = proposal(db, context)
    assert result["status"] == "waiting_for_user"
    seed = result["cards"][0]["data"]["adjust_record"]
    assert seed["record_id"] == context[-1].id
    assert seed["food_items"] == "汤一碗" and seed["proposed_food_items"] == "牛肉面 约1碗"
    assert "updated_at" in seed
    assert context[-1].food_items == "汤一碗" and context[-1].calories == 100
    assert "尚未修改" in result["reply"]


@pytest.mark.parametrize("text", ["不要" + REQUEST, "假如" + REQUEST, "朋友说：" + REQUEST,
                                REQUEST.replace("今天", "朋友今天"), REQUEST + "，删除其他记录"])
def test_non_authorizing_or_extra_operands_do_not_start_read(db, context, text):
    assert proposal(db, context, text) is None


@pytest.mark.parametrize("damage", ["food", "image", "expired", "missing", "intervening"])
def test_source_must_be_signed_fresh_and_immediate(db, context, damage):
    from app.models.agent_conversation import AgentMessage
    _, conv, source, current, _ = context
    now = NOW
    if damage == "food":
        metadata = dict(source.meta)
        snapshot = dict(metadata["diet_photo_recognition"])
        snapshot["food_items"] = "篡改的食物"
        source.meta = {**metadata, "diet_photo_recognition": snapshot}
    elif damage == "image":
        source.image_url = '["/synthetic/different.jpg"]'
    elif damage == "expired":
        now += timedelta(days=2)
    elif damage == "missing":
        source.meta = {}
    else:
        # Replace the immediately preceding source with an unrelated user turn.
        source.image_url = None
    db.flush()
    result = proposal(db, context, now=now)
    assert result["status"] == "blocked"
    assert result["cards"] == []
    assert context[-1].food_items == "汤一碗"


def test_multiple_targets_never_choose_first(db, context):
    from app.models.daily_health import DietRecord
    db.add(DietRecord(user_id=context[0].id, record_date=NOW.date(), meal_type="lunch", food_items="另一餐"))
    db.flush()
    result = proposal(db, context)
    assert result["reason"] == "ambiguous_target" and result["cards"] == []


def test_owner_and_meal_date_filters_prevent_unrelated_matches(db, context):
    target = context[-1]
    target.record_date = NOW.date() - timedelta(days=1)
    db.flush()
    assert proposal(db, context)["reason"] == "target_not_found"
    assert build_correction_proposal(db, context[0].id + 999, context[1].id,
                                     context[3].id, REQUEST, NOW, "Asia/Shanghai")["status"] == "blocked"


def test_database_errors_propagate():
    class Broken:
        def query(self, *_args):
            raise RuntimeError("synthetic database failure")
    with pytest.raises(RuntimeError, match="synthetic database failure"):
        build_correction_proposal(Broken(), 1, 1, 1, REQUEST, NOW, "Asia/Shanghai")


def test_cancelled_request_never_queries_database():
    class NoReads:
        def query(self, *_args):
            pytest.fail("negated request must not read records")
    assert build_correction_proposal(NoReads(), 1, 1, 1, "不要" + REQUEST, NOW, "Asia/Shanghai") is None


def test_target_date_uses_user_timezone_not_server_date(db, context):
    now = NOW.replace(hour=20)
    context[-1].record_date = (now + timedelta(hours=8)).date()
    db.flush()
    assert proposal(db, context, now=now)["status"] == "waiting_for_user"


def test_photo_already_counted_as_other_meal_cannot_duplicate_it(db, context):
    from app.models.daily_health import DietPhotoAsset, DietRecord
    user, _, source, _, _ = context
    other = DietRecord(user_id=user.id, record_date=NOW.date(), meal_type="dinner", food_items="牛肉面")
    db.add(other)
    db.flush()
    db.add(DietPhotoAsset(id="synthetic-photo", user_id=user.id, origin_message_id=source.id,
                         storage_key="/synthetic/photo.jpg", content_sha256="a" * 64,
                         media_type="image/jpeg", origin="chat", classification="food",
                         intent_decision="auto_record", lifecycle="attached", diet_record_id=other.id))
    db.flush()
    assert proposal(db, context)["reason"] == "photo_already_recorded"


@pytest.mark.asyncio
async def test_real_stream_emits_and_persists_editor_without_model_or_record_write(db, context, monkeypatch):
    from app.models.agent_conversation import AgentMessage
    from app.services.agent_executor import AgentExecutor
    user, conv, source, current, target = context
    # run_stream creates its own current user turn; preserve the original photo exchange.
    db.delete(current)
    db.commit()
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_agent_kernel_reference_now", lambda: NOW)

    async def no_model(*_args, **_kwargs):
        pytest.fail("photo edit proposal must not ask a model to choose a record")
        yield {}

    monkeypatch.setattr(executor, "_call_llm_stream", no_model)
    events = [event async for event in executor.run_stream(
        user_id=user.id, conversation_id=conv.id, message=REQUEST, channel="typed")]
    done = next(event["data"] for event in events if event.get("event") == "done")
    assert done["mode"] == "diet_photo_correction_proposal"
    assert done["turn_outcome"]["status"] == "waiting_for_user"
    assert done["turn_outcome"]["confirmation_required"] is True
    assert done["write_receipts"] == []
    assert done["cards"][0]["data"]["adjust_record"]["proposed_food_items"] == "牛肉面 约1碗"
    saved = db.get(AgentMessage, done["message_id"])
    assert saved.meta["cards"][0]["data"]["adjust_record"]["record_id"] == target.id
    db.refresh(target)
    assert target.food_items == "汤一碗"


def test_structured_vision_not_free_form_answer_supplies_the_signed_source(db, context, monkeypatch):
    from app.services.agent_executor import AgentExecutor
    user, _, source, _, _ = context
    source.meta = {}
    db.commit()
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_source_message_id = source.id
    monkeypatch.setattr(executor, "_agent_kernel_reference_now", lambda: NOW)
    executor._format_food_recognition_for_agent("分析照片", {
        "success": True, "foods": [{"name": "面条", "quantity": "一碗", "confidence": 0.9}],
        "consumed_fraction_label": "1/5",
    })
    result = proposal(db, context)
    assert result["cards"][0]["data"]["adjust_record"]["proposed_food_items"] == "面条 一碗（按实际食用1/5计）"
