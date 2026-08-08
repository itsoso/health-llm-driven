"""补剂记录自动建档(镜像 medication 先例)。

用户拍照/口述一个不在补剂库里的新补剂("记录这个补剂")时,agent 应
自动 POST /supplements/definitions 建档再打卡,而不是报"未找到名为 X
的活跃补剂"把用户推去手动页面(实测:正官庄红参液 Royal Everytime)。
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


@pytest.mark.asyncio
async def test_registered_supplement_taps_without_creating(db):
    ex = _executor(db)
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
