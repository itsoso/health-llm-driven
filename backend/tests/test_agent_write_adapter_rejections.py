from __future__ import annotations

import json
import logging

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


@pytest.mark.asyncio
async def test_medical_exam_unparseable_text_is_rejected_before_import(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services.agent_executor import AgentExecutor
    from app.services.data_collection.medical_exam_import import (
        MedicalExamImportService,
    )

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id

    def import_must_not_run(*args, **kwargs):
        raise AssertionError("import service crossed the dispatch boundary")

    monkeypatch.setattr(
        MedicalExamImportService,
        "import_from_items",
        import_must_not_run,
    )

    result = await executor._exec_upload_medical_exam_text(
        "http://example.test",
        {},
        {"text": "今天化验结果都挺好的"},
    )

    _assert_local_rejection(result, error_code="medical_exam_text_invalid")


@pytest.mark.asyncio
async def test_medical_exam_error_after_import_dispatch_is_uncertain_and_log_safe(
    db,
    auth_user_and_headers,
    monkeypatch,
    caplog,
):
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_write_outcome import classify_write_execution
    from app.services.data_collection.medical_exam_import import (
        MedicalExamImportService,
    )

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id

    def commit_then_fail(db_session, **kwargs):
        user.name = "committed-before-error"
        db_session.commit()
        raise ValueError("private-lab-content")

    monkeypatch.setattr(
        MedicalExamImportService,
        "import_from_items",
        commit_then_fail,
    )
    caplog.set_level(logging.ERROR, logger="app.services.agent_executor")

    result = await executor._exec_upload_medical_exam_text(
        "http://example.test",
        {},
        {"text": "ALT 31 U/L，AST 24 U/L"},
    )

    assert classify_write_execution(result).status == "uncertain"
    assert result == "Error: 化验指标入库失败"
    assert "private-lab-content" not in caplog.text
    db.expire_all()
    assert user.name == "committed-before-error"
