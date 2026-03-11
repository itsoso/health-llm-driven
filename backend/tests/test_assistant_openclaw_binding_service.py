import pytest

from app.models.assistant_openclaw import AssistantOpenClawBinding
from app.models.user import User
from app.services.assistant_openclaw_binding_service import AssistantOpenClawBindingService


def create_user(db, username: str = "assistant-binding-user") -> User:
    user = User(
        name="测试用户",
        username=username,
        email=f"{username}@example.com",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_validate_gateway_url_allows_localhost(db):
    service = AssistantOpenClawBindingService(db)

    assert service.validate_gateway_url("http://127.0.0.1:28789") == "http://127.0.0.1:28789"
    assert service.validate_gateway_url("http://localhost:18789") == "http://localhost:18789"


def test_validate_gateway_url_rejects_public_ip(db):
    service = AssistantOpenClawBindingService(db)

    with pytest.raises(ValueError, match="不在允许范围内"):
        service.validate_gateway_url("http://8.8.8.8:18789")


def test_upsert_binding_encrypts_token_and_resolves_connection(db):
    user = create_user(db)
    service = AssistantOpenClawBindingService(db)

    binding = service.upsert_binding(
        user_id=user.id,
        display_name="我的 OpenClaw",
        gateway_url="http://127.0.0.1:28789",
        gateway_token="secret-token-1234",
        enabled=True,
    )

    assert binding.gateway_token_last4 == "1234"
    assert binding.gateway_token_encrypted != "secret-token-1234"

    binding.status = "active"
    db.commit()

    gateway_url, token = service.get_active_connection(user.id)
    assert gateway_url == "http://127.0.0.1:28789"
    assert token == "secret-token-1234"


@pytest.mark.asyncio
async def test_test_binding_persists_saved_result(db, monkeypatch):
    user = create_user(db, username="assistant-binding-user-2")
    service = AssistantOpenClawBindingService(db)
    service.upsert_binding(
        user_id=user.id,
        display_name="我的 OpenClaw",
        gateway_url="http://127.0.0.1:28789",
        gateway_token="secret-token-5678",
        enabled=True,
    )

    async def fake_probe(gateway_url: str, gateway_token: str):
        assert gateway_url == "http://127.0.0.1:28789"
        assert gateway_token == "secret-token-5678"
        return {
            "reachable": True,
            "authenticated": True,
            "status": "active",
            "latency_ms": 12,
            "message": "连接成功",
        }

    monkeypatch.setattr(service, "_probe_gateway", fake_probe)
    result = await service.test_binding(user.id, persist_result=True)

    db_binding = db.query(AssistantOpenClawBinding).filter_by(user_id=user.id).first()
    assert result["status"] == "active"
    assert db_binding is not None
    assert db_binding.status == "active"
    assert db_binding.last_error is None
    assert db_binding.last_tested_at is not None
