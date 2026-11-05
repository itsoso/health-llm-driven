"""Synthetic identity clarifications prefill one item and retain the save gate."""
import pytest

from tests.test_meal_item_removal import item_context, attached_source, NOW
from app.models.agent_conversation import AgentMessage
from app.models.daily_health import DietRecord
from app.services.diet_photo_correction import build_correction_proposal

REQUEST = "黄色条装物是胡萝卜"
FOODS = "小米粥 约1碗 + 黄色条状食物 约1条 + 豆腐脑 约1碗"
EXPECTED = "小米粥 约1碗 + 胡萝卜 约1条 + 豆腐脑 约1碗"


def configure(db, ctx, text=REQUEST, foods=FOODS):
    ctx[4].content = text
    ctx[5].food_items = foods
    db.flush()


def propose(db, ctx, text=REQUEST, now=NOW):
    return build_correction_proposal(db, ctx[0].id, ctx[1].id, ctx[4].id, text, now, "Asia/Shanghai")


@pytest.mark.parametrize("text", [REQUEST, "黄色条状食物是胡萝卜。", "黄色条状物是胡萝卜", "黄色条状的是胡萝卜"])
def test_identity_replaces_only_one_item_in_revision_bound_editor(db, item_context, text):
    configure(db, item_context, text)
    result = propose(db, item_context, text)
    assert result and result["status"] == "waiting_for_user"
    seed = result["cards"][0]["data"]["adjust_record"]
    assert seed["record_id"] == item_context[5].id
    assert seed["food_items"] == FOODS and seed["proposed_food_items"] == EXPECTED
    assert "updated_at" in seed
    assert item_context[5].food_items == FOODS and item_context[5].calories == 500
    assert "保存" in result["reply"] and "胡萝卜" in result["reply"]


@pytest.mark.parametrize("foods", ["小米粥1碗", "黄色条状食物1条，黄色条状食物2条", "黄色条状食物和米饭", "不是黄色条状食物"])
def test_ambiguous_item_never_replaces_whole_meal(db, item_context, foods):
    configure(db, item_context, foods=foods)
    result = propose(db, item_context)
    assert result and not result["cards"]
    assert "食物" in result["reply"]
    assert item_context[5].food_items == foods


@pytest.mark.parametrize("text", [
    "黄色条状物是胡萝卜吗", "黄色条状物可能是胡萝卜", "黄色条状物不是胡萝卜",
    "他说黄色条状物是胡萝卜", "“黄色条状物是胡萝卜”", "黄色条状物是胡萝卜，不要修改",
    "黄色条状物是胡萝卜，删除其他记录", "黄色条状物是胡萝卜还是土豆", "黄色条状物是胰岛素",
])
def test_questions_quotes_medication_or_compound_instructions_never_read(text):
    class NoReads:
        def query(self, *_args):
            pytest.fail("unsupported identity must not read")
    assert build_correction_proposal(NoReads(), 1, 1, 1, text, NOW, "Asia/Shanghai") is None


@pytest.mark.parametrize("damage", ["pending", "expired", "foreign_owner", "unfinalized", "different_source", "foreign_conversation", "unrelated_turn"])
def test_identity_requires_owned_finalized_recent_photo(db, item_context, damage):
    from datetime import timedelta
    from app.models.agent_conversation import AgentConversation
    from app.models.user import User
    configure(db, item_context)
    user, conv, source, answer, current, target, draft = item_context
    now = NOW
    if damage == "pending": draft.status = "pending"
    elif damage == "expired": now += timedelta(days=2)
    elif damage == "unfinalized": answer.meta = {**answer.meta, "client_turn_finalized": False}
    elif damage == "different_source": draft.source_message_id = current.id
    elif damage == "unrelated_turn": source.image_url = None
    elif damage == "foreign_conversation":
        other_conv = AgentConversation(user_id=user.id)
        db.add(other_conv); db.flush(); current.conversation_id = other_conv.id
    else:
        other = User(name="Synthetic", email="identity-other@example.invalid")
        db.add(other); db.flush(); target.user_id = other.id
    db.flush()
    result = propose(db, item_context, now=now)
    assert result and not result["cards"] and result["status"] == "waiting_for_user"
    assert target.food_items == FOODS


