"""Fast-model routing for simple 阿衡 turns (/api/v1/agent/stream).

Simple record / simple query turns route to the FASTEST reliable-tool-calling
model to cut latency; advice/analysis/复盘 turns keep the user's quality model
(qwen3.7-plus). Explicit UI model choice is always honored (never overridden).

The chosen fast model must have reliable_tool_calling=True — simple record/query
turns almost always call a tool (health_record/health_query/health_manage), and a
fast model that can't tool-call would silently break them.
"""
import json
from unittest.mock import MagicMock

import pytest

from app.services import agent_executor as ae
from app.services.agent_executor import (
    AgentExecutor,
    _is_fast_eligible_turn,
)
from app.services.llm import model_registry as reg


# ──── registry: pick_fast_tool_model_id ────

def test_pick_fast_tool_model_is_reliable_tool_caller():
    """The fast model chosen must be reliable_tool_calling=True (env-agnostic)."""
    fast_id = reg.pick_fast_tool_model_id(only_available=False)
    assert fast_id is not None
    entry = reg.get_model(fast_id)
    assert entry is not None
    assert entry.reliable_tool_calling is True
    assert entry.speed_tier == "fast"


def test_pick_fast_prefers_fastest_reliable_tier(monkeypatch):
    """Prefer fast tier; skip a fast-but-unreliable model, fall to next reliable tier."""
    monkeypatch.setattr(
        reg, "list_models",
        lambda only_available=False: [
            # fastest tier is unreliable → must be skipped
            reg.ModelEntry("fastbad", "fb", "x", "m", "fast", reliable_tool_calling=False),
            reg.ModelEntry("balrel", "b", "x", "m", "balanced", reliable_tool_calling=True),
            reg.ModelEntry("reasonrel", "r", "x", "m", "reasoning", reliable_tool_calling=True),
        ],
    )
    # no reliable fast model → next fastest reliable = balanced
    assert reg.pick_fast_tool_model_id(only_available=False) == "balrel"


def test_pick_fast_picks_fastest_when_reliable(monkeypatch):
    monkeypatch.setattr(
        reg, "list_models",
        lambda only_available=False: [
            reg.ModelEntry("balrel", "b", "x", "m", "balanced", reliable_tool_calling=True),
            reg.ModelEntry("fastrel", "f", "x", "m", "fast", reliable_tool_calling=True),
        ],
    )
    assert reg.pick_fast_tool_model_id(only_available=False) == "fastrel"


def test_pick_fast_none_when_no_reliable(monkeypatch):
    """No reliable model at all → None (caller keeps default, does not route)."""
    monkeypatch.setattr(
        reg, "list_models",
        lambda only_available=False: [
            reg.ModelEntry("bad", "bad", "x", "m", "fast", reliable_tool_calling=False),
        ],
    )
    assert reg.pick_fast_tool_model_id(only_available=False) is None


# ──── classifier: _is_fast_eligible_turn ────

@pytest.mark.parametrize("msg", [
    "记录我喝了500ml水",
    "帮我打卡今天的体重68kg",
    "我今天喝了多少水",
    "查一下我最近的血压",
    "看一下我今天走了几步",
    "本周体重是多少",
])
def test_record_and_simple_query_are_fast_eligible(msg):
    assert _is_fast_eligible_turn(msg, has_images=False, has_file=False) is True


@pytest.mark.parametrize("msg", [
    "综合分析我的健康趋势",
    "复盘我这周的睡眠",
    "为什么我最近血压偏高",
    "给我一个减脂饮食方案",
    "结合我的基因该怎么补叶酸",
    "帮我评估心血管风险",
])
def test_advice_and_analysis_not_fast_eligible(msg):
    assert _is_fast_eligible_turn(msg, has_images=False, has_file=False) is False


def test_attachments_never_fast_eligible():
    # even a pure record message is not fast-eligible when images/file present
    assert _is_fast_eligible_turn("记录我喝了水", has_images=True, has_file=False) is False
    assert _is_fast_eligible_turn("查一下体重", has_images=False, has_file=True) is False


def test_ambiguous_falls_to_quality_model():
    # neither record nor simple-query nor advice → conservative: not fast-eligible
    assert _is_fast_eligible_turn("你好呀", has_images=False, has_file=False) is False


# ──── end-to-end routing through run_stream ────

# The concrete fast model id used in these tests. Registry picks it deterministically
# (fastest reliable-tool-calling chat model). We pin the helper so the test does not
# depend on env-gated availability.
_FAST_ID = "deepseek-v4-flash"


def _stub_registry_fast(monkeypatch, fast_id=_FAST_ID):
    monkeypatch.setattr(reg, "pick_fast_tool_model_id", lambda **_k: fast_id)


