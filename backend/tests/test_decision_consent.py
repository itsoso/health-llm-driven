"""Remote recipient changes require new grants; local does not widen egress."""

import pytest
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.config import settings
from app.services import ai_consent
from tests.conftest import create_authenticated_user


def test_remote_recipient_change_invalidates_existing_grant(db, monkeypatch):
    user, _ = create_authenticated_user(db)
    monkeypatch.setattr(settings, "decision_mode", "off")
    initial = ai_consent.get_ai_consent(db, user.id)
    ai_consent.update_ai_consent(db, user.id, True, initial["policy_version"])
    monkeypatch.setattr(settings, "decision_mode", "shadow")
    monkeypatch.setattr(settings, "decision_provider", "jev")
    monkeypatch.setattr(settings, "decision_base_url", None)
    monkeypatch.setattr(settings, "decision_recipient_name", None)
    remote = ai_consent.get_ai_consent(db, user.id)
    assert remote["accepted"] is False
    assert remote["policy_version"] != initial["policy_version"]
    assert any("TypeSafe" in r["name"] for r in remote["recipients"])
    with pytest.raises(HTTPException):
        ai_consent.update_ai_consent(db, user.id, True, initial["policy_version"])
    ai_consent.update_ai_consent(db, user.id, True, remote["policy_version"])
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    ai_consent.require_ai_consent(
        user.id, destination="https://api.typesafe.ai/v1/systemone"
    )
    for bad in (
        "https://api.typesafe.ai/other",
        "https://api.typesafe.ai/v1/systemone?x=1",
        "http://api.typesafe.ai/v1/systemone",
    ):
        with pytest.raises(HTTPException):
            ai_consent.require_ai_consent(user.id, destination=bad)
    monkeypatch.setattr(settings, "decision_api_key", "rotated-key")
    assert ai_consent.get_ai_consent(db, user.id)["accepted"] is True
    monkeypatch.setattr(settings, "decision_base_url", "https://decision.example/v1")
    monkeypatch.setattr(settings, "decision_recipient_name", "Self-hosted service")
    assert ai_consent.get_ai_consent(db, user.id)["accepted"] is False
    assert not ai_consent.is_disclosed_destination(
        "https://api.typesafe.ai/v1/systemone"
    )


def test_local_does_not_add_remote_recipient(db, monkeypatch):
    user, _ = create_authenticated_user(db)
    monkeypatch.setattr(settings, "decision_mode", "on")
    monkeypatch.setattr(settings, "decision_provider", "laya")
    monkeypatch.setattr(settings, "decision_base_url", None)
    state = ai_consent.get_ai_consent(db, user.id)
    assert state["policy_version"] == ai_consent.POLICY_VERSION
    assert state["recipients"] == ai_consent.RECIPIENTS
    assert not ai_consent.is_disclosed_destination("http://127.0.0.1:8092/v1/systemone")


def test_invalid_optional_configuration_preserves_existing_consent(db, monkeypatch):
    user, _ = create_authenticated_user(db)
    monkeypatch.setattr(settings, "decision_mode", "on")
    monkeypatch.setattr(settings, "decision_provider", "systemone")
    monkeypatch.setattr(settings, "decision_base_url", "https://decision.example/v1")
    monkeypatch.setattr(settings, "decision_model", "custom")
    monkeypatch.setattr(settings, "decision_recipient_name", None)
    state = ai_consent.get_ai_consent(db, user.id)
    assert state["policy_version"] == ai_consent.POLICY_VERSION
    ai_consent.update_ai_consent(db, user.id, True, state["policy_version"])
    assert ai_consent.get_ai_consent(db, user.id)["accepted"] is True
    assert ai_consent.is_disclosed_destination("https://dashscope.aliyuncs.com/api/v1")
    assert not ai_consent.is_disclosed_destination(
        "https://decision.example/v1/systemone"
    )
