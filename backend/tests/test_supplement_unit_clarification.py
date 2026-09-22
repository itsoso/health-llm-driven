"""Synthetic shorthand intake regressions: never infer a dose unit."""
import pytest

from app.models.agent_conversation import AgentMessage
from app.services.agent_executor import AgentExecutor, _record_intent_needs_detail_message
from app.services.agent_kernel import capability_policy as policy
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.types import (
    AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot,
)

pytestmark = pytest.mark.usefixtures("consenting_agent_user")


@pytest.mark.parametrize("message,missing", [
    ("记录补剂：1 复合VB 1 Mitoq", ("复合VB", "Mitoq")),
    ("记录补剂：1复合VB 1Mitoq", ("复合VB", "Mitoq")),
    ("打卡补剂：一 复合VB，一 Mitoq", ("复合VB", "Mitoq")),
    ("记录补剂：1片复合VB 1 Mitoq", ("Mitoq",)),
    ("记录补剂：1 维生素B12 1 Mitoq", ("维生素B12", "Mitoq")),
    ("记录补剂：1 Mitoq", ("Mitoq",)),
    ("记录补剂：1片复合VB 1 GABA", ("GABA",)),
    ("记录补剂：1 GABA 1 NMN", ("GABA", "NMN")),
])
def test_missing_units_are_identified_without_authorizing_writes(message, missing):
    assert policy.supplement_missing_unit_names(message) == missing


@pytest.mark.parametrize("message", [
    "记录补剂：1片复合VB 1粒Mitoq", "记录补剂：复合VB、Mitoq",
    "明天记录补剂：1 复合VB 1 Mitoq", "不要记录补剂：1 复合VB 1 Mitoq",
    "妈妈说记录补剂：1 复合VB 1 Mitoq", "记录补剂：1 复合VB 1 Mitoq吗？",
    "帮我写一句：记录补剂：1 复合VB 1 Mitoq", "给妈妈记录补剂：1 复合VB 1 Mitoq",
    "记录补剂：1 复合VB 1 Mitoq，明天继续", "记录补剂：0 复合VB 1 Mitoq",
    "记录补剂：1 复合VB 1 未知东西", "记录补剂：-1 复合VB 1 Mitoq",
])
def test_missing_unit_detector_is_only_a_narrow_current_intake_question(message):
    assert policy.supplement_missing_unit_names(message) == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("message", [
    "记录补剂：1 复合VB 1 Mitoq", "记录补剂：1片复合VB 1 GABA",
])
async def test_stream_clarifies_missing_units_without_model_or_health_write(
    db, auth_user_and_headers, monkeypatch, message,
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Missing units must not enter model or tool execution")
        yield  # async generator contract

    monkeypatch.setattr(executor, "_run_stream_impl", forbidden)
    events = [event async for event in executor.run_stream(
        user_id=user.id, message=message,
        client_turn_id="test-supplement-missing-unit",
    )]
    done = events[-1]["data"]
    assert done["turn_outcome"]["status"] == "waiting_for_user"
    assert done["turn_outcome"]["reason_code"] == "supplement_unit_required"
    assert done["turn_outcome"]["verified_receipt_count"] == 0
    assert done["model_call_count"] == 0
    reply = db.get(AgentMessage, done["message_id"])
    assert "单位" in reply.content
    assert "尚未记录" in reply.content and "重试" not in reply.content
    assert reply.meta["turn_outcome"] == done["turn_outcome"]


def test_target_mismatch_does_not_recommend_blind_retry():
    reply = _record_intent_needs_detail_message(
        "记录补剂：1粒营养素甲 1粒营养素乙",
        reason_codes=("health_record_target_mismatch",),
    )
    assert "名称" in reply and "剂量" in reply
    assert "重试" not in reply and "还没记下来" in reply


@pytest.mark.parametrize("name", ["复合VB", "Mitoq", "1Mitoq"])
def test_missing_unit_cannot_be_invented_by_a_tool_call(name):
    envelope = AgentEnvelope(user_id=1, channel="chat", text="记录补剂：1 复合VB 1 Mitoq")
    context = ExecutionContext.for_test(user_id=1, channel="chat")
    decision = policy.decide_tool_capability(
        TurnSnapshot(envelope=envelope, context=context,
                     intent=build_intent_frame(envelope, context)),
        ToolExecutionRequest(tool_name="health_record", arguments={
            "record_type": "supplement", "data": {"supplement_name": name, "dosage": "1粒"},
        }),
    )
    assert decision.action == "block"
    assert decision.reason == "supplement_unit_required"


def test_runtime_preserves_actionable_supplement_reason_codes():
    from app.services.agent_runtime import AgentRuntimeCoordinator
    for code in ("supplement_unit_required", "health_record_target_mismatch"):
        assert AgentRuntimeCoordinator._safe_error_code(code) == code


@pytest.mark.parametrize("message", [
    "记录补剂：1片复合VB 1 GABA", "记录补剂：1片复合VB 1gGABA",
    "记录补剂：1片复合VB 1mgNAC", "记录补剂：1片复合VB 1MLAB",
])
def test_latin_name_prefix_cannot_become_a_mass_or_volume_unit(message):
    envelope = AgentEnvelope(user_id=1, channel="chat", text=message)
    context = ExecutionContext.for_test(user_id=1, channel="chat")
    snapshot = TurnSnapshot(envelope=envelope, context=context,
                            intent=build_intent_frame(envelope, context))
    # A model or deterministic parser must not manufacture ABA from GABA.
    decision = policy.decide_tool_capability(snapshot, ToolExecutionRequest(
        tool_name="health_record", arguments={"record_type":"supplement", "data": {"items": [
            {"supplement_name":"复合VB", "dosage":"1片"},
            {"supplement_name":"ABA", "dosage":"1g"},
        ]}},
    ))
    assert decision.action == "block"
    assert policy._explicit_labeled_supplement_dose_prefix_details(message) == ()


def test_explicit_separated_latin_unit_is_preserved():
    assert policy._explicit_labeled_supplement_dose_prefix_details(
        "记录补剂：1片复合VB 1g GABA",
    ) == (("复合VB", "1片"), ("GABA", "1g"))
