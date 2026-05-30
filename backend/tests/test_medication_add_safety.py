"""POST /medication/medications 即时安全检查 —— Tier 0 ② 回归测试.

新增药物时同步跑 SafetyGuardian (而非等 23:00 批量), 把 DDI/DSI/PGx 高危
相互作用当场回到响应体的 safety_alerts, 并对 high/critical 触发 health_alert 推送.

确定性触发: 华法林 + 布洛芬(NSAID) → ddi.warfarin_bleeding (HIGH).
"""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import sessionmaker


@pytest.fixture(autouse=True)
def bind_session_local_to_test_db(db):
    """build_twin 的并行 filler (medication 等) 走 app.database.SessionLocal,
    默认绑生产 engine, 测试里看不到刚加的药. 绑到测试 in-memory engine (StaticPool 共享连接)。"""
    TestSession = sessionmaker(bind=db.get_bind())
    with patch("app.database.SessionLocal", TestSession):
        yield


def _add_med(client, headers, name, **kw):
    body = {"name": name, **kw}
    resp = client.post("/api/v1/medication/medications", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_first_med_no_interaction_returns_empty_alerts(client, auth_user_and_headers):
    _user, headers = auth_user_and_headers
    with patch(
        "app.services.notification.push_service.PushService.send_notification",
        new_callable=AsyncMock,
    ) as mock_send:
        body = _add_med(client, headers, "华法林", category="抗凝")

    assert "safety_alerts" in body
    assert body["safety_alerts"] == []
    mock_send.assert_not_called()


def test_ddi_returns_safety_alerts_and_fires_push(client, auth_user_and_headers):
    user, headers = auth_user_and_headers

    with patch(
        "app.services.notification.push_service.PushService.send_notification",
        new_callable=AsyncMock,
    ) as mock_send:
        _add_med(client, headers, "华法林", category="抗凝")          # 单药: 不触发
        body = _add_med(client, headers, "布洛芬", category="止痛")    # + NSAID → HIGH

    alerts = body["safety_alerts"]
    assert len(alerts) >= 1, alerts
    warfarin = [a for a in alerts if a["rule_id"] == "ddi.warfarin_bleeding"]
    assert warfarin, f"期望 ddi.warfarin_bleeding 告警, 实际: {[a['rule_id'] for a in alerts]}"
    a = warfarin[0]
    assert a["category"] == "ddi"
    assert a["severity"]["label"] == "high"

    # high/critical 必须触发推送 (用户离开页面也能收到)
    assert mock_send.await_count >= 1
    kwargs = mock_send.await_args.kwargs
    assert kwargs["notification_type"] == "health_alert"
    assert kwargs["severity"] == "high"
    assert kwargs["data"]["rule_id"] == "ddi.warfarin_bleeding"


def test_eval_failure_never_blocks_save(client, auth_user_and_headers):
    """安全评估抛错时药品仍要保存成功, safety_alerts 退化为空 (防御式, 不假装成功也不阻断)。"""
    _user, headers = auth_user_and_headers
    with patch("app.twin.builder.build_twin", side_effect=RuntimeError("twin boom")):
        body = _add_med(client, headers, "华法林", category="抗凝")

    assert body["id"]  # 药品保存成功
    assert body["name"] == "华法林"
    assert body["safety_alerts"] == []
