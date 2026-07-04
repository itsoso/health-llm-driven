"""OpenClaw external runtime has been retired."""


def test_openclaw_channel_routes_are_not_registered(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    response = client.post(
        "/api/v1/openclaw/send",
        json={"message": "测试"},
        headers=headers,
    )

    assert response.status_code == 404


def test_assistant_openclaw_routes_are_not_registered(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    response = client.get("/api/v1/assistant-openclaw/binding/me", headers=headers)

    assert response.status_code == 404


def test_openclaw_skill_admin_routes_are_not_registered(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    response = client.get("/api/v1/openclaw/skills/gateway/status", headers=headers)

    assert response.status_code == 404
