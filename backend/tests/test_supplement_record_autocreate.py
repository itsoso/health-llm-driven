"""补剂记录自动建档(镜像 medication 先例)。

用户在当前纯文本消息明确写出一个不在补剂库里的新补剂时,agent 应自动
POST /supplements/definitions 建档再打卡；图片或历史上下文推断的名称不得写入。
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent_executor import AgentExecutor


def _executor(db):
    ex = AgentExecutor(db)
    ex._current_user_id = 1
    return ex


@pytest.mark.asyncio
async def test_unregistered_supplement_autocreates_then_taps(db):
    ex = _executor(db)
    ex._current_turn_user_message = "帮我记录：正官庄红参液 10mL，确认打卡"
    create_payload: dict = {}
    tap_payload: dict = {}

    async def fake_get_json(url, headers):
        assert "/supplements/me/definitions" in url
        return [], None  # 补剂库为空

    async def fake_post_json(url, headers, payload):
        assert "/supplements/definitions" in url
        create_payload.update(payload)
        return {"id": 88, "name": payload["name"]}, None

    async def fake_post(url, headers, payload):
        assert "/nfc/tap" in url
        tap_payload.update(payload)
        return '{"status": "ok"}'

    with patch.object(ex, "_api_get_json", new=AsyncMock(side_effect=fake_get_json)), \
         patch.object(ex, "_api_post_json", new=AsyncMock(side_effect=fake_post_json)), \
         patch.object(ex, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await ex._exec_health_record("http://x", {}, {
            "record_type": "supplement",
            "data": {"supplement_name": "正官庄红参液", "dosage": "10mL", "category": "herbal"},
        })

    assert create_payload.get("name") == "正官庄红参液"
    assert create_payload.get("dosage") == "10mL"
    assert tap_payload.get("supplement_id") == 88
    parsed = json.loads(result)
    assert "加入补剂库" in parsed["message"]
    assert "88" in parsed["message"]  # 补剂号入回显,撤销回合有 id 可用
    assert "撤销" in parsed["message"]


@pytest.mark.asyncio
async def test_registered_supplement_taps_without_creating(db):
    ex = _executor(db)
    ex._current_turn_user_message = "记录红参液"
    created = {"called": False}

    async def fake_get_json(url, headers):
        return [{"id": 7, "name": "正官庄红参液", "is_active": True}], None

    async def fake_post_json(url, headers, payload):
        created["called"] = True
        return {}, None

    async def fake_post(url, headers, payload):
        assert payload.get("supplement_id") == 7
        return '{"status": "ok"}'

    with patch.object(ex, "_api_get_json", new=AsyncMock(side_effect=fake_get_json)), \
         patch.object(ex, "_api_post_json", new=AsyncMock(side_effect=fake_post_json)), \
         patch.object(ex, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await ex._exec_health_record("http://x", {}, {
            "record_type": "supplement",
            "data": {"supplement_name": "红参液"},
        })

    assert created["called"] is False  # 已注册 → 不重复建档
    assert "ok" in result


@pytest.mark.asyncio
async def test_autocreate_failure_gives_friendly_fallback_no_raw_error(db):
    ex = _executor(db)
    ex._current_turn_user_message = "记录红参液"

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
