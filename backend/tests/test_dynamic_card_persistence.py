from datetime import UTC, date, datetime, timedelta

from app.models.daily_health import DietPhotoAsset, DietPhotoDraft, DietRecord
from app.services.dynamic_card_persistence import (
    cards_for_persistence,
    message_metas_for_delivery,
)

from tests.conftest import create_authenticated_user


def _record_quality_meta(record_id):
    seed = {"record_id": record_id, "food_items": "米饭100克", "updated_at": None}
    return {"cards": [{
        "type": "record_quality",
        "data": {"domain": "diet", "record_id": record_id, "adjust_record": seed,
                 "summary": "米饭100克", "progress": {"calories_total": 200},
                 "primary_judgement": "旧判断", "next_action": "旧建议"},
        "actions": [{"id": "adjust-record", "action": "ui.inline.expand",
                     "label": "修正本餐", "payload": {"target": "adjust_record", "patch": {
                         "expanded_sections": ["adjust_record"], "adjust_record": seed,
                     }}}, {"id": "show-next-meal", "action": "ui.inline.expand",
                           "payload": {"target": "next_meal", "patch": {"next_meal_detail": "旧建议"}}}],
    }]}


def _saved_photo_meta(record_id):
    seed = {"record_id": record_id, "food_items": "旧食物", "calories": None,
            "updated_at": None}
    return {"cards": [{"type": "diet_draft", "data": {
        "card_id": f"diet-record:{record_id}", "recorded": True,
        "record_id": record_id, "food_items": "旧食物", "calories": None,
        "protein": None, "adjust_record": seed,
    }, "actions": [{"action": "ui.inline.expand", "payload": {
        "target": "adjust_record", "patch": {"adjust_record": seed},
    }}]}]}


