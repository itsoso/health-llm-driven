from __future__ import annotations

import json
import logging
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest


def _assert_local_rejection(
    result: str,
    *,
    error_code: str,
) -> None:
    from app.services.agent_write_outcome import classify_write_execution

    payload = json.loads(result)
    assert payload["status"] == "rejected"
    assert payload["success"] is False
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == error_code
    outcome = classify_write_execution(result)
    assert outcome.status == "rejected"
    assert outcome.dispatch_started is False


def _assert_uncertain_write(result: str) -> None:
    from app.services.agent_write_outcome import classify_write_execution

    payload = json.loads(result)
    assert payload == {
        "status": "uncertain",
        "success": False,
        "dispatch_started": True,
        "error_code": "doctor_feedback_write_uncertain",
    }
    outcome = classify_write_execution(result)
    assert outcome.status == "uncertain"
    assert outcome.dispatch_started is True
    assert outcome.error_code == "doctor_feedback_write_uncertain"


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "args",
    (
        {},
        {"summary": None, "assessment": "", "plan": "   \n\t"},
        {"summary": " \u3000 ", "assessment": "\n", "plan": "\t"},
    ),
)
async def test_doctor_feedback_rejects_when_all_text_fields_are_blank(db, args):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1

    result = await executor._exec_record_doctor_feedback(args)

    _assert_local_rejection(
        result,
        error_code="doctor_feedback_content_missing",
    )


@pytest.mark.asyncio
async def test_doctor_feedback_rejects_missing_current_user_before_service(
    db,
    monkeypatch,
):
    from app.services import doctor_report_service
    from app.services.agent_executor import AgentExecutor

    record = Mock(side_effect=AssertionError("service must not run"))
    monkeypatch.setattr(doctor_report_service, "record_doctor_feedback", record)
    executor = AgentExecutor(db)

    result = await executor._exec_record_doctor_feedback(
        {"assessment": "臀肌无力导致腰肌代偿"}
    )

    _assert_local_rejection(result, error_code="doctor_feedback_user_missing")
    record.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "visit_date",
    (
        "2026/08/01",
        "20260801",
        "2026-8-1",
        "2026-02-30",
        "昨天",
    ),
)
async def test_doctor_feedback_requires_strict_iso_visit_date(
    db,
    monkeypatch,
    visit_date,
):
    from app.services import doctor_report_service
    from app.services.agent_executor import AgentExecutor

    record = Mock(side_effect=AssertionError("service must not run"))
    monkeypatch.setattr(doctor_report_service, "record_doctor_feedback", record)
    executor = AgentExecutor(db)
    executor._current_user_id = 1

    result = await executor._exec_record_doctor_feedback(
        {"assessment": "臀肌无力导致腰肌代偿", "visit_date": visit_date}
    )

    _assert_local_rejection(result, error_code="doctor_feedback_date_invalid")
    record.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invisible_text",
    (
        "\u200b",
        "\ufeff",
        " \t\u200b\n\ufeff ",
    ),
)
async def test_doctor_feedback_rejects_format_controls_without_visible_content(
    db,
    monkeypatch,
    invisible_text,
):
    from app.services import doctor_report_service
    from app.services.agent_executor import AgentExecutor

    record = Mock(side_effect=AssertionError("service must not run"))
    monkeypatch.setattr(doctor_report_service, "record_doctor_feedback", record)
    executor = AgentExecutor(db)
    executor._current_user_id = 1

    result = await executor._exec_record_doctor_feedback(
        {"assessment": invisible_text}
    )

    _assert_local_rejection(
        result,
        error_code="doctor_feedback_content_not_visible",
    )
    record.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ("summary", "assessment", "plan"))
async def test_doctor_feedback_rejects_oversized_field_before_service(
    db,
    monkeypatch,
    field,
):
    from app.services import doctor_report_service
    from app.services.agent_executor import AgentExecutor

    record = Mock(side_effect=AssertionError("service must not run"))
    monkeypatch.setattr(doctor_report_service, "record_doctor_feedback", record)
    executor = AgentExecutor(db)
    executor._current_user_id = 1

    result = await executor._exec_record_doctor_feedback({field: "诊" * 4001})

    _assert_local_rejection(
        result,
        error_code="doctor_feedback_field_too_long",
    )
    record.assert_not_called()


