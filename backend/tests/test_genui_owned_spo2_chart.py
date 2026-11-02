"""Charts project completed, scope-bound facts, without fresh data access."""
import copy
import json

import pytest

from app.services.agent_executor import _genui_readout_fences

ARGS = {"dimension": "spo2", "start_date": "2031-03-31", "end_date": "2031-04-04", "timezone": "Asia/Shanghai"}


def payload():
    return {"dimension": "spo2", "window": {k: v for k, v in ARGS.items() if k != "dimension"},
            "source_scope": "owned_daily_spo2_summaries_and_samples", "date_attribution": "record_date",
            "availability": "partial", "records": [
                {"record_date": "2031-04-01", "daily_metrics": {"spo2_avg": 96.12345},
                 "daily_sources": {"spo2_avg": "ringconn"}},
                {"record_date": "2031-04-04", "daily_metrics": {"spo2_avg": 97},
                 "daily_sources": {"spo2_avg": "apple-watch"}},
            ]}


def project(data=None, *, batch=False, chart_on=True, args=None):
    args = args or ARGS
    data = payload() if data is None else data
    calls = [("health_query_batch", {"queries": [args]}, json.dumps({"status": "success", "results": [data]}))] if batch else [("health_query", args, json.dumps(data))]
    return _genui_readout_fences(calls, table_on=False, diet_summary_on=False,
                               sleep_summary_on=False, medication_list_on=False, chart_on=chart_on)


@pytest.mark.parametrize("batch", [False, True])
def test_completed_spo2_read_renders_exact_window_with_gaps(batch):
    data = payload()
    original = copy.deepcopy(data)
    fences = project(data, batch=batch)
    assert len(fences) == 1
    card = json.loads(fences[0].split("\n")[1])
    assert card["component"] == "line_chart"
    assert card["x"] == ["2031-03-31", "2031-04-01", "2031-04-02", "2031-04-03", "2031-04-04"]
    assert card["series"] == [{"name": "日均血氧", "points": [None, 96.12, None, None, 97]}]
    assert "2031-03-31" in card["data_note"] and "2031-04-04" in card["data_note"]
    assert data == original


@pytest.mark.parametrize("case", ["outside", "duplicate", "window", "source", "nan", "bool", "over100", "failed", "no_data", "night", "missing_source"])
def test_untrusted_or_unusable_result_does_not_make_chart(case):
    data = payload()
    row = data["records"][0]
    if case == "outside": row["record_date"] = "2030-11-01"
    elif case == "duplicate": data["records"].append(copy.deepcopy(row))
    elif case == "window": data["window"]["start_date"] = "2030-11-01"
    elif case == "source": row["daily_sources"]["spo2_avg"] = "garmin"
    elif case == "nan": row["daily_metrics"]["spo2_avg"] = float("nan")
    elif case == "bool": row["daily_metrics"]["spo2_avg"] = True
    elif case == "over100": row["daily_metrics"]["spo2_avg"] = 101
    elif case == "failed": data["success"] = False
    elif case == "no_data": data["availability"] = "no_data"
    elif case == "night": data["date_attribution"] = "wake_date"
    elif case == "missing_source": row["daily_sources"] = {}
    assert project(data) == []


def test_cap_off_and_no_daily_averages_do_not_invent_chart():
    assert project(chart_on=False) == []
    data = payload()
    for row in data["records"]: row["daily_metrics"]["spo2_avg"] = None
    assert project(data) == []


@pytest.mark.parametrize("text, expected", [
    ("绘制本周血氧饱和度数据", True), ("画出本周血氧数据", True),
    ("查询本周血氧数据", False), ("不绘制本周血氧数据", False),
    ("不要画出本周血氧数据", False), ("假如绘制本周血氧数据", False),
    ("绘制本周血氧数据，取消", False),
])
def test_chart_intent_respects_active_speech_act(text, expected):
    from app.services.genui.owned_spo2_chart import requests_owned_chart
    from tests.test_agent_spo2_read_scope import snapshot
    assert requests_owned_chart(snapshot(text)) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("caps", [["genui-v1"], []])
async def test_real_stream_reads_only_owned_week_and_emits_chart_once(db, auth_user_and_headers, monkeypatch, caps, isolated_agent_protocol_transport):
    from datetime import date, datetime
    from app.models.daily_health import GarminData
    from app.services.agent_executor import AgentExecutor
    from tests.test_genui_table import _wire, _run, _tokens

    user, _ = auth_user_and_headers
    from app.models.user import User
    other = User(username="oxygen-other", email="oxygen-other@example.test", name="Synthetic", hashed_password="fixture")
    db.add(other)
    db.flush()
    db.add_all([
        GarminData(user_id=other.id, record_date=date(2031, 4, 1), data_source="ringconn", spo2_avg=51),
        GarminData(user_id=user.id, record_date=date(2031, 4, 1), data_source="ringconn", spo2_avg=96.12345),
        GarminData(user_id=user.id, record_date=date(2031, 4, 4), data_source="apple-watch", spo2_avg=97),
        GarminData(user_id=user.id, record_date=date(2031, 3, 30), data_source="ringconn", spo2_avg=55),
        GarminData(user_id=user.id, record_date=date(2031, 4, 5), data_source="ringconn", spo2_avg=56),
    ])
    db.flush()
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    from app.services.agent_kernel.context import build_turn_snapshot
    def frozen_snapshot(*args, **kwargs):
        kwargs["now_utc"] = datetime.fromisoformat("2031-04-03T17:10:00+00:00")
        return build_turn_snapshot(*args, **kwargs)
    monkeypatch.setattr("app.services.agent_executor.build_turn_snapshot", frozen_snapshot)
    rounds = []
    async def model(messages, round_tools):
        rounds.append(1)
        if len(rounds) == 1:
            yield {"type": "tool_calls", "tool_calls": [{"id": "spo2-week", "function": {
                "name": "health_query", "arguments": '{"dimension":"spo2","days":180}'}}]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "已按本周记录日期展示血氧日均值，缺失日期留空。"}
            yield {"type": "finish", "finish_reason": "stop"}
    monkeypatch.setattr(executor, "_call_llm_stream", model)
    events = await _run(executor, "绘制本周血氧饱和度数据", client_caps=caps, user_id=user.id)
    tokens = _tokens(events)
    tools = [e["data"] for e in events if e.get("event") == "tool_result"]
    assert tools and all(t["success"] for t in tools), events
    result = json.loads(tools[0]["result"])
    assert result["window"] == payload()["window"]
    assert [r["record_date"] for r in result["records"]] == ["2031-04-01", "2031-04-04"]
    assert tokens.count('"component":"line_chart"') == (1 if caps else 0), events
    assert "没有授权" not in tokens
    if caps:
        card = json.loads(tokens.split("```reva-ui\n")[1].split("\n```")[0])
        assert card["series"][0]["points"] == [None, 96.12, None, None, 97]
