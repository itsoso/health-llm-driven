import pytest

from app.services import agent_loop


@pytest.mark.asyncio
async def test_agent_loop_notify_uses_user_kb_evidence_builder(db, monkeypatch):
    captured = {}

    class FakeProvider:
        async def chat(self, *args, **kwargs):
            return '{"action":"notify","title":"补剂提醒","message":"今天关注叶酸补充","severity":"info"}'

    class FakePushService:
        def __init__(self, db_arg):
            self.db = db_arg

        async def send_notification(self, **kwargs):
            captured.update(kwargs)
            return {"success": True}

    def fake_evidence_builder(db_arg, **kwargs):
        assert db_arg is db
        assert kwargs["user_id"] == 7
        assert kwargs["notification_type"] == "ai_advice"
        return {
            "source": "agent_loop",
            "severity": "info",
            "evidence_refs": ["claim:c_mthfr_c677t_hcy_folate_boundary"],
            "support_status": "supported",
            "unsupported": False,
        }

    monkeypatch.setattr(agent_loop, "_check_push_limit", lambda user_id: True)
    monkeypatch.setattr(agent_loop, "_increment_push_count", lambda user_id: None)
    monkeypatch.setattr(agent_loop, "_build_context", lambda *args, **kwargs: "context")
    monkeypatch.setattr("app.services.llm.factory.create_llm_provider", lambda _name=None: FakeProvider())
    monkeypatch.setattr("app.services.notification.push_service.PushService", FakePushService)
    monkeypatch.setattr(
        "app.services.notification.evidence_policy.build_notification_evidence_data_for_user",
        fake_evidence_builder,
    )

    result = await agent_loop.post_sync_reasoning(
        db=db,
        user_id=7,
        twin=None,
        anomaly_alerts=[],
        safety_report=None,
    )

    assert result["action"] == "notify"
    assert captured["data"]["support_status"] == "supported"
    assert captured["data"]["evidence_refs"] == ["claim:c_mthfr_c677t_hcy_folate_boundary"]
