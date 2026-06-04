"""用药记录: 未登记的药(短程抗生素等)应自动登记再记录, 不报"未找到活跃药物"。

复现 bug: "吃了两粒阿奇霉素" → 旧逻辑返回 "未找到名为 '阿奇霉素' 的活跃药物" 并放弃。
"""
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_medication_autocreates_when_not_registered(db):
    from app.services.agent_executor import AgentExecutor
    ex = AgentExecutor(db)

    create_payload = {}
    log_payload = {}

    async def fake_get_json(url, headers):
        return [], None  # 没有任何活跃药物

    async def fake_post_json(url, headers, payload):
        create_payload.update(payload)
        create_payload["_url"] = url
        return {"id": 99, "name": payload.get("name"), "is_active": True}, None

    async def fake_post(url, headers, payload):
        log_payload.update(payload)
        log_payload["_url"] = url
        return '{"id": 1, "status": "taken"}'

    with patch.object(ex, "_api_get_json", new=AsyncMock(side_effect=fake_get_json)), \
         patch.object(ex, "_api_post_json", new=AsyncMock(side_effect=fake_post_json)), \
         patch.object(ex, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await ex._exec_health_record("http://x", {}, {
            "record_type": "medication",
            "data": {"medication_name": "阿奇霉素", "dosage": "2粒"},
        })

    assert "未找到" not in result
    # 自动登记
    assert create_payload.get("name") == "阿奇霉素"
    assert create_payload.get("dosage") == "2粒"
    assert "/medication/medications" in create_payload.get("_url", "")
    # 再记录服用, 用新建药物的 id
    assert log_payload.get("medication_id") == 99
    assert log_payload.get("status") == "taken"
    assert "/medication/logs" in log_payload.get("_url", "")


@pytest.mark.asyncio
async def test_medication_logs_existing_active_without_creating(db):
    from app.services.agent_executor import AgentExecutor
    ex = AgentExecutor(db)
    log_payload = {}

    async def fake_get_json(url, headers):
        return [{"id": 7, "name": "二甲双胍", "is_active": True}], None

    async def fake_post_json(url, headers, payload):
        raise AssertionError("已有活跃药物时不应自动新建")

    async def fake_post(url, headers, payload):
        log_payload.update(payload)
        return '{"id": 2}'

    with patch.object(ex, "_api_get_json", new=AsyncMock(side_effect=fake_get_json)), \
         patch.object(ex, "_api_post_json", new=AsyncMock(side_effect=fake_post_json)), \
         patch.object(ex, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await ex._exec_health_record("http://x", {}, {
            "record_type": "medication",
            "data": {"medication_name": "二甲双胍"},
        })

    assert "未找到" not in result
    assert log_payload.get("medication_id") == 7


@pytest.mark.asyncio
async def test_medication_autocreate_failure_is_graceful(db):
    from app.services.agent_executor import AgentExecutor
    ex = AgentExecutor(db)

    async def fake_get_json(url, headers):
        return [], None

    async def fake_post_json(url, headers, payload):
        return None, "API 返回 500"

    with patch.object(ex, "_api_get_json", new=AsyncMock(side_effect=fake_get_json)), \
         patch.object(ex, "_api_post_json", new=AsyncMock(side_effect=fake_post_json)), \
         patch.object(ex, "_api_post", new=AsyncMock()):
        result = await ex._exec_health_record("http://x", {}, {
            "record_type": "medication",
            "data": {"medication_name": "阿奇霉素"},
        })

    assert "没成功" in result  # 友好兜底, 不抛
