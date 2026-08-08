"""写入回执身份提取 — 2026-07-12 生产实锤回归。

实锤:founder 拍照记录 4 种补剂,vision 识别 ✓、四笔 /nfc/tap 全 200 ✓,
但其中 1 笔走「自动建档」分支,返回的手拼 JSON 无任何 id 字段 → 回执身份
提取不到 → 整轮被诚实门替换成「没有取得可验证的写入回执」,还诱导重试。
同类潜伏:化验写入只带 exam_id,而 id_keys 不认 exam_id。

不变量:凡写类工具的成功返回,必须携带可验证身份(id 族键 + resource_type);
诚实门 fail-closed 是对的,错的是回执生产端。
"""
import json

import pytest

from app.services.agent_executor import (
    _receipt_resource_identity,
    _write_receipt_from_tool_result,
    _write_tool_completed,
)


def test_old_supplement_autocreate_shape_was_unverifiable():
    """病灶复现:旧手拼 JSON(仅 message)提不出身份 → 回执 None(文档化根因)。"""
    old_shape = json.dumps(
        {"message": "已把「辅酶Q10」加入补剂库并完成今日打卡（补剂号 55，说「撤销」可移除）"},
        ensure_ascii=False,
    )
    assert _write_receipt_from_tool_result("health_record", "supplement", old_shape) is None
    assert _write_tool_completed("health_record", {"record_type": "supplement"}, old_shape) is False


def test_new_supplement_autocreate_shape_is_verifiable():
    """修复后:透传 tap record_id + resource_type → 回执 verified。"""
    new_shape = json.dumps(
        {
            "message": "已把「辅酶Q10」加入补剂库并完成今日打卡（补剂号 55，说「撤销」可移除）",
            "id": 9981,
            "record_id": 9981,
            "resource_type": "supplement_log",
            "supplement_definition_id": 55,
            "status": "recorded",
        },
        ensure_ascii=False,
    )
    receipt = _write_receipt_from_tool_result("health_record", "supplement", new_shape)
    assert receipt is not None and receipt["verified"] is True
    assert receipt["resource_type"] == "supplement_log"
    assert receipt["resource_id"] == "9981"
    assert _write_tool_completed("health_record", {"record_type": "supplement"}, new_shape) is True


def test_nfc_tap_direct_shape_is_verifiable():
    """命中已有补剂的直通路径(NfcTapResponse 原样透传)一直是可验证的——钉住不回退。"""
    tap_shape = json.dumps(
        {"status": "recorded", "message": "已打卡 甘氨酸镁（2粒）", "record_id": 7788},
        ensure_ascii=False,
    )
    receipt = _write_receipt_from_tool_result("health_record", "supplement", tap_shape)
    assert receipt is not None and receipt["resource_id"] == "7788"


def test_exam_id_now_recognized_as_identity():
    """潜伏同类:化验写入 exam_id 进 id_keys,不再假阴性。"""
    resource_type, resource_id = _receipt_resource_identity(
        {"message": "化验指标已写入系统", "exam_id": 321}
    )
    assert resource_id == "321"


def test_resource_id_now_recognized_as_identity():
    """Runtime replay/standard receipts use resource_type + resource_id."""
    resource_type, resource_id = _receipt_resource_identity(
        {"status": "verified", "resource_type": "diet_record", "resource_id": 829}
    )
    assert resource_type == "diet_record"
    assert resource_id == "829"


def test_explicit_unverified_result_never_builds_verified_receipt():
    shape = json.dumps(
        {
            "status": "verified",
            "verified": False,
            "resource_type": "diet_record",
            "resource_id": 829,
        }
    )

    assert _write_receipt_from_tool_result("health_record", "diet", shape) is None
    assert _write_tool_completed("health_record", {"record_type": "diet"}, shape) is False


def test_nested_explicit_unverified_result_never_builds_verified_receipt():
    shape = json.dumps(
        {
            "status": "recorded",
            "resource_type": "diet_record",
            "result": {
                "verified": False,
                "record_id": 830,
            },
        }
    )

    assert _write_receipt_from_tool_result("health_record", "diet", shape) is None
    assert _write_tool_completed("health_record", {"record_type": "diet"}, shape) is False


@pytest.mark.parametrize(
    "failure_payload",
    [
        {"status": "failed"},
        {"ok": False},
        {"error": "persist failed"},
    ],
)
def test_nested_failure_state_never_builds_verified_receipt(failure_payload):
    shape = json.dumps(
        {
            "status": "recorded",
            "resource_type": "diet_record",
            "result": {
                "record_id": 831,
                **failure_payload,
            },
        }
    )

    assert _write_receipt_from_tool_result("health_record", "diet", shape) is None
    assert _write_tool_completed("health_record", {"record_type": "diet"}, shape) is False


def test_conflicting_resource_id_aliases_never_build_receipt():
    shape = json.dumps(
        {
            "status": "recorded",
            "resource_type": "diet_record",
            "id": 101,
            "record_id": 202,
        }
    )

    assert _receipt_resource_identity(json.loads(shape)) == (None, None)
    assert _write_receipt_from_tool_result("health_record", "diet", shape) is None


