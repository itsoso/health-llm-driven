"""补剂记录自动建档(镜像 medication 先例)。

用户在当前纯文本消息明确写出一个不在补剂库里的新补剂时,agent 应自动
POST /supplements/definitions 建档再打卡；图片或历史上下文推断的名称不得写入。
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent_executor import AgentExecutor, _write_receipt_from_tool_result


def _executor(db):
    ex = AgentExecutor(db)
    ex._current_user_id = 1
    return ex


@pytest.mark.asyncio
async def test_unregistered_supplement_autocreates_then_taps(db):
    ex = _executor(db)
    ex._current_turn_user_message = "帮我记录：「正官庄红参液」 10mL，确认打卡"
    create_payload: dict = {}
    tap_payload: dict = {}

    async def fake_get_json(url, headers):
        assert "/supplements/me/definitions" in url
        return [], None  # 补剂库为空

    async def fake_post_json(url, headers, payload):
        assert "/supplements/definitions" in url
        create_payload.update(payload)
        return {
            "id": 88,
            "name": payload["name"],
            "user_id": 1,
            "is_active": True,
        }, None

    async def fake_post(url, headers, payload):
        assert "/nfc/tap" in url
        tap_payload.update(payload)
        return '{"status": "ok"}'

    with patch.object(ex, "_api_get_json", new=AsyncMock(side_effect=fake_get_json)), \
         patch.object(ex, "_api_post_json", new=AsyncMock(side_effect=fake_post_json)), \
         patch.object(ex, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await ex._exec_health_record("http://x", {}, {
            "record_type": "supplement",
            "data": {
                "supplement_name": "正官庄红参液",
                "dosage": "10mL",
                "timing": "evening",
                "category": "herbal",
            },
        })

    assert create_payload.get("name") == "正官庄红参液"
    assert create_payload.get("dosage") == "10mL"
    assert create_payload.get("timing") == "evening"
    assert tap_payload.get("supplement_id") == 88
    parsed = json.loads(result)
    assert "加入补剂库" in parsed["message"]
    assert "88" in parsed["message"]  # 补剂号入回显,撤销回合有 id 可用
    assert "撤销" in parsed["message"]
    assert parsed["status"] == "unverified"
    assert parsed["verified"] is False
    assert _write_receipt_from_tool_result(
        "health_record",
        {"record_type": "supplement"},
        result,
    ) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lookup_payload",
    (
        {"unexpected": True},
        {"status": "failed", "data": []},
        {"error": "合成错误详情", "data": []},
        {"data": "not-a-list"},
        {"data": ["not-an-object"]},
        {"data": [{"name": "营养素甲", "is_active": True}]},
        {"data": [{"id": 7, "name": "营养素甲", "is_active": "false"}]},
        {
            "user_id": 2,
            "data": [{"id": 7, "name": "营养素甲", "is_active": True}],
        },
        {
            "name": "营养素甲",
            "data": [{"id": 7, "name": "营养素甲", "is_active": True}],
        },
        {
            "is_active": True,
            "data": [{"id": 7, "name": "营养素甲", "is_active": True}],
        },
        {
            "resource_type": "diet_record",
            "data": [{"id": 7, "name": "营养素甲", "is_active": True}],
        },
        {
            "data": [{"id": 7, "name": "营养素甲", "is_active": True}],
            "result": {"user_id": 2},
        },
        {
            "data": [{"id": 7, "name": "营养素甲", "is_active": True}],
            "result": {"name": "营养素乙"},
        },
        {
            "data": [{"id": 7, "name": "营养素甲", "is_active": True}],
            "result": {"resource_type": "diet_record"},
        },
        {
            "data": [
                {
                    "id": 7,
                    "name": "营养素甲",
                    "is_active": True,
                    "user_id": 2,
                }
            ]
        },
        {
            "data": [
                {"id": 7, "name": "营养素甲", "is_active": True},
                {"id": 7, "name": "营养素乙", "is_active": True},
            ]
        },
        {
            "data": [
                {
                    "id": 7,
                    "name": "营养素甲",
                    "is_active": True,
                    "error": "synthetic",
                }
            ]
        },
        {
            "data": [
                {
                    "id": 7,
                    "name": "营养素甲",
                    "is_active": True,
                    "resource_type": "medication_definition",
                }
            ]
        },
        {
            "data": [
                {
                    "id": 7,
                    "name": "营养素甲",
                    "is_active": True,
                    "success": False,
                }
            ]
        },
        {
            "data": [
                {
                    "id": 7,
                    "name": "营养素甲",
                    "is_active": True,
                    "result": [{"status": "failed"}],
                }
            ]
        },
        {
            "data": [
                {
                    "id": 7,
                    "name": "营养素甲",
                    "is_active": True,
                    "result": {"is_active": False},
                }
            ]
        },
    ),
)
async def test_autocreate_rejects_malformed_definition_lookup_response(
    db,
    lookup_payload,
):
    ex = _executor(db)
    ex._current_turn_user_message = "记录「营养素甲」"
    create = AsyncMock()
    tap = AsyncMock()

    with patch.object(
        ex,
        "_api_get_json",
        new=AsyncMock(return_value=(lookup_payload, None)),
    ), patch.object(ex, "_api_post_json", new=create), patch.object(
        ex,
        "_api_post",
        new=tap,
    ):
        result = await ex._exec_health_record(
            "http://x",
            {},
            {
                "record_type": "supplement",
                "data": {"supplement_name": "营养素甲"},
            },
        )

    parsed = json.loads(result)
    assert parsed["status"] == "rejected"
    assert parsed["error_code"] == "supplement_definition_lookup_invalid"
    assert parsed["dispatch_started"] is False
    create.assert_not_awaited()
    tap.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "create_payload",
    (
        {"status": "failed", "id": 88},
        {"errors": ["failed"], "id": 88},
        {"error_code": "FAILED", "id": 88},
        {"id": 0},
        {"id": []},
        {"id": 88, "name": "营养素乙", "user_id": 1},
        {"id": 88, "name": "营养素甲", "user_id": 2},
        {"id": 88, "name": "营养素甲", "user_id": 1, "is_active": False},
        {"id": 88, "name": "营养素甲", "user_id": 1, "is_active": "true"},
        {
            "id": 88,
            "name": "营养素甲",
            "user_id": 1,
            "resource_id": 89,
        },
        {
            "id": 88,
            "name": "营养素甲",
            "user_id": 1,
            "data": {"id": 89},
        },
        {
            "id": 88,
            "name": "营养素甲",
            "user_id": 1,
            "resource_type": "medication_definition",
        },
        {
            "id": 88,
            "name": "营养素甲",
            "user_id": 1,
            "data": {"result": {"status": "failed"}},
        },
        {
            "id": 88,
            "name": "营养素甲",
            "user_id": 1,
            "result": [{"status": "failed"}],
        },
    ),
)
async def test_invalid_autocreate_response_never_reaches_tap(db, create_payload):
    ex = _executor(db)
    ex._current_turn_user_message = "记录「营养素甲」"
    tap = AsyncMock()

    with patch.object(
        ex,
        "_api_get_json",
        new=AsyncMock(return_value=([], None)),
    ), patch.object(
        ex,
        "_api_post_json",
        new=AsyncMock(return_value=(create_payload, None)),
    ), patch.object(ex, "_api_post", new=tap):
        result = await ex._exec_health_record(
            "http://x",
            {},
            {
                "record_type": "supplement",
                "data": {"supplement_name": "营养素甲"},
            },
        )

    assert "完成今日打卡" not in result
    assert _write_receipt_from_tool_result(
        "health_record",
        {"record_type": "supplement"},
        result,
    ) is None
    tap.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tap_payload", "expected_status"),
    (
        ({"status": "failed", "record_id": 901}, "failed"),
        ({"id": 88, "resource_type": "supplement_definition"}, "unverified"),
        ({"record_id": 901, "resource_type": "diet_record"}, "unverified"),
        ({"record_id": []}, "unverified"),
        ({"record_id": 0}, "unverified"),
        ({"record_id": -1}, "unverified"),
        ({"record_id": "0.0"}, "unverified"),
        ({"id": 88}, "unverified"),
        ({"record_id": 901, "id": 902}, "unverified"),
        ({"record_id": 901, "errors": ["failed"]}, "failed"),
        ({"record_id": 901, "error_code": "FAILED"}, "failed"),
        (
            {"record_id": 901, "data": {"result": {"status": "failed"}}},
            "failed",
        ),
        ({"record_id": 901, "result": [{"status": "failed"}]}, "failed"),
        ({"record_id": 901, "status": False}, "unverified"),
        ({"record_id": 901, "status": 0}, "unverified"),
        ({"record_id": 901, "status": []}, "unverified"),
        ({"record_id": 901, "status": {}}, "unverified"),
        ({"record_id": 901, "resource_type": []}, "unverified"),
        ({"record_id": 901, "resource_type": 0}, "unverified"),
        ({"record_id": 901, "data": {"type": "medication_log"}}, "unverified"),
        (
            {
                "status": "ok",
                "record_id": 901,
                "data": {"result": {"record_id": 77}},
            },
            "unverified",
        ),
        (
            {"status": "ok", "record_id": 901, "data": [{"record_id": 77}]},
            "unverified",
        ),
        (
            {
                "record_id": 901,
                "data": [
                    {"success": False, "error": "synthetic", "record_id": 77}
                ],
            },
            "failed",
        ),
    ),
)
async def test_autocreate_invalid_tap_never_builds_verified_receipt(
    db,
    tap_payload,
    expected_status,
):
    ex = _executor(db)
    ex._current_turn_user_message = "记录「营养素甲」"

    with patch.object(
        ex,
        "_api_get_json",
        new=AsyncMock(return_value=([], None)),
    ), patch.object(
        ex,
        "_api_post_json",
        new=AsyncMock(
            return_value=(
                {
                    "id": 88,
                    "name": "营养素甲",
                    "user_id": 1,
                    "is_active": True,
                },
                None,
            )
        ),
    ), patch.object(
        ex,
        "_api_post",
        new=AsyncMock(return_value=json.dumps(tap_payload)),
    ):
        result = await ex._exec_health_record(
            "http://x",
            {},
            {
                "record_type": "supplement",
                "data": {"supplement_name": "营养素甲"},
            },
        )

    parsed = json.loads(result)
    assert parsed["verified"] is False
    assert parsed["status"] == expected_status
    assert "完成今日打卡" not in parsed["message"]
    assert _write_receipt_from_tool_result(
        "health_record",
        {"record_type": "supplement"},
        result,
    ) is None


@pytest.mark.asyncio
async def test_supplement_lookup_error_detail_is_not_logged_or_returned(db, caplog):
    ex = _executor(db)
    ex._current_turn_user_message = "记录「营养素甲」"
    private_detail = "营养素甲 合成错误"

    with patch.object(
        ex,
        "_api_get_json",
        new=AsyncMock(return_value=(None, f"网络错误: {private_detail}")),
    ), patch.object(ex, "_api_post_json", new=AsyncMock()), patch.object(
        ex,
        "_api_post",
        new=AsyncMock(),
    ):
        result = await ex._exec_health_record(
            "http://x",
            {},
            {
                "record_type": "supplement",
                "data": {"supplement_name": "营养素甲"},
            },
        )

    assert private_detail not in caplog.text
    assert private_detail not in result


@pytest.mark.asyncio
async def test_unquoted_unknown_supplement_requires_an_explicit_name_boundary(db):
    ex = _executor(db)
    ex._current_turn_user_message = "记录正官庄红参液 10mL"
    lookup = AsyncMock(return_value=([], None))
    create = AsyncMock(return_value=({"id": 88, "name": "正官庄红参液"}, None))
    tap = AsyncMock(return_value='{"record_id": 1073}')

    with patch.object(ex, "_api_get_json", new=lookup), \
         patch.object(ex, "_api_post_json", new=create), \
         patch.object(ex, "_api_post", new=tap):
        result = await ex._exec_health_record("http://x", {}, {
            "record_type": "supplement",
            "data": {"supplement_name": "正官庄红参液", "dosage": "10mL"},
        })

    parsed = json.loads(result)
    assert parsed["error_code"] == "supplement_name_not_user_grounded"
    assert parsed["dispatch_started"] is False
    assert "「正官庄红参液」" in parsed["recovery_guidance"]
    lookup.assert_not_awaited()
    create.assert_not_awaited()
    tap.assert_not_awaited()


@pytest.mark.asyncio
async def test_registered_supplement_taps_without_creating(db):
    ex = _executor(db)
    ex._current_turn_user_message = "记录「正官庄红参液」"
    created = {"called": False}

    async def fake_get_json(url, headers):
        return [{"id": 7, "name": "正官庄红参液", "is_active": True}], None

    async def fake_post_json(url, headers, payload):
        created["called"] = True
        return {}, None

    async def fake_post(url, headers, payload):
        assert payload.get("supplement_id") == 7
        return '{"status": "ok", "record_id": 1073}'

    with patch.object(ex, "_api_get_json", new=AsyncMock(side_effect=fake_get_json)), \
         patch.object(ex, "_api_post_json", new=AsyncMock(side_effect=fake_post_json)), \
         patch.object(ex, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await ex._exec_health_record("http://x", {}, {
            "record_type": "supplement",
            "data": {"supplement_name": "正官庄红参液"},
        })

    assert created["called"] is False  # 已注册 → 不重复建档
    assert "ok" in result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "configured_dosage,requested_dosage",
    ((None, "2粒"), ("1粒", "2粒"), ("1.5滴", "15滴"),
     ("1.5颗", "15颗")),
)
async def test_registered_supplement_rejects_unpersistable_dosage(
    db,
    configured_dosage,
    requested_dosage,
):
    ex = _executor(db)
    ex._current_turn_user_message = f"吃了{requested_dosage}红景天"
    tap = AsyncMock()

    with patch.object(
        ex,
        "_api_get_json",
        new=AsyncMock(
            return_value=(
                [
                    {
                        "id": 7,
                        "name": "红景天",
                        "dosage": configured_dosage,
                        "is_active": True,
                    }
                ],
                None,
            )
        ),
    ), patch.object(ex, "_api_post", new=tap):
        result = await ex._exec_health_record(
            "http://x",
            {},
            {
                "record_type": "supplement",
                "data": {"supplement_name": "红景天", "dosage": requested_dosage},
            },
        )

    parsed = json.loads(result)
    assert parsed["error_code"] == "supplement_dosage_not_persistable"
    assert "剂量" in parsed["message"]
    tap.assert_not_awaited()


@pytest.mark.asyncio
async def test_registered_supplement_accepts_matching_dosage(db):
    ex = _executor(db)
    ex._current_turn_user_message = "吃了两粒红景天"
    tap = AsyncMock(return_value='{"status":"ok","record_id":1073}')

    with patch.object(
        ex,
        "_api_get_json",
        new=AsyncMock(
            return_value=(
                [
                    {
                        "id": 7,
                        "name": "红景天",
                        "dosage": "2粒",
                        "is_active": True,
                    }
                ],
                None,
            )
        ),
    ), patch.object(ex, "_api_post", new=tap):
        result = await ex._exec_health_record(
            "http://x",
            {},
            {
                "record_type": "supplement",
                "data": {"supplement_name": "红景天", "dosage": "2粒"},
            },
        )

    assert json.loads(result)["record_id"] == 1073
    tap.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_exact_supplement_definitions_require_clarification(db):
    ex = _executor(db)
    ex._current_turn_user_message = "记录「营养素甲」"
    create = AsyncMock()
    tap = AsyncMock()

    with patch.object(
        ex,
        "_api_get_json",
        new=AsyncMock(
            return_value=(
                [
                    {"id": 7, "name": "营养素甲", "is_active": True},
                    {"id": 8, "name": " 营养素甲 ", "is_active": True},
                ],
                None,
            )
        ),
    ), patch.object(ex, "_api_post_json", new=create), patch.object(
        ex,
        "_api_post",
        new=tap,
    ):
        result = await ex._exec_health_record(
            "http://x",
            {},
            {
                "record_type": "supplement",
                "data": {"supplement_name": "营养素甲"},
            },
        )

    parsed = json.loads(result)
    assert parsed["status"] == "rejected"
    assert parsed["error_code"] == "supplement_definition_ambiguous"
    create.assert_not_awaited()
    tap.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tap_payload",
    (
        {"status": "ok", "id": 9},
        {"status": "ok", "record_id": False, "id": 9},
        {"status": "ok", "data": {"record_id": 9}},
        {"record_id": 1073, "success": 0},
        {"record_id": 1073, "ok": "false"},
        {"status": "ok", "record_id": 1073, "id": [55]},
        {"record_id": 1073, "data": {"result": {"status": "failed"}}},
        {"record_id": 1073, "result": [{"status": "failed"}]},
        {"record_id": 1073, "status": False},
        {"record_id": 1073, "status": 0},
        {"record_id": 1073, "status": []},
        {"record_id": 1073, "status": {}},
        {"record_id": 1073, "resource_type": []},
        {"record_id": 1073, "resource_type": 0},
        {"record_id": 1073, "data": {"type": "medication_log"}},
        {
            "status": "ok",
            "record_id": 1073,
            "data": {"result": {"record_id": 77}},
        },
        {"status": "ok", "record_id": 1073, "data": [{"record_id": 77}]},
        {
            "record_id": 1073,
            "data": [
                {"success": False, "error": "synthetic", "record_id": 77}
            ],
        },
    ),
)
async def test_registered_supplement_requires_strict_tap_receipt(db, tap_payload):
    ex = _executor(db)
    ex._current_turn_user_message = "记录「营养素甲」"

    with patch.object(
        ex,
        "_api_get_json",
        new=AsyncMock(
            return_value=([{"id": 7, "name": "营养素甲", "is_active": True}], None)
        ),
    ), patch.object(ex, "_api_post_json", new=AsyncMock()), patch.object(
        ex,
        "_api_post",
        new=AsyncMock(return_value=json.dumps(tap_payload)),
    ):
        result = await ex._exec_health_record(
            "http://x",
            {},
            {
                "record_type": "supplement",
                "data": {"supplement_name": "营养素甲"},
            },
        )

    parsed = json.loads(result)
    assert parsed["verified"] is False
    assert "已完成" not in parsed["message"]
    assert "完成今日打卡" not in parsed["message"]
    assert _write_receipt_from_tool_result(
        "health_record",
        {"record_type": "supplement"},
        result,
    ) is None


@pytest.mark.asyncio
async def test_colon_delimited_supplement_list_grounds_each_exact_name(db):
    ex = _executor(db)
    ex._current_turn_user_message = (
        "记录补剂：一粒营养素甲、一粒营养素乙和一粒两粒营养素丙。"
    )
    definitions = [
        {"id": 41, "name": "营养素甲", "is_active": True},
        {"id": 42, "name": "营养素乙", "is_active": True},
        {"id": 43, "name": "营养素丙", "is_active": True},
    ]
    create = AsyncMock()
    tapped_ids = []

    async def fake_post(url, headers, payload):  # noqa: ARG001
        tapped_ids.append(payload["supplement_id"])
        return json.dumps(
            {"status": "recorded", "record_id": 1000 + payload["supplement_id"]}
        )

    with patch.object(
        ex,
        "_api_get_json",
        new=AsyncMock(return_value=(definitions, None)),
    ), patch.object(ex, "_api_post_json", new=create), patch.object(
        ex,
        "_api_post",
        new=AsyncMock(side_effect=fake_post),
    ):
        for name in ("营养素甲", "营养素乙", "营养素丙"):
            result = await ex._exec_health_record(
                "http://x",
                {},
                {
                    "record_type": "supplement",
                    "data": {"supplement_name": name},
                },
            )
            assert json.loads(result)["record_id"] == 1000 + tapped_ids[-1]

    assert tapped_ids == [41, 42, 43]
    create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_message",
    (
        "护士提及：记录补剂：营养素甲",
        "记录朋友的补剂：营养素甲",
    ),
)
async def test_colon_delimited_supplement_list_rejects_unowned_provenance(
    db,
    user_message,
):
    ex = _executor(db)
    ex._current_turn_user_message = user_message
    lookup = AsyncMock(return_value=([], None))
    create = AsyncMock()
    tap = AsyncMock()

    with patch.object(ex, "_api_get_json", new=lookup), patch.object(
        ex,
        "_api_post_json",
        new=create,
    ), patch.object(ex, "_api_post", new=tap):
        result = await ex._exec_health_record(
            "http://x",
            {},
            {
                "record_type": "supplement",
                "data": {"supplement_name": "营养素甲"},
            },
        )

    parsed = json.loads(result)
    assert parsed["error_code"] == "supplement_name_not_user_grounded"
    assert parsed["dispatch_started"] is False
    lookup.assert_not_awaited()
    create.assert_not_awaited()
    tap.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_message", "supplement_name"),
    (
        ("记录补剂：营养素甲、不要营养素乙", "不要营养素乙"),
        ("记录补剂：营养素甲、如果吃营养素乙", "如果吃营养素乙"),
        ("记录补剂：营养素甲、没吃营养素乙", "没吃营养素乙"),
        ("记录补剂：营养素甲、可能吃营养素乙", "可能吃营养素乙"),
        ("记录补剂：营养素甲（仅作假设）", "营养素甲（仅作假设）"),
        ("记录补剂：鱼油、营养素甲（没吃）", "营养素甲（没吃）"),
        ("记录补剂：营养素甲（可能吃）", "营养素甲（可能吃）"),
        ("记录补剂：营养素甲（如果吃）", "营养素甲（如果吃）"),
        ("记录补剂：营养素甲、营养素乙没吃", "营养素乙没吃"),
        ("记录补剂：营养素甲、营养素乙只是假设", "营养素乙"),
        ("记录补剂：营养素甲不吃", "营养素甲不吃"),
        ("记录补剂：营养素甲不曾吃", "营养素甲不曾吃"),
        ("记录补剂：营养素乙、不记录营养素甲", "营养素甲"),
        ("记录补剂：营养素甲不想再吃", "营养素甲不想再吃"),
        ("记录补剂：营养素甲以后吃", "营养素甲以后吃"),
        ("记录补剂：营养素甲能吃吗", "营养素甲能吃吗"),
        ("记录补剂：营养素甲、下周吃营养素乙", "下周吃营养素乙"),
        ("记录补剂：营养素甲、营养素乙不需要记", "营养素乙不需要记"),
        ("记录补剂：营养素甲、营养素乙已停", "营养素乙已停"),
        ("记录补剂：营养素甲、过两小时吃营养素乙", "过两小时吃营养素乙"),
        ("记录补剂：营养素甲、预备吃营养素乙", "预备吃营养素乙"),
        ("记录补剂：营养素甲、将会吃营养素乙", "将会吃营养素乙"),
        ("记录补剂：营养素甲、服营养素乙", "服营养素乙"),
        ("记录补剂：营养素甲、补营养素乙", "补营养素乙"),
        ("记录补剂：营养素甲、吞营养素乙", "吞营养素乙"),
        ("记录补剂：营养素甲、下周再服一片", "营养素甲"),
        ("记录补剂：营养素甲、计划每天两粒", "营养素甲"),
        ("记录补剂：营养素甲、以后再吃一点", "营养素甲"),
        ("记录补剂：营养素甲、no intake", "营养素甲"),
        ("记录补剂：营养素甲、will take later", "营养素甲"),
        ("记录补剂：营养素甲、仅供参考", "营养素甲"),
        ("记录补剂：营养素甲、暂停这次", "营养素甲"),
        ("记录补剂：明早营养素甲", "明早营养素甲"),
        ("记录补剂：昨晚已服营养素甲", "昨晚已服营养素甲"),
        ("记录补剂：鱼油；记录补剂营养素甲", "营养素甲"),
        ("记录补剂：鱼油，记录补剂营养素甲", "营养素甲"),
        ("记录补剂：鱼油\n记录补剂营养素甲", "营养素甲"),
    ),
)
async def test_colon_delimited_supplement_list_rejects_unscoped_names(
    db,
    user_message,
    supplement_name,
):
    ex = _executor(db)
    ex._current_turn_user_message = user_message
    lookup = AsyncMock(return_value=([], None))
    create = AsyncMock()
    tap = AsyncMock()

    with patch.object(ex, "_api_get_json", new=lookup), patch.object(
        ex,
        "_api_post_json",
        new=create,
    ), patch.object(ex, "_api_post", new=tap):
        result = await ex._exec_health_record(
            "http://x",
            {},
            {
                "record_type": "supplement",
                "data": {"supplement_name": supplement_name},
            },
        )

    parsed = json.loads(result)
    assert parsed["error_code"] == "supplement_name_not_user_grounded"
    assert parsed["dispatch_started"] is False
    lookup.assert_not_awaited()
    create.assert_not_awaited()
    tap.assert_not_awaited()


@pytest.mark.asyncio
async def test_short_name_matching_registered_supplement_requires_clarification(db):
    ex = _executor(db)
    ex._current_turn_user_message = "记录「红参液」"
    create = AsyncMock(return_value=({"id": 88}, None))
    tap = AsyncMock(return_value='{"record_id": 1073}')

    with patch.object(
        ex,
        "_api_get_json",
        new=AsyncMock(
            return_value=([
                {"id": 7, "name": "正官庄红参液", "is_active": True},
            ], None)
        ),
    ), patch.object(ex, "_api_post_json", new=create), patch.object(
        ex,
        "_api_post",
        new=tap,
    ):
        result = await ex._exec_health_record("http://x", {}, {
            "record_type": "supplement",
            "data": {"supplement_name": "红参液"},
        })

    parsed = json.loads(result)
    assert parsed["status"] == "rejected"
    assert parsed["error_code"] == "supplement_name_ambiguous"
    assert parsed["dispatch_started"] is False
    assert "正官庄红参液" in parsed["recovery_guidance"]
    create.assert_not_awaited()
    tap.assert_not_awaited()


@pytest.mark.asyncio
async def test_overlapping_supplement_names_match_distinct_exact_definitions(db):
    ex = _executor(db)
    ex._current_turn_user_message = "记录维生素D3和维生素D"
    ex._turn_contextual_supplement_names = ("维生素D3", "维生素D")
    dispatched_ids: list[int] = []

    async def fake_get_json(url, headers):  # noqa: ARG001
        return [
            {"id": 31, "name": "维生素D3", "is_active": True},
            {"id": 32, "name": "维生素D", "is_active": True},
        ], None

    async def fake_post(url, headers, payload):  # noqa: ARG001
        dispatched_ids.append(payload["supplement_id"])
        return json.dumps(
            {"status": "recorded", "record_id": 1000 + payload["supplement_id"]}
        )

    with patch.object(ex, "_api_get_json", new=AsyncMock(side_effect=fake_get_json)), \
         patch.object(ex, "_api_post_json", new=AsyncMock()), \
         patch.object(ex, "_api_post", new=AsyncMock(side_effect=fake_post)):
        for name in ("维生素D3", "维生素D"):
            result = await ex._exec_health_record("http://x", {}, {
                "record_type": "supplement",
                "data": {"supplement_name": name},
            })
            assert json.loads(result)["record_id"] == 1000 + dispatched_ids[-1]

    assert dispatched_ids == [31, 32]


@pytest.mark.asyncio
async def test_contextual_all_taken_name_passes_gateway_and_taps_existing_definition(
    db,
):
    ex = _executor(db)
    ex._current_turn_user_message = "全部已服用"
    ex._current_turn_recent_messages = [
        {"role": "assistant", "content": "要把全部补剂都记为已服用吗？"}
    ]
    ex._turn_contextual_supplement_names = ("甘氨酸镁",)
    lookup = AsyncMock(
        return_value=([{"id": 7, "name": "甘氨酸镁", "is_active": True}], None)
    )
    tap = AsyncMock(return_value='{"status": "recorded", "record_id": 1073}')

    with patch.object(ex, "_api_get_json", new=lookup), \
         patch.object(ex, "_api_post_json", new=AsyncMock()), \
         patch.object(ex, "_api_post", new=tap):
        result = await ex._execute_tool(
            "health_record",
            {
                "record_type": "supplement",
                "data": {"supplement_name": "甘氨酸镁"},
            },
            "test-token",
        )

    assert json.loads(result)["record_id"] == 1073
    lookup.assert_awaited_once()
    tap.assert_awaited_once()


@pytest.mark.asyncio
async def test_contextual_all_taken_rejects_name_outside_server_owned_set(db):
    ex = _executor(db)
    ex._current_turn_user_message = "全部已服用"
    ex._current_turn_recent_messages = [
        {"role": "assistant", "content": "要把全部补剂都记为已服用吗？"}
    ]
    ex._turn_contextual_supplement_names = ("甘氨酸镁",)
    lookup = AsyncMock()
    tap = AsyncMock()

    with patch.object(ex, "_api_get_json", new=lookup), \
         patch.object(ex, "_api_post_json", new=AsyncMock()), \
         patch.object(ex, "_api_post", new=tap):
        result = await ex._execute_tool(
            "health_record",
            {
                "record_type": "supplement",
                "data": {"supplement_name": "褪黑素"},
            },
            "test-token",
        )

    parsed = json.loads(result)
    assert parsed["error_code"] in {
        "health_record_target_mismatch",
        "write_tool_without_write_intent",
    }
    assert parsed["dispatch_started"] is False
    lookup.assert_not_awaited()
    tap.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(("user_message", "model_name"), [
    ("记录 vitamin D 1 capsule 500 IU", "vitamin D"),
    ("记录维生素D1粒500IU", "维生素D"),
])
async def test_multiple_trailing_amounts_are_removed_without_rejecting_the_name(
    db,
    user_message,
    model_name,
):
    ex = _executor(db)
    ex._current_turn_user_message = user_message
    lookup = AsyncMock(return_value=([{"id": 7, "name": model_name, "is_active": True}], None))
    create = AsyncMock()
    tap = AsyncMock(return_value='{"status": "ok", "record_id": 1073}')

    with patch.object(ex, "_api_get_json", new=lookup), \
         patch.object(ex, "_api_post_json", new=create), \
         patch.object(ex, "_api_post", new=tap):
        result = await ex._exec_health_record("http://x", {}, {
            "record_type": "supplement",
            "data": {"supplement_name": model_name},
        })

    assert "ok" in result
    lookup.assert_awaited_once()
    create.assert_not_awaited()
    tap.assert_awaited_once()


@pytest.mark.asyncio
async def test_autocreate_failure_gives_friendly_fallback_no_raw_error(db):
    ex = _executor(db)
    ex._current_turn_user_message = "记录「红参液」"

    async def fake_get_json(url, headers):
        return [], None

    async def fake_post_json(url, headers, payload):
        return None, "HTTP 500"

    with patch.object(ex, "_api_get_json", new=AsyncMock(side_effect=fake_get_json)), \
         patch.object(ex, "_api_post_json", new=AsyncMock(side_effect=fake_post_json)), \
         patch.object(ex, "_api_post", new=AsyncMock()):
        result = await ex._exec_health_record("http://x", {}, {
            "record_type": "supplement",
            "data": {"supplement_name": "红参液"},
        })

    assert "没成功" in result  # 友好兜底
    assert "Traceback" not in result


@pytest.mark.asyncio
async def test_model_inferred_supplement_name_is_rejected_before_dispatch(db):
    ex = _executor(db)
    ex._current_turn_user_message = "识别图中的补剂并且帮我打卡"
    ex._current_turn_has_attachment = False
    lookup = AsyncMock(return_value=([], None))
    create = AsyncMock(return_value=({"id": 73, "name": "维生素D"}, None))
    tap = AsyncMock(return_value='{"record_id": 1073}')

    with patch.object(ex, "_api_get_json", new=lookup), \
         patch.object(ex, "_api_post_json", new=create), \
         patch.object(ex, "_api_post", new=tap):
        result = await ex._exec_health_record("http://x", {}, {
            "record_type": "supplement",
            "data": {"supplement_name": "维生素D"},
        })

    parsed = json.loads(result)
    assert parsed["error_code"] == "supplement_name_not_user_grounded"
    assert parsed["dispatch_started"] is False
    lookup.assert_not_awaited()
    create.assert_not_awaited()
    tap.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(("user_message", "model_name"), [
    ("识别图中的补剂并且帮我打卡", "补剂"),
    ("识别图中的补剂并且帮我打卡", "图"),
    ("识别图中的补剂并且帮我打卡", "打卡"),
    ("记录这个补剂", "记录"),
    ("记录这个补剂", "这个"),
    ("记录这个补剂", "这个补剂"),
    ("记录维生素", "维生素"),
])
async def test_generic_current_turn_words_cannot_become_supplement_names(
    db,
    user_message,
    model_name,
):
    ex = _executor(db)
    ex._current_turn_user_message = user_message
    ex._current_turn_has_attachment = False
    lookup = AsyncMock(return_value=([], None))
    create = AsyncMock(return_value=({"id": 73, "name": model_name}, None))
    tap = AsyncMock(return_value='{"record_id": 1073}')

    with patch.object(ex, "_api_get_json", new=lookup), \
         patch.object(ex, "_api_post_json", new=create), \
         patch.object(ex, "_api_post", new=tap):
        result = await ex._exec_health_record("http://x", {}, {
            "record_type": "supplement",
            "data": {"supplement_name": model_name},
        })

    parsed = json.loads(result)
    assert parsed["error_code"] == "supplement_name_not_user_grounded"
    assert parsed["dispatch_started"] is False
    lookup.assert_not_awaited()
    create.assert_not_awaited()
    tap.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(("user_message", "model_name"), [
    ("记录维生素D并且帮我打卡", "维生素D并且帮我打卡"),
    ("记录这个补剂维生素D", "这个补剂维生素D"),
    ("记录维生素D和鱼油", "维生素D和鱼油"),
    ("记录维生素D每天1片", "维生素D每天1片"),
    ("记录 vitamin D and fish oil", "vitamin D and fish oil"),
    ("记录 this supplement vitamin D", "this supplement vitamin D"),
    ("记录 vitamin D and log it", "vitamin D and log it"),
    ("记录 supplement", "supplement"),
    ("记录 today", "today"),
    ("记录维生素D+鱼油", "维生素D+鱼油"),
    ("记录 vitamin D plus fish oil", "vitamin D plus fish oil"),
    ("记录维生素D确认", "维生素D确认"),
    ("记录维生素D一日一次", "维生素D一日一次"),
    ("记录 vitamin D 1 capsule 500 IU", "vitamin D 1 capsule"),
    ("记录维生素D&鱼油", "维生素D&鱼油"),
    ("记录维生素D／鱼油", "维生素D／鱼油"),
    ("记录维生素D加鱼油", "维生素D加鱼油"),
    ("记录维生素D还有鱼油", "维生素D还有鱼油"),
    ("记录 vitamin D with fish oil", "vitamin D with fish oil"),
    ("记录维生素D饭后", "维生素D饭后"),
    ("记录 vitamin D after meals", "vitamin D after meals"),
    ("记录维生素D鱼油", "维生素D鱼油"),
    ("记录维生素D别忘了", "维生素D别忘了"),
    ("记录帮忙维生素D", "帮忙维生素D"),
    ("记录需要维生素D", "需要维生素D"),
    ("记录vitaminDfishoil", "vitaminDfishoil"),
    ("记录d3fishoil", "d3fishoil"),
    ("记录coq10fishoil", "coq10fishoil"),
    ("记录b12magnesium", "b12magnesium"),
    ("记录vitamindandfishoil", "vitamindandfishoil"),
    ("记录vitamin-d-fishoil", "vitamin-d-fishoil"),
    ("记录d3-fish-oil", "d3-fish-oil"),
])
async def test_directive_or_multi_entity_superstrings_cannot_become_supplement_names(
    db,
    user_message,
    model_name,
):
    """当前回合出现同一长串，也不能把指令、剂量或多实体当成补剂名。"""
    ex = _executor(db)
    ex._current_turn_user_message = user_message
    ex._current_turn_has_attachment = False
    lookup = AsyncMock(return_value=([], None))
    create = AsyncMock(return_value=({"id": 73, "name": model_name}, None))
    tap = AsyncMock(return_value='{"record_id": 1073}')

    with patch.object(ex, "_api_get_json", new=lookup), \
         patch.object(ex, "_api_post_json", new=create), \
         patch.object(ex, "_api_post", new=tap):
        result = await ex._exec_health_record("http://x", {}, {
            "record_type": "supplement",
            "data": {"supplement_name": model_name},
        })

    parsed = json.loads(result)
    assert parsed["error_code"] == "supplement_name_not_user_grounded"
    assert parsed["dispatch_started"] is False
    lookup.assert_not_awaited()
    create.assert_not_awaited()
    tap.assert_not_awaited()


@pytest.mark.asyncio
async def test_attachment_supplement_write_requires_text_confirmation(db):
    ex = _executor(db)
    ex._current_turn_user_message = "识别并记录维生素D"
    ex._current_turn_has_attachment = True
    lookup = AsyncMock(return_value=([], None))
    create = AsyncMock(return_value=({"id": 73, "name": "维生素D"}, None))
    tap = AsyncMock(return_value='{"record_id": 1073}')

    with patch.object(ex, "_api_get_json", new=lookup), \
         patch.object(ex, "_api_post_json", new=create), \
         patch.object(ex, "_api_post", new=tap):
        result = await ex._exec_health_record("http://x", {}, {
            "record_type": "supplement",
            "data": {"supplement_name": "维生素D"},
        })

    parsed = json.loads(result)
    assert parsed["error_code"] == "supplement_image_confirmation_required"
    assert parsed["dispatch_started"] is False
    lookup.assert_not_awaited()
    create.assert_not_awaited()
    tap.assert_not_awaited()