async def _run(executor, message, extra_context=None, user_id=1):
    return [
        event
        async for event in executor.run_stream(
            user_id=user_id,
            message=message,
            user_auth_token="test-token",
            extra_context=extra_context,
        )
    ]


class _FakeProvider:
    """Answers directly with no tool call (keeps the round loop short)."""

    def __init__(self, model_id):
        self.model = model_id

    async def chat_stream(self, **kwargs):  # noqa: ARG002
        yield {"type": "content", "text": "OK"}
        yield {"type": "finish", "finish_reason": "stop"}


def _wire_common(executor, monkeypatch, provider_factory):
    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda: [{
        "type": "function",
        "function": {"name": "noop", "description": "x", "parameters": {"type": "object", "properties": {}}},
    }])
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        provider_factory,
    )
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")


@pytest.mark.asyncio
async def test_record_turn_routes_to_fast_model(db, auth_user_and_headers, monkeypatch):
    """(a) A record turn → fast model selected."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    created = []

    def factory(model_id):
        created.append(model_id)
        return _FakeProvider(model_id)

    _stub_registry_fast(monkeypatch)
    _wire_common(executor, monkeypatch, factory)

    events = await _run(executor, "记录我喝了500ml水", user_id=user.id)
    done = events[-1]["data"]

    assert created == [_FAST_ID]
    assert done["model"] == _FAST_ID
    assert done["selected_model"] == _FAST_ID
    assert executor._request_model_id == _FAST_ID


@pytest.mark.asyncio
async def test_simple_query_turn_routes_to_fast_model(db, auth_user_and_headers, monkeypatch):
    """(b) A simple query turn → fast model."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    created = []

    def factory(model_id):
        created.append(model_id)
        return _FakeProvider(model_id)

    _stub_registry_fast(monkeypatch)
    _wire_common(executor, monkeypatch, factory)

    events = await _run(executor, "查一下我今天喝了多少水", user_id=user.id)
    done = events[-1]["data"]

    assert created == [_FAST_ID]
    assert done["model"] == _FAST_ID
    assert executor._request_model_id == _FAST_ID


@pytest.mark.asyncio
async def test_analysis_turn_keeps_quality_model(db, auth_user_and_headers, monkeypatch):
    """(c) An analysis/复盘 turn → quality/preference model (NO fast override)."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)

    # If the code ever routed this to the fast model, create_provider_for_model_id
    # would be called with _FAST_ID — assert it is NOT.
    created = []

    def model_factory(model_id):
        created.append(model_id)
        return _FakeProvider(model_id)

    default_provider = _FakeProvider("qwen3.7-plus")

    _stub_registry_fast(monkeypatch)
    _wire_common(executor, monkeypatch, model_factory)
    # user-preference / default path
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_user",
        lambda uid, db, **k: default_provider,
    )

    events = await _run(executor, "综合分析我的健康趋势", user_id=user.id)
    done = events[-1]["data"]

    assert executor._request_model_id is None  # not overridden to fast
    assert _FAST_ID not in created  # never built the fast provider
    assert done["model"] == "qwen3.7-plus"  # answered by the default/quality model


@pytest.mark.asyncio
async def test_explicit_model_override_is_honored(db, auth_user_and_headers, monkeypatch):
    """(d) Explicit _request_model_id (UI pick) → honored, not overridden by fast route."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    created = []

    def factory(model_id):
        created.append(model_id)
        return _FakeProvider(model_id)

    _stub_registry_fast(monkeypatch)
    _wire_common(executor, monkeypatch, factory)

    # Even though "记录..." is fast-eligible, the user explicitly picked claude.
    events = await _run(
        executor,
        "记录我喝了500ml水",
        extra_context=json.dumps({"client": "mac", "model_id": "claude-opus-4.7"}),
        user_id=user.id,
    )
    done = events[-1]["data"]

    assert executor._request_model_id == "claude-opus-4.7"
    assert created == ["claude-opus-4.7"]
    assert _FAST_ID not in created
    # selected_model is the registry display name (entry.model), not the id
    assert done["selected_model"] == "commercial/Claude-Opus-4.7"


# ──── auto-confirm 分级: _auto_confirm_fast_record_args ────
# symptom/rhinitis 免确认前置(回显+可撤销);医疗级/资金类永远确认;
# unknown kind fail-closed 走确认。对抗:模型预置 confirmed=true 必须被剥掉。


def _auto_confirm(kind: str, *, pre_confirmed: bool = False, channel: str | None = None) -> dict:
    args = {"record_type": kind, "data": {"description": "x", "body_part": "general"}}
    if pre_confirmed:
        args["confirmed"] = True
        args["data"]["confirmed"] = True
    out = ae._auto_confirm_fast_record_args("health_record", args, channel=channel)
    return out