def test_conflicting_record_type_aliases_never_build_receipt():
    shape = json.dumps(
        {
            "status": "recorded",
            "resource_type": "diet_record",
            "resource_id": 101,
        }
    )

    assert _write_receipt_from_tool_result(
        "health_record",
        {"record_type": "diet", "type": "water"},
        shape,
    ) is None


def test_autocreate_with_unparseable_tap_stays_fail_closed():
    """tap 响应解析不出 record_id → id=None → 回执仍 None(fail-closed:不可验证就不声称)。"""
    shape = json.dumps(
        {
            "message": "已把「X」加入补剂库并完成今日打卡",
            "id": None,
            "record_id": None,
            "resource_type": "supplement_log",
            "status": "recorded",
        },
        ensure_ascii=False,
    )
    assert _write_receipt_from_tool_result("health_record", "supplement", shape) is None


def test_pending_smart_reminder_is_a_verified_persisted_write():
    """Reminder pending means scheduled, not an unverified database write."""
    shape = json.dumps(
        {
            "id": 150,
            "resource_type": "smart_reminder",
            "status": "pending",
            "created_at": "2026-07-14T12:00:00+08:00",
        }
    )

    receipt = _write_receipt_from_tool_result("health_record", "reminder", shape)

    assert receipt is not None
    assert receipt["resource_type"] == "smart_reminder"
    assert receipt["resource_id"] == "150"
    assert receipt["verified"] is True


def test_pending_non_reminder_write_stays_fail_closed():
    """Do not weaken the write gate for ordinary records."""
    shape = json.dumps({"id": 151, "status": "pending"})

    assert _write_receipt_from_tool_result("health_record", "diet", shape) is None


@pytest.mark.parametrize(
    "status",
    ["uncertain", "in_flight", "processing", "queued", "reconciliation_required"],
)
def test_nonterminal_status_with_resource_identity_never_builds_receipt(status):
    """An ID does not prove completion while the producer declares a nonterminal state."""
    shape = json.dumps(
        {
            "status": status,
            "dispatch_started": True,
            "resource_type": "diet_record",
            "resource_id": 829,
            "message": "已记录晚餐",
        },
        ensure_ascii=False,
    )

    assert _write_receipt_from_tool_result("health_record", "diet", shape) is None
    assert _write_tool_completed("health_record", {"record_type": "diet"}, shape) is False


def test_unknown_explicit_status_with_resource_identity_stays_fail_closed():
    shape = json.dumps(
        {
            "status": "awaiting_replication",
            "resource_type": "diet_record",
            "resource_id": 830,
        }
    )

    assert _write_receipt_from_tool_result("health_record", "diet", shape) is None


def test_registered_terminal_status_with_resource_identity_remains_verifiable():
    shape = json.dumps(
        {
            "status": "recorded",
            "resource_type": "diet_record",
            "resource_id": 831,
        }
    )

    receipt = _write_receipt_from_tool_result("health_record", "diet", shape)

    assert receipt is not None
    assert receipt["resource_id"] == "831"


def test_dated_write_receipt_preserves_the_persisted_record_date():
    shape = json.dumps(
        {
            "status": "recorded",
            "resource_type": "water_record",
            "resource_id": 832,
            "record_date": "2026-07-17",
        }
    )

    receipt = _write_receipt_from_tool_result(
        "health_record",
        {"record_type": "water", "data": {"date": "2026-07-17"}},
        shape,
    )

    assert receipt is not None
    assert receipt["date"] == "2026-07-17"


def test_nested_persisted_date_conflict_never_builds_receipt():
    shape = json.dumps(
        {
            "status": "recorded",
            "resource_type": "water_record",
            "result": {
                "resource_id": 833,
                "record_date": "2099-01-01",
            },
        }
    )

    receipt = _write_receipt_from_tool_result(
        "health_record",
        {"record_type": "water", "data": {"date": "2026-07-17"}},
        shape,
    )

    assert receipt is None


def test_aigc_draft_pending_confirmation_is_a_verified_persisted_write():
    shape = json.dumps(
        {
            "id": "aigc_confirm_0123456789abcdef0123456789abcdef",
            "resource_type": "aigc_media_confirmation",
            "status": "pending_user_confirmation",
        }
    )

    receipt = _write_receipt_from_tool_result("draft_aigc_media", {}, shape)

    assert receipt is not None
    assert receipt["resource_type"] == "aigc_media_confirmation"


def test_pending_user_confirmation_is_not_generic_write_success():
    shape = json.dumps(
        {
            "id": 832,
            "resource_type": "diet_record",
            "status": "pending_user_confirmation",
        }
    )

    assert _write_receipt_from_tool_result("health_record", "diet", shape) is None


