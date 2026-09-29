"""Synthetic source-bound item edits propose; they never delete or write meals."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.daily_health import DietPhotoDraft, DietRecord
from app.services.diet_photo_correction import build_correction_proposal

NOW = datetime(2031, 4, 4, 5, tzinfo=timezone.utc)
REQUEST = "玉米没吃 去掉记录中的这一部分"


@pytest.fixture
def item_context(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    conv = AgentConversation(user_id=user.id)
    db.add(conv); db.flush()
    source = AgentMessage(conversation_id=conv.id, role="user", content="记录这张早餐照片",
                          image_url='["/synthetic/meal.jpg"]')
    db.add(source); db.flush()
    target = DietRecord(user_id=user.id, record_date=NOW.date(), meal_type="breakfast",
                        food_items="包子 1个 + 玉米 约半根 + 鸡蛋 1个", calories=500)
    db.add(target); db.flush()
    draft = DietPhotoDraft(token="synthetic-meal-draft", user_id=user.id,
        source_message_id=source.id, image_type="jpeg", recognition_result={},
        status="consumed", consumed_record_id=target.id, consumed_at=NOW,
        created_at=NOW, expires_at=NOW + timedelta(hours=1))
    card = AgentMessage(conversation_id=conv.id, role="assistant", content="餐食卡片",
        meta={"client_turn_finalized": True, "cards": [{"type": "diet_draft",
            "data": {"photo_draft_token": draft.token}}]})
    db.add_all([draft, card]); db.flush()
    current = AgentMessage(conversation_id=conv.id, role="user", content=REQUEST)
    db.add(current); db.commit()
    return user, conv, source, card, current, target, draft


def propose(db, ctx, text=REQUEST, now=NOW):
    return build_correction_proposal(db, ctx[0].id, ctx[1].id, ctx[4].id, text, now, "Asia/Shanghai")


def test_item_removal_is_revision_bound_editor_not_delete(db, item_context):
    result = propose(db, item_context)
    assert result and result["status"] == "waiting_for_user"
    seed = result["cards"][0]["data"]["adjust_record"]
    assert seed["record_id"] == item_context[5].id
    assert seed["proposed_food_items"] == "包子 1个 + 鸡蛋 1个"
    assert "updated_at" in seed and seed["food_items"] == item_context[5].food_items
    assert item_context[5].calories == 500
    assert "尚未修改" in result["reply"]
    assert db.query(DietRecord).count() == 1


@pytest.mark.parametrize("message", ["玉米没吃，去掉记录中的这一部分", "玉米没有吃，去掉记录里的这部分。",
    "把刚才这餐里的玉米去掉", "请把这餐里的玉米移除"])
def test_supported_closed_phrases(db, item_context, message):
    item_context[4].content = message; db.flush()
    result = propose(db, item_context, message)
    assert result and result["cards"]


@pytest.mark.parametrize("message", ["不要" + REQUEST, "朋友说：" + REQUEST,
    "假如" + REQUEST, "“" + REQUEST + "”", REQUEST + "，再删除晚餐", "玉米没吃？", "删除早餐记录"])
def test_other_speech_acts_never_start_lookup(message):
    class NoReads:
        def query(self, *_a): pytest.fail("unauthorized phrase must not read")
    assert build_correction_proposal(NoReads(), 1, 1, 1, message, NOW, "Asia/Shanghai") is None


@pytest.mark.parametrize("damage", ["pending", "foreign_owner", "foreign_conversation", "missing_record", "expired", "future", "unfinalized", "different_source", "unrelated_turn"])
def test_target_must_be_owned_consumed_fresh_and_conversation_bound(db, item_context, damage):
    user, conv, source, card, current, target, draft = item_context
    now = NOW
    if damage == "pending": draft.status = "pending"
    elif damage == "foreign_owner":
        from app.models.user import User
        other = User(name="Synthetic other", email="meal-other@example.invalid")
        db.add(other); db.flush(); target.user_id = other.id
    elif damage == "foreign_conversation":
        other_conv = AgentConversation(user_id=user.id); db.add(other_conv); db.flush()
        source.conversation_id = other_conv.id
    elif damage == "missing_record": draft.consumed_record_id = None
    elif damage == "expired": now += timedelta(days=2)
    elif damage == "future": now -= timedelta(minutes=1)
    elif damage == "unfinalized": card.meta = {**card.meta, "client_turn_finalized": False}
    elif damage == "different_source": draft.source_message_id = current.id
    elif damage == "unrelated_turn": source.image_url = None
    db.flush()
    result = propose(db, item_context, now=now)
    assert result and not result["cards"] and result["status"] == "waiting_for_user"
    assert target.food_items == "包子 1个 + 玉米 约半根 + 鸡蛋 1个"


@pytest.mark.parametrize("food", ["玉米饼 1个 + 鸡蛋 1个", "玉米 半根 + 玉米 1根", "玉米 半根", "鸡蛋 1个", "玉米半根配黄油 + 鸡蛋1个"])
def test_exact_unique_item_and_nonempty_remainder_required(db, item_context, food):
    item_context[5].food_items = food; db.flush()
    result = propose(db, item_context)
    assert result and not result["cards"]
    assert item_context[5].food_items == food


def test_retry_after_failed_removal_still_binds_original_card(db, item_context):
    user, conv, _, _, current, _, _ = item_context
    db.add(AgentMessage(conversation_id=conv.id, role="assistant", content="未执行",
        meta={"client_turn_finalized": True, "turn_outcome": {"status": "blocked"}}))
    db.flush()
    retry = AgentMessage(conversation_id=conv.id, role="user", content=REQUEST)
    db.add(retry); db.flush()
    result = build_correction_proposal(db, user.id, conv.id, retry.id, REQUEST, NOW, "Asia/Shanghai")
    assert result and result["cards"]


def test_unrelated_intervening_turn_does_not_skip_to_old_meal(db, item_context):
    user, conv, _, _, current, _, _ = item_context
    current.content = "解释一下通用运动原则"
    db.add(AgentMessage(conversation_id=conv.id, role="assistant", content="合成回复",
        meta={"client_turn_finalized": True, "turn_outcome": {"status": "blocked"}}))
    db.flush()
    retry = AgentMessage(conversation_id=conv.id, role="user", content=REQUEST)
    db.add(retry); db.flush()
    result = build_correction_proposal(db, user.id, conv.id, retry.id, REQUEST, NOW, "Asia/Shanghai")
    assert result and not result["cards"]


def test_auth_and_exact_current_message_required(db, item_context):
    user, conv, _, _, current, _, _ = item_context
    assert not build_correction_proposal(db, user.id + 999, conv.id, current.id,
        REQUEST, NOW, "Asia/Shanghai")["cards"]
    assert not propose(db, item_context, "把这餐里的玉米去掉")["cards"]


def test_confirmed_existing_editor_recalculates_same_record_and_replays(db, client, item_context,
        auth_user_and_headers, monkeypatch):
    from app.services.ai.food_recognition import food_recognition_service
    _, headers = auth_user_and_headers
    seed = propose(db, item_context)["cards"][0]["data"]["adjust_record"]
    estimates = []
    def estimate(description):
        estimates.append(description)
        return {"success": True, "foods": [
            {"name": "合成包子", "quantity": "1个", "calories": 180, "protein": 6,
             "carbs": 28, "fat": 4, "fiber": 1, "confidence": 0.9},
            {"name": "合成鸡蛋", "quantity": "1个", "calories": 70, "protein": 6,
             "carbs": 1, "fat": 5, "fiber": 0, "confidence": 0.9}],
            "total_calories": 250, "total_protein": 12, "total_carbs": 29,
            "total_fat": 9, "total_fiber": 1}
    monkeypatch.setattr(food_recognition_service, "estimate_nutrition_from_text", estimate)
    payload = {"food_items": seed["proposed_food_items"], "meal_type": seed["meal_type"],
               "expected_updated_at": seed["updated_at"]}
    url = f"/api/v1/diet/records/{seed['record_id']}/recalculate-nutrition"
    command_headers = {**headers, "Idempotency-Key": "synthetic-component-removal-save"}
    first = client.post(url, json=payload, headers=command_headers)
    assert first.status_code == 200, first.text
    repeated = client.post(url, json=payload, headers=command_headers)
    assert repeated.status_code == 200 and len(estimates) == 1
    db.refresh(item_context[5])
    assert item_context[5].food_items == seed["proposed_food_items"]
    assert item_context[5].calories != 500 and db.query(DietRecord).count() == 1
    assert item_context[6].consumed_record_id == item_context[5].id
    conflict = client.post(url, json=payload,
        headers={**headers, "Idempotency-Key": "synthetic-stale-component-save"})
    assert conflict.status_code == 409 and len(estimates) == 1


@pytest.mark.asyncio
async def test_real_stream_removal_skips_model_and_persists_confirmation(db, item_context, monkeypatch):
    from app.services.agent_executor import AgentExecutor
    user, conv, _, _, current, target, _ = item_context
    db.delete(current); db.commit()
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_agent_kernel_reference_now", lambda: NOW)
    async def no_model(*_a, **_kw):
        pytest.fail("removal must resolve before model")
        yield {}
    monkeypatch.setattr(executor, "_call_llm_stream", no_model)
    events = [e async for e in executor.run_stream(user_id=user.id, conversation_id=conv.id,
        message=REQUEST, channel="typed", client_turn_id="synthetic-item-removal-turn")]
    done = next(e["data"] for e in events if e.get("event") == "done")
    assert done["turn_outcome"]["status"] == "waiting_for_user"
    assert done["turn_outcome"]["confirmation_required"] is True
    assert done["write_receipts"] == [] and done["llm_rounds"] == 0
    saved = db.get(AgentMessage, done["message_id"])
    assert saved.meta["cards"][0]["data"]["adjust_record"]["proposed_food_items"] == "包子 1个 + 鸡蛋 1个"
    db.refresh(target)
    assert target.calories == 500 and "玉米" in target.food_items
