"""AtomicCapability registry contracts for Agent Native DynamicView."""

from __future__ import annotations

import pytest


def test_today_dynamic_view_uses_registered_atomic_capabilities(monkeypatch):
    from app.services import today_dynamic_view_service
    from app.services.atomic_capability_registry import (
        get_atomic_capability,
        validate_dynamic_view,
    )

    runtime_action = _runtime_action("smart_daily_plan_action_walk", "晚餐后步行 15 分钟")

    def fake_artifact(db, user_id, followup_within_days=7):
        assert user_id == 42
        assert followup_within_days == 7
        return _artifact("smart_daily_plan_action_sleep", "今晚提前 30 分钟睡前准备")

    def fake_runtime(db, user_id, days=7, max_items_per_day=3):
        assert user_id == 42
        assert days == 7
        assert max_items_per_day == 3
        return _runtime(runtime_action)

    monkeypatch.setattr(today_dynamic_view_service.daily_artifact_service, "build_daily_artifact", fake_artifact)
    monkeypatch.setattr(today_dynamic_view_service.agenda_service, "runtime_range_view", fake_runtime)
    # db=object() 无法真评估;stub 成「零告警、零规则失败」保持本测试原意(hero/runtime 组合)。
    monkeypatch.setattr(today_dynamic_view_service, "_evaluate_safety_alerts", lambda db, user_id: ([], 0))

    view = today_dynamic_view_service.build_today_dynamic_view(object(), 42)
    card_types = {
        card["type"]
        for section in view["sections"]
        for card in section["cards"]
    }

    assert card_types == {"daily_artifact", "runtime_agenda"}
    assert validate_dynamic_view(view) == []
    for card_type in card_types:
        capability = get_atomic_capability(card_type)
        assert capability is not None
        assert "mobile.today" in capability.surfaces
        assert capability.first_class_objects
        assert capability.telemetry_events


def test_dynamic_view_validation_flags_unknown_card_type():
    from app.services.atomic_capability_registry import validate_dynamic_view

    view = {
        "surface": "mobile.today",
        "sections": [
            {
                "slot": "hero",
                "cards": [
                    {
                        "type": "model_generated_widget",
                        "data": {},
                    }
                ],
            }
        ],
    }

    assert validate_dynamic_view(view) == [
        "sections[0].cards[0]: unknown AtomicCapability card type 'model_generated_widget'"
    ]


def test_dynamic_view_validation_requires_payload_fields():
    from app.services.atomic_capability_registry import validate_dynamic_view

    view = {
        "surface": "mobile.today",
        "sections": [
            {
                "slot": "hero",
                "cards": [
                    {
                        "type": "daily_artifact",
                        "data": {
                            "generated_by": "daily_artifact_runtime_v1",
                            "top_action": None,
                        },
                    }
                ],
            }
        ],
    }

    assert validate_dynamic_view(view) == [
        "sections[0].cards[0]: daily_artifact data missing required field 'artifact_date'",
        "sections[0].cards[0]: daily_artifact data missing required field 'safety_boundary'",
    ]


def test_dynamic_view_validation_rejects_actions_outside_capability_allowlist():
    from app.services.atomic_capability_registry import validate_dynamic_view

    view = {
        "surface": "mobile.today",
        "sections": [
            {
                "slot": "runtime",
                "cards": [
                    {
                        "type": "runtime_agenda",
                        "data": {
                            "mode": "runtime",
                            "generated_by": "rolling_health_runtime_v1",
                            "start": "2026-06-29",
                            "end": "2026-07-05",
                            "next_action": {},
                            "days": [],
                        },
                        "actions": [
                            {
                                "id": "unsafe-write",
                                "label": "直接写入",
                                "action": "diet_record.create",
                            }
                        ],
                    }
                ],
            }
        ],
    }

    assert validate_dynamic_view(view) == [
        "sections[0].cards[0].actions[0]: action 'diet_record.create' is not allowed for runtime_agenda"
    ]


def test_runtime_agenda_capability_allows_only_governed_completion_actions():
    from app.services.atomic_capability_registry import get_atomic_capability, validate_dynamic_view

    capability = get_atomic_capability("runtime_agenda")
    assert capability is not None
    assert capability.execution == "manual_confirm_complete_or_route_open"

    view = {
        "surface": "mobile.today",
        "sections": [{
            "slot": "runtime",
            "cards": [{
                "type": "runtime_agenda",
                "data": {
                    "mode": "runtime",
                    "generated_by": "rolling_health_runtime_v1",
                    "start": "2026-07-14",
                    "end": "2026-07-20",
                    "next_action": {},
                    "days": [],
                },
                "actions": [{
                    "label": "完成这一步",
                    "action": "daily_plan_action.complete",
                    "endpoint": "/daily-plan/actions/intervention.card.42/events",
                    "requires_manual_confirm": True,
                    "payload": {"action_id": "intervention.card.42", "event_type": "completed"},
                    "capability_id": "runtime_agenda.v1",
                    "required_receipt": True,
                    "autonomy_tier": "manual_confirm",
                    "policy_reason": "manual_confirm_write",
                }],
            }],
        }],
    }
    assert validate_dynamic_view(view) == []

    view["sections"][0]["cards"][0]["actions"][0].pop("requires_manual_confirm")
    assert validate_dynamic_view(view) == [
        "sections[0].cards[0].actions[0]: write action requires manual confirmation"
    ]


def test_today_dynamic_view_fails_loud_when_composer_emits_unregistered_card(monkeypatch):
    from app.services import today_dynamic_view_service

    def fake_artifact(db, user_id, followup_within_days=7):
        return _artifact("smart_daily_plan_action_sleep", "今晚提前 30 分钟睡前准备")

    def fake_runtime(db, user_id, days=7, max_items_per_day=3):
        return _runtime(_runtime_action("smart_daily_plan_action_walk", "晚餐后步行 15 分钟"))

    def fake_sections(artifact, runtime, safety_cards):
        return [
            {
                "slot": "hero",
                "priority": 100,
                "cards": [{"type": "model_generated_widget", "data": {}}],
            }
        ]

    monkeypatch.setattr(today_dynamic_view_service.daily_artifact_service, "build_daily_artifact", fake_artifact)
    monkeypatch.setattr(today_dynamic_view_service.agenda_service, "runtime_range_view", fake_runtime)
    monkeypatch.setattr(today_dynamic_view_service, "_evaluate_safety_alerts", lambda db, user_id: ([], 0))
    monkeypatch.setattr(today_dynamic_view_service, "_compose_sections", fake_sections)

    with pytest.raises(ValueError, match="invalid_dynamic_view"):
        today_dynamic_view_service.build_today_dynamic_view(object(), 42)


def test_safety_capability_registered_with_pinned_read_only_actions():
    """安全地板卡的能力契约:只允许 route.open,读侧,永不携带写路径。"""
    from app.services.atomic_capability_registry import get_atomic_capability

    capability = get_atomic_capability("safety")
    assert capability is not None
    assert "mobile.today" in capability.surfaces
    assert capability.action_types == ("route.open",)
    assert capability.execution == "read_only_route_open"
    for field in ("title", "severity", "summary", "boundary", "requires_medical_attention"):
        assert field in capability.data_required_fields


def _runtime_action(action_id: str, title: str):
    return {
        "id": action_id,
        "type": "movement",
        "title": title,
        "time_window": "evening",
        "priority_tier": "P1",
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
