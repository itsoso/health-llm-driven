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


def _managed_doctor_feedback_executor(db, *, user_id: int, run_suffix: str):
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_runtime import AgentRuntimeCoordinator

    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id=f"run-doctor-feedback-{run_suffix}",
        attempt_id=f"attempt-doctor-feedback-{run_suffix}",
        user_id=user_id,
        conversation_id=None,
        client_turn_id=f"turn-doctor-feedback-{run_suffix}",
        origin="test",
    )
    runtime.mark_running(admission.context)
    executor = AgentExecutor(db)
    executor._current_user_id = user_id
    executor._current_turn_user_message = "请记录医生诊断：当前评估"
    executor._runtime_run_id = admission.context.run_id
    executor._runtime_attempt_id = admission.context.attempt_id
    executor._runtime_managed = True
    executor._agent_kernel_reference_now = lambda: datetime.fromisoformat(
        "2026-08-01T21:30:00+08:00"
    )
    return executor


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
@pytest.mark.parametrize("field", ("summary", "assessment", "plan"))
async def test_doctor_feedback_rejects_non_string_text_before_service(
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

    result = await executor._exec_record_doctor_feedback(
        {field: {"unexpected": "structured value"}}
    )

    _assert_local_rejection(
        result,
        error_code="doctor_feedback_field_invalid",
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


def test_doctor_feedback_canonicalizer_drops_unknowns_and_normalizes_equivalents():
    from app.services.agent_executor import _canonicalize_doctor_feedback_args

    reference_now = datetime.fromisoformat("2026-08-01T21:30:00+08:00")
    canonical = _canonicalize_doctor_feedback_args(
        {
            "owner_id": 999,
            "plan": "  下一步计划  ",
            "assessment": " \u200b医生判断\ufeff ",
            "summary": "",
            "visit_date": " ",
            "user_id": 999,
        },
        reference_now=reference_now,
    )

    assert canonical == {
        "summary": None,
        "assessment": "\u200b医生判断\ufeff",
        "plan": "下一步计划",
        "visit_date": "2026-08-01",
    }


def test_doctor_feedback_exact_null_sql_is_portable():
    from sqlalchemy.dialects import postgresql, sqlite

    from app.models.clinical_journal import ClinicalJournalEntry
    from app.services.agent_executor import _doctor_feedback_exact_sql

    predicate = _doctor_feedback_exact_sql(
        ClinicalJournalEntry.subjective,
        None,
    )

    for dialect in (sqlite.dialect(), postgresql.dialect()):
        compiled = str(
            predicate.compile(
                dialect=dialect,
                compile_kwargs={"literal_binds": True},
            )
        ).upper()
        assert " IS NULL" in compiled
        assert " = NULL" not in compiled


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "assessment"),
    (
        (
            "请记录医生意见：按医嘱调整训练强度",
            "按医嘱调整训练强度",
        ),
        (
            "请记录医生医嘱：患者需要按医嘱调整用药剂量",
            "患者需要按医嘱调整用药剂量",
        ),
        (
            "请记录医生意见：根据医生建议调整训练强度",
            "根据医生建议调整训练强度",
        ),
        (
            "请记录医生意见：按医🩺嘱调整训练强度",
            "按医🩺嘱调整训练强度",
        ),
        ("请记录医生意见：餐后记录血糖", "餐后记录血糖"),
        ("请记录医生意见：术后记录血压", "术后记录血压"),
        ("请记录医生意见：运动后记录疼痛", "运动后记录疼痛"),
        ("请记录医生意见：服药后记录反应", "服药后记录反应"),
        ("请记录医生意见：术后提醒复查", "术后提醒复查"),
        (
            "请记录医生诊断：医生让我训练，医 生",
            "医生让我训练，医 生",
        ),
        ("请记录医生诊断：保存方法，保 存", "保存方法，保 存"),
        (
            "请记录医生诊断：诊断是臀肌无力，诊\u200b断",
            "诊断是臀肌无力，诊\u200b断",
        ),
        (
            "请记录医生意见：根据医★生建议调整训练强度",
            "根据医★生建议调整训练强度",
        ),
        (
            "请记录医生意见：根据医生建★议调整训练强度",
            "根据医生建★议调整训练强度",
        ),
        (
            "请记录医生意见：根据医生建议调★整训练强度",
            "根据医生建议调★整训练强度",
        ),
    ),
)
async def test_doctor_feedback_executes_through_gateway_for_current_owner(
    db,
    auth_user_and_headers,
    message,
    assessment,
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
    executor._current_turn_user_message = message
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
    assert entry.assessment == assessment
    assert payload["id"] == entry.id
    assert receipt is not None
    assert receipt["status"] == "verified"
    assert receipt["resource_type"] == "clinical_journal_entry"
    assert receipt["resource_id"] == str(entry.id)
    assert operation.status == "succeeded"
    assert operation.resource_type == "clinical_journal_entry"
    assert operation.resource_id == str(entry.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "遵医嘱删除这条用药记录",
        "按医嘱停药并删除记录",
        "请遵医嘱删除这条用药记录",
        "麻烦按医嘱停药并删除记录",
        "我想遵医嘱删除这条用药记录",
        "那就按医嘱停药并删除记录",
        "请根据医生诊断删除这条用药记录",
        "希望按医嘱删除这条用药记录",
        "需要遵医嘱删除这条用药记录",
        "先按医嘱删除这条用药记录",
        "顺便按医嘱删除这条用药记录",
        "请您按医嘱删除这条用药记录",
        "麻烦您按医嘱删除这条用药记录",
        "希望能按医嘱删除这条用药记录",
        "我要按医嘱删除这条用药记录",
        "可以按医嘱删除这条用药记录",
        "如果按医嘱删除这条用药记录",
        "并非要按医嘱删除这条用药记录",
        "如果需要就根据医生诊断删除这条用药记录",
        "请您遵照医嘱删除昨天的用药记录",
        "请您依照医嘱删除昨天的用药记录",
        "请您照医嘱删除昨天的用药记录",
        "请您按着医嘱删除昨天的用药记录",
        "请您按，医嘱删除昨天的用药记录",
        "请您按/医嘱删除昨天的用药记录",
        "请您按医，嘱删除昨天的用药记录",
        "请您照着医嘱删除昨天的用药记录",
        "请您听从医嘱删除昨天的用药记录",
        "请您遵循医嘱删除昨天的用药记录",
        "请您医嘱删除昨天的用药记录",
        "请按医\ufe0f嘱删除记录",
        "请按医\u034f嘱删除记录",
        "请按医🩺嘱删除记录",
        "请按医★嘱删除记录",
        "请按医\u0007嘱删除记录",
        "请按医\u007f嘱删除记录",
        "请按医\u0080嘱删除记录",
        "请按医\ue000嘱删除记录",
        "请按医\ufdd0嘱删除记录",
        "请按醫囑删除记录",
        "请遵嘱删除记录",
        "请依嘱删除记录",
        "请记录医生意见：按医嘱调整训练强度，然后按医嘱删除昨天用药记录",
        "请记录医生意见：按医嘱调整训练强度，然后按照医生意见同步健康数据",
        "按医嘱调整剂量有什么风险吗，顺便记录早餐",
        "按医嘱调整剂量有什么风险吗，并创建一个提醒",
        "按医嘱调整剂量有什么风险吗，查询昨天的体重",
        "请比较按医嘱调整剂量和自行调整剂量的风险并记录早餐",
        "“说明”按医嘱删除记录是什么意思“结尾”？",
        "我想了解按医嘱调整剂量的风险，查询昨天体重",
        "分析按医嘱调整剂量的副作用并记录早餐",
        "解释“按医嘱删除记录”的意思并创建提醒",
        "按医嘱调整剂量的风险并生成图片",
        "按医嘱调整剂量的风险并制定计划",
        "可以按醫囑删除记录吗？",
        "我想了解按医嘱删除这条记录并记录早餐有什么风险？",
        "我想了解按医嘱删除这条记录并★记录早餐有什么风险？",
        "我想了解按医嘱调整剂量并★查询昨天体重有什么风险？",
        "分析按医嘱调整剂量并🩺创建提醒的副作用",
        "分析按医嘱调整剂量后记录早餐的副作用",
        "分析按医嘱调整剂量之后制定计划的副作用",
        "按医嘱调整剂量而生成图片的风险",
        "分析按医嘱调整剂量接下来查询体重的副作用",
        "分析按医嘱调整剂量并立即记录早餐的副作用",
        "分析按医嘱调整剂量接下来记录早餐的副作用",
        "分析按医嘱调整剂量然后去记录早餐的副作用",
        "分析按医嘱调整剂量然后去设置闹钟的副作用",
        "分析按医嘱调整剂量接下来生成图片的副作用",
        "分析按医嘱调整剂量随后开始制定计划的副作用",
    ),
)
async def test_medical_instruction_basis_blocks_direct_destructive_dispatch(
    db,
    monkeypatch,
    message,
):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = message
    dispatch = AsyncMock()
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)

    result = await executor._execute_tool(
        "health_manage",
        {
            "record_type": "medication",
            "operation": "delete",
            "record_id": 1,
        },
        None,
    )

    _assert_local_rejection(
        result,
        error_code="clinician_provenance_tool_not_authorized",
    )
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    ("请您删除用药记录 1", "请您删除用药记录 1🩺"),
)
async def test_ordinary_delete_without_clinician_basis_dispatches(
    db,
    monkeypatch,
    message,
):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = message
    dispatch = AsyncMock(
        return_value=json.dumps({"success": True, "deleted_id": 1})
    )
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)

    result = await executor._execute_tool(
        "health_manage",
        {
            "record_type": "medication",
            "operation": "delete",
            "record_id": 1,
        },
        None,
    )

    assert json.loads(result)["success"] is True
    dispatch.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "按医嘱调整用药剂量会有什么风险？",
        "医生说按医嘱调整剂量会有副作用吗？",
        "为什么要按医嘱调整剂量？",
        "请比较按医嘱调整剂量和自行调整剂量的风险",
        "“按医嘱删除记录”是什么意思？",
        "搜索“按医嘱删除记录”的法律含义",
        "照着医嘱调整剂量会有什么风险？",
        "“听从医嘱删除记录”是什么意思？",
        "我想了解按医嘱调整剂量的风险",
        "分析按医嘱调整剂量的副作用",
        "解释“按医嘱删除记录”的意思",
        "按医嘱调整剂量的风险",
        "我想了解按医嘱删除记录的风险",
        "我想了解按医嘱删除这条用药记录的风险",
        "按医嘱同步数据有什么风险？",
        "分析按医\ufe0f嘱调整剂量的风险",
        "解释“按医★嘱删除记录”的意思",
    ),
)
async def test_medical_basis_analysis_dispatches_reads_not_mutations(
    db,
    monkeypatch,
    message,
):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = message
    dispatch = AsyncMock(return_value=json.dumps({"success": True}))
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)

    mutation_result = await executor._execute_tool(
        "health_manage",
        {
            "record_type": "medication",
            "operation": "delete",
            "record_id": 1,
        },
        None,
    )
    read_result = await executor._execute_tool(
        "knowledge_search",
        {"query": message},
        None,
    )

    mutation_payload = json.loads(mutation_result)
    assert mutation_payload["status"] == "rejected"
    assert mutation_payload["dispatch_started"] is False
    assert (
        mutation_payload["error_code"]
        == "manage_write_without_mutate_intent"
    )
    assert json.loads(read_result)["success"] is True
    dispatch.assert_awaited_once()
    assert dispatch.await_args.args[0].tool_name == "knowledge_search"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_name", "first_args", "second_args"),
    (
        (
            "blank_unknowns",
            {"assessment": "目标内容"},
            {
                "summary": "",
                "assessment": " 目标内容 ",
                "visit_date": "",
                "owner_id": 999,
                "user_id": 999,
            },
        ),
        (
            "explicit_default_date",
            {"assessment": "目标内容"},
            {"visit_date": "2026-08-01", "assessment": "目标内容"},
        ),
        (
            "field_order",
            {
                "summary": "复诊摘要",
                "assessment": "目标内容",
                "plan": "下一步计划",
            },
            {
                "plan": "下一步计划",
                "assessment": "目标内容",
                "summary": "复诊摘要",
            },
        ),
    ),
)
async def test_doctor_feedback_runtime_binds_raw_turn_and_rejects_second_dispatch(
    db,
    auth_user_and_headers,
    monkeypatch,
    case_name,
    first_args,
    second_args,
):
    from app.models.agent_runtime import AgentToolOperation
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.services.agent_executor import (
        AgentExecutor,
        _write_receipt_from_tool_result,
    )
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id=f"run-doctor-feedback-canonical-{case_name}",
        attempt_id=f"attempt-doctor-feedback-canonical-{case_name}",
        user_id=user.id,
        conversation_id=None,
        client_turn_id=f"turn-doctor-feedback-canonical-{case_name}",
        origin="test",
    )
    runtime.mark_running(admission.context)
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = "请记录医生诊断：目标内容"
    executor._runtime_run_id = admission.context.run_id
    executor._runtime_attempt_id = admission.context.attempt_id
    executor._runtime_managed = True
    monkeypatch.setattr(
        executor,
        "_agent_kernel_reference_now",
        lambda: datetime.fromisoformat("2026-08-01T21:30:00+08:00"),
    )
    handler_args = []
    real_handler = executor._exec_record_doctor_feedback

    async def capture_handler_args(args):
        handler_args.append(dict(args))
        return await real_handler(args)

    monkeypatch.setattr(
        executor,
        "_exec_record_doctor_feedback",
        capture_handler_args,
    )

    first_result = await executor._execute_tool(
        "record_doctor_feedback",
        first_args,
        None,
    )
    second_result = await executor._execute_tool(
        "record_doctor_feedback",
        second_args,
        None,
    )

    first_payload = json.loads(first_result)
    second_payload = json.loads(second_result)
    first_receipt = _write_receipt_from_tool_result(
        "record_doctor_feedback", first_args, first_result
    )
    second_receipt = _write_receipt_from_tool_result(
        "record_doctor_feedback", second_args, second_result
    )
    rows = db.query(ClinicalJournalEntry).filter_by(user_id=user.id).all()
    operations = db.query(AgentToolOperation).all()
    assert len(rows) == 1
    assert len(operations) == 1
    assert len(handler_args) == 1
    assert set(handler_args[0]) == {
        "summary",
        "assessment",
        "plan",
        "visit_date",
    }
    assert handler_args[0]["visit_date"] == "2026-08-01"
    assert handler_args[0]["summary"] is None
    assert handler_args[0]["assessment"] == "目标内容"
    assert handler_args[0]["plan"] is None
    assert second_payload == {
        "status": "rejected",
        "success": False,
        "dispatch_started": False,
        "error_code": "doctor_feedback_turn_cardinality_exceeded",
        "message": "本回合已经处理过一次医生反馈保存请求。",
        "recovery_guidance": "不要在同一回合再次调用该工具。",
    }
    assert first_receipt is not None
    assert second_receipt is None
    assert first_receipt["resource_id"] == str(first_payload["id"])
    assert operations[0].status == "succeeded"


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
async def test_doctor_feedback_exact_matching_old_row_cannot_forge_freshness(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.services import doctor_report_service
    from app.services.agent_executor import (
        AgentExecutor,
        _write_receipt_from_tool_result,
    )

    user, _headers = auth_user_and_headers
    assessment = "与请求完全一致的医生评估"
    old = ClinicalJournalEntry(
        user_id=user.id,
        subjective=None,
        objective="医生随访 @ 2026-08-01",
        assessment=assessment,
        plan=None,
        created_by="doctor",
    )
    db.add(old)
    db.commit()
    old_id = old.id
    monkeypatch.setattr(
        doctor_report_service,
        "record_doctor_feedback",
        Mock(return_value=old),
    )
    executor = AgentExecutor(db)
    executor._current_user_id = user.id

    result = await executor._exec_record_doctor_feedback(
        {"assessment": assessment, "visit_date": "2026-08-01"}
    )

    _assert_uncertain_write(result)
    assert _write_receipt_from_tool_result(
        "record_doctor_feedback",
        {"assessment": assessment, "visit_date": "2026-08-01"},
        result,
    ) is None
    rows = db.query(ClinicalJournalEntry).filter_by(user_id=user.id).all()
    assert len(rows) == 1
    assert rows[0].id == old_id


@pytest.mark.asyncio
async def test_doctor_feedback_service_cannot_insert_new_row_but_return_old_row(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.services import doctor_report_service
    from app.services.agent_executor import (
        AgentExecutor,
        _write_receipt_from_tool_result,
    )

    user, _headers = auth_user_and_headers
    old = ClinicalJournalEntry(
        user_id=user.id,
        objective="医生随访 @ 2026-08-01",
        assessment="新行",
        created_by="doctor",
    )
    db.add(old)
    db.commit()
    old_id = old.id
    real_record = doctor_report_service.record_doctor_feedback

    def insert_new_but_return_old(db_session, **kwargs):
        real_record(db_session, **kwargs)
        return old

    monkeypatch.setattr(
        doctor_report_service,
        "record_doctor_feedback",
        insert_new_but_return_old,
    )
    executor = AgentExecutor(db)
    executor._current_user_id = user.id

    result = await executor._exec_record_doctor_feedback(
        {"assessment": "新行", "visit_date": "2026-08-01"}
    )

    _assert_uncertain_write(result)
    assert _write_receipt_from_tool_result(
        "record_doctor_feedback",
        {"assessment": "新行", "visit_date": "2026-08-01"},
        result,
    ) is None
    rows = db.query(ClinicalJournalEntry).filter_by(user_id=user.id).all()
    assert len(rows) == 2
    assert {row.id for row in rows} > {old_id}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "concurrent_case",
    ("same_owner_different", "other_owner_different", "other_owner_exact"),
)
async def test_doctor_feedback_concurrent_insert_keeps_requested_receipt_verified(
    db,
    auth_user_and_headers,
    monkeypatch,
    concurrent_case,
):
    from app.models.agent_runtime import AgentToolOperation
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.models.user import User
    from app.services import doctor_report_service
    from app.services.agent_executor import _write_receipt_from_tool_result

    user, _headers = auth_user_and_headers
    concurrent_user_id = user.id
    if concurrent_case.startswith("other_owner"):
        other = User(
            id=user.id + 1,
            username=f"doctor-feedback-{concurrent_case}",
            name="并发反馈其他用户",
        )
        db.add(other)
        db.commit()
        concurrent_user_id = other.id
    real_record = doctor_report_service.record_doctor_feedback
    requested_id = None
    concurrent_id = None

    def record_with_concurrent_insert(db_session, **kwargs):
        nonlocal requested_id, concurrent_id
        requested = real_record(db_session, **kwargs)
        requested_id = requested.id
        if concurrent_case == "other_owner_exact":
            concurrent = ClinicalJournalEntry(
                user_id=concurrent_user_id,
                subjective=kwargs["summary"],
                objective=f"医生随访 @ {kwargs['visit_date'].isoformat()}",
                assessment=kwargs["assessment"],
                plan=kwargs["plan"],
                created_by="doctor",
            )
        else:
            concurrent = ClinicalJournalEntry(
                user_id=concurrent_user_id,
                assessment="并发创建的另一条医生反馈",
                created_by="doctor",
            )
        db_session.add(concurrent)
        db_session.commit()
        db_session.refresh(concurrent)
        concurrent_id = concurrent.id
        return requested

    monkeypatch.setattr(
        doctor_report_service,
        "record_doctor_feedback",
        record_with_concurrent_insert,
    )
    executor = _managed_doctor_feedback_executor(
        db,
        user_id=user.id,
        run_suffix=f"concurrent-{concurrent_case}",
    )
    args = {"assessment": "当前请求的医生反馈", "visit_date": "2026-08-01"}

    result = await executor._execute_tool("record_doctor_feedback", args, None)

    payload = json.loads(result)
    receipt = _write_receipt_from_tool_result(
        "record_doctor_feedback", args, result
    )
    rows = db.query(ClinicalJournalEntry).all()
    operation = db.query(AgentToolOperation).one()
    assert requested_id is not None
    assert concurrent_id is not None
    assert requested_id < concurrent_id
    assert len(rows) == 2
    assert payload["id"] == requested_id
    assert receipt is not None
    assert receipt["status"] == "verified"
    assert receipt["resource_id"] == str(requested_id)
    assert operation.status == "succeeded"
    assert operation.resource_id == str(requested_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("returned_row", ("requested", "duplicate"))
async def test_doctor_feedback_runtime_rejects_ambiguous_fresh_exact_duplicates(
    db,
    auth_user_and_headers,
    monkeypatch,
    returned_row,
):
    from app.models.agent_runtime import AgentToolOperation
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.services import doctor_report_service
    from app.services.agent_executor import _write_receipt_from_tool_result

    user, _headers = auth_user_and_headers
    real_record = doctor_report_service.record_doctor_feedback
    requested_id = None
    duplicate_id = None

    def record_with_exact_duplicate(db_session, **kwargs):
        nonlocal requested_id, duplicate_id
        requested = real_record(db_session, **kwargs)
        requested_id = requested.id
        duplicate = ClinicalJournalEntry(
            user_id=kwargs["user_id"],
            subjective=kwargs["summary"],
            objective=f"医生随访 @ {kwargs['visit_date'].isoformat()}",
            assessment=kwargs["assessment"],
            plan=kwargs["plan"],
            created_by="doctor",
        )
        db_session.add(duplicate)
        db_session.commit()
        db_session.refresh(duplicate)
        duplicate_id = duplicate.id
        return requested if returned_row == "requested" else duplicate

    monkeypatch.setattr(
        doctor_report_service,
        "record_doctor_feedback",
        record_with_exact_duplicate,
    )
    executor = _managed_doctor_feedback_executor(
        db,
        user_id=user.id,
        run_suffix=f"ambiguous-exact-{returned_row}",
    )
    args = {
        "summary": "完全相同的当前摘要",
        "assessment": "完全相同的当前评估",
        "plan": "完全相同的当前计划",
        "visit_date": "2026-08-01",
    }

    result = await executor._execute_tool("record_doctor_feedback", args, None)

    _assert_uncertain_write(result)
    assert _write_receipt_from_tool_result(
        "record_doctor_feedback", args, result
    ) is None
    rows = db.query(ClinicalJournalEntry).all()
    operation = db.query(AgentToolOperation).one()
    assert requested_id is not None
    assert duplicate_id is not None
    assert requested_id < duplicate_id
    assert len(rows) == 2
    assert {row.id for row in rows} == {requested_id, duplicate_id}
    assert operation.status == "reconciliation_required"
    assert operation.error_code == "write_uncertain"
    assert operation.resource_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("returned_row", ("requested", "low_id_duplicate"))
async def test_doctor_feedback_runtime_rejects_fresh_exact_low_id_duplicate(
    db,
    auth_user_and_headers,
    monkeypatch,
    returned_row,
):
    from app.models.agent_runtime import AgentToolOperation
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.services import doctor_report_service
    from app.services.agent_executor import _write_receipt_from_tool_result

    user, _headers = auth_user_and_headers
    db.add(
        ClinicalJournalEntry(
            id=100,
            user_id=user.id,
            assessment="用于建立全局高水位的不相关记录",
            created_by="doctor",
        )
    )
    db.commit()
    real_record = doctor_report_service.record_doctor_feedback
    requested_id = None

    def record_with_low_id_exact_duplicate(db_session, **kwargs):
        nonlocal requested_id
        requested = real_record(db_session, **kwargs)
        requested_id = requested.id
        low_id_duplicate = ClinicalJournalEntry(
            id=50,
            user_id=kwargs["user_id"],
            subjective=kwargs["summary"],
            objective=f"医生随访 @ {kwargs['visit_date'].isoformat()}",
            assessment=kwargs["assessment"],
            plan=kwargs["plan"],
            created_by="doctor",
        )
        db_session.add(low_id_duplicate)
        db_session.commit()
        db_session.refresh(low_id_duplicate)
        return requested if returned_row == "requested" else low_id_duplicate

    monkeypatch.setattr(
        doctor_report_service,
        "record_doctor_feedback",
        record_with_low_id_exact_duplicate,
    )
    executor = _managed_doctor_feedback_executor(
        db,
        user_id=user.id,
        run_suffix=f"low-id-exact-{returned_row}",
    )
    args = {
        "summary": "低 ID 重复摘要",
        "assessment": "低 ID 重复评估",
        "plan": "低 ID 重复计划",
        "visit_date": "2026-08-01",
    }

    result = await executor._execute_tool("record_doctor_feedback", args, None)

    _assert_uncertain_write(result)
    assert _write_receipt_from_tool_result(
        "record_doctor_feedback", args, result
    ) is None
    rows = db.query(ClinicalJournalEntry).all()
    operation = db.query(AgentToolOperation).one()
    assert requested_id == 101
    assert {row.id for row in rows} == {50, 100, 101}
    assert operation.status == "reconciliation_required"
    assert operation.error_code == "write_uncertain"
    assert operation.resource_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("duplicate_id", "expected_requested_id"),
    ((101, 102), (50, 101)),
)
async def test_doctor_feedback_runtime_rejects_exact_insert_between_pre_snapshots(
    db,
    auth_user_and_headers,
    monkeypatch,
    duplicate_id,
    expected_requested_id,
):
    from app.models.agent_runtime import AgentToolOperation
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.services.agent_executor import _write_receipt_from_tool_result

    user, _headers = auth_user_and_headers
    db.add(
        ClinicalJournalEntry(
            id=100,
            user_id=user.id,
            assessment="用于建立竞态窗口高水位的不相关记录",
            created_by="doctor",
        )
    )
    db.commit()
    executor = _managed_doctor_feedback_executor(
        db,
        user_id=user.id,
        run_suffix=f"between-snapshots-{duplicate_id}",
    )
    args = {
        "assessment": "当前评估",
        "visit_date": "2026-08-01",
    }
    original_query = db.query
    injected = False

    class InjectExactRowAfterJournalMaxScalar:
        def __init__(self, query):
            self._query = query

        def scalar(self):
            nonlocal injected
            value = self._query.scalar()
            if not injected:
                injected = True
                db.add(
                    ClinicalJournalEntry(
                        id=duplicate_id,
                        user_id=user.id,
                        subjective=None,
                        objective="医生随访 @ 2026-08-01",
                        assessment=args["assessment"],
                        plan=None,
                        created_by="doctor",
                    )
                )
                db.commit()
            return value

        def __getattr__(self, name):
            return getattr(self._query, name)

    def inject_after_journal_max_scalar(*entities, **kwargs):
        query = original_query(*entities, **kwargs)
        is_journal_max = (
            len(entities) == 1
            and getattr(entities[0], "name", None) == "max"
            and "clinical_journal_entries.id" in str(entities[0])
        )
        if is_journal_max:
            return InjectExactRowAfterJournalMaxScalar(query)
        return query

    monkeypatch.setattr(db, "query", inject_after_journal_max_scalar)

    result = await executor._execute_tool("record_doctor_feedback", args, None)

    _assert_uncertain_write(result)
    assert _write_receipt_from_tool_result(
        "record_doctor_feedback", args, result
    ) is None
    monkeypatch.setattr(db, "query", original_query)
    rows = original_query(ClinicalJournalEntry).all()
    operation = original_query(AgentToolOperation).one()
    assert injected is True
    assert {row.id for row in rows} == {100, duplicate_id, expected_requested_id}
    assert operation.status == "reconciliation_required"
    assert operation.error_code == "write_uncertain"
    assert operation.resource_id is None


@pytest.mark.asyncio
async def test_doctor_feedback_success_has_no_final_entity_lookup(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.agent_runtime import AgentToolOperation
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.services.agent_executor import _write_receipt_from_tool_result

    user, _headers = auth_user_and_headers
    executor = _managed_doctor_feedback_executor(
        db,
        user_id=user.id,
        run_suffix="no-final-entity-lookup",
    )
    args = {
        "assessment": "最终 SQL 核验后的成功评估",
        "visit_date": "2026-08-01",
    }
    original_query = db.query
    final_entity_lookups = 0

    def reject_final_entity_lookup(*entities, **kwargs):
        nonlocal final_entity_lookups
        if len(entities) == 1 and entities[0] is ClinicalJournalEntry:
            final_entity_lookups += 1
            raise RuntimeError("final entity lookup must not execute")
        return original_query(*entities, **kwargs)

    monkeypatch.setattr(db, "query", reject_final_entity_lookup)

    result = await executor._execute_tool("record_doctor_feedback", args, None)

    payload = json.loads(result)
    receipt = _write_receipt_from_tool_result(
        "record_doctor_feedback", args, result
    )
    monkeypatch.setattr(db, "query", original_query)
    operation = original_query(AgentToolOperation).one()
    rows = original_query(ClinicalJournalEntry).all()
    assert final_entity_lookups == 0
    assert len(rows) == 1
    assert payload["id"] == rows[0].id
    assert receipt is not None
    assert receipt["status"] == "verified"
    assert receipt["resource_id"] == str(rows[0].id)
    assert operation.status == "succeeded"
    assert operation.resource_id == str(rows[0].id)


@pytest.mark.asyncio
async def test_doctor_feedback_historical_exact_row_does_not_make_new_write_ambiguous(
    db,
    auth_user_and_headers,
):
    from app.models.agent_runtime import AgentToolOperation
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.services.agent_executor import _write_receipt_from_tool_result

    user, _headers = auth_user_and_headers
    args = {
        "summary": "模型生成但不会入库的摘要",
        "assessment": "模型生成但不会入库的评估",
        "plan": "模型生成但不会入库的计划",
        "visit_date": "2026-08-01",
    }
    historical = ClinicalJournalEntry(
        user_id=user.id,
        subjective=None,
        objective="医生随访 @ 2026-08-01",
        assessment="当前评估",
        plan=None,
        created_by="doctor",
    )
    db.add(historical)
    db.commit()
    historical_id = historical.id
    executor = _managed_doctor_feedback_executor(
        db,
        user_id=user.id,
        run_suffix="historical-exact-new-write",
    )

    result = await executor._execute_tool("record_doctor_feedback", args, None)

    payload = json.loads(result)
    receipt = _write_receipt_from_tool_result(
        "record_doctor_feedback", args, result
    )
    rows = db.query(ClinicalJournalEntry).all()
    operation = db.query(AgentToolOperation).one()
    assert len(rows) == 2
    assert payload["id"] != historical_id
    assert receipt is not None
    assert receipt["status"] == "verified"
    assert receipt["resource_id"] == str(payload["id"])
    assert operation.status == "succeeded"
    assert operation.resource_id == str(payload["id"])


@pytest.mark.asyncio
async def test_doctor_feedback_scope_move_plus_new_write_is_ambiguous(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.agent_runtime import AgentToolOperation
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.services import doctor_report_service
    from app.services.agent_executor import _write_receipt_from_tool_result

    user, _headers = auth_user_and_headers
    old = ClinicalJournalEntry(
        user_id=user.id,
        assessment="移动前的旧评估",
        created_by="orchestrator",
    )
    db.add(old)
    db.commit()
    old_id = old.id
    real_record = doctor_report_service.record_doctor_feedback
    requested_id = None

    def record_new_then_move_old_into_scope(db_session, **kwargs):
        nonlocal requested_id
        requested = real_record(db_session, **kwargs)
        requested_id = requested.id
        old.created_by = "doctor"
        old.subjective = kwargs["summary"]
        old.objective = f"医生随访 @ {kwargs['visit_date'].isoformat()}"
        old.assessment = kwargs["assessment"]
        old.plan = kwargs["plan"]
        db_session.commit()
        return requested

    monkeypatch.setattr(
        doctor_report_service,
        "record_doctor_feedback",
        record_new_then_move_old_into_scope,
    )
    executor = _managed_doctor_feedback_executor(
        db,
        user_id=user.id,
        run_suffix="scope-move-plus-new",
    )
    args = {
        "summary": "移动后相同摘要",
        "assessment": "移动后相同评估",
        "plan": "移动后相同计划",
        "visit_date": "2026-08-01",
    }

    result = await executor._execute_tool("record_doctor_feedback", args, None)

    _assert_uncertain_write(result)
    assert _write_receipt_from_tool_result(
        "record_doctor_feedback", args, result
    ) is None
    rows = db.query(ClinicalJournalEntry).all()
    operation = db.query(AgentToolOperation).one()
    assert requested_id is not None
    assert {row.id for row in rows} == {old_id, requested_id}
    assert operation.status == "reconciliation_required"
    assert operation.error_code == "write_uncertain"
    assert operation.resource_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation_kind",
    ("current_orchestrator", "other_owner_doctor"),
)
async def test_doctor_feedback_runtime_rejects_mutated_preexisting_row(
    db,
    auth_user_and_headers,
    monkeypatch,
    mutation_kind,
):
    from app.models.agent_runtime import AgentToolOperation
    from app.models.clinical_journal import ClinicalJournalEntry
    from app.models.user import User
    from app.services import doctor_report_service
    from app.services.agent_executor import _write_receipt_from_tool_result

    user, _headers = auth_user_and_headers
    if mutation_kind == "current_orchestrator":
        old_owner_id = user.id
        old_created_by = "orchestrator"
    else:
        other = User(
            id=user.id + 1,
            username="doctor-feedback-mutated-other",
            name="被篡改反馈其他用户",
        )
        db.add(other)
        db.commit()
        old_owner_id = other.id
        old_created_by = "doctor"
    old = ClinicalJournalEntry(
        user_id=old_owner_id,
        subjective="旧摘要",
        objective="旧客观内容",
        assessment="旧评估",
        plan="旧计划",
        created_by=old_created_by,
    )
    db.add(old)
    db.commit()
    old_id = old.id

    def mutate_old_row(db_session, **kwargs):
        old.user_id = kwargs["user_id"]
        old.created_by = "doctor"
        old.subjective = kwargs["summary"]
        old.assessment = kwargs["assessment"]
        old.plan = kwargs["plan"]
        old.objective = f"医生随访 @ {kwargs['visit_date'].isoformat()}"
        db_session.commit()
        db_session.refresh(old)
        return old

    monkeypatch.setattr(
        doctor_report_service,
        "record_doctor_feedback",
        mutate_old_row,
    )
    executor = _managed_doctor_feedback_executor(
        db,
        user_id=user.id,
        run_suffix=f"mutated-{mutation_kind}",
    )
    args = {
        "summary": "当前摘要",
        "assessment": "当前评估",
        "plan": "当前计划",
        "visit_date": "2026-08-01",
    }

    result = await executor._execute_tool("record_doctor_feedback", args, None)

    _assert_uncertain_write(result)
    assert _write_receipt_from_tool_result(
        "record_doctor_feedback", args, result
    ) is None
    rows = db.query(ClinicalJournalEntry).all()
    operation = db.query(AgentToolOperation).one()
    assert len(rows) == 1
    assert rows[0].id == old_id
    assert rows[0].user_id == user.id
    assert rows[0].created_by == "doctor"
    assert rows[0].assessment == "当前评估"
    assert operation.status == "reconciliation_required"
    assert operation.error_code == "write_uncertain"
    assert operation.resource_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_call", (1, 2))
async def test_doctor_feedback_prewrite_snapshot_failure_is_non_dispatched_and_log_safe(
    db,
    auth_user_and_headers,
    monkeypatch,
    caplog,
    failure_call,
):
    from app.services import doctor_report_service
    from app.services.agent_executor import AgentExecutor

    user, _headers = auth_user_and_headers
    private_text = "私密快照异常内容"
    record = Mock(side_effect=AssertionError("service must not run"))
    monkeypatch.setattr(doctor_report_service, "record_doctor_feedback", record)
    original_query = db.query
    query_calls = 0

    def fail_selected_prewrite_query(*entities, **kwargs):
        nonlocal query_calls
        query_calls += 1
        if query_calls == failure_call:
            raise RuntimeError(private_text)
        return original_query(*entities, **kwargs)

    monkeypatch.setattr(db, "query", fail_selected_prewrite_query)
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    caplog.set_level(logging.ERROR, logger="app.services.agent_executor")

    result = await executor._exec_record_doctor_feedback(
        {"assessment": "可见医生评估"}
    )

    _assert_local_rejection(
        result,
        error_code="doctor_feedback_snapshot_unavailable",
    )
    record.assert_not_called()
    assert private_text not in caplog.text


@pytest.mark.asyncio
async def test_doctor_feedback_postwrite_snapshot_failure_is_uncertain(
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
    private_text = "私密持久化核验异常"
    original_query = db.query
    query_calls = 0

    def fail_postwrite_query(*entities, **kwargs):
        nonlocal query_calls
        query_calls += 1
        if query_calls > 2:
            raise RuntimeError(private_text)
        return original_query(*entities, **kwargs)

    monkeypatch.setattr(db, "query", fail_postwrite_query)
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    caplog.set_level(logging.ERROR, logger="app.services.agent_executor")

    result = await executor._exec_record_doctor_feedback(
        {"assessment": "可见医生评估"}
    )

    _assert_uncertain_write(result)
    assert _write_receipt_from_tool_result(
        "record_doctor_feedback",
        {"assessment": "可见医生评估"},
        result,
    ) is None
    monkeypatch.setattr(db, "query", original_query)
    rows = original_query(ClinicalJournalEntry).filter_by(user_id=user.id).all()
    assert len(rows) == 1
    assert private_text not in caplog.text


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


@pytest.mark.asyncio
async def test_verified_doctor_feedback_invalidates_only_owner_context_cache(
    db,
    auth_user_and_headers,
):
    from app.services.agent_executor import AgentExecutor
    from app.services.health_context_lite_service import (
        INJECTION_FULL,
        INJECTION_MINIMAL,
        _context_cache,
    )

    user, _headers = auth_user_and_headers
    other_user_id = user.id + 1000
    _context_cache[(user.id, INJECTION_FULL)] = (1.0, "stale-owner-full")
    _context_cache[(user.id, INJECTION_MINIMAL)] = (1.0, "stale-owner-minimal")
    _context_cache[(other_user_id, INJECTION_FULL)] = (1.0, "other-full")
    _context_cache[(other_user_id, INJECTION_MINIMAL)] = (1.0, "other-minimal")
    executor = AgentExecutor(db)
    executor._current_user_id = user.id

    result = await executor._exec_record_doctor_feedback(
        {"assessment": "需要失效缓存的医生评估"}
    )

    payload = json.loads(result)
    assert payload["resource_type"] == "clinical_journal_entry"
    assert (user.id, INJECTION_FULL) not in _context_cache
    assert (user.id, INJECTION_MINIMAL) not in _context_cache
    assert _context_cache[(other_user_id, INJECTION_FULL)][1] == "other-full"
    assert _context_cache[(other_user_id, INJECTION_MINIMAL)][1] == "other-minimal"
    _context_cache.pop((other_user_id, INJECTION_FULL), None)
    _context_cache.pop((other_user_id, INJECTION_MINIMAL), None)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ("rejected", "uncertain"))
async def test_unverified_doctor_feedback_retains_context_cache(
    db,
    auth_user_and_headers,
    monkeypatch,
    outcome,
):
    from app.services import doctor_report_service
    from app.services.agent_executor import AgentExecutor
    from app.services.health_context_lite_service import (
        INJECTION_FULL,
        INJECTION_MINIMAL,
        _context_cache,
    )

    user, _headers = auth_user_and_headers
    _context_cache[(user.id, INJECTION_FULL)] = (1.0, "keep-full")
    _context_cache[(user.id, INJECTION_MINIMAL)] = (1.0, "keep-minimal")
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    args = {}
    if outcome == "uncertain":
        private_text = "私密写入异常"
        monkeypatch.setattr(
            doctor_report_service,
            "record_doctor_feedback",
            Mock(side_effect=RuntimeError(private_text)),
        )
        args = {"assessment": "写入后状态不确定"}

    result = await executor._exec_record_doctor_feedback(args)

    if outcome == "rejected":
        _assert_local_rejection(
            result,
            error_code="doctor_feedback_content_missing",
        )
    else:
        _assert_uncertain_write(result)
    assert _context_cache[(user.id, INJECTION_FULL)][1] == "keep-full"
    assert _context_cache[(user.id, INJECTION_MINIMAL)][1] == "keep-minimal"
    _context_cache.pop((user.id, INJECTION_FULL), None)
    _context_cache.pop((user.id, INJECTION_MINIMAL), None)


@pytest.mark.asyncio
async def test_cache_invalidation_failure_keeps_verified_receipt_and_log_safe(
    db,
    auth_user_and_headers,
    monkeypatch,
    caplog,
):
    from app.services import health_context_lite_service
    from app.services.agent_executor import (
        AgentExecutor,
        _write_receipt_from_tool_result,
    )

    user, _headers = auth_user_and_headers
    private_text = "私密医生意见不得进入缓存日志"

    def fail_invalidation(_user_id):
        raise RuntimeError(private_text)

    monkeypatch.setattr(
        health_context_lite_service,
        "invalidate_health_context",
        fail_invalidation,
        raising=False,
    )
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    caplog.set_level(logging.WARNING, logger="app.services.agent_executor")

    result = await executor._exec_record_doctor_feedback(
        {"assessment": "已确认持久化的医生意见"}
    )

    payload = json.loads(result)
    receipt = _write_receipt_from_tool_result(
        "record_doctor_feedback",
        {"assessment": "已确认持久化的医生意见"},
        result,
    )
    assert payload["resource_type"] == "clinical_journal_entry"
    assert isinstance(payload["id"], int) and payload["id"] > 0
    assert receipt is not None
    assert receipt["status"] == "verified"
    assert receipt["resource_id"] == str(payload["id"])
    assert "operation=invalidate_health_context" in caplog.text
    assert "RuntimeError" in caplog.text
    assert private_text not in caplog.text
