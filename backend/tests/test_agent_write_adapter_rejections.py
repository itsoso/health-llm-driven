from __future__ import annotations

import json

import pytest


def _assert_local_rejection(
    result: str,
    *,
    error_code: str,
) -> None:
    payload = json.loads(result)
    assert payload["status"] == "rejected"
    assert payload["success"] is False
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == error_code


@pytest.mark.asyncio
async def test_health_record_missing_diet_items_is_structured_local_rejection(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    result = await executor._exec_health_record(
        "http://example.test",
        {},
        {"record_type": "diet", "data": {}},
    )

    _assert_local_rejection(result, error_code="diet_food_items_missing")


@pytest.mark.asyncio
async def test_health_manage_missing_record_id_is_structured_local_rejection(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    result = await executor._exec_health_manage(
        "http://example.test",
        {},
        {"record_type": "diet", "operation": "update", "data": {}},
    )

    _assert_local_rejection(result, error_code="record_id_missing")


@pytest.mark.asyncio
async def test_manage_plan_missing_item_identity_is_structured_local_rejection(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    result = await executor._exec_manage_plan(
        "http://example.test",
        {},
        {"action": "complete_item", "data": {}},
    )

    _assert_local_rejection(result, error_code="plan_item_identity_missing")


@pytest.mark.asyncio
async def test_intervention_update_without_cycle_is_structured_local_rejection(
    db,
    auth_user_and_headers,
):
    from app.services.agent_executor import AgentExecutor

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    result = await executor._exec_intervention_cycle(
        {"action": "update", "confirmed": True, "days": 30}
    )

    _assert_local_rejection(result, error_code="intervention_cycle_not_found")


@pytest.mark.asyncio
async def test_aigc_missing_source_image_is_structured_local_rejection(
    db,
    auth_user_and_headers,
):
    from app.services.agent_executor import AgentExecutor

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    result = await executor._exec_draft_aigc_media(
        {"kind": "image_to_video", "prompt": "生成短视频"}
    )

    _assert_local_rejection(result, error_code="aigc_source_image_missing")


@pytest.mark.asyncio
async def test_genetic_upload_short_text_is_structured_local_rejection(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    result = await executor._exec_upload_genetic_txt(
        "http://example.test",
        {},
        {"txt_content": "too short"},
    )

    _assert_local_rejection(result, error_code="genetic_text_invalid")


@pytest.mark.asyncio
async def test_medical_exam_empty_text_is_structured_local_rejection(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    result = await executor._exec_upload_medical_exam_text(
        "http://example.test",
        {},
        {"text": ""},
    )

    _assert_local_rejection(result, error_code="medical_exam_text_missing")
