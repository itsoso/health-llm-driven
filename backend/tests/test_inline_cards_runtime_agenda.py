"""Chat inline runtime-agenda card contract."""


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
    assert cards[0]["data"]["horizon_days"] == 7
    assert cards[0]["data"]["next_action"]["title"] == "晚餐后步行 15 分钟"
    assert cards[0]["data"]["next_action"]["replan_reason"] == "today_smart_rank"
    assert cards[0]["data"]["next_action"]["verification_metrics"] == [
        "post_meal_walk_completed",
        "waist_cm",
        "hrv",
    ]
    assert cards[0]["actions"] == [
        {
            "id": "open-runtime-agenda",
            "label": "查看7天计划",
            "action": "route.open",
            "payload": {"route": "/agenda"},
            "style": "primary",
        }
    ]


def test_inline_cards_runtime_agenda_does_not_trigger_for_record_intent(monkeypatch):
    from app.services import inline_cards

    monkeypatch.setattr(
        inline_cards.agenda_service,
        "runtime_range_view",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call runtime")),
    )

    cards = inline_cards.build_cards(db=None, user_id=3, query="记录我刚喝了200ml水")

    assert all(card["type"] != "runtime_agenda" for card in cards)


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
    assert cards[0]["actions"] == [
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
    assert cards[0]["actions"] == [
        {
            "id": "open-hrv-history",
            "label": "查看HRV历史",
            "action": "route.open",
            "payload": {"route": "/indicator-history?type=hrv"},
            "style": "secondary",
        }
    ]