@pytest.mark.asyncio
async def test_doctor_feedback_defaults_visit_date_to_kernel_reference_date(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.services.agent_executor import AgentExecutor

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    monkeypatch.setattr(
        executor,
        "_agent_kernel_reference_now",
        lambda: datetime.fromisoformat("2026-08-01T21:30:00+08:00"),
    )

    result = await executor._exec_record_doctor_feedback(
        {"assessment": "臀肌无力导致腰肌代偿"}
    )

    payload = json.loads(result)
    entry = db.query(ClinicalJournalEntry).filter_by(user_id=user.id).one()
    assert payload["id"] == entry.id
    assert entry.objective == "医生随访 @ 2026-08-01"


@pytest.mark.asyncio
async def test_doctor_feedback_success_is_owner_scoped_and_receipted(
    db,
    auth_user_and_headers,
):
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.models.user import User
    from app.services.agent_executor import AgentExecutor

    user, _headers = auth_user_and_headers
    other = User(id=user.id + 1, username="doctor-feedback-other", name="其他用户")
    db.add(other)
    db.add(
        ClinicalJournalEntry(
            user_id=other.id,
            assessment="另一位用户的既有记录",
            created_by="doctor",
        )
    )
    db.commit()
    assessment = "臀肌无力导致腰肌代偿，进而引发腰肌痛"
    executor = AgentExecutor(db)
    executor._current_user_id = user.id

    result = await executor._exec_record_doctor_feedback(
        {
            "summary": "  医生复诊反馈  ",
            "assessment": assessment,
            "plan": "  减少负重训练  ",
            "visit_date": "2026-08-01",
        }
    )

    payload = json.loads(result)
    current_rows = (
        db.query(ClinicalJournalEntry)
        .filter(ClinicalJournalEntry.user_id == user.id)
        .all()
    )
    other_rows = (
        db.query(ClinicalJournalEntry)
        .filter(ClinicalJournalEntry.user_id == other.id)
        .all()
    )
    assert len(current_rows) == 1
    assert len(other_rows) == 1
    entry = current_rows[0]
    assert entry.created_by == "doctor"
    assert entry.assessment == assessment
    assert entry.subjective == "医生复诊反馈"
    assert entry.plan == "减少负重训练"
    assert entry.objective == "医生随访 @ 2026-08-01"
    assert isinstance(payload["id"], int) and payload["id"] > 0
    assert payload["id"] == entry.id
    assert payload["resource_type"] == "clinical_journal_entry"
    assert payload["created_by"] == "doctor"


@pytest.mark.asyncio
async def test_doctor_feedback_visible_content_preserves_format_controls(
    db,
    auth_user_and_headers,
):
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.services.agent_executor import AgentExecutor

    user, _headers = auth_user_and_headers
    assessment = "\u200b医生判断保持原文\ufeff"
    executor = AgentExecutor(db)
    executor._current_user_id = user.id

    result = await executor._exec_record_doctor_feedback(
        {"assessment": assessment}
    )

    payload = json.loads(result)
    entry = db.query(ClinicalJournalEntry).filter_by(user_id=user.id).one()
    assert payload["id"] == entry.id
    assert entry.assessment == assessment


@pytest.mark.asyncio
async def test_doctor_feedback_executes_through_gateway_for_current_owner(
    db,
    auth_user_and_headers,
):
    from app.models.agent_runtime import AgentToolOperation
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.models.user import User
    from app.services.agent_executor import (
        AgentExecutor,
        _write_receipt_from_tool_result,
    )
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    other = User(
        id=user.id + 1,
        username="doctor-feedback-gateway-other",
        name="网关其他用户",
    )
    db.add(other)
    db.commit()
    assessment = "臀肌无力导致腰肌代偿"
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-doctor-feedback-gateway",
        attempt_id="attempt-doctor-feedback-gateway",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-doctor-feedback-gateway",
        origin="test",
    )
    runtime.mark_running(admission.context)
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = f"请记录医生诊断：{assessment}"
    executor._runtime_run_id = admission.context.run_id
    executor._runtime_attempt_id = admission.context.attempt_id
    executor._runtime_managed = True
    args = {
        "assessment": assessment,
        "user_id": other.id,
        "owner_id": other.id,
    }

    result = await executor._execute_tool(
        "record_doctor_feedback",
        args,
        None,
    )

    payload = json.loads(result)
    receipt = _write_receipt_from_tool_result(
        "record_doctor_feedback",
        args,
        result,
    )
    entry = db.query(ClinicalJournalEntry).one()
    operation = db.query(AgentToolOperation).one()
    assert executor._agent_kernel_last_decision is not None
    assert executor._agent_kernel_last_decision.action == "allow"
    assert entry.user_id == user.id
    assert entry.user_id != other.id
    assert payload["id"] == entry.id
    assert receipt is not None
    assert receipt["status"] == "verified"
    assert receipt["resource_type"] == "clinical_journal_entry"
    assert receipt["resource_id"] == str(entry.id)
    assert operation.status == "succeeded"
    assert operation.resource_type == "clinical_journal_entry"
    assert operation.resource_id == str(entry.id)