def test_saved_meal_reload_cannot_restore_cleared_advice_from_action(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    record = DietRecord(user_id=user.id, record_date=date.today(), meal_type='lunch',
                        food_items='合成餐食', calories=200)
    db.add(record)
    db.commit()
    meta = _saved_photo_meta(record.id)
    meta['cards'][0]['actions'].append({
        'action': 'ui.inline.expand', 'payload': {'target': 'next_meal',
            'patch': {'expanded_sections': ['next_meal'], 'next_meal_detail': {'summary': '旧建议'}}},
    })
    card = message_metas_for_delivery(db, [meta], user.id)[0]['cards'][0]
    assert 'next_meal_detail' not in card['data']
    assert all(action['payload']['target'] != 'next_meal' for action in card['actions'])
    assert len(meta['cards'][0]['actions']) == 2


def test_saved_photo_history_refreshes_later_nutrition_write(client, db, auth_user_and_headers):
    from copy import deepcopy

    from app.models.agent_conversation import AgentConversation, AgentMessage

    user, headers = auth_user_and_headers
    record = DietRecord(user_id=user.id, record_date=date.today(), meal_type="lunch",
                        food_items="合成食物", calories=None,
                        updated_at=datetime(2026, 10, 14, 8, tzinfo=UTC))
    db.add(record)
    db.flush()
    meta = _saved_photo_meta(record.id)
    # Same message can contain two receipts for the same saved record.
    meta["cards"].append(deepcopy(meta["cards"][0]))
    meta["cards"][1]["data"]["card_id"] = "diet-capture:synthetic"
    conversation = AgentConversation(user_id=user.id, title="合成营养回填")
    db.add(conversation)
    db.flush()
    message = AgentMessage(conversation_id=conversation.id, role="assistant",
                           content="已记录", meta=meta)
    db.add(message)
    db.commit()
    response = client.put(f"/api/v1/diet/records/{record.id}", headers=headers,
                          json={"calories": 221.2345, "protein": 9.87654, "carbs": None,
                                "expected_updated_at": record.updated_at.isoformat()})
    assert response.status_code == 200, response.status_code
    saved = response.json()
    response = client.get(f"/api/v1/agent/conversations/{conversation.id}", headers=headers)
    assert response.status_code == 200
    for card in response.json()["messages"][0]["meta"]["cards"]:
        assert card["data"]["calories"] == 221.23
        assert card["data"]["protein"] == 9.88
        assert card["data"]["carbs"] is None  # missing is not zero
        assert card["data"]["food_items"] == "合成食物"
        assert card["data"]["updated_at"] == saved["updated_at"]
        assert card["data"]["adjust_record"]["calories"] == 221.2345
        assert card["actions"][0]["payload"]["patch"]["adjust_record"] == card["data"]["adjust_record"]
    db.refresh(message)
    assert message.meta == meta  # materialization is read-only


def test_saved_photo_history_rejects_foreign_deleted_and_missing_parents(db):
    owner, _ = create_authenticated_user(db)
    viewer, _ = create_authenticated_user(db)
    record = DietRecord(user_id=owner.id, record_date=date.today(), meal_type="lunch",
                        food_items="私有合成食物", calories=500)
    db.add(record)
    db.commit()
    original = _saved_photo_meta(record.id)
    foreign = message_metas_for_delivery(db, [original], viewer.id)[0]["cards"][0]
    assert foreign["data"]["record_unavailable"] is True
    assert foreign["data"]["recorded"] is False
    assert "adjust_record" not in foreign["data"]
    assert "food_items" not in foreign["data"]
    assert foreign["actions"] == []
    db.delete(record)
    db.commit()
    deleted = message_metas_for_delivery(db, [original], owner.id)[0]["cards"][0]
    assert deleted == foreign
    missing_id = _saved_photo_meta(None)
    invalid = message_metas_for_delivery(db, [missing_id], owner.id)[0]["cards"][0]
    assert invalid["data"]["record_unavailable"] is True


def test_saved_photo_projection_does_not_promote_unconfirmed_draft(db):
    owner, _ = create_authenticated_user(db)
    record = DietRecord(user_id=owner.id, record_date=date.today(), meal_type="lunch",
                        food_items="合成食物", calories=500)
    db.add(record)
    db.commit()
    draft = _saved_photo_meta(record.id)
    draft["cards"][0]["data"]["recorded"] = False
    projected = message_metas_for_delivery(db, [draft], owner.id)[0]["cards"][0]
    assert projected["data"]["recorded"] is False
    assert projected["data"]["calories"] is None


def test_saved_photo_projection_batches_mixed_cards_and_binds_their_own_record(db):
    from copy import deepcopy

    from sqlalchemy import event

    owner, _ = create_authenticated_user(db)
    records = [DietRecord(user_id=owner.id, record_date=date.today(), meal_type="lunch",
                          food_items=f"合成食物{index}", calories=100 + index)
               for index in range(3)]
    db.add_all(records)
    db.commit()
    metas = [_saved_photo_meta(record.id) for record in records]
    metas[0]["cards"][0]["data"]["adjust_record"]["record_id"] = records[1].id
    metas[0]["cards"].append(_record_quality_meta(records[0].id)["cards"][0])
    original = deepcopy(metas)
    statements = []
    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)
    owner_id = owner.id
    event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        delivered = message_metas_for_delivery(db, metas, owner_id)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture)
    assert len(statements) == 1 and statements[0].lstrip().upper().startswith("SELECT")
    assert metas == original
    for index, meta in enumerate(delivered):
        card = meta["cards"][0]
        assert card["data"]["calories"] == 100 + index
        assert card["data"]["adjust_record"]["record_id"] == records[index].id


def test_saved_photo_projection_database_failure_is_not_hidden(monkeypatch):
    from unittest.mock import Mock

    import pytest

    db = Mock()
    db.query.side_effect = RuntimeError("unavailable")
    with pytest.raises(RuntimeError, match="unavailable"):
        message_metas_for_delivery(db, [_saved_photo_meta(1)], 1)


def test_quality_history_reload_uses_saved_record_not_old_action_seed(client, db, auth_user_and_headers):
    from app.models.agent_conversation import AgentConversation, AgentMessage

    user, headers = auth_user_and_headers
    record = DietRecord(user_id=user.id, record_date=date.today(), meal_type="lunch",
                        food_items="米饭150克", calories=195.1234, protein=3.5,
                        updated_at=datetime(2026, 9, 10, 8, tzinfo=UTC))
    db.add(record)
    db.flush()
    original = _record_quality_meta(record.id)
    conv = AgentConversation(user_id=user.id, title="测试修正回读")
    db.add(conv)
    db.flush()
    message = AgentMessage(conversation_id=conv.id, role="assistant", content="已记录", meta=original)
    db.add(message)
    db.commit()

    response = client.get(f"/api/v1/agent/conversations/{conv.id}", headers=headers)
    assert response.status_code == 200
    card = response.json()["messages"][0]["meta"]["cards"][0]
    assert card['type'] == 'diet_draft'
    assert card['data']['recorded'] is True
    assert card['data']['record_date'] == record.record_date.isoformat()
    assert card['data']['calories'] == 195.12
    assert card["data"]["adjust_record"]["food_items"] == "米饭150克"
    assert card["data"]["adjust_record"]["calories"] == 195.1234  # never round edit data
    assert card["data"]["adjust_record"]["updated_at"] is not None
    assert card["actions"][0]["payload"]["patch"]["adjust_record"] == card["data"]["adjust_record"]
    assert card["data"]["summary"] == "米饭150克"
    assert card["data"]["metrics"][0]["value"] == "195.12kcal"
    assert "progress" not in card["data"] and "next_action" not in card["data"]
    assert not any(a.get("id") == "show-next-meal" for a in card["actions"])
    db.refresh(message)
    assert message.meta == original  # delivery must not rewrite conversation history


