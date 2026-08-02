"""Wechat login must not bypass invitation-only registration rollout."""

import logging

import pytest

from app.api import wechat as wechat_api
from app.config import settings
from app.models.invitation import InvitationCode
from app.models.user import User


@pytest.fixture(autouse=True)
def _wechat_session(monkeypatch):
    async def fake_session(code: str) -> dict:
        return {"openid": f"openid-{code}", "session_key": "session-key"}

    monkeypatch.setattr(wechat_api, "get_wechat_session", fake_session)


@pytest.mark.parametrize("rollout", [True, False])
@pytest.mark.parametrize("invite_source", ["default", "database"])
def test_enforcement_blocks_unknown_wechat_before_any_legacy_invite_mutation(
    client, db, monkeypatch, rollout, invite_source
):
    monkeypatch.setattr(settings, "registration_invitation_rollout_enabled", rollout)
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    monkeypatch.setattr(settings, "default_invite_code", "DEFAULT8")
    invite_code = settings.default_invite_code
    database_invite = None
    if invite_source == "database":
        database_invite = InvitationCode(
            code="DATABASE8", max_uses=2, used_count=0, is_active=True
        )
        db.add(database_invite)
        db.commit()
        invite_code = database_invite.code

    response = client.post(
        "/api/v1/wechat/login",
        json={"code": f"unknown-{rollout}-{invite_source}", "invite_code": invite_code},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "REGISTRATION_INVITATION_REQUIRED"
    assert db.query(User).count() == 0
    if database_invite is not None:
        db.refresh(database_invite)
        assert database_invite.used_count == 0


@pytest.mark.parametrize("enforcement", [False, True])
def test_existing_wechat_user_login_continues_in_both_enforcement_states(
    client, db, monkeypatch, enforcement
):
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", enforcement)
    user = User(
        username=f"existing_wechat_{enforcement}",
        name="Existing WeChat",
        wechat_openid="openid-existing",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    response = client.post("/api/v1/wechat/login", json={"code": "existing"})

    assert response.status_code == 200
    assert response.json()["user_id"] == user.id
    assert response.json()["is_new_user"] is False
    assert response.json()["access_token"]


def test_compatibility_wechat_registration_does_not_log_raw_invite_code(
    client, db, monkeypatch, caplog
):
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", False)
    invitation = InvitationCode(code="WECHAT88", max_uses=2, used_count=0, is_active=True)
    db.add(invitation)
    db.commit()
    caplog.set_level(logging.INFO, logger="app.api.wechat")

    response = client.post(
        "/api/v1/wechat/login",
        json={"code": "compat", "nickname": "Compat", "invite_code": invitation.code},
    )

    assert response.status_code == 200
    assert invitation.code not in caplog.text
