"""Frozen, owned SpO2 daily facts; synthetic data, no clinical inference."""
from dataclasses import replace
from datetime import date, datetime

import pytest

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.types import (
    AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot,
)
from app.services.agent_longitudinal_read import read_longitudinal_health_query
from app.services.agent_query_window import parse_query_window

REQUEST = "分析最近一周的睡眠血氧情况，给出你的建议"


def snapshot(text=REQUEST):
    envelope = AgentEnvelope(user_id=17, channel="typed", text=text)
    context = ExecutionContext(
        current_time=datetime.fromisoformat("2031-04-03T17:10:00+00:00"),
        timezone="Asia/Shanghai", user_id=17, channel="typed",
    )
    return TurnSnapshot(envelope, context, build_intent_frame(envelope, context))


def window():
    return parse_query_window({
        "start_date": "2031-03-29", "end_date": "2031-04-04", "timezone": "Asia/Shanghai",
    })


def decision(text=REQUEST, **args):
    return decide_tool_capability(snapshot(text), ToolExecutionRequest(
        tool_name="health_query", arguments={"dimension": "spo2", **args},
        source="structured_or_recovered",
    ))


@pytest.mark.parametrize("text", [REQUEST, "分析最近一周的睡眠和血氧，给出你的建议"])
def test_sleep_spo2_request_binds_both_frozen_domains(text):
    scope = resolve_owned_read_scope(snapshot(text))
    assert scope is not None
    assert {q["dimension"] for q in scope.queries} == {"sleep", "spo2"}
    for dimension in ("sleep", "spo2"):
        result = decision(text, dimension=dimension, days=7)
        assert result.action == "allow", result.reason
        assert result.normalized_args == {"dimension": dimension, "days": 7, **window().as_dict()}


@pytest.mark.parametrize("text", [
    "分析我朋友最近一周的睡眠血氧情况，给出你的建议",
    "分析最近一周小王的睡眠血氧情况，给出你的建议",
    "不要分析最近一周的睡眠血氧情况，给出你的建议",
    "假如分析最近一周的睡眠血氧情况，给出你的建议",
    "分析最近一周的睡眠血氧情况，仅限出差之后，给出你的建议",
    "分析最近一周的睡眠血氧情况，给出你的建议并删除记录",
    "分析最近一周的睡眠情况，给出你的建议",
    "分析这个例句：“分析最近一周的睡眠血氧情况，给出你的建议”",
    "分析最近一周的睡眠血氧情况，给出你的建议，只看凌晨",
    "分析最近一周的睡眠血氧情况，给出你的建议，别读取记录",
    "分析最近一周的睡眠血氧情况，给出你的建议，停止",
])
def test_spo2_scope_does_not_erase_owner_speech_act_or_restrictions(text):
    assert decision(text).action == "block"


@pytest.mark.parametrize("args", [
    {"user_id": 99}, {"owner_id": 99}, {"tenant_id": 99},
    {"start_date": "2020-01-01", "end_date": "2020-01-31"},
    {"timezone": "UTC"}, {"days": 30},
])
def test_model_arguments_cannot_expand_spo2_scope(args):
    assert decision(**args).action == "block"


def test_context_owner_mismatch_cannot_bind_spo2():
    s = snapshot()
    assert resolve_owned_read_scope(replace(s, context=replace(s.context, user_id=18))) is None


def test_batch_uses_same_owned_window_and_rejects_extra_domains():
    for dimensions, expected in [(('sleep', 'spo2'), 'allow'), (('sleep', 'spo2', 'diet'), 'block')]:
        result = decide_tool_capability(snapshot(), ToolExecutionRequest(
            tool_name="health_query_batch", arguments={"queries": [
                {"dimension": d, "days": 7} for d in dimensions
            ]}, source="structured_or_recovered",
        ))
        assert result.action == expected, result.reason
        if expected == 'allow':
            assert all(q == {"dimension": q["dimension"], "days": 7, **window().as_dict()}
                       for q in result.normalized_args["queries"])


def test_exact_date_spo2_and_sleep_do_not_authorize_other_domains():
    text = "查询2031-04-02的睡眠和血氧，给出你的建议"
    result = decision(text)
    assert result.action == "allow", result.reason
    assert result.normalized_args == {
        "dimension": "spo2", "start_date": "2031-04-02", "end_date": "2031-04-02",
        "timezone": "Asia/Shanghai",
    }
    assert decision(text, dimension="diet").action == "block"


@pytest.fixture
def owners(db):
    from app.models.user import User
    users = [User(username=f"spo2-scope-{n}", email=f"spo2-scope-{n}@example.test",
                  name="Synthetic", hashed_password="fixture") for n in ("a", "b")]
    db.add_all(users)
    db.flush()
    return users[0].id, users[1].id