def test_quality_history_does_not_restore_foreign_or_deleted_record(db):
    owner, _ = create_authenticated_user(db)
    viewer, _ = create_authenticated_user(db)
    record = DietRecord(user_id=owner.id, record_date=date.today(), meal_type="lunch",
                        food_items="私有食物", calories=500)
    db.add(record)
    db.commit()
    meta = _record_quality_meta(record.id)
    foreign = message_metas_for_delivery(db, [meta], viewer.id)[0]["cards"][0]
    assert foreign["data"]["title"] == "记录不可用"
    assert "adjust_record" not in foreign["data"]
    assert foreign["actions"] == []
    assert "私有食物" not in str(foreign)
    db.delete(record)
    db.commit()
    deleted = message_metas_for_delivery(db, [meta], owner.id)[0]["cards"][0]
    assert deleted == foreign


def test_quality_history_batches_reads_and_does_not_mutate_input(db):
    from copy import deepcopy

    from sqlalchemy import event

    owner, _ = create_authenticated_user(db)
    records = [DietRecord(user_id=owner.id, record_date=date.today(), meal_type="dinner",
                          food_items=f"测试食物{index}", calories=100) for index in range(3)]
    db.add_all(records)
    db.commit()
    metas = [_record_quality_meta(record.id) for record in records]
    original = deepcopy(metas)
    owner_id = owner.id
    statements = []
    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)
    event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        delivered = message_metas_for_delivery(db, metas, owner_id)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture)
    assert len(statements) == 1 and statements[0].lstrip().upper().startswith("SELECT")
    assert metas == original
    assert all(meta["cards"][0]["data"]["title"] == "晚餐已记录" for meta in delivered)


def test_quality_history_database_failure_is_not_hidden(monkeypatch):
    from unittest.mock import Mock

    import pytest

    db = Mock()
    db.query.side_effect = RuntimeError("unavailable")
    with pytest.raises(RuntimeError, match="unavailable"):
        message_metas_for_delivery(db, [_record_quality_meta(1)], 1)


def test_diet_draft_persistence_removes_ephemeral_signed_photo_url():
    cards = [{
        "type": "diet_draft",
        "data": {
            "photo_asset_id": "photo-1",
            "photo_url": "/api/v1/upload/files/diet/7/lunch.jpg?expires=1&signature=secret",
            "food_items": "鸡胸肉和杂粮饭",
        },
        "actions": [],
    }]

    persisted = cards_for_persistence(cards)

    assert persisted[0]["data"] == {
        "photo_asset_id": "photo-1",
        "food_items": "鸡胸肉和杂粮饭",
    }
    assert "photo_url" in cards[0]["data"]


def test_non_diet_cards_keep_their_existing_persistence_contract():
    cards = [{
        "type": "system_knowledge_evidence",
        "data": {"title": "证据", "url": "https://example.test/evidence"},
        "actions": [],
    }]

    assert cards_for_persistence(cards) == cards


def test_diet_draft_persistence_removes_all_ephemeral_photo_urls():
    cards = [{
        "type": "diet_draft",
        "data": {
            "card_id": "diet-record:42",
            "photo_asset_id": "photo-1",
            "photo_asset_ids": ["photo-1", "photo-2"],
            "photo_url": "/api/v1/upload/files/diet/7/one.jpg?signature=one",
            "photo_urls": [
                "/api/v1/upload/files/diet/7/one.jpg?signature=one",
                "/api/v1/upload/files/diet/7/two.jpg?signature=two",
            ],
        },
        "actions": [],
    }]

    persisted = cards_for_persistence(cards)

    assert persisted[0]["data"] == {
        "card_id": "diet-record:42",
        "photo_asset_id": "photo-1",
        "photo_asset_ids": ["photo-1", "photo-2"],
    }


