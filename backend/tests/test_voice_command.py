"""Voice shortcut requests must enter the Agent Kernel before any write."""
from __future__ import annotations

import pytest

from app.models.daily_health import WaterIntake
from app.models.user import User
from app.services.agent_executor import AgentExecutor
from app.services.voice_command_service import VoiceCommandService


@pytest.fixture
def test_user(db):
    user = User(name="语音测试用户", phone="13800138001", is_active=True, is_approved=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def service(db, test_user):
    return VoiceCommandService(db, test_user.id)


def test_build_draft_uses_semantic_write_intent_and_explicit_amount(service):
    draft = service.build_draft("喝了两杯水")

    assert draft is not None
    assert draft["command_type"] == "water"
    assert draft["arguments"] == {
        "record_type": "water",
        "data": {"amount": 500, "drink_type": "水"},
    }
    assert draft["snapshot"].intent.primary == "write"
    assert draft["snapshot"].context.channel == "voice"


@pytest.mark.parametrize("text", ["喝水", "血压有点高", "体重多少"])
def test_ambiguous_voice_observations_do_not_create_a_draft(service, text):
    assert service.build_draft(text) is None


def test_query_about_records_never_becomes_a_voice_write(service):
    assert service.build_draft("列出今天饮食记录") is None
    assert service.build_draft("今天喝水了吗？") is None


def test_draft_building_never_writes_to_database(db, test_user, service):
    assert service.build_draft("喝了300ml水") is not None

    assert db.query(WaterIntake).filter(WaterIntake.user_id == test_user.id).count() == 0


@pytest.mark.asyncio
async def test_execute_routes_voice_record_through_confirmation_boundary(db, test_user, service):
    result = await service.execute("体重72.5kg")

    assert result is not None
    assert result["command_type"] == "weight"
    assert result["requires_confirmation"] is True
    assert "已记录" not in result["message"]
    assert db.query(WaterIntake).filter(WaterIntake.user_id == test_user.id).count() == 0


@pytest.mark.asyncio
async def test_execute_does_not_report_structured_policy_rejection_as_recorded(
    db,
    test_user,
    service,
    monkeypatch,
):
    async def rejected_tool(*_args, **_kwargs):
        return (
            '{"status":"rejected","error_code":"write_tool_without_write_intent",'
            '"dispatch_started":false}'
        )

    monkeypatch.setattr(AgentExecutor, "_execute_tool", rejected_tool)

    result = await service.execute("体重72.5kg")

    assert result is not None
    assert result["execution_status"] == "blocked_or_failed"
    assert result["requires_confirmation"] is False
    assert "未写入" in result["message"]


@pytest.mark.asyncio
async def test_execute_does_not_promote_uncertain_result_with_identity(
    db,
    test_user,
    service,
    monkeypatch,
):
    async def uncertain_tool(*_args, **_kwargs):
        return (
            '{"status":"uncertain","dispatch_started":true,"success":true,'
            '"record_id":72,"message":"已记录体重72.5kg"}'
        )

    monkeypatch.setattr(AgentExecutor, "_execute_tool", uncertain_tool)

    result = await service.execute("体重72.5kg")

    assert result is not None
    assert result["execution_status"] == "unverified_result"
    assert "已记录" not in result["message"]
    assert result.get("record_id") is None


class TestVoiceCommandAPI:
    def test_api_auto_records_explicit_water_voice_command(self, client, db):
        from app.services.auth import auth_service

        user = User(name="API测试用户", phone="13800138002", is_active=True, is_approved=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        token = auth_service.create_access_token({"sub": str(user.id)})

        response = client.post(
            "/api/v1/chat/voice-command",
            json={"text": "喝了一杯水"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["matched"] is True
        assert payload["command_type"] == "water"
        assert payload["requires_confirmation"] is False
        assert payload["execution_status"] == "recorded"
        record = db.query(WaterIntake).filter(WaterIntake.user_id == user.id).one()
        assert record.amount_ml == 250

    def test_api_not_matched(self, client, db):
        from app.services.auth import auth_service

        user = User(name="API测试用户2", phone="13800138003", is_active=True, is_approved=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        token = auth_service.create_access_token({"sub": str(user.id)})

        response = client.post(
            "/api/v1/chat/voice-command",
            json={"text": "列出我今天吃的所有东西"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["matched"] is False

    def test_api_requires_auth(self, client):
        response = client.post("/api/v1/chat/voice-command", json={"text": "喝了300ml水"})
        assert response.status_code in [401, 403]