def test_symptom_record_auto_confirms_on_typed_channel():
    out = _auto_confirm("symptom", channel="typed")
    assert out["confirmed"] is True
    assert out["data"]["confirmed"] is True
    assert "_fast_record_requires_confirmation" not in out


def test_symptom_without_channel_fails_closed_to_confirmation():
    # 旧客户端/Siri/未声明通道:症状保留确认前置(传输层 fail-closed)
    out = _auto_confirm("symptom", pre_confirmed=True, channel=None)
    assert out.get("confirmed") is not True
    assert out["_fast_record_requires_confirmation"] is True


def test_rhinitis_record_auto_confirms_on_typed_channel():
    out = _auto_confirm("rhinitis", channel="typed")
    assert out["confirmed"] is True


def test_medication_always_requires_confirmation_even_if_model_preconfirms():
    out = _auto_confirm("medication", pre_confirmed=True)
    assert out.get("confirmed") is not True
    assert out["data"].get("confirmed") is not True
    assert out["_fast_record_requires_confirmation"] is True


def test_dose_and_payment_stay_confirm_first():
    for kind in ("dose", "payment", "prescription", "adherence"):
        out = _auto_confirm(kind, pre_confirmed=True)
        assert out.get("confirmed") is not True, kind
        assert out["_fast_record_requires_confirmation"] is True, kind


def test_unknown_kind_fails_closed_to_confirmation():
    out = _auto_confirm("mystery_kind", pre_confirmed=True)
    assert out.get("confirmed") is not True
    assert out["_fast_record_requires_confirmation"] is True


def test_water_still_auto_confirms():
    out = _auto_confirm("water")
    assert out["confirmed"] is True


def test_symptom_friendly_echo_offers_undo():
    reply = ae._friendly_record_confirmation({"description": "舌头尖溃疡", "body_part": "other"})
    assert "已记录症状" in reply
    assert "撤销" in reply


def test_symptom_friendly_echo_carries_record_id_for_undo_turn():
    # 撤销回合走快路由只带上一行回显 → 回显必须含记录号,否则模型无 id 可删
    reply = ae._friendly_record_confirmation({"id": 19, "description": "舌头尖溃疡", "body_part": "other"})
    assert "记录号 19" in reply
    assert "撤销" in reply


def test_list_tool_result_never_claims_records_created():
    # 对抗评审实测:撤销回合模型 list 查 ID,数组结果曾被答成"✅已记录 2 条"(假写入宣称)
    import json as _json
    msgs = [{"role": "tool", "content": _json.dumps([
        {"id": 18, "description": "a"}, {"id": 19, "description": "b"},
    ], ensure_ascii=False)}]
    reply = ae._fast_record_reply_from_tool_results(msgs)
    assert "已记录" not in reply
    assert "查到 2 条" in reply
    assert "18" in reply and "19" in reply


def test_symptom_via_voice_channels_keeps_confirmation():
    # 语音/siri 通道转写失真率高(且 Siri 单轮无法撤销)→ 症状保留确认前置
    for channel in ("voice", "siri"):
        args = {"record_type": "symptom", "data": {"description": "头痛", "body_part": "head"}}
        out = ae._auto_confirm_fast_record_args("health_record", args, channel=channel)
        assert out["_fast_record_requires_confirmation"] is True, channel
        assert "confirmed" not in out


def test_water_auto_confirms_regardless_of_channel():
    # 通道守卫只作用于症状类;低风险数值记录(water)任何通道免确认
    for channel in (None, "voice", "typed"):
        args = {"record_type": "water", "data": {"amount": 250}}
        out = ae._auto_confirm_fast_record_args("health_record", args, channel=channel)
        assert out["confirmed"] is True, channel


@pytest.mark.asyncio
async def test_typed_symptom_writes_without_confirmation_roundtrip(db):
    # 打字通道症状:auto-confirm 后端到端直达 API 写入(不再 [NEEDS_CONFIRMATION])
    executor = AgentExecutor(db)
    posted = {}

    async def _capture_post(url, headers, payload):
        posted["url"] = url
        posted["payload"] = payload
        return '{"id": 1, "body_part": "other", "description": "舌头尖溃疡"}'

    executor._api_post = _capture_post
    args = ae._auto_confirm_fast_record_args(
        "health_record",
        {"record_type": "symptom", "data": {"body_part": "other", "description": "舌头尖溃疡"}},
        channel="typed",
    )
    result = await executor._exec_health_record("http://x", {}, args)

    assert "NEEDS_CONFIRMATION" not in result
    assert posted["url"].endswith("/symptoms")
    assert posted["payload"]["description"] == "舌头尖溃疡"
