from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock

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
@pytest.mark.parametrize("model_source", (None, "manual"))
async def test_agent_text_diet_without_nutrition_is_rejected_before_dispatch(
    db,
    monkeypatch,
    model_source,
):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = (
        "记录早餐，一个包子、一个茶叶蛋、一碗粥，计算热量和营养成分"
    )
    dispatch = AsyncMock()
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)

    data = {
        "meal_type": "breakfast",
        "food_items": "一个包子、一个茶叶蛋、一碗粥",
    }
    if model_source is not None:
        data["source"] = model_source

    result = await executor._execute_tool(
        "health_record",
        {"record_type": "diet", "data": data},
        None,
    )

    _assert_local_rejection(result, error_code="diet_nutrition_incomplete")
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_complete_text_diet_gets_server_provenance_and_dispatches(
    db,
    monkeypatch,
):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "记录早餐，一个包子和一个茶叶蛋"
    dispatch = AsyncMock(
        return_value=json.dumps({"status": "verified", "success": True})
    )
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)

    result = await executor._execute_tool(
        "health_record",
        {
            "record_type": "diet",
            "data": {
                "meal_type": "breakfast",
                "food_items": "一个包子和一个茶叶蛋",
                "source": "manual",
                "calories": 330,
                "protein": 15,
                "carbs": 42,
                "fat": 12,
                "fiber": 3,
            },
        },
        None,
    )

    assert json.loads(result)["success"] is True
    request = dispatch.await_args.args[0]
    assert request.arguments["data"]["source"] == "agent_text"


@pytest.mark.asyncio
async def test_attachment_diet_without_auto_save_cannot_bypass_nutrition_guard(
    db,
    monkeypatch,
):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "记录这餐"
    executor._current_turn_has_attachment = True
    executor._diet_photo_auto_save = False
    dispatch = AsyncMock()
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)

    result = await executor._execute_tool(
        "health_record",
        {
            "record_type": "diet",
            "data": {
                "meal_type": "lunch",
                "food_items": "米饭和鸡肉",
                "source": "manual",
            },
        },
        None,
    )

    _assert_local_rejection(
        result,
        error_code="diet_nutrition_incomplete",
    )
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_complete_attachment_diet_uses_server_attachment_provenance(
    db,
    monkeypatch,
):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "记录这餐"
    executor._current_turn_has_attachment = True
    executor._diet_photo_auto_save = False
    dispatch = AsyncMock(
        return_value=json.dumps({"status": "verified", "success": True})
    )
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)

    await executor._execute_tool(
        "health_record",
        {
            "record_type": "diet",
            "data": {
                "meal_type": "lunch",
                "food_items": "米饭和鸡肉",
                "source": "manual",
                "calories": 520,
                "protein": 32,
                "carbs": 58,
                "fat": 17,
                "fiber": 5,
            },
        },
        None,
    )

    request = dispatch.await_args.args[0]
    assert request.arguments["data"]["source"] == "agent_attachment"


@pytest.mark.asyncio
async def test_recipe_replay_does_not_inherit_agent_text_nutrition_guard(
    db,
    monkeypatch,
):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "执行已确认模板"
    dispatch = AsyncMock(
        return_value=json.dumps({"status": "verified", "success": True})
    )
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)

    await executor._execute_recipe_step(
        "health_record",
        {
            "record_type": "diet",
            "data": {
                "meal_type": "breakfast",
                "food_items": "历史早餐模板",
                "source": "agent_text",
            },
        },
        None,
    )

    request = dispatch.await_args.args[0]
    assert request.arguments["data"]["source"] == "procedure_recipe"


def test_only_diet_nutrition_rejection_is_hidden_while_model_recovers():
    from app.services.agent_executor import (
        _write_result_is_pre_dispatch_validation_error,
    )
    from app.services.agent_write_outcome import local_write_rejection

    assert _write_result_is_pre_dispatch_validation_error(
        local_write_rejection("diet_nutrition_incomplete")
    )
    assert not _write_result_is_pre_dispatch_validation_error(
        local_write_rejection("policy_check_failed")
    )
    assert not _write_result_is_pre_dispatch_validation_error(
        local_write_rejection("record_date_invalid")
    )


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
async def test_medical_exam_narrative_mri_text_persists_without_numeric_items(
    db,
    auth_user_and_headers,
):
    from app.models.medical_exam import MedicalExam
    from app.services.agent_executor import AgentExecutor

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    result = await executor._exec_upload_medical_exam_text(
        "http://example.test",
        {},
        {
            "text": "MRI 检查所见：右膝内侧半月板后角损伤，关节腔少量积液。",
            "report_type": "imaging",
            "exam_date": "昨天",
        },
    )

    payload = json.loads(result)
    exam = db.query(MedicalExam).filter(MedicalExam.user_id == user.id).one()
    assert payload["resource_type"] == "medical_exam"
    assert payload["exam_id"] == exam.id
    assert exam.exam_type == "imaging"
    assert exam.overall_assessment == (
        "MRI 检查所见：右膝内侧半月板后角损伤，关节腔少量积液。"
    )
    assert "右膝内侧半月板" not in (exam.notes or "")
    assert len(exam.items) == 0


@pytest.mark.asyncio
async def test_medical_exam_runtime_operation_sets_opaque_source_fingerprint(
    db,
    auth_user_and_headers,
):
    from app.models.medical_exam import MedicalExam
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_operation_reconciliation import (
        runtime_operation_source_fingerprint,
    )

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    operation_id = "op_" + ("a" * 64)

    result = await executor._exec_upload_medical_exam_text(
        "http://example.test",
        {},
        {
            "text": "ALT 47 U/L，GGT 78 U/L",
            "_runtime_operation_id": operation_id,
        },
    )

    payload = json.loads(result)
    exam = db.query(MedicalExam).filter(MedicalExam.user_id == user.id).one()
    assert payload["resource_type"] == "medical_exam"
    assert exam.source_fingerprint == runtime_operation_source_fingerprint(
        operation_id
    )
    assert operation_id not in exam.source_fingerprint


@pytest.mark.asyncio
async def test_attachment_medical_report_receipt_does_not_swallow_other_writes(
    monkeypatch,
    db,
):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_attachment_write_receipts = [
        {
            "operation_id": "medical-report-image:48",
            "status": "verified",
            "resource_type": "medical_exam",
            "resource_id": "48",
            "verified": True,
        }
    ]
    implementation = AsyncMock(
        return_value=json.dumps(
            {
                "status": "verified",
                "resource_type": "water_record",
                "resource_id": "91",
                "verified": True,
            }
        )
    )
    monkeypatch.setattr(executor, "_execute_tool_impl", implementation)

    result = await executor._execute_tool(
        "health_record",
        {"record_type": "water", "data": {"amount": 500}},
        None,
    )

    payload = json.loads(result)
    assert payload["status"] == "verified"
    assert payload["resource_id"] == "91"
    implementation.assert_awaited_once()


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