def test_saved_photo_binding_survives_draft_deletion(db, item_context):
    configure(db, item_context)
    attached_source(db, item_context)
    assert propose(db, item_context)["cards"][0]["data"]["adjust_record"]["proposed_food_items"] == EXPECTED


@pytest.mark.asyncio
async def test_real_stream_persists_correction_and_replays_without_model_or_write(db, item_context, monkeypatch):
    from app.services.agent_executor import AgentExecutor
    configure(db, item_context)
    user, conv, _, _, current, target, _ = item_context
    db.delete(current); db.commit()
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_agent_kernel_reference_now", lambda: NOW)
    async def no_model(*_args, **_kwargs):
        pytest.fail("identity correction must resolve before model")
        yield {}
    monkeypatch.setattr(executor, "_call_llm_stream", no_model)
    for _ in range(2):
        events = [event async for event in executor.run_stream(user_id=user.id, conversation_id=conv.id,
            message=REQUEST, channel="typed", client_turn_id="synthetic-food-identity-turn")]
        done = next(event["data"] for event in events if event.get("event") == "done")
        assert done["turn_outcome"]["status"] == "waiting_for_user"
        assert done["write_receipts"] == [] and done["llm_rounds"] == 0
        saved = db.get(AgentMessage, done["message_id"])
        assert "本轮数据查询未完成" not in saved.content
        seed = saved.meta["cards"][0]["data"]["adjust_record"]
        assert seed["proposed_food_items"] == EXPECTED
        assert seed["record_id"] == target.id
    db.refresh(target)
    assert target.food_items == FOODS and db.query(DietRecord).count() == 1


def auto_recorded_context(db, ctx):
    configure(db, ctx)
    asset = attached_source(db, ctx)
    ctx[3].meta = {"client_turn_finalized": True, "cards": [{"type": "diet_draft", "data": {
        "recorded": True, "record_id": ctx[5].id, "user_id": ctx[0].id,
        "photo_asset_id": asset.id, "photo_asset_ids": [asset.id]}}]}
    db.flush()
    return asset


def test_auto_saved_photo_card_without_draft_token_is_bound_to_private_asset(db, item_context):
    auto_recorded_context(db, item_context)
    seed = propose(db, item_context)["cards"][0]["data"]["adjust_record"]
    assert seed["record_id"] == item_context[5].id and seed["proposed_food_items"] == EXPECTED


@pytest.mark.parametrize("damage", ["record", "card_owner", "asset_id", "asset_list", "deleted", "non_food", "future", "foreign_asset", "multiple"])
def test_auto_saved_identity_card_cannot_authorize_a_different_or_stale_asset(db, item_context, damage):
    from datetime import timedelta
    # Client-visible card fields alone never choose an owned row.
    from app.models.daily_health import DietPhotoAsset
    from tests.conftest import create_authenticated_user
    asset = auto_recorded_context(db, item_context)
    data = dict(item_context[3].meta["cards"][0]["data"])
    if damage == "record": data["record_id"] += 1
    elif damage == "card_owner": data["user_id"] += 1
    elif damage == "asset_id": data["photo_asset_id"] = "unknown"
    elif damage == "asset_list": data["photo_asset_ids"] = []
    elif damage == "deleted": asset.deleted_at = NOW
    elif damage == "non_food": asset.classification = "non_food"
    elif damage == "future": asset.created_at = NOW + timedelta(minutes=1)
    elif damage == "foreign_asset":
        other, _ = create_authenticated_user(db); asset.user_id = other.id
    else:
        db.add(DietPhotoAsset(id="synthetic-identity-second", user_id=asset.user_id,
            diet_record_id=asset.diet_record_id, origin_message_id=asset.origin_message_id,
            ordinal=1, storage_key=asset.storage_key, content_sha256="b" * 64,
            media_type="image/jpeg", origin="agent", classification="food",
            intent_decision="confirm", lifecycle="attached", created_at=NOW))
    item_context[3].meta = {"client_turn_finalized": True, "cards": [{"type": "diet_draft", "data": data}]}
    db.flush()
    assert not propose(db, item_context)["cards"]


