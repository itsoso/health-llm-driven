"""写入回执身份提取 — 2026-07-12 生产实锤回归。

实锤:founder 拍照记录 4 种补剂,vision 识别 ✓、四笔 /nfc/tap 全 200 ✓,
但其中 1 笔走「自动建档」分支,返回的手拼 JSON 无任何 id 字段 → 回执身份
提取不到 → 整轮被诚实门替换成「没有取得可验证的写入回执」,还诱导重试。
同类潜伏:化验写入只带 exam_id,而 id_keys 不认 exam_id。

不变量:凡写类工具的成功返回,必须携带可验证身份(id 族键 + resource_type);
诚实门 fail-closed 是对的,错的是回执生产端。
"""
import json

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
