"""Inline cards composition telemetry — dropped builders must be fail-loud observable.

历史事故类型: builder 抛异常被吞成"当天没数据", 卡片静默消失。
契约: 返回 shape 不变 (其他卡片照常返回), 但 >=1 builder RAISED 时必须有
WARNING 日志带 builder 名 + 异常 repr; 全部正常 (含 gate 未命中) 时无 WARNING。
"""
import logging


def _fake_runtime_range_view(db, user_id, days=7, max_items_per_day=3):
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


def test_build_cards_warns_and_keeps_other_cards_when_builder_raises(monkeypatch, caplog):
    from app.services import inline_cards

    def boom(db, *, user_id, query):
        raise RuntimeError("chart datasource down")

    # metric_chart builder 是无内部 try/except 的直通调用 → 替换其依赖即让 builder 真抛
    monkeypatch.setattr(inline_cards, "build_metric_chart", boom, raising=False)
    monkeypatch.setattr(
        inline_cards.agenda_service, "runtime_range_view", _fake_runtime_range_view
    )

    with caplog.at_level(logging.DEBUG, logger="app.services.inline_cards"):
        cards = inline_cards.build_cards(
            db=None, user_id=3, query="接下来7天我应该怎么安排健康行动？"
        )

    # 返回 shape 不变: 其他卡片照常返回, 坏 builder 只是缺席
    assert [c["type"] for c in cards] == ["runtime_agenda"]

    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "[inline_cards]" in r.getMessage()
    ]
    assert len(warnings) == 1
    msg = warnings[0].getMessage()
    # dropped 携带 builder 名 + 异常 repr
    assert "metric_chart" in msg
    assert "RuntimeError" in msg
    assert "chart datasource down" in msg
    # 组装快照: 被考虑与实际发出的 builder 都可观测
    assert "runtime_agenda" in msg
    # 隐私: 不记 query 原文
    assert "接下来7天" not in msg


def test_build_cards_no_warning_when_all_builders_fine(monkeypatch, caplog):
    from app.services import inline_cards

    # metric_chart 正常 gate 未命中 (返回 None) —— 不是 drop
    monkeypatch.setattr(
        inline_cards, "build_metric_chart",
        lambda db, *, user_id, query: None,
        raising=False,
    )
    monkeypatch.setattr(
        inline_cards.agenda_service, "runtime_range_view", _fake_runtime_range_view
    )

    with caplog.at_level(logging.DEBUG, logger="app.services.inline_cards"):
        cards = inline_cards.build_cards(
            db=None, user_id=3, query="接下来7天我应该怎么安排健康行动？"
        )

    assert cards and cards[0]["type"] == "runtime_agenda"
    assert not [
        r for r in caplog.records
        if r.levelno >= logging.WARNING and "[inline_cards]" in r.getMessage()
    ]
    # gate 未命中走 DEBUG 组装快照 (正常, 非 drop)
    debug_msgs = [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.DEBUG and "composition" in r.getMessage()
    ]
    assert len(debug_msgs) == 1
    assert "metric_chart" in debug_msgs[0]
    assert "gate_miss" in debug_msgs[0]
    assert "emitted=['runtime_agenda'" in debug_msgs[0]
