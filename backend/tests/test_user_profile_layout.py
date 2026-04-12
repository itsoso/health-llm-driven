"""AI 助理首页布局配置 API 测试"""


def test_profile_layout_defaults_to_empty_device_configs(client, auth_user_and_headers):
    """未配置时应返回空的 web/mobile 布局"""
    _, headers = auth_user_and_headers

    response = client.get("/api/v1/profile/me", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["assistant_dashboard_layouts"] == {
        "web": {"order": [], "hidden": []},
        "mobile": {"order": [], "hidden": []},
    }


def test_profile_layout_updates_only_current_device_without_overwriting_other(client, auth_user_and_headers):
    """更新单端布局时应保留另一端配置"""
    _, headers = auth_user_and_headers

    response = client.put(
        "/api/v1/profile/me",
        json={
            "assistant_dashboard_layouts": {
                "web": {
                    "order": ["hero", "alerts", "action_cards"],
                    "hidden": ["specialists"],
                }
            }
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["assistant_dashboard_layouts"]["web"] == {
        "order": ["hero", "alerts", "action_cards"],
        "hidden": ["specialists"],
    }
    assert data["assistant_dashboard_layouts"]["mobile"] == {"order": [], "hidden": []}

    response = client.put(
        "/api/v1/profile/me",
        json={
            "assistant_dashboard_layouts": {
                "mobile": {
                    "order": ["hero", "quick_record", "workout"],
                    "hidden": ["trends"],
                }
            }
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["assistant_dashboard_layouts"]["web"] == {
        "order": ["hero", "alerts", "action_cards"],
        "hidden": ["specialists"],
    }
    assert data["assistant_dashboard_layouts"]["mobile"] == {
        "order": ["hero", "quick_record", "workout"],
        "hidden": ["trends"],
    }