def test_retry_after_failed_same_identity_uses_original_photo_not_an_unrelated_meal(db, item_context):
    configure(db, item_context)
    user, conv, _, _, current, _, _ = item_context
    db.add(AgentMessage(conversation_id=conv.id, role="assistant", content="本轮数据查询未完成",
        meta={"client_turn_finalized": True, "turn_outcome": {"status": "blocked"}}))
    db.flush()
    retry = AgentMessage(conversation_id=conv.id, role="user", content=REQUEST)
    db.add(retry); db.flush()
    result = build_correction_proposal(db, user.id, conv.id, retry.id, REQUEST, NOW, "Asia/Shanghai")
    assert result["cards"][0]["data"]["adjust_record"]["proposed_food_items"] == EXPECTED


def test_confirmed_identity_editor_recalculates_same_owned_record_and_replays(db, client, item_context,
        auth_user_and_headers, monkeypatch):
    from app.services.ai.food_recognition import food_recognition_service
    from app.services.dynamic_card_persistence import message_metas_for_delivery
    from tests.conftest import create_authenticated_user
    auto_recorded_context(db, item_context)
    # SQLite's server timestamp is second-granular. Give the initial revision
    # a distinct instant so this test does not depend on crossing a clock tick.
    item_context[5].updated_at = NOW
    db.commit()
    _, headers = auth_user_and_headers
    result = propose(db, item_context)
    delivered = message_metas_for_delivery(db, [{"cards": result["cards"]}], item_context[0].id)
    seed = delivered[0]["cards"][0]["data"]["adjust_record"]
    assert seed["proposed_food_items"] == EXPECTED
    estimates = []
    def estimate(description):
        estimates.append(description)
        return {"success": True, "foods": [{"name": "合成更正餐", "quantity": "1份", "calories": 350,
            "protein": 12, "carbs": 55, "fat": 9, "fiber": 6, "confidence": 0.9}],
            "total_calories": 350, "total_protein": 12, "total_carbs": 55, "total_fat": 9, "total_fiber": 6}
    monkeypatch.setattr(food_recognition_service, "estimate_nutrition_from_text", estimate)
    payload = {"food_items": seed["proposed_food_items"], "meal_type": seed["meal_type"],
               "expected_updated_at": seed["updated_at"]}
    url = f"/api/v1/diet/records/{seed['record_id']}/recalculate-nutrition"
    other, other_token = create_authenticated_user(db)
    other_headers = {"Authorization": f"Bearer {other_token}"}
    foreign_attempt = client.post(url, json=payload,
        headers={**other_headers, "Idempotency-Key": "synthetic-identity-foreign"})
    assert foreign_attempt.status_code in {403, 404} and not estimates
    command_headers = {**headers, "Idempotency-Key": "synthetic-identity-save"}
    first = client.post(url, json=payload, headers=command_headers)
    assert first.status_code == 200, first.text
    assert client.post(url, json=payload, headers=command_headers).status_code == 200
    assert len(estimates) == 1 and estimates[0] == EXPECTED
    db.refresh(item_context[5])
    assert item_context[5].food_items == EXPECTED and item_context[5].calories == 350
    assert db.query(DietRecord).count() == 1
    stale = client.post(url, json=payload, headers={**headers, "Idempotency-Key": "synthetic-identity-stale"})
    assert stale.status_code == 409 and len(estimates) == 1