def test_draft_card_recovers_current_record_parent_after_confirmation(db):
    user, _ = create_authenticated_user(db)
    draft = DietPhotoDraft(
        token="stable-card-draft-token",
        user_id=user.id,
        source_message_id=991,
        image_url=f"/api/v1/upload/files/diet/{user.id}/meal.jpg",
        image_type="jpeg",
        recognition_result={"food_items": "鸡胸肉", "calories": 220},
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    asset = DietPhotoAsset(
        id="stable-card-asset",
        user_id=user.id,
        photo_draft_token=draft.token,
        storage_key=f"/api/v1/upload/files/diet/{user.id}/meal.jpg",
        content_sha256="a" * 64,
        media_type="image/jpeg",
        origin="chat",
        origin_message_id=991,
        ordinal=0,
        classification="food",
        recognition_confidence=0.93,
        intent_decision="confirm",
        recognition_snapshot={},
        lifecycle="pending",
    )
    db.add(draft)
    db.flush()  # PostgreSQL enforces the parent FK before the asset insert.
    db.add(asset)
    db.commit()
    record = DietRecord(
        user_id=user.id,
        record_date=date.today(),
        meal_type="lunch",
        food_name="鸡胸肉",
        food_items="鸡胸肉",
        source="chat_photo",
        client_action_id=f"diet-photo:{draft.token}",
        calories=220,
    )
    db.add(record)
    db.flush()
    asset.diet_record_id = record.id
    asset.photo_draft_token = None
    asset.lifecycle = "attached"
    db.delete(draft)
    db.commit()
    meta = {
        "cards": [{
            "type": "diet_draft",
            "data": {
                "card_id": "diet-capture:meal-photo:991",
                "capture_session_id": "meal-photo:991",
                "recorded": False,
                "photo_draft_token": "stable-card-draft-token",
                "photo_asset_id": asset.id,
                "photo_asset_ids": [asset.id],
            },
            "actions": [{"action": "diet_record.create"}],
        }],
    }

    delivered = message_metas_for_delivery(db, [meta], user.id)

    card = delivered[0]["cards"][0]
    assert card["data"]["card_id"] == "diet-capture:meal-photo:991"
    assert card["data"]["recorded"] is True
    assert card["data"]["record_id"] == record.id
    assert "photo_draft_token" not in card["data"]
    assert card["data"]["media_stage"] == "attached"
    assert card["data"]["photo_asset_ids"] == [asset.id]
    assert card["data"]["photo_url"]
    assert card["actions"] == []


def test_failed_diet_photo_signature_counts_asset_as_unavailable(
    db, monkeypatch
):
    user, _ = create_authenticated_user(db)
    record = DietRecord(
        user_id=user.id,
        record_date=date.today(),
        meal_type="lunch",
        food_name="鸡胸肉",
        food_items="鸡胸肉",
        source="chat_photo",
    )
    db.add(record)
    db.flush()
    asset = DietPhotoAsset(
        id="unsignable-card-asset",
        user_id=user.id,
        diet_record_id=record.id,
        storage_key=f"/api/v1/upload/files/diet/{user.id}/meal.jpg",
        content_sha256="b" * 64,
        media_type="image/jpeg",
        origin="chat",
        origin_message_id=992,
        ordinal=0,
        classification="food",
        recognition_confidence=0.93,
        intent_decision="auto_record",
        recognition_snapshot={},
        lifecycle="attached",
    )
    db.add(asset)
    db.commit()
    monkeypatch.setattr(
        "app.utils.diet_image_url.diet_response_image_url",
        lambda *_args, **_kwargs: None,
    )
    meta = {
        "cards": [{
            "type": "diet_draft",
            "data": {
                "card_id": "diet-capture:meal-photo:992",
                "capture_session_id": "meal-photo:992",
                "recorded": True,
                "record_id": record.id,
                "photo_asset_ids": [asset.id],
            },
            "actions": [],
        }],
    }

    delivered = message_metas_for_delivery(db, [meta], user.id)

    data = delivered[0]["cards"][0]["data"]
    assert data["photo_asset_ids"] == []
    assert data["photo_unavailable_count"] == 1
    assert data["media_stage"] == "unavailable"
    assert "photo_url" not in data
    assert "photo_urls" not in data


def test_capture_session_restores_assets_added_after_card_was_persisted(db):
    user, _ = create_authenticated_user(db)
    record = DietRecord(
        user_id=user.id,
        record_date=date.today(),
        meal_type="lunch",
        food_name="鸡胸肉和西兰花",
        food_items="鸡胸肉和西兰花",
        source="chat_photo",
    )
    db.add(record)
    db.flush()
    assets = [
        DietPhotoAsset(
            id=f"expanded-card-asset-{ordinal}",
            user_id=user.id,
            diet_record_id=record.id,
            storage_key=(
                f"/api/v1/upload/files/diet/{user.id}/expanded-{ordinal}.jpg"
            ),
            content_sha256=str(ordinal + 5) * 64,
            media_type="image/jpeg",
            origin="chat",
            origin_message_id=994,
            ordinal=ordinal,
            classification="food",
            recognition_confidence=0.93,
            intent_decision="auto_record",
            recognition_snapshot={},
            lifecycle="attached",
        )
        for ordinal in range(2)
    ]
    db.add_all(assets)
    db.commit()
    meta = {
        "cards": [{
            "type": "diet_draft",
            "data": {
                "card_id": "diet-capture:meal-photo:994",
                "capture_session_id": "meal-photo:994",
                "recorded": True,
                "record_id": record.id,
                # This is the durable card written before the second image was
                # attached to the same capture session.
                "photo_asset_ids": [assets[0].id],
            },
            "actions": [],
        }],
    }

    delivered = message_metas_for_delivery(db, [meta], user.id)

    data = delivered[0]["cards"][0]["data"]
    assert data["photo_asset_ids"] == [asset.id for asset in assets]
    assert len(data["photo_urls"]) == 2
    assert data["media_stage"] == "attached"


def test_capture_session_never_recovers_another_owners_asset(db):
    owner, _ = create_authenticated_user(db)
    viewer, _ = create_authenticated_user(db)
    record = DietRecord(
        user_id=owner.id,
        record_date=date.today(),
        meal_type="lunch",
        food_name="私有餐食",
        food_items="私有餐食",
        source="chat_photo",
    )
    db.add(record)
    db.flush()
    asset = DietPhotoAsset(
        id="other-owner-card-asset",
        user_id=owner.id,
        diet_record_id=record.id,
        storage_key=f"/api/v1/upload/files/diet/{owner.id}/private.jpg",
        content_sha256="c" * 64,
        media_type="image/jpeg",
        origin="chat",
        origin_message_id=993,
        ordinal=0,
        classification="food",
        recognition_confidence=0.93,
        intent_decision="auto_record",
        recognition_snapshot={},
        lifecycle="attached",
    )
    db.add(asset)
    db.commit()
    meta = {
        "cards": [{
            "type": "diet_draft",
            "data": {
                "card_id": "diet-capture:meal-photo:993",
                "capture_session_id": "meal-photo:993",
                "photo_asset_ids": [asset.id],
            },
            "actions": [],
        }],
    }

    delivered = message_metas_for_delivery(db, [meta], viewer.id)

    data = delivered[0]["cards"][0]["data"]
    assert data["photo_asset_ids"] == []
    assert data["media_stage"] == "unavailable"
def test_legacy_instruction_medication_cards_are_removed_on_delivery_without_mutation():
    from copy import deepcopy
    from app.services.dynamic_card_persistence import message_metas_for_delivery

    invalid = {'type': 'medication_draft', 'data': {'medication_name': '提醒 先查询核实药品、计划时间和记录状态 不要记录服药'}, 'actions': [{'action': 'route.open'}]}
    valid = {'type': 'medication_draft', 'data': {'medication_name': '奥美拉唑', 'dose': '20mg'}}
    meta = {'cards': [invalid, valid, {'type': 'cards_group', 'data': {'cards': [invalid, valid]}}]}
    original = deepcopy(meta)
    delivered = message_metas_for_delivery(None, [meta], 1)[0]
    assert delivered['cards'] == [valid, {'type': 'cards_group', 'data': {'cards': [valid]}}]
    assert meta == original


def test_instruction_cards_do_not_persist_or_survive_inside_batches():
    invalid = {'type': 'medication_draft', 'data': {'items': [
        {'medication_name': '奥美拉唑'},
        {'medication_name': '请帮我核对今天的用药记录'},
    ]}}
    valid = {'type': 'medication_draft', 'data': {'items': [
        {'medication_name': '奥美拉唑', 'actual_dosage': '20mg'},
        {'medication_name': '阿司匹林', 'actual_dosage': '1片'},
    ]}}
    assert cards_for_persistence([invalid, valid]) == [valid]
    assert message_metas_for_delivery(None, [{'cards': [{'type': 'cards_group', 'data': {'cards': [invalid]}}]}], 1) == [{'cards': []}]
