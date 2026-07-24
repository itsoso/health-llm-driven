import json

from app.services.agent_kernel.actionable_context import (
    extract_actionable_references,
    format_actionable_context_prompt,
)
from app.models.agent_conversation import AgentConversation, AgentMessage
from app.services.agent_conversation_service import AgentConversationService


def _diet_descriptor() -> dict:
    return {
        "type": "diet_daily_summary",
        "v": 1,
        "data": {
            "record_date": "2026-07-24",
            "meals": [
                {
                    "meal_type": "breakfast",
                    "name": "早餐",
                    "detail": "豆腐脑约1碗 + 小笼包1个",
                    "calories": None,
                },
                {
                    "meal_type": "lunch",
                    "name": "午餐",
                    "detail": "三文鱼约1块 + 藜麦约半碗",
                    "calories": None,
                },
            ],
        },
    }


def test_extracts_visible_diet_card_from_persisted_meta_and_normalizes_food_items():
    references = extract_actionable_references(
        [
            {
                "id": 101,
                "content": "已查询今日饮食。",
                "meta": {"cards": [_diet_descriptor()]},
            }
        ]
    )

    assert len(references) == 1
    assert references[0].kind == "diet_daily_summary"
    assert references[0].source_message_id == "101"
    assert references[0].data == {
        "record_date": "2026-07-24",
        "meals": [
            {
                "meal_type": "breakfast",
                "food_items": "豆腐脑约1碗 + 小笼包1个",
                "calories": None,
            },
            {
                "meal_type": "lunch",
                "food_items": "三文鱼约1块 + 藜麦约半碗",
                "calories": None,
            },
        ],
    }


def test_extracts_visible_diet_card_from_reva_ui_fence_and_deduplicates_meta_copy():
    descriptor = _diet_descriptor()
    content = f"今日饮食如下\n```reva-ui\n{json.dumps(descriptor, ensure_ascii=False)}\n```"
    references = extract_actionable_references(
        [
            {
                "id": 102,
                "content": content,
                "meta": {"cards": [descriptor]},
            }
        ]
    )

    assert len(references) == 1
    prompt = format_actionable_context_prompt(references)
    assert "早餐: 豆腐脑约1碗 + 小笼包1个" in prompt
    assert "卡片仅用于解析用户指代" in prompt
    assert "写入前必须查询数据库" in prompt


def test_drops_non_actionable_fields_and_non_diet_cards():
    descriptor = _diet_descriptor()
    descriptor["data"]["image_url"] = "https://private.example/token"
    descriptor["data"]["diagnosis"] = "private"

    references = extract_actionable_references(
        [
            {
                "id": 103,
                "content": "",
                "meta": {
                    "cards": [
                        descriptor,
                        {"type": "line_chart", "data": {"secret": "value"}},
                    ]
                },
            }
        ]
    )

    assert len(references) == 1
    rendered = repr(references[0].data)
    assert "private.example" not in rendered
    assert "diagnosis" not in rendered


def test_conversation_service_recovers_recent_persisted_card_as_typed_context(
    db,
    auth_user_and_headers,
):
    user, _headers = auth_user_and_headers
    conversation = AgentConversation(
        user_id=user.id,
        title="饮食修正",
        session_key=f"actionable-{user.id}",
    )
    db.add(conversation)
    db.flush()
    db.add(
        AgentMessage(
            conversation_id=conversation.id,
            role="assistant",
            content="已查询今日饮食。",
            meta={"cards": [_diet_descriptor()]},
        )
    )
    db.commit()

    references = AgentConversationService(db).build_actionable_references(
        conversation.id
    )

    assert len(references) == 1
    assert references[0].kind == "diet_daily_summary"
    assert references[0].data["meals"][0]["meal_type"] == "breakfast"


def test_conversation_service_orders_actionable_cards_newest_first(
    db,
    auth_user_and_headers,
):
    user, _headers = auth_user_and_headers
    conversation = AgentConversation(
        user_id=user.id,
        title="多日饮食",
        session_key=f"actionable-order-{user.id}",
    )
    db.add(conversation)
    db.flush()
    old_card = _diet_descriptor()
    old_card["data"]["record_date"] = "2026-07-23"
    new_card = _diet_descriptor()
    new_card["data"]["record_date"] = "2026-07-24"
    db.add_all(
        [
            AgentMessage(
                conversation_id=conversation.id,
                role="assistant",
                content="昨天饮食。",
                meta={"cards": [old_card]},
            ),
            AgentMessage(
                conversation_id=conversation.id,
                role="assistant",
                content="今天饮食。",
                meta={"cards": [new_card]},
            ),
        ]
    )
    db.commit()

    references = AgentConversationService(db).build_actionable_references(
        conversation.id
    )

    assert [reference.data["record_date"] for reference in references] == [
        "2026-07-24",
        "2026-07-23",
    ]