@pytest.mark.asyncio
async def test_doctor_feedback_service_failure_rolls_back_and_is_log_safe(
    db,
    auth_user_and_headers,
    monkeypatch,
    caplog,
):
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.services import doctor_report_service
    from app.services.agent_executor import (
        AgentExecutor,
        _write_receipt_from_tool_result,
    )

    user, _headers = auth_user_and_headers
    private_text = "臀肌无力导致腰肌代偿"

    def add_then_fail(db_session, **kwargs):
        db_session.add(
            ClinicalJournalEntry(
                user_id=kwargs["user_id"],
                assessment=private_text,
                created_by="doctor",
            )
        )
        raise RuntimeError(private_text)

    monkeypatch.setattr(
        doctor_report_service,
        "record_doctor_feedback",
        add_then_fail,
    )
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    caplog.set_level(logging.ERROR, logger="app.services.agent_executor")

    result = await executor._exec_record_doctor_feedback(
        {"assessment": private_text}
    )

    _assert_uncertain_write(result)
    assert _write_receipt_from_tool_result(
        "record_doctor_feedback",
        {"assessment": private_text},
        result,
    ) is None
    assert db.query(ClinicalJournalEntry).count() == 0
    assert "record_doctor_feedback" in caplog.text
    assert "RuntimeError" in caplog.text
    assert private_text not in caplog.text


@pytest.mark.asyncio
async def test_doctor_feedback_refresh_failure_after_commit_is_uncertain_without_receipt(
    db,
    auth_user_and_headers,
    monkeypatch,
    caplog,
):
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.services.agent_executor import (
        AgentExecutor,
        _write_receipt_from_tool_result,
    )

    user, _headers = auth_user_and_headers
    private_text = "医生评估原文"

    def fail_refresh(_instance):
        raise RuntimeError(private_text)

    monkeypatch.setattr(db, "refresh", fail_refresh)
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    caplog.set_level(logging.ERROR, logger="app.services.agent_executor")

    result = await executor._exec_record_doctor_feedback(
        {"assessment": private_text}
    )

    _assert_uncertain_write(result)
    assert _write_receipt_from_tool_result(
        "record_doctor_feedback",
        {"assessment": private_text},
        result,
    ) is None
    db.expire_all()
    rows = db.query(ClinicalJournalEntry).filter_by(user_id=user.id).all()
    assert len(rows) == 1
    assert rows[0].assessment == private_text
    assert private_text not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ("wrong_owner", "not_persisted", "old_row"))
async def test_doctor_feedback_rejects_forged_or_unverified_service_entry(
    db,
    auth_user_and_headers,
    monkeypatch,
    failure_kind,
):
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.models.user import User
    from app.services import doctor_report_service
    from app.services.agent_executor import (
        AgentExecutor,
        _write_receipt_from_tool_result,
    )

    user, _headers = auth_user_and_headers
    assessment = "需要持久化核验的新评估"
    if failure_kind == "wrong_owner":
        other = User(
            id=user.id + 1,
            username="doctor-feedback-forged-owner",
            name="伪造归属用户",
        )
        db.add(other)
        forged = ClinicalJournalEntry(
            user_id=other.id,
            assessment=assessment,
            created_by="doctor",
        )
        db.add(forged)
        db.commit()
    elif failure_kind == "not_persisted":
        forged = ClinicalJournalEntry(
            id=999,
            user_id=user.id,
            assessment=assessment,
            created_by="doctor",
        )
    else:
        forged = ClinicalJournalEntry(
            user_id=user.id,
            assessment="旧评估",
            created_by="doctor",
        )
        db.add(forged)
        db.commit()

    monkeypatch.setattr(
        doctor_report_service,
        "record_doctor_feedback",
        Mock(return_value=forged),
    )
    executor = AgentExecutor(db)
    executor._current_user_id = user.id

    result = await executor._exec_record_doctor_feedback(
        {"assessment": assessment}
    )

    _assert_uncertain_write(result)
    assert _write_receipt_from_tool_result(
        "record_doctor_feedback",
        {"assessment": assessment},
        result,
    ) is None


@pytest.mark.asyncio
async def test_doctor_feedback_rollback_failure_does_not_leak_private_text(
    db,
    auth_user_and_headers,
    monkeypatch,
    caplog,
):
    from app.services import doctor_report_service
    from app.services.agent_executor import AgentExecutor

    user, _headers = auth_user_and_headers
    private_text = "私密医生评估内容"
    monkeypatch.setattr(
        doctor_report_service,
        "record_doctor_feedback",
        Mock(side_effect=RuntimeError(private_text)),
    )
    monkeypatch.setattr(
        db,
        "rollback",
        Mock(side_effect=RuntimeError(f"rollback:{private_text}")),
    )
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    caplog.set_level(logging.ERROR, logger="app.services.agent_executor")

    result = await executor._exec_record_doctor_feedback(
        {"assessment": private_text}
    )

    _assert_uncertain_write(result)
    assert private_text not in caplog.text
