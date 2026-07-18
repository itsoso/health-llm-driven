"""Watch voice fast-record auto-confirm must fail closed.

Only low-risk, explicit record types may bypass the two-turn confirmation gate.
Medication, dose/adherence, financial, and unknown record kinds must keep the
manual confirmation path.
"""
import json

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.agent_executor import _auto_confirm_fast_record_args


def _as_json(args: dict) -> str:
    return json.dumps(args, ensure_ascii=False)


@pytest.fixture(autouse=True)
def _declare_explicit_turn_for_raw_watch_record_contracts(monkeypatch):
    original = AgentExecutor._execute_tool

    async def with_explicit_test_turn(self, tool_name, args_raw, user_token):
        self._current_user_id = self._current_user_id or 1
        if not getattr(self, "_current_turn_user_message", ""):
            self._current_turn_user_message = "记录俯卧撑20次"
        return await original(self, tool_name, args_raw, user_token)

    monkeypatch.setattr(AgentExecutor, "_execute_tool", with_explicit_test_turn)


def test_fast_record_auto_confirms_allowed_watch_record_types():
    for record_type in ("water", "weight", "bp", "blood_pressure", "diet", "exercise", "supplement"):
        out = _auto_confirm_fast_record_args(
            "health_record",
            {"record_type": record_type, "data": {"source": "apple_watch"}},
        )
        assert out["confirmed"] is True
        assert out["data"]["confirmed"] is True
        if record_type == "bp":
            assert out["record_type"] == "blood_pressure"


def test_fast_record_auto_confirms_pushup_exercise():
    out = _auto_confirm_fast_record_args(
        "health_record",
        {
            "record_type": "exercise",
            "data": {"exercise_type": "俯卧撑", "reps": 20, "sets": 2},
        },
    )

    assert out["confirmed"] is True
    assert out["data"]["confirmed"] is True


def test_fast_record_auto_confirms_json_string_for_allowed_types():
    out = _auto_confirm_fast_record_args(
        "health_record",
        _as_json({"record_type": "water", "data": {"amount": 250}}),
    )
    parsed = json.loads(out)
    assert parsed["confirmed"] is True
    assert parsed["data"]["confirmed"] is True


def test_fast_record_never_auto_confirms_medication_dose_or_financial_types():
    for record_type in ("medication", "medicine", "drug", "dose", "dosage", "adherence", "financial"):
        original = {"record_type": record_type, "confirmed": True, "data": {"value": "x", "confirmed": True}}
        out = _auto_confirm_fast_record_args("health_record", original)
        assert out["_fast_record_requires_confirmation"] is True
        assert "confirmed" not in out
        assert "confirmed" not in out["data"]


def test_fast_record_strips_confirmed_inside_json_string_data_for_never_types():
    out_raw = _auto_confirm_fast_record_args(
        "health_record",
        _as_json({
            "record_type": "medication",
            "data": _as_json({"medication_name": "布洛芬", "confirmed": True}),
            "confirmed": True,
        }),
    )
    out = json.loads(out_raw)

    assert out["_fast_record_requires_confirmation"] is True
    assert "confirmed" not in out
    assert isinstance(out["data"], dict)
    assert "confirmed" not in out["data"]


def test_fast_record_unknown_type_keeps_manual_confirmation_gate():
    original = {"record_type": "unknown_metric", "data": {"value": 480}}

    out = _auto_confirm_fast_record_args("health_record", original)

    assert out["_fast_record_requires_confirmation"] is True
    assert "confirmed" not in out
    assert "confirmed" not in out["data"]


def test_fast_record_symptom_keeps_manual_confirmation_gate():
    # watch 语音通道(source=apple_watch):症状保留确认前置(转写失真+表盘回显易漏)。
    # 打字通道的症状免确认见 test_agent_executor_fast_routing.py。
    original = {
        "record_type": "symptom",
        "data": {"body_part": "head", "description": "头痛", "source": "apple_watch"},
    }

    out = _auto_confirm_fast_record_args("health_record", original)

    assert out["_fast_record_requires_confirmation"] is True
    assert "confirmed" not in out
    assert "confirmed" not in out["data"]


def test_fast_record_looks_inside_data_for_record_type_before_confirming():
    allowed = {"data": {"record_type": "diet", "food_items": "鸡蛋"}}
    denied = {"data": {"record_type": "dose", "name": "维生素D"}}

    allowed_out = _auto_confirm_fast_record_args("health_record", allowed)
    denied_out = _auto_confirm_fast_record_args("health_record", denied)

    assert allowed_out["confirmed"] is True
    assert allowed_out["data"]["confirmed"] is True
    assert denied_out["_fast_record_requires_confirmation"] is True
    assert "confirmed" not in denied_out
    assert "confirmed" not in denied_out["data"]


@pytest.mark.asyncio
async def test_medication_execution_requires_manual_confirmation(db):
    executor = AgentExecutor(db)

    async def _must_not_fetch(*_args, **_kwargs):
        raise AssertionError("unconfirmed medication must not reach API lookup/write")

    executor._api_get_json = _must_not_fetch
    args = _auto_confirm_fast_record_args(
        "health_record",
        {"record_type": "medication", "data": {"medication_name": "布洛芬"}},
    )
    result = await executor._exec_health_record(
        "http://x",
        {},
        args,
    )

    assert result.startswith("[NEEDS_CONFIRMATION]")
    assert "用药" in result


@pytest.mark.asyncio
async def test_symptom_execution_requires_manual_confirmation(db):
    executor = AgentExecutor(db)

    async def _must_not_post(*_args, **_kwargs):
        raise AssertionError("unconfirmed symptom must not reach API write")

    executor._api_post = _must_not_post
    # 语音通道(source=apple_watch)的症状:端到端仍确认前置,不落库。
    # (watch 真实路径是直连 /watch 端点不经 executor;此契约钉 agent 路径的语音语义。)
    args = _auto_confirm_fast_record_args(
        "health_record",
        {
            "record_type": "symptom",
            "data": {"body_part": "head", "description": "头痛", "source": "apple_watch"},
        },
    )
    result = await executor._exec_health_record(
        "http://x",
        {},
        args,
    )

    assert result.startswith("[NEEDS_CONFIRMATION]")
    assert "症状" in result


@pytest.mark.asyncio
async def test_pushup_exercise_execution_still_fast_records(db):
    executor = AgentExecutor(db)
    captured = {}

    async def _fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return json.dumps({"message": "已记录运动：俯卧撑 20 次"}, ensure_ascii=False)

    executor._api_post = _fake_post
    result = await executor._exec_health_record(
        "http://x",
        {},
        {
            "record_type": "exercise",
            "data": {"exercise_type": "俯卧撑", "reps": 20, "sets": 2},
        },
    )

    assert captured["url"] == "http://x/daily-health/exercise"
    assert captured["payload"]["exercise_type"] == "俯卧撑"
    assert "已记录运动" in result


@pytest.mark.asyncio
async def test_pushup_exercise_type_alias_passes_validator_and_fast_records(db):
    executor = AgentExecutor(db)
    captured = {}

    async def _fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return json.dumps({"message": "已记录运动：俯卧撑 20 次"}, ensure_ascii=False)

    executor._api_post = _fake_post
    result = await executor._execute_tool(
        "health_record",
        _as_json({"record_type": "exercise", "data": {"type": "俯卧撑", "reps": 20}}),
        user_token=None,
    )

    assert captured["url"] == "http://localhost:8000/api/v1/daily-health/exercise"
    assert captured["payload"]["exercise_type"] == "俯卧撑"
    assert "已记录运动" in result