def test_spo2_projection_preserves_owner_window_source_and_precision(db, owners):
    from app.models.daily_health import GarminData
    owner, other = owners
    db.add_all([
        GarminData(user_id=owner, record_date=date(2031, 3, 29), data_source="ringconn",
                   spo2_avg=96.12345, spo2_min=93, spo2_max=99),
        GarminData(user_id=owner, record_date=date(2031, 3, 29), data_source="garmin",
                   spo2_avg=60, spo2_min=50, spo2_max=70),
        GarminData(user_id=owner, record_date=date(2031, 4, 4), data_source="apple-watch",
                   spo2_avg=97, spo2_min=94, spo2_max=99),
        GarminData(user_id=other, record_date=date(2031, 3, 29), data_source="ringconn", spo2_avg=51),
        GarminData(user_id=owner, record_date=date(2031, 3, 28), data_source="ringconn", spo2_avg=52),
        GarminData(user_id=owner, record_date=date(2031, 4, 5), data_source="ringconn", spo2_avg=53),
    ])
    db.flush()
    result = read_longitudinal_health_query(db, owner, "spo2", window())
    assert result["window"] == window().as_dict()
    assert result["availability"] == "partial"
    assert result["date_attribution"] == "record_date"
    assert result["source_scope"] == "owned_daily_spo2_summaries_and_samples"
    assert len(result["records"]) == 2
    first, last = result["records"]
    assert first["record_date"] == "2031-03-29" and last["record_date"] == "2031-04-04"
    assert first["daily_metrics"]["spo2_avg"] == 96.12345
    assert first["daily_sources"] == {key: "ringconn" for key in ("spo2_avg", "spo2_min", "spo2_max")}
    assert "daily_summary_not_sleep_episode" in result["limitations"]
    assert "sample_coverage_unknown" in result["limitations"]
    assert not {"odi", "severity", "apnea_risk", "pattern_flags"} & result.keys()
    assert all(not {"odi", "severity", "apnea_risk"} & row.keys() for row in result["records"])


@pytest.mark.parametrize("source", ["garmin", "garmin-app", "ringconn"])
def test_sleep_only_or_excluded_spo2_is_not_normal_or_zero(db, owners, source):
    from app.models.daily_health import GarminData
    owner, _ = owners
    db.add(GarminData(
        user_id=owner, record_date=date(2031, 4, 1), data_source=source,
        total_sleep_duration=480, spo2_avg=88 if source != "ringconn" else None,
    ))
    db.flush()
    result = read_longitudinal_health_query(db, owner, "spo2", window())
    assert result["records"] == []
    assert result["availability"] == "no_data"


def test_partial_metrics_keep_nulls_and_each_metric_source(db, owners):
    from app.models.daily_health import GarminData
    owner, _ = owners
    db.add_all([
        GarminData(user_id=owner, record_date=date(2031, 4, 1), data_source="ringconn",
                   spo2_avg=97, spo2_min=94),
        GarminData(user_id=owner, record_date=date(2031, 4, 1), data_source="apple-watch",
                   spo2_avg=96, spo2_min=95),
    ])
    db.flush()
    result = read_longitudinal_health_query(db, owner, "spo2", window())
    row = result["records"][0]
    assert row["daily_metrics"] == {"spo2_avg": 96, "spo2_min": 94, "spo2_max": None}
    assert row["daily_sources"] == {"spo2_avg": "apple-watch", "spo2_min": "ringconn"}
    assert result["availability"] == "partial"


@pytest.mark.parametrize("owner", [None, True, 0, -1])
def test_reader_requires_authenticated_owner(db, owner):
    with pytest.raises(ValueError, match="owner_required"):
        read_longitudinal_health_query(db, owner, "spo2", window())


def test_spo2_database_failure_propagates():
    class BrokenDB:
        def query(self, *_args):
            raise RuntimeError("synthetic database failure")
    with pytest.raises(RuntimeError, match="synthetic database failure"):
        read_longitudinal_health_query(BrokenDB(), 17, "spo2", window())


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [False, True])
async def test_executor_dispatch_uses_frozen_daily_facts_not_latest_night(db, owners, monkeypatch, batch):
    import json
    from app.models.daily_health import GarminData
    from app.services.agent_executor import AgentExecutor
    from app.services import agent_read_tools_analysis

    owner, _ = owners
    db.add_all([
        GarminData(user_id=owner, record_date=date(2031, 4, 1), data_source="ringconn",
                   spo2_avg=97, total_sleep_duration=480),
        GarminData(user_id=owner, record_date=date(2031, 4, 5), data_source="ringconn",
                   spo2_avg=80, total_sleep_duration=120),
    ])
    db.flush()
    executor = AgentExecutor(db)
    executor._current_user_id = owner
    executor._current_turn_user_message = REQUEST
    original = snapshot()
    frozen = replace(original, envelope=replace(original.envelope, user_id=owner),
                     context=replace(original.context, user_id=owner))
    monkeypatch.setattr(executor, "_ensure_agent_kernel_turn", lambda **_kw: frozen)

    def unexpected_latest_or_http(*_a, **_kw):
        pytest.fail("Bounded daily query must not fall back to latest-night or HTTP")

    monkeypatch.setattr(agent_read_tools_analysis, "read_latest_night_spo2", unexpected_latest_or_http)
    monkeypatch.setattr(executor, "_api_get", unexpected_latest_or_http)
    name = "health_query_batch" if batch else "health_query"
    proposals = ({"queries": [{"dimension": d, "days": 7} for d in ("sleep", "spo2")]}
                 if batch else {"dimension": "spo2", "days": 7})
    permitted = decide_tool_capability(frozen, ToolExecutionRequest(
        tool_name=name, arguments=proposals, source="structured_or_recovered"))
    assert permitted.action == "allow", permitted.reason
    dispatch = executor._exec_health_query_batch if batch else executor._exec_health_query
    result = json.loads(await dispatch("http://unused", {}, permitted.normalized_args))
    results = result["results"] if batch else [result]
    assert {item["dimension"] for item in results} == ({"sleep", "spo2"} if batch else {"spo2"})
    for item in results:
        assert item["window"] == window().as_dict()
        assert [row["record_date"] for row in item["records"]] == ["2031-04-01"]
    spo2 = next(item for item in results if item["dimension"] == "spo2")
    assert spo2["records"][0]["daily_metrics"]["spo2_avg"] == 97
    assert spo2["source_scope"] == "owned_daily_spo2_summaries_and_samples"
