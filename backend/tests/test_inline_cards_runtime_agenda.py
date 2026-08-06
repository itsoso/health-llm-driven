"""Chat inline runtime-agenda card contract."""

import pytest


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


def test_inline_cards_builds_runtime_agenda_card(monkeypatch):
    from app.services import inline_cards

    calls = {}

    def fake_runtime_range_view(db, user_id, days=7, max_items_per_day=3):
        calls["user_id"] = user_id
        calls["days"] = days
        calls["max_items_per_day"] = max_items_per_day
        action = {
            "id": "smart_daily_plan_action_walk",
            "type": "movement",
            "title": "晚餐后步行 15 分钟",
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
        return {
            "mode": "runtime",
            "generated_by": "rolling_health_runtime_v1",
            "horizon_days": 7,
            "start": "2026-06-28",
            "end": "2026-07-04",
            "next_action": action,
            "runtime_context": {"safety_boundary": "这是健康管理行动建议, 不替代医生诊断。"},
            "days": [
                {"date": "2026-06-28", "next_action": action, "time_windows": [{"label": "evening", "items": [action]}]},
                {"date": "2026-06-29", "next_action": None, "time_windows": [{"label": "morning", "items": []}]},
            ],
        }

    monkeypatch.setattr(inline_cards.agenda_service, "runtime_range_view", fake_runtime_range_view)

    cards = inline_cards.build_cards(db=None, user_id=3, query="接下来7天我应该怎么安排健康行动？")

    assert calls == {"user_id": 3, "days": 7, "max_items_per_day": 3}
    assert cards[0]["type"] == "runtime_agenda"
    assert cards[0]["data"]["generated_by"] == "rolling_health_runtime_v1"
    assert cards[0]["data"]["presentation_mode"] == "horizon"
    assert cards[0]["data"]["horizon_days"] == 7
    assert cards[0]["data"]["next_action"]["title"] == "晚餐后步行 15 分钟"
    assert cards[0]["data"]["next_action"]["source"] == {
        "object_type": "daily_plan_action",
        "object_id": "walk",
    }
    assert cards[0]["data"]["next_action"]["replan_reason"] == "today_smart_rank"
    assert cards[0]["data"]["next_action"]["verification_metrics"] == [
        "post_meal_walk_completed",
        "waist_cm",
        "hrv",
    ]
    assert cards[0]["actions"][0]["action"] == "daily_plan_action.complete"
    assert cards[0]["actions"][0]["payload"] == {"action_id": "walk", "event_type": "completed"}
    assert _without_kernel_action_policy(cards[0]["actions"][1]) == {
        "id": "open-runtime-agenda",
        "label": "查看完整计划",
        "action": "route.open",
        "payload": {"route": "/agenda"},
        "style": "secondary",
    }


def test_inline_cards_runtime_agenda_emits_manual_confirm_complete_action(monkeypatch):
    from app.services import inline_cards

    def fake_runtime_range_view(db, user_id, days=7, max_items_per_day=3):
        action = {
            "id": "smart_health_protocol_9",
            "type": "hydration",
            "title": "喝温水 200ml",
            "time_window": "morning",
            "priority_tier": "P0",
            "source": {"object_type": "health_protocol", "object_id": 9},
            "runtime_context": {
                "current_state_summary": "起床后补水窗口。",
                "replan_reason": "morning_runtime",
                "verification_window": {"metrics": ["water_ml"], "window_days": 1},
            },
        }
        return {
            "mode": "runtime",
            "generated_by": "rolling_health_runtime_v1",
            "horizon_days": 7,
            "start": "2026-06-30",
            "end": "2026-07-06",
            "next_action": action,
            "runtime_context": {},
            "days": [{"date": "2026-06-30", "next_action": action, "time_windows": []}],
        }

    monkeypatch.setattr(inline_cards.agenda_service, "runtime_range_view", fake_runtime_range_view)

    cards = inline_cards.build_cards(db=None, user_id=3, query="我现在下一步该做什么？")

    assert cards[0]["type"] == "runtime_agenda"
    assert cards[0]["data"]["presentation_mode"] == "today"
    assert _without_kernel_action_policy(cards[0]["actions"][0]) == {
        "id": "complete-runtime-action",
        "label": "完成这一步",
        "action": "agenda.complete",
        "endpoint": "/agenda/complete",
        "requires_manual_confirm": True,
        "payload": {
            "source": {"object_type": "health_protocol", "object_id": 9},
            "status": "done",
            "track": "manual",
        },
        "style": "primary",
        "confirmation": {
            "title": "完成：喝温水 200ml？",
            "detail": "将写入今天的健康运行时执行记录。",
            "confirm_label": "确认完成",
            "cancel_label": "再看看",
        },
        "optimistic": True,
    }
    assert _without_kernel_action_policy(cards[0]["actions"][1]) == {
        "id": "open-runtime-agenda",
        "label": "管理今日行动",
        "action": "route.open",
        "payload": {"route": "/agenda"},
        "style": "secondary",
    }


def test_inline_cards_runtime_agenda_can_complete_daily_plan_action(monkeypatch):
    from app.services import inline_cards

    action = {
        "id": "smart_daily_plan_action_intervention.card.42",
        "type": "intervention",
        "title": "今晚暂停高强度训练",
        "time_window": "evening",
        "priority_tier": "P1",
        "source": {"object_type": "daily_plan_action", "object_id": "intervention.card.42"},
        "runtime_context": {
            "current_state_summary": "今天先恢复。",
            "verification_window": {"metrics": ["hrv"], "window_days": 1},
        },
    }
    monkeypatch.setattr(inline_cards.agenda_service, "runtime_range_view", lambda *a, **k: {
        "mode": "runtime",
        "generated_by": "rolling_health_runtime_v1",
        "horizon_days": 7,
        "next_action": action,
        "runtime_context": {},
        "days": [{"date": "2026-07-14", "next_action": action, "time_windows": []}],
    })

    card = inline_cards.build_cards(db=None, user_id=3, query="我现在下一步该做什么？")[0]

    assert _without_kernel_action_policy(card["actions"][0]) == {
        "id": "complete-daily-plan-action",
        "label": "完成这一步",
        "action": "daily_plan_action.complete",
        "endpoint": "/daily-plan/actions/intervention.card.42/events",
        "requires_manual_confirm": True,
        "payload": {"action_id": "intervention.card.42", "event_type": "completed"},
        "style": "primary",
        "confirmation": {
            "title": "完成：今晚暂停高强度训练？",
            "detail": "将写入今天的行动记录，并从待执行列表移除。",
            "confirm_label": "确认完成",
            "cancel_label": "再看看",
        },
        "optimistic": True,
    }


def test_inline_cards_runtime_agenda_does_not_trigger_for_add_to_today_intent(monkeypatch):
    from app.services import inline_cards

    monkeypatch.setattr(
        inline_cards.agenda_service,
        "runtime_range_view",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call runtime")),
    )

    cards = inline_cards.build_cards(
        db=None,
        user_id=3,
        query="把这项建议加入今天计划：今晚暂停高强度训练",
    )

    assert all(card["type"] != "runtime_agenda" for card in cards)


def test_inline_cards_runtime_agenda_excludes_common_add_to_today_phrases(monkeypatch):
    from app.services import inline_cards

    monkeypatch.setattr(
        inline_cards.agenda_service,
        "runtime_range_view",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call runtime")),
    )

    for query in [
        "把这条加到我的今日安排里",
        "把这个列入今天计划",
        "把这项排进今日待办",
        "把这条放入今日计划",
    ]:
        cards = inline_cards.build_cards(db=None, user_id=3, query=query)
        assert all(card["type"] != "runtime_agenda" for card in cards)


def test_inline_cards_runtime_agenda_does_not_trigger_for_generic_how_to(monkeypatch):
    from app.services import inline_cards

    monkeypatch.setattr(
        inline_cards.agenda_service,
        "runtime_range_view",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call runtime")),
    )

    cards = inline_cards.build_cards(db=None, user_id=3, query="教我怎么做俯卧撑")
    assert all(card["type"] != "runtime_agenda" for card in cards)


def test_inline_cards_runtime_agenda_excludes_non_health_how_to_queries(monkeypatch):
    from app.services import inline_cards

    monkeypatch.setattr(
        inline_cards.agenda_service,
        "runtime_range_view",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call runtime")),
    )

    for query in (
        "我现在怎么做番茄炒蛋",
        "我现在怎么做红烧肉",
        "今天怎么安排会议",
        "今天怎么安排论文写作",
    ):
        cards = inline_cards.build_cards(db=None, user_id=3, query=query)
        assert all(card["type"] != "runtime_agenda" for card in cards)


@pytest.mark.parametrize(
    "query",
    [
        "今天怎么安排锻炼",
        "今天怎么安排服药",
        "今天怎么安排康复",
        "今天怎么安排冥想",
    ],
)
def test_runtime_agenda_recognizes_common_health_context_terms(query):
    from app.services.inline_cards import _runtime_agenda_presentation_mode

    assert _runtime_agenda_presentation_mode(query) == "today"


@pytest.mark.parametrize(
    "query",
    [
        "今天怎么安排健康产品会议",
        "今天怎么安排运动会",
        "今天怎么安排健康科技产品会议",
        "今天怎么安排健康类产品发布会",
        "今天怎么安排运动员会议",
        "今天怎么安排运动服品牌发布会",
        "今天怎么安排休息室会议",
        "今天怎么安排康复产业论坛",
        "今天怎么安排睡眠产品会议",
        "今天怎么安排营养行业会议",
        "今天怎么安排健康管理行业会议",
        "今天怎么安排运动健康产品会议",
        "今天怎么安排康复医学产业论坛",
    ],
)
def test_runtime_agenda_disambiguates_non_health_compound_words(query):
    from app.services.inline_cards import _runtime_agenda_presentation_mode

    assert _runtime_agenda_presentation_mode(query) is None


def test_inline_cards_runtime_agenda_does_not_trigger_for_record_intent(monkeypatch):
    from app.services import inline_cards

    monkeypatch.setattr(
        inline_cards.agenda_service,
        "runtime_range_view",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call runtime")),
    )

    cards = inline_cards.build_cards(db=None, user_id=3, query="记录我刚喝了200ml水")

    assert all(card["type"] != "runtime_agenda" for card in cards)


def test_inline_cards_builds_confirmable_diet_draft_card():
    from app.services import inline_cards

    cards = inline_cards.build_cards(
        db=None,
        user_id=3,
        query="记录午餐吃了煎牛肉能量碗和姜黄鲜柠维C茶，770 kcal，蛋白30g，碳水70g，脂肪17g",
    )

    assert cards[0]["type"] == "diet_draft"
    assert cards[0]["data"] == {
        "meal_type": "lunch",
        "food_items": "煎牛肉能量碗和姜黄鲜柠维C茶",
        "calories": 770,
        "protein": 30,
        "carbs": 70,
        "fat": 17,
        "confidence": 0.82,
        "source": "chat",
        "suggestions": [
            "确认后更新今日饮食进度",
            "如估算不准，可去饮食页修正",
        ],
        "next_meal_detail": {
            "title": "下一餐建议",
            "summary": "下一餐优先补足蛋白和蔬菜,避免连续高油高糖。",
            "context": "基于本餐营养估算和今日饮食闭环生成,确认记录后会纳入今日进度。",
            "options": [
                "鱼/鸡胸/瘦牛肉 150-200g + 熟蔬菜 + 半份主食",
                "豆腐/鸡蛋 + 希腊酸奶或牛奶,补足蛋白缺口",
            ],
            "rationale": [
                "这餐已有明确热量和蛋白估算,下一餐重点是补齐蛋白和纤维。",
                "餐后轻走 10 分钟作为低打扰代谢行动。",
            ],
            "continue_prompt": "基于这餐和今天目标,帮我安排下一餐",
        },
        "post_meal_walk": {"recommended": True, "minutes": 10},
        "boundary": "营养为估算值,确认后写入今日饮食记录。",
    }
    assert _without_kernel_action_policy(cards[0]["actions"][0]) == {
        "id": "confirm-diet-draft",
        "label": "确认记录",
        "action": "diet_record.create",
        "endpoint": "/diet/records",
        "requires_manual_confirm": True,
        "payload": {
            "record": {
                "meal_type": "lunch",
                "food_items": "煎牛肉能量碗和姜黄鲜柠维C茶",
                "calories": 770,
                "protein": 30,
                "carbs": 70,
                "fat": 17,
                "notes": "来源: chat; 置信度 82%",
            },
        },
        "style": "primary",
        "confirmation": {
            "title": "记录这顿午餐？",
            "detail": "确认后会写入今天的饮食记录，可稍后在饮食页修正。",
            "confirm_label": "确认记录",
            "cancel_label": "再看看",
        },
        "optimistic": True,
    }
    assert _without_kernel_action_policy(cards[0]["actions"][1]) == {
        "id": "expand-next-meal",
        "label": "看下一餐建议",
        "action": "ui.inline.expand",
        "payload": {
            "target": "diet_draft",
            "patch": {
                "expanded_sections": ["next_meal"],
                "next_meal_detail": cards[0]["data"]["next_meal_detail"],
            },
        },
        "style": "secondary",
    }
    assert _without_kernel_action_policy(cards[0]["actions"][2]) == {
        "id": "open-diet-edit",
        "label": "去饮食页修正",
        "action": "route.open",
        "payload": {
            "route": "/diet?draft=diet&meal_type=lunch&food_items=%E7%85%8E%E7%89%9B%E8%82%89%E8%83%BD%E9%87%8F%E7%A2%97%E5%92%8C%E5%A7%9C%E9%BB%84%E9%B2%9C%E6%9F%A0%E7%BB%B4C%E8%8C%B6&calories=770&protein=30&carbs=70&fat=17"
        },
        "style": "secondary",
    }


def test_inline_cards_diet_draft_does_not_trigger_for_water_record():
    from app.services import inline_cards

    cards = inline_cards.build_cards(db=None, user_id=3, query="记录我刚喝了200ml水")

    assert all(card["type"] != "diet_draft" for card in cards)


def test_inline_cards_diet_draft_does_not_trigger_for_medication_intake():
    from app.services import inline_cards

    for query in [
        "记录刚吃了替普瑞酮",
        "记录刚服用了替普瑞酮胶囊（施维舒）",
        "记录刚吃了奥美拉唑20mg",
    ]:
        cards = inline_cards.build_cards(db=None, user_id=3, query=query)

        assert all(card["type"] != "diet_draft" for card in cards)


def test_inline_cards_builds_medication_draft_for_medication_intake():
    from app.services import inline_cards

    cards = inline_cards.build_cards(db=None, user_id=3, query="记录刚吃了替普瑞酮胶囊（施维舒）")

    assert cards[0]["type"] == "medication_draft"
    assert cards[0]["data"]["medication_name"] == "替普瑞酮胶囊（施维舒）"
    assert cards[0]["data"]["source"] == "chat"
    assert cards[0]["data"]["confidence"] == 0.9
    assert cards[0]["data"]["presentation_state"] == "suggestion"
    assert "尚未写入" in cards[0]["data"]["boundary"]
    assert _without_kernel_action_policy(cards[0]["actions"]) == [
        {
            "id": "open-medication-draft",
            "label": "去用药页记录",
            "action": "route.open",
            "payload": {
                "route": "/medications?draft=medication&name=%E6%9B%BF%E6%99%AE%E7%91%9E%E9%85%AE%E8%83%B6%E5%9B%8A%EF%BC%88%E6%96%BD%E7%BB%B4%E8%88%92%EF%BC%89"
            },
            "style": "primary",
        },
        {
            "id": "ask-medication-draft",
            "label": "问小巴",
            "action": "route.open",
            "payload": {
                "route": "/chat?prompt=%E8%AF%B7%E5%B8%AE%E6%88%91%E6%A0%B8%E5%AF%B9%E6%9B%BF%E6%99%AE%E7%91%9E%E9%85%AE%E8%83%B6%E5%9B%8A%EF%BC%88%E6%96%BD%E7%BB%B4%E8%88%92%EF%BC%89%E7%9A%84%E7%94%A8%E8%8D%AF%E8%AE%B0%E5%BD%95%EF%BC%8C%E4%B8%8D%E8%A6%81%E5%BB%BA%E8%AE%AE%E6%88%91%E8%87%AA%E8%A1%8C%E5%81%9C%E8%8D%AF%E3%80%81%E6%8D%A2%E8%8D%AF%E6%88%96%E6%94%B9%E5%89%82%E9%87%8F%E3%80%82"
            },
            "style": "secondary",
        },
    ]


def test_inline_cards_medication_draft_route_carries_dose_when_present():
    from app.services import inline_cards

    cards = inline_cards.build_cards(db=None, user_id=3, query="记录刚吃了奥美拉唑20mg")

    assert cards[0]["type"] == "medication_draft"
    assert cards[0]["data"]["medication_name"] == "奥美拉唑"
    assert cards[0]["data"]["dose"] == "20mg"
    assert cards[0]["actions"][0]["payload"]["route"] == (
        "/medications?draft=medication&name=%E5%A5%A5%E7%BE%8E%E6%8B%89%E5%94%91&dose=20mg"
    )


def test_inline_cards_builds_supplement_draft_for_supplement_intake():
    from app.services import inline_cards

    cards = inline_cards.build_cards(db=None, user_id=3, query="记录刚吃了鱼油")

    assert cards[0]["type"] == "supplement_draft"
    assert cards[0]["data"]["supplement_name"] == "鱼油"
    assert cards[0]["data"]["source"] == "chat"
    assert cards[0]["data"]["confidence"] == 0.82
    assert cards[0]["data"]["presentation_state"] == "suggestion"
    assert "尚未写入" in cards[0]["data"]["boundary"]
    assert _without_kernel_action_policy(cards[0]["actions"]) == [
        {
            "id": "open-supplement-draft",
            "label": "去补剂页记录",
            "action": "route.open",
            "payload": {
                "route": "/supplement-inventory?draft=supplement&name=%E9%B1%BC%E6%B2%B9"
            },
            "style": "primary",
        },
        {
            "id": "ask-supplement-draft",
            "label": "问小巴",
            "action": "route.open",
            "payload": {
                "route": "/chat?prompt=%E8%AF%B7%E5%B8%AE%E6%88%91%E6%A0%B8%E5%AF%B9%E9%B1%BC%E6%B2%B9%E7%9A%84%E8%A1%A5%E5%89%82%E8%AE%B0%E5%BD%95%EF%BC%8C%E6%B3%A8%E6%84%8F%E5%89%82%E9%87%8F%E3%80%81%E6%9C%8D%E7%94%A8%E6%97%B6%E9%97%B4%E5%92%8C%E4%B8%8E%E8%8D%AF%E7%89%A9%2F%E7%96%BE%E7%97%85%E7%9A%84%E7%9B%B8%E4%BA%92%E4%BD%9C%E7%94%A8%E3%80%82"
            },
            "style": "secondary",
        },
    ]


def test_inline_cards_diet_management_does_not_create_diet_draft():
    from app.services import inline_cards

    cards = inline_cards.build_cards(db=None, user_id=3, query="删除这一餐")

    assert all(card["type"] != "diet_draft" for card in cards)


def test_inline_cards_builds_operating_review_card(monkeypatch):
    from app.services import inline_cards

    calls = {}

    def fake_review(db, *, user_id, window_days, end_date=None):
        calls["db"] = db
        calls["user_id"] = user_id
        calls["window_days"] = window_days
        calls["end_date"] = end_date
        return {
            "window_days": window_days,
            "start_date": "2026-06-22",
            "end_date": "2026-06-28",
            "execution": {
                "total_events": 4,
                "completed_events": 3,
                "completion_rate": 0.75,
                "by_status": {"completed": 3, "skipped": 1},
                "by_domain": {"movement": 2, "sleep": 2},
            },
            "metrics": {
                "waist_cm": {
                    "status": "present",
                    "count": 2,
                    "current": 94.8,
                    "delta": -1.2,
                    "current_date": "2026-06-28",
                },
            },
            "prediction_backtest": {
                "version": "prediction_backtest_v1",
                "status": "ready",
                "reason": "has_matched_prediction_results",
                "candidate_count": 1,
                "ready_candidate_count": 1,
                "window_days": window_days,
                "minimum_window_days": 7,
                "completed_action_count": 3,
                "eligible_metrics": ["waist_cm"],
                "requirements": [],
                "summary": {"met": 1, "not_met": 0, "inconclusive": 0},
                "confidence_summary": {"high": 0, "medium": 1, "low": 0},
                "results": [
                    {
                        "prediction_id": "pred-waist-7d",
                        "action_title": "累计 35-45 分钟中等强度活动",
                        "metric": "waist_cm",
                        "horizon_days": 7,
                        "expected_signal": {"direction": "down", "expected_delta": -0.5},
                        "actual_result": {"current": 94.8, "current_date": "2026-06-28"},
                        "observed_delta": -1.2,
                        "verdict": "met",
                        "confidence_after": "medium",
                        "boundary": "观察性回测, 不证明单个行动造成指标变化。",
                    }
                ],
                "boundary": "预测回测只比较预期信号与窗口内实际变化, 属观察性复盘, 不证明单个行动造成指标变化。",
            },
            "causal_memory": {
                "notes": [{"metric": "hrv", "text": "晚餐提前之后 HRV 改善(相关非因果)"}],
                "claim_boundary": "事件先于指标变化的时序相关,非证明因果;不替代医学结论。",
            },
        }

    monkeypatch.setattr(inline_cards, "build_health_operating_review", fake_review, raising=False)

    cards = inline_cards.build_cards(db="db", user_id=3, query="帮我做一次预测回测和近期复盘")

    assert calls == {"db": "db", "user_id": 3, "window_days": 7, "end_date": None}
    assert cards[0]["type"] == "operating_review"
    assert cards[0]["data"]["window_days"] == 7
    assert cards[0]["data"]["execution"]["completion_rate"] == 0.75
    assert cards[0]["data"]["prediction_backtest"]["summary"]["met"] == 1
    assert cards[0]["data"]["prediction_backtest"]["results"][0]["prediction_id"] == "pred-waist-7d"
    assert cards[0]["data"]["metrics"][0]["metric"] == "waist_cm"
    assert cards[0]["data"]["causal_memory"]["notes"][0]["text"] == "晚餐提前之后 HRV 改善(相关非因果)"
    assert _without_kernel_action_policy(cards[0]["actions"]) == [
        {
            "id": "open-operating-review",
            "label": "查看复盘详情",
            "action": "route.open",
            "payload": {"route": "/my-progress"},
            "style": "primary",
        }
    ]


def test_inline_cards_operating_review_does_not_trigger_for_record_intent(monkeypatch):
    from app.services import inline_cards

    monkeypatch.setattr(
        inline_cards,
        "build_health_operating_review",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call review")),
        raising=False,
    )

    cards = inline_cards.build_cards(db=None, user_id=3, query="记录我刚做完今天复盘")

    assert all(card["type"] != "operating_review" for card in cards)


def test_inline_cards_builds_hrv_metric_chart_card(monkeypatch):
    from app.services import inline_cards

    calls = {}

    def fake_metric_chart(db, *, user_id, query):
        calls["db"] = db
        calls["user_id"] = user_id
        calls["query"] = query
        return {
            "metric": "hrv",
            "title": "最近半年 HRV",
            "unit": "ms",
            "start_date": "2025-12-29",
            "end_date": "2026-06-30",
            "coverage": {"days_with_data": 181, "days_in_window": 184},
            "latest": {"date": "2026-06-30", "value": 56.0, "source": "apple-watch"},
            "summary": {
                "avg": 57.3,
                "last_7d_avg": 48.8,
                "last_30d_avg": 50.9,
                "prev_30d_avg": 57.5,
                "last_30_vs_prev_30_delta": -6.6,
            },
            "series": [
                {"date": "2026-06-24", "value": 52.0, "rolling_7d": 54.0, "source": "garmin"},
                {"date": "2026-06-25", "value": 49.0, "rolling_7d": 53.0, "source": "garmin"},
                {"date": "2026-06-30", "value": 56.0, "rolling_7d": 48.8, "source": "apple-watch"},
            ],
            "boundary": "HRV 趋势仅用于健康管理参考, 不替代诊断或治疗。",
        }

    monkeypatch.setattr(inline_cards, "build_metric_chart", fake_metric_chart, raising=False)

    cards = inline_cards.build_cards(db="db", user_id=3, query="绘制最近半年的 HRV 曲线")

    assert calls == {"db": "db", "user_id": 3, "query": "绘制最近半年的 HRV 曲线"}
    assert cards[0]["type"] == "metric_chart"
    assert cards[0]["data"]["metric"] == "hrv"
    assert cards[0]["data"]["coverage"] == {"days_with_data": 181, "days_in_window": 184}
    assert cards[0]["data"]["latest"] == {
        "date": "2026-06-30",
        "value": 56.0,
        "source": "apple-watch",
    }
    assert _without_kernel_action_policy(cards[0]["actions"]) == [
        {
            "id": "open-hrv-history",
            "label": "查看HRV历史",
            "action": "route.open",
            "payload": {"route": "/indicator-history?type=hrv"},
            "style": "secondary",
        }
    ]


def test_inline_cards_metric_chart_uses_metric_specific_history_action(monkeypatch):
    from app.services import inline_cards

    def fake_metric_chart(db, *, user_id, query):
        return {
            "metric": "sleep_score",
            "label": "睡眠评分",
            "title": "最近7天 睡眠评分",
            "unit": "分",
            "coverage": {"days_with_data": 3, "days_in_window": 8},
            "latest": {"date": "2026-06-30", "value": 86.0, "source": "garmin"},
            "summary": {},
            "series": [
                {"date": "2026-06-28", "value": 72.0, "source": "garmin"},
                {"date": "2026-06-29", "value": 81.0, "source": "garmin"},
                {"date": "2026-06-30", "value": 86.0, "source": "garmin"},
            ],
        }

    monkeypatch.setattr(inline_cards, "build_metric_chart", fake_metric_chart, raising=False)

    cards = inline_cards.build_cards(db="db", user_id=3, query="画最近7天睡眠评分趋势")

    assert _without_kernel_action_policy(cards[0]["actions"]) == [
        {
            "id": "open-sleep_score-history",
            "label": "查看睡眠评分历史",
            "action": "route.open",
            "payload": {"route": "/indicator-history?type=sleep_score"},
            "style": "secondary",
        }
    ]