def test_non_health_record_writes_produce_typed_receipts():
    cases = [
        (
            "upload_genetic_txt",
            {"txt_content": "rsid\tchromosome\tposition\tgenotype"},
            {"id": 41, "message": "基因档案已导入"},
            "genetic_profile",
        ),
        (
            "upload_medical_exam_text",
            {"text": "LDL 3.8 mmol/L"},
            {"id": 42, "message": "化验指标已写入系统"},
            "medical_exam",
        ),
        (
            "manage_plan",
            {"action": "save_to_card", "data": {"title": "今日计划"}},
            {"id": 43, "message": "行动卡片已保存"},
            "action_card",
        ),
    ]

    for tool_name, args, payload, resource_type in cases:
        result = json.dumps(payload, ensure_ascii=False)
        receipt = _write_receipt_from_tool_result(tool_name, args, result)

        assert receipt is not None
        assert receipt["resource_type"] == resource_type
        assert receipt["resource_id"] == str(payload["id"])
        assert _write_tool_completed(tool_name, args, result) is True


def test_polymorphic_write_tools_derive_resource_type_from_arguments():
    cases = [
        (
            "health_manage",
            {
                "record_type": "supplement_definition",
                "operation": "update",
                "record_id": 55,
            },
            "supplement_definition",
        ),
        (
            "health_manage",
            {"record_type": "medication", "operation": "update", "record_id": 55},
            "medication",
        ),
        (
            "health_manage",
            {
                "record_type": "medication_log",
                "operation": "update",
                "record_id": 55,
            },
            "medication_log",
        ),
        ("manage_plan", {"action": "generate_weekly"}, "smart_plan"),
        ("manage_plan", {"action": "complete_item"}, "smart_plan_item"),
        ("manage_plan", {"action": "save_to_card"}, "action_card"),
    ]

    for tool_name, args, expected_resource_type in cases:
        receipt = _write_receipt_from_tool_result(
            tool_name,
            args,
            json.dumps({"id": 55, "message": "操作成功"}),
        )

        assert receipt is not None
        assert receipt["resource_type"] == expected_resource_type
        assert receipt["resource_id"] == "55"


def test_health_record_receipt_marks_verified_mapping_args_as_create():
    receipt = _write_receipt_from_tool_result(
        "health_record",
        {"record_type": "water"},
        json.dumps({"id": 718, "resource_type": "water_record"}),
    )

    assert receipt is not None
    assert receipt["action"] == "create"


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_health_manage_receipt_marks_verified_operation(operation):
    receipt = _write_receipt_from_tool_result(
        "health_manage",
        {"record_type": "water", "operation": operation, "record_id": 718},
        json.dumps({"id": 718, "resource_type": "water_record"}),
    )

    assert receipt is not None
    assert receipt["action"] == operation


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_health_manage_receipt_rejects_result_for_a_different_record(operation):
    args = {
        "record_type": "water",
        "operation": operation,
        "record_id": 718,
    }
    result = json.dumps(
        {
            "id": 719,
            "resource_type": "water_record",
            "operation_id": "health_manage:water_record:718",
        },
    )

    assert _write_receipt_from_tool_result("health_manage", args, result) is None
    assert _write_tool_completed("health_manage", args, result) is False


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_health_manage_receipt_accepts_canonically_equal_record_id(operation):
    receipt = _write_receipt_from_tool_result(
        "health_manage",
        {
            "record_type": "water",
            "operation": operation,
            "record_id": "0718",
        },
        json.dumps({"record_id": 718, "resource_type": "water_record"}),
    )

    assert receipt is not None
    assert receipt["resource_id"] == "718"
    assert receipt["action"] == operation


def test_health_manage_receipt_normalizes_operation_case_and_whitespace():
    receipt = _write_receipt_from_tool_result(
        "health_manage",
        {"record_type": "water", "operation": " UPDATE ", "record_id": 718},
        json.dumps({"id": 718, "resource_type": "water_record"}),
    )

    assert receipt is not None
    assert receipt["action"] == "update"


def test_health_manage_receipt_does_not_expose_unreachable_create_action():
    receipt = _write_receipt_from_tool_result(
        "health_manage",
        {"record_type": "water", "operation": "create"},
        json.dumps({"id": 718, "resource_type": "water_record"}),
    )

    assert receipt is not None
    assert "action" not in receipt


def test_health_manage_receipt_uses_args_action_over_result_payload_action():
    receipt = _write_receipt_from_tool_result(
        "health_manage",
        {"record_type": "water", "operation": "update", "record_id": 718},
        json.dumps(
            {
                "id": 718,
                "resource_type": "water_record",
                "action": "delete",
            }
        ),
    )

    assert receipt is not None
    assert receipt["action"] == "update"


def test_health_manage_receipt_ignores_invalid_operation_action():
    receipt = _write_receipt_from_tool_result(
        "health_manage",
        {"record_type": "water", "operation": "replace"},
        json.dumps(
            {
                "id": 718,
                "resource_type": "water_record",
                "action": "delete",
            }
        ),
    )

    assert receipt is not None
    assert "action" not in receipt


def test_legacy_health_record_context_does_not_invent_action():
    receipt = _write_receipt_from_tool_result(
        "health_record",
        "water",
        json.dumps({"id": 718, "resource_type": "water_record"}),
    )

    assert receipt is not None
    assert "action" not in receipt
