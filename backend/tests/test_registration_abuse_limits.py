import pytest


def test_auth_routes_share_the_application_limiter():
    from main import app
    from app.api import auth, data_export, speech, wechat, workout

    for api in (auth, data_export, speech, wechat, workout):
        assert api.limiter is app.state.limiter


def test_default_limit_applies_to_undecorated_route(client):
    responses = [client.get("/").status_code for _ in range(201)]
    assert responses[:200] == [200] * 200
    assert responses[-1] == 429


def test_self_registration_default_is_open_but_remains_configurable():
    from app.config import Settings

    configured = Settings(_env_file=None)
    assert configured.auth_phone_self_registration_enabled is True
    assert Settings(_env_file=None, auth_phone_self_registration_enabled=False).auth_phone_self_registration_enabled is False
