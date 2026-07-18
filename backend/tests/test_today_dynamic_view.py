"""Today DynamicView contract composed by Aheng."""


def _without_kernel_action_policy(value):
    if isinstance(value, list):
        return [_without_kernel_action_policy(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: item
        for key, item in value.items()
        if key not in {"capability_id", "required_receipt", "autonomy_tier", "policy_reason"}
    }


def test_today_dynamic_view_suppresses_runtime_duplicate_of_daily_artifact(
    client,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services import today_dynamic_view_service

    user, headers = auth_user_and_headers
    runtime_action = _runtime_action("smart_daily_plan_action_walk", "晚餐后步行 15 分钟")

    def fake_artifact(db, user_id, followup_within_days=7):
        assert user_id == user.id
        assert followup_within_days == 7
        return _artifact("smart_daily_plan_action_walk", "晚餐后步行 15 分钟")

    def fake_runtime(db, user_id, days=7, max_items_per_day=3):
        assert user_id == user.id
        assert days == 7
        assert max_items_per_day == 3
        return _runtime(runtime_action)

    monkeypatch.setattr(today_dynamic_view_service.daily_artifact_service, "build_daily_artifact", fake_artifact)
    monkeypatch.setattr(today_dynamic_view_service.agenda_service, "runtime_range_view", fake_runtime)

    resp = client.post(
        "/api/v1/dynamic-views/today",
        headers=headers,
        json={
            "surface": "mobile.today",
            "trigger": "open",
            "client_context": {"timezone": "Asia/Shanghai", "client_capabilities": ["daily_artifact"]},
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["surface"] == "mobile.today"
    assert body["trigger"] == "open"
    assert body["generated_by"] == "aheng_today_view_v1"
    assert body["view_id"].startswith("today:2026-06-29:")
    assert body["context_hash"]
    assert body["safety_boundary"] == "这是健康管理行动建议, 不替代医生诊断。"
    assert {section["slot"] for section in body["sections"]} == {"hero"}

    hero = next(section for section in body["sections"] if section["slot"] == "hero")
    card = hero["cards"][0]
    assert card["id"] == "daily-artifact:2026-06-29:smart_daily_plan_action_walk"
    assert card["type"] == "daily_artifact"
    assert card["render"]["atom"] == "daily_artifact"
    assert card["render"]["dedupe_key"] == "action:smart_daily_plan_action_walk"
    assert card["render"]["reason"] == "primary_today_action"
    assert card["data"]["top_action"]["title"] == "晚餐后步行 15 分钟"


def test_today_dynamic_view_keeps_distinct_runtime_atom(client, auth_user_and_headers, monkeypatch):
    from app.services import today_dynamic_view_service

    user, headers = auth_user_and_headers
    runtime_action = _runtime_action("smart_daily_plan_action_walk", "晚餐后步行 15 分钟")

    def fake_artifact(db, user_id, followup_within_days=7):
        assert user_id == user.id
        assert followup_within_days == 7
        return _artifact("smart_daily_plan_action_sleep", "今晚提前 30 分钟睡前准备")

    def fake_runtime(db, user_id, days=7, max_items_per_day=3):
        assert user_id == user.id
        assert days == 7
        assert max_items_per_day == 3
        return _runtime(runtime_action)

    monkeypatch.setattr(today_dynamic_view_service.daily_artifact_service, "build_daily_artifact", fake_artifact)
    monkeypatch.setattr(today_dynamic_view_service.agenda_service, "runtime_range_view", fake_runtime)

    resp = client.post(
        "/api/v1/dynamic-views/today",
        headers=headers,
        json={
            "surface": "mobile.today",
            "trigger": "open",
            "client_context": {"timezone": "Asia/Shanghai", "client_capabilities": ["daily_artifact"]},
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {section["slot"] for section in body["sections"]} == {"hero", "runtime"}

    runtime = next(section for section in body["sections"] if section["slot"] == "runtime")
    card = runtime["cards"][0]
    assert card["id"] == "runtime-agenda:2026-06-29:smart_daily_plan_action_walk"
    assert card["type"] == "runtime_agenda"
    assert card["render"]["atom"] == "runtime_agenda"
    assert card["render"]["dedupe_key"] == "action:smart_daily_plan_action_walk"
    assert card["render"]["reason"] == "next_runtime_action"
    assert card["data"]["generated_by"] == "rolling_health_runtime_v1"
    assert card["data"]["presentation_mode"] == "today"
    assert card["data"]["next_action"]["replan_reason"] == "today_smart_rank"
    assert _without_kernel_action_policy(card["actions"]) == [
        {
            "id": "complete-daily-plan-action",
            "label": "完成这一步",
            "action": "daily_plan_action.complete",
            "endpoint": "/daily-plan/actions/walk/events",
            "requires_manual_confirm": True,
            "payload": {"action_id": "walk", "event_type": "completed"},
            "style": "primary",
            "confirmation": {
                "title": "完成：晚餐后步行 15 分钟？",
                "detail": "将写入今天的行动记录，并从待执行列表移除。",
                "confirm_label": "确认完成",
                "cancel_label": "再看看",
            },
            "optimistic": True,
        },
        {
            "id": "open-runtime-agenda",
            "label": "管理今日行动",
            "action": "route.open",
            "payload": {"route": "/alerts"},
            "style": "secondary",
        }
    ]


def test_today_dynamic_view_rejects_unknown_surface(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    resp = client.post(
        "/api/v1/dynamic-views/today",
        headers=headers,
        json={"surface": "mobile.dashboard", "trigger": "open", "client_context": {}},
    )

    assert resp.status_code == 422


# ── R4 安全地板(pin_safety_floor)不变量 ──


def test_today_dynamic_view_pins_safety_floor_above_hero_on_critical(
    client,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services import today_dynamic_view_service

    user, headers = auth_user_and_headers
    _patch_artifact_and_runtime(today_dynamic_view_service, monkeypatch, user)
    monkeypatch.setattr(
        today_dynamic_view_service,
        "_evaluate_safety_alerts",
        lambda db, user_id: ([_critical_alert()], 0),
    )

    resp = client.post("/api/v1/dynamic-views/today", headers=headers, json=_request_body())

    assert resp.status_code == 200, resp.text
    body = resp.json()

    # 安全 section 恒在 index 0(hero 之上),priority 高于 hero
    assert body["sections"][0]["slot"] == "safety"
    safety_section = body["sections"][0]
    hero = next(section for section in body["sections"] if section["slot"] == "hero")
    assert safety_section["priority"] == 120
    assert safety_section["priority"] > hero["priority"]

    card = safety_section["cards"][0]
    assert card["type"] == "safety"
    assert card["id"] == "safety-alert:bp_hypertensive_crisis"
    assert card["render"]["atom"] == "safety"
    assert card["render"]["priority"] == 120
    assert card["data"]["title"] == "血压达到高血压危象水平"
    assert card["data"]["severity"] == "critical"
    assert card["data"]["requires_medical_attention"] is True
    assert card["data"]["boundary"]
    assert card["data"]["rule_id"] == "bp_hypertensive_crisis"

    # 安全卡唯一允许的动作:route.open 到安全告警页,绝无写路径
    assert [a["action"] for a in card["actions"]] == ["route.open"]
    assert card["actions"][0]["payload"] == {"route": "/(tabs)/alerts"}

    # CRITICAL 活跃 → TTL 归零,客户端缓存立即过期(不许 60s 藏 CRITICAL)
    assert body["expires_at"] == body["generated_at"]


def test_today_dynamic_view_no_alerts_no_safety_section_and_normal_ttl(
    client,
    auth_user_and_headers,
    monkeypatch,
):
    from datetime import datetime

    from app.services import today_dynamic_view_service

    user, headers = auth_user_and_headers
    _patch_artifact_and_runtime(today_dynamic_view_service, monkeypatch, user)
    monkeypatch.setattr(
        today_dynamic_view_service, "_evaluate_safety_alerts", lambda db, user_id: ([], 0)
    )

    resp = client.post("/api/v1/dynamic-views/today", headers=headers, json=_request_body())

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "safety" not in {section["slot"] for section in body["sections"]}
    # 无 CRITICAL → 正常 60s TTL
    generated = datetime.fromisoformat(body["generated_at"])
    expires = datetime.fromisoformat(body["expires_at"])
    assert (expires - generated).total_seconds() == 60


def test_today_dynamic_view_injects_advisory_when_safety_evaluation_unavailable(
    client,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services import today_dynamic_view_service

    user, headers = auth_user_and_headers
    _patch_artifact_and_runtime(today_dynamic_view_service, monkeypatch, user)

    def boom(db, user_id):
        raise RuntimeError("twin build exploded")

    monkeypatch.setattr(today_dynamic_view_service, "_evaluate_safety_alerts", boom)

    resp = client.post("/api/v1/dynamic-views/today", headers=headers, json=_request_body())

    assert resp.status_code == 200, resp.text
    body = resp.json()

    # fail-loud:评估不可用绝不静默省略,注入确定性 advisory 卡钉在最上面
    assert body["sections"][0]["slot"] == "safety"
    card = body["sections"][0]["cards"][0]
    assert card["type"] == "safety"
    assert card["data"]["title"] == "安全评估不可用"
    assert card["data"]["severity"] == "high"
    assert card["data"]["requires_medical_attention"] is True
    assert card["data"]["rule_id"] == "safety.evaluation_unavailable"
    assert [a["action"] for a in card["actions"]] == ["route.open"]
    # 评估退化 → 同样跳过 TTL 缓存(不能确认没有 CRITICAL)
    assert body["expires_at"] == body["generated_at"]


def test_today_dynamic_view_partial_rule_failure_injects_fail_safe_advisory(
    client,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services import today_dynamic_view_service

    user, headers = auth_user_and_headers
    _patch_artifact_and_runtime(today_dynamic_view_service, monkeypatch, user)
    # 规则级部分失败(failed_rule_count>0):alerts 为空也必须出 guardian 的 HIGH advisory
    monkeypatch.setattr(
        today_dynamic_view_service, "_evaluate_safety_alerts", lambda db, user_id: ([], 2)
    )

    resp = client.post("/api/v1/dynamic-views/today", headers=headers, json=_request_body())

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sections"][0]["slot"] == "safety"
    card = body["sections"][0]["cards"][0]
    assert card["data"]["rule_id"] == "safety.evaluation_incomplete"
    assert card["data"]["severity"] == "high"
    assert card["data"]["requires_medical_attention"] is True
    assert body["expires_at"] == body["generated_at"]


def test_today_dynamic_view_context_hash_changes_when_alert_appears(
    client,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services import today_dynamic_view_service

    user, headers = auth_user_and_headers
    _patch_artifact_and_runtime(today_dynamic_view_service, monkeypatch, user)

    monkeypatch.setattr(
        today_dynamic_view_service, "_evaluate_safety_alerts", lambda db, user_id: ([], 0)
    )
    quiet = client.post("/api/v1/dynamic-views/today", headers=headers, json=_request_body())
    assert quiet.status_code == 200, quiet.text

    monkeypatch.setattr(
        today_dynamic_view_service,
        "_evaluate_safety_alerts",
        lambda db, user_id: ([_critical_alert()], 0),
    )
    alerted = client.post("/api/v1/dynamic-views/today", headers=headers, json=_request_body())
    assert alerted.status_code == 200, alerted.text

    # 同一 artifact/runtime/trigger/client_context,只有告警出现 → hash 与 view_id 必须翻转
    assert quiet.json()["context_hash"] != alerted.json()["context_hash"]
    assert quiet.json()["view_id"] != alerted.json()["view_id"]


def _patch_artifact_and_runtime(service_module, monkeypatch, user):
    """安全地板测试共用的 artifact/runtime stub(与既有测试同 shape)。"""
    runtime_action = _runtime_action("smart_daily_plan_action_walk", "晚餐后步行 15 分钟")

    def fake_artifact(db, user_id, followup_within_days=7):
        assert user_id == user.id
        return _artifact("smart_daily_plan_action_sleep", "今晚提前 30 分钟睡前准备")

    def fake_runtime(db, user_id, days=7, max_items_per_day=3):
        assert user_id == user.id
        return _runtime(runtime_action)

    monkeypatch.setattr(service_module.daily_artifact_service, "build_daily_artifact", fake_artifact)
    monkeypatch.setattr(service_module.agenda_service, "runtime_range_view", fake_runtime)


def _request_body():
    return {
        "surface": "mobile.today",
        "trigger": "open",
        "client_context": {"timezone": "Asia/Shanghai", "client_capabilities": ["daily_artifact"]},
    }


def _critical_alert():
    from app.agents.safety_guardian.schema import Alert, Severity

    return Alert(
        rule_id="bp_hypertensive_crisis",
        category="vitals",
        severity=Severity.CRITICAL,
        title="血压达到高血压危象水平",
        message="收缩压 ≥ 180 mmHg,建议立即处理。",
        action="立即静坐休息 5 分钟后复测;若仍 ≥180/120 或伴随胸痛/视物模糊,立即就医。",
        requires_medical_attention=True,
    )


def _runtime_action(action_id: str, title: str):
    return {
        "id": action_id,
        "type": "movement",
        "title": title,
        "time_window": "evening",
        "priority_tier": "P1",
        "source": {"object_type": "daily_plan_action", "object_id": "walk"},
        "runtime_context": {
            "current_state_summary": "晚餐后是今天最短的代谢干预窗口。",
            "replan_reason": "today_smart_rank",
            "safety_boundary": "这是健康管理行动建议, 不替代医生诊断。",
            "verification_window": {
                "metrics": ["post_meal_walk_completed", "waist_cm", "hrv"],
                "window_days": 7,
            },
        },
    }


def _artifact(action_id: str, title: str):
    return {
        "artifact_date": "2026-06-29",
        "generated_by": "daily_artifact_runtime_v1",
        "source": {"kind": "agenda.runtime_range"},
        "empty_state": False,
        "state": {"label": "今日最重要行动", "tone": "focused", "summary": "先完成餐后步行。"},
        "top_action": {
            "id": action_id,
            "title": title,
            "actions": {"complete": {"enabled": True}, "skip": {"requires_reason": True}},
        },
        "evidence": [],
        "confidence": "medium",
        "freshness": {"status": "fresh", "sources": ["agenda.runtime_range"]},
        "safety_boundary": "这是健康管理行动建议, 不替代医生诊断。",
    }


def _runtime(runtime_action: dict):
    return {
        "mode": "runtime",
        "generated_by": "rolling_health_runtime_v1",
        "horizon_days": 7,
        "start": "2026-06-29",
        "end": "2026-07-05",
        "next_action": runtime_action,
        "runtime_context": {"safety_boundary": "这是健康管理行动建议, 不替代医生诊断。"},
        "days": [
            {
                "date": "2026-06-29",
                "next_action": runtime_action,
                "time_windows": [{"label": "evening", "items": [runtime_action]}],
            },
        ],
    }
