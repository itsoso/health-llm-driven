import json
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.context import build_turn_snapshot
from app.services.agent_kernel.goal_spec import compile_goal_spec
from app.services.agent_kernel.tool_gateway import (
    ToolGateway,
    ToolPreflightError,
    blocked_tool_result,
)
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot
from app.services.utterance_intent_lexicon import WRITE_COMMAND_ACTIONS


def _snapshot(text: str, *, policy_mode: str = "enforce") -> TurnSnapshot:
    envelope = AgentEnvelope(user_id=1, channel="chat", text=text)
    context = ExecutionContext.for_test(user_id=1, channel="chat")
    return TurnSnapshot(
        envelope=envelope,
        context=context,
        intent=build_intent_frame(envelope, context),
        policy_mode=policy_mode,
    )


def test_tool_gateway_blocks_recovered_health_record_in_read_turn():
    gateway = ToolGateway(_snapshot("今天我的饮食的记录，帮我列个表格出来。"))

    decision = gateway.preflight(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments={"record_type": "diet", "data": {"food_items": "米饭"}},
            source="text_recovery",
        )
    )

    assert decision.action == "block"
    assert decision.reason == "write_tool_without_write_intent"
    assert decision.receipt_required is True


@pytest.mark.parametrize(
    "message",
    (
        "记录过口腔溃疡吗？",
        "记录了几次口腔溃疡？",
        "记录口腔溃疡的历史有哪些？",
    ),
)
def test_tool_gateway_blocks_write_for_historical_record_questions(message):
    gateway = ToolGateway(_snapshot(message))

    decision = gateway.preflight(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments={"record_type": "illness", "data": {"name": "口腔溃疡"}},
            source="structured",
        )
    )

    assert decision.action == "block"
    assert decision.reason == "write_tool_without_write_intent"


@pytest.mark.parametrize(
    "message",
    (
        "记录过口腔溃疡没有",
        "记录过口腔溃疡没",
        "记录过口腔溃疡",
        "记录了口腔溃疡没有",
        "记录了口腔溃疡",
        "以前的口腔溃疡记录",
        "上一次口腔溃疡记录",
    ),
)
@pytest.mark.asyncio
async def test_gateway_blocks_write_for_unpunctuated_record_history(message):
    gateway = ToolGateway(_snapshot(message))

    dispatched = False

    async def dispatch(_request):
        nonlocal dispatched
        dispatched = True
        return "unexpected"

    request = ToolExecutionRequest(
        tool_name="health_record",
        arguments={"record_type": "illness", "data": {"name": "口腔溃疡"}},
        source="structured",
    )

    result = await gateway.execute(request, dispatch)

    assert dispatched is False
    assert result.decision is not None
    assert result.decision.action == "block"
    assert result.decision.reason == "write_tool_without_write_intent"
    assert json.loads(result.content)["dispatch_started"] is False


@pytest.mark.parametrize(
    "message",
    (
        "勿帮我记录晚餐，分析一下热量",
        "甭帮我记录晚餐，分析一下热量",
        "请勿帮我记录口腔溃疡，分析一下原因",
        "这个功能可以帮我记录口腔溃疡吗？",
        "系统可以帮我记录口腔溃疡吗？",
        "小巴能帮我记录口腔溃疡吗？",
        "请问小巴能帮我记录口腔溃疡吗？",
        "请问系统可以帮我记录口腔溃疡吗？",
        "我想问这个功能可以帮我记录口腔溃疡吗？",
        "不用让小巴帮我记录口腔溃疡，分析一下原因",
        "不要让系统帮我记录口腔溃疡",
        "勿让小巴帮我记录晚餐，分析一下热量",
        "请不要主动帮我记录口腔溃疡",
        "不要默默帮我记录口腔溃疡",
        "别总是帮我记录口腔溃疡",
        "请勿擅自帮我记录口腔溃疡",
        "记录口腔溃疡历史",
        "记录列表",
        "记录汇总",
        "保存过口腔溃疡吗？",
        "录入过口腔溃疡吗？",
        "新增过口腔溃疡吗？",
        "写入过口腔溃疡吗？",
        "打卡过口腔溃疡吗？",
        "上次帮我记录口腔溃疡了吗？",
        "上回帮我记录口腔溃疡了吗？",
        "之前帮我记录口腔溃疡了吗？",
        "刚才帮我记录口腔溃疡了吗？",
        "你帮我保存口腔溃疡了吗？",
        "我想知道小巴能不能帮我记录口腔溃疡",
        "请告诉我小巴能否帮我记录口腔溃疡",
        "系统是否会帮我记录口腔溃疡？",
        "小巴会帮我记录口腔溃疡吗？",
        "这个功能支持帮我记录口腔溃疡吗？",
        "系统有没有帮我记录口腔溃疡的功能？",
        "请问能否记录口腔溃疡？",
        "无须让系统帮我记录口腔溃疡",
        "禁止帮我记录口腔溃疡",
        "我拒绝让系统帮我记录口腔溃疡",
        "请停止帮我记录口腔溃疡",
        "避免帮我记录口腔溃疡",
        "我不愿意让小巴帮我记录口腔溃疡",
        "我没有授权小巴帮我记录口腔溃疡",
        "未授权系统帮我记录口腔溃疡",
        "不一定要记录口腔溃疡",
        "不一定需要记录口腔溃疡",
        "不要执行：记录一下口腔溃疡",
        "请勿执行以下操作：记录一下今天晚餐",
        "禁止：记录口腔溃疡",
        "我从未同意系统帮我记录口腔溃疡",
        "我没有同意小巴帮我记录口腔溃疡",
        "我从没允许系统帮我记录口腔溃疡",
        "我没让系统帮我记录口腔溃疡",
        "我从没想过让系统帮我记录口腔溃疡",
        "我并没有要求系统帮我记录口腔溃疡",
        "我不乐意让小巴帮我记录口腔溃疡",
        "我无意让小巴帮我记录口腔溃疡",
        "我反对让系统帮我记录口腔溃疡",
        "未经我同意小巴帮我记录口腔溃疡",
        "严禁以下行为：记录口腔溃疡",
        "不要执行以下行为：记录口腔溃疡",
        "你帮我记录口腔溃疡没有",
        "你帮我保存口腔溃疡没有啊",
        "昨天帮我记录的口腔溃疡",
        "这个能帮我记录口腔溃疡吗？",
        "它能帮我记录口腔溃疡吗？",
        "请查询口腔溃疡记录",
        "请查看我的口腔溃疡记录",
        "请帮我确认有没有记录成功",
        "麻烦查查保存成功不成功",
        "帮我核对一下是否新增成功",
        "请查看口腔溃疡是否已录入",
        "客服说请记录口腔溃疡",
        "文档写着：帮我记录口腔溃疡",
        "他说记录一下口腔溃疡",
        "请转述这句话：记录口腔溃疡",
        "请复述“帮我记录口腔溃疡”",
        "请不必帮我记录口腔溃疡",
        "请杜绝系统自动记录口腔溃疡",
        "在没有得到我同意的情况下，记录口腔溃疡是不允许的",
        "记录口腔溃疡就免了",
        "记录口腔溃疡这件事作罢",
        "记录口腔溃疡未获授权",
        "记录口腔溃疡，还是算了",
        "记录口腔溃疡，取消吧",
        "不要做这件事：帮我记录口腔溃疡",
        "我从未叫你帮我记录口腔溃疡",
        "我可没让你帮我记录口腔溃疡",
        "未经我许可就帮我记录口腔溃疡",
        "我并不乐意让你帮我记录口腔溃疡",
        "请确认小巴具备记录健康数据的能力",
        "请说明小巴具不具备记录口腔溃疡的能力",
        "请确认它会自动记录口腔溃疡",
        "帮我看看昨天口腔溃疡是否已经记录",
        "请查一下上周那次口腔溃疡是否已保存",
        "请确认口腔溃疡是否已经成功写入数据库",
        "帮我核对口腔溃疡是否已经保存到病历中",
        "我只是举个例子：帮我记录口腔溃疡",
        "假设我说“帮我记录口腔溃疡”",
        "如果以后我说帮我记录口腔溃疡会怎样",
        "“帮我记录口腔溃疡”是什么意思",
        "文档写着：我午餐吃了米饭",
        "假设我午餐吃了米饭会怎样",
    ),
)
@pytest.mark.asyncio
async def test_gateway_never_dispatches_negated_or_capability_writes(message):
    gateway = ToolGateway(_snapshot(message))
    dispatched = False

    async def dispatch(_request):
        nonlocal dispatched
        dispatched = True
        return "unexpected"

    result = await gateway.execute(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments={"record_type": "illness", "data": {"name": "口腔溃疡"}},
            source="structured",
        ),
        dispatch,
    )

    assert dispatched is False
    assert result.decision is not None
    assert result.decision.action == "block"
    assert json.loads(result.content)["dispatch_started"] is False


@pytest.mark.asyncio
async def test_gateway_adversarial_speech_act_matrix_never_dispatches() -> None:
    frames = (
        "我拒绝让系统帮我{action}口腔溃疡",
        "禁止帮我{action}口腔溃疡",
        "请停止帮我{action}口腔溃疡",
        "我没有授权小巴帮我{action}口腔溃疡",
        "上次帮我{action}口腔溃疡了吗？",
        "你帮我{action}口腔溃疡了吗？",
        "系统是否会帮我{action}口腔溃疡？",
        "我想知道小巴能不能帮我{action}口腔溃疡",
        "朋友说帮我{action}口腔溃疡",
        "同事转告我：帮我{action}口腔溃疡",
        "例如：帮我{action}口腔溃疡",
        "帮我{action}口腔溃疡暂缓",
    )

    for frame in frames:
        for action in WRITE_COMMAND_ACTIONS:
            message = frame.format(action=action)
            dispatched = False

            async def dispatch(_request):
                nonlocal dispatched
                dispatched = True
                return "unexpected"

            gateway = ToolGateway(_snapshot(message))
            result = await gateway.execute(
                ToolExecutionRequest(
                    tool_name="health_record",
                    arguments={
                        "record_type": "illness",
                        "data": {"name": "口腔溃疡"},
                    },
                    source="structured",
                ),
                dispatch,
            )

            assert dispatched is False, message
            assert result.decision is not None
            assert result.decision.action == "block", message
            assert json.loads(result.content)["dispatch_started"] is False


@pytest.mark.asyncio
async def test_gateway_reported_observation_matrix_never_dispatches() -> None:
    observations = (
        "午餐吃了米饭",
        "喝了300ml水",
        "服药1片",
        "已服用药物1片",
        "已吃午餐",
        "已喝300ml水",
    )
    frames = ("朋友说我{observation}", "假定我{observation}")

    for frame in frames:
        for observation in observations:
            message = frame.format(observation=observation)
            dispatched = False

            async def dispatch(_request):
                nonlocal dispatched
                dispatched = True
                return "unexpected"

            result = await ToolGateway(_snapshot(message)).execute(
                ToolExecutionRequest(
                    tool_name="health_record",
                    arguments={
                        "record_type": "illness",
                        "data": {"name": "口腔溃疡"},
                    },
                    source="structured",
                ),
                dispatch,
            )

            assert dispatched is False, message
            assert result.decision is not None
            assert result.decision.action == "block", message
            assert json.loads(result.content)["dispatch_started"] is False


def test_gateway_mixed_polarity_turn_binds_the_positive_target() -> None:
    snapshot = _snapshot("不要记录口腔溃疡但记录今天晚餐吃米饭")
    goal = compile_goal_spec(
        envelope=snapshot.envelope,
        context=snapshot.context,
        intent=snapshot.intent,
    )
    gateway = ToolGateway(replace(snapshot, goal=goal))

    denied_target = gateway.preflight(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments={
                "record_type": "illness",
                "data": {"name": "口腔溃疡"},
            },
            source="structured",
        )
    )
    authorized_target = gateway.preflight(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments={
                "record_type": "diet",
                "data": {"meal_type": "dinner", "food_items": "米饭"},
            },
            source="structured",
        )
    )

    assert denied_target.action == "block"
    assert denied_target.reason == "health_record_target_mismatch"
    assert authorized_target.action == "allow"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "朋友说帮我记录口腔溃疡",
        "同事转告我：帮我记录口腔溃疡",
        "例如：帮我记录口腔溃疡",
        "朋友说我午餐吃了米饭",
        "小王表示我喝了300ml水",
        "朋友说我头痛",
        "体检报告写着体重71kg",
        "请分析昨天的口腔溃疡记录",
        "帮我总结上次口腔溃疡记录",
        "记录体重71kg，算了吧",
        "记录体重71kg，取消这件事",
        "记录体重71kg，撤回",
        "帮我记录口腔溃疡暂缓",
        "记录口腔溃疡，算了吧不要记了",
        "等我确诊后再记录感冒",
        "等以后如果我确诊感冒，再记录感冒",
        "请记录朋友的感冒",
        "帮我记录我妈妈的感冒",
    ),
)
async def test_gateway_never_dispatches_non_authorizing_health_record_frames(
    message,
):
    dispatched = False

    async def dispatch(_request):
        nonlocal dispatched
        dispatched = True
        return "unexpected"

    result = await ToolGateway(_snapshot(message)).execute(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments={
                "record_type": "illness",
                "data": {"name": "口腔溃疡"},
            },
            source="structured",
        ),
        dispatch,
    )

    assert dispatched is False
    assert result.decision is not None
    assert result.decision.action == "block"
    assert json.loads(result.content)["dispatch_started"] is False


@pytest.mark.asyncio
async def test_gateway_dispatches_canonical_record_date_not_ignored_alias():
    calls = []

    async def dispatch(request):
        calls.append(request.arguments)
        return "ok"

    result = await ToolGateway(_snapshot("记录昨天体重70kg")).execute(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments={
                "record_type": "weight",
                "data": {"weight": 70, "date": "2026-07-16"},
            },
            source="structured",
        ),
        dispatch,
    )

    assert result.decision is not None
    assert result.decision.action == "allow"
    assert calls == [
        {
            "record_type": "weight",
            "data": {
                "weight": 70,
                "date": "2026-07-16",
                "record_date": "2026-07-16",
            },
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "denied_args", "authorized_args"),
    (
        (
            "记录体重71kg",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
            {"record_type": "weight", "data": {"weight": 71, "unit": "kg"}},
        ),
        (
            "不要记录早餐但记录午餐吃了米饭",
            {"record_type": "diet", "data": {"meal_type": "breakfast", "food_items": "米饭"}},
            {"record_type": "diet", "data": {"meal_type": "lunch", "food_items": "米饭"}},
        ),
        (
            "不要记录喝水300ml但记录晚餐吃了米饭",
            {"record_type": "water", "data": {"amount_ml": 300}},
            {"record_type": "diet", "data": {"meal_type": "dinner", "food_items": "米饭"}},
        ),
    ),
)
async def test_gateway_dispatches_only_the_concrete_authorized_target(
    message, denied_args, authorized_args
):
    calls = []

    async def dispatch(request):
        calls.append(request.arguments)
        return "ok"

    gateway = ToolGateway(_snapshot(message))
    denied = await gateway.execute(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments=denied_args,
            source="structured",
        ),
        dispatch,
    )
    authorized = await gateway.execute(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments=authorized_args,
            source="structured",
        ),
        dispatch,
    )

    assert denied.decision is not None
    assert denied.decision.action == "block"
    assert json.loads(denied.content)["dispatch_started"] is False
    assert authorized.decision is not None
    assert authorized.decision.action == "allow"
    assert calls == [authorized_args]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "record_args"),
    (
        ("记录体重71kg", {"record_type": "weight", "value": 72}),
        ("记录喝水300ml", {"record_type": "water", "amount": 500}),
        (
            "记录血压120/80",
            {
                "record_type": "blood_pressure",
                "systolic": 130,
                "diastolic": 90,
            },
        ),
        ("记录腰围80cm", {"record_type": "waist", "waist": 90}),
        ("记录口腔溃疡", {"record_type": "illness", "name": "感冒"}),
        (
            "记录午餐吃米饭",
            {"record_type": "diet", "data": {"food_items": "米饭"}},
        ),
        (
            "不要记录晚餐面包但记录晚餐米饭",
            {
                "record_type": "diet",
                "data": {"meal_type": "dinner", "food_items": "面包"},
            },
        ),
    ),
)
async def test_gateway_never_dispatches_alias_or_selector_target_transfer(
    message, record_args
):
    calls = []

    async def dispatch(request):
        calls.append(request.arguments)
        return "unexpected"

    result = await ToolGateway(_snapshot(message)).execute(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments=record_args,
            source="structured",
        ),
        dispatch,
    )

    assert calls == []
    assert result.decision is not None
    assert result.decision.action == "block"
    assert json.loads(result.content)["dispatch_started"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "record_args"),
    (
        (
            "记录体重71kg改记录72kg",
            {"record_type": "weight", "data": {"weight": 72}},
        ),
        (
            "记录喝水300ml和晚餐吃了米饭",
            {"record_type": "water", "data": {"amount": 300}},
        ),
        (
            "记录喝水300ml和晚餐吃了米饭",
            {
                "record_type": "diet",
                "data": {"meal_type": "dinner", "food_items": "米饭"},
            },
        ),
        (
            "不要记录午餐面包只记录晚餐米饭",
            {
                "record_type": "diet",
                "data": {"meal_type": "dinner", "food_items": "米饭"},
            },
        ),
    ),
)
async def test_gateway_dispatches_each_member_of_the_authorized_target_set(
    message, record_args
):
    calls = []

    async def dispatch(request):
        calls.append(request.arguments)
        return "ok"

    result = await ToolGateway(_snapshot(message)).execute(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments=record_args,
            source="structured",
        ),
        dispatch,
    )

    assert result.decision is not None
    assert result.decision.action == "allow"
    assert calls == [record_args]


def test_blocked_tool_result_includes_a_recovery_instruction_for_the_agent():
    gateway = ToolGateway(_snapshot("今天我的饮食的记录，帮我列个表格出来。"))
    decision = gateway.preflight(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments={"record_type": "diet", "data": {"food_items": "米饭"}},
            source="text_recovery",
        )
    )

    result = blocked_tool_result(decision)

    payload = json.loads(result)

    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == "write_tool_without_write_intent"
    assert payload["tool"] == "health_record"
    assert payload["message"].startswith("[NEEDS_CLARIFICATION]")
    assert "先澄清" in payload["recovery_guidance"]


@pytest.mark.asyncio
async def test_gateway_execute_dispatches_allowed_request_exactly_once():
    gateway = ToolGateway(_snapshot("记录午餐吃了牛肉面"))
    calls = []
    events = []
    request = ToolExecutionRequest(
        tool_name="health_record",
        arguments={
            "record_type": "diet",
            "data": {"meal_type": "lunch", "food_items": "牛肉面"},
        },
    )

    async def dispatch(normalized_request):
        events.append("dispatch")
        calls.append(normalized_request)
        return '{"id": 1, "resource_type": "diet_record"}'

    result = await gateway.execute(
        request,
        dispatch,
        on_decision=lambda _decision: events.append("decision"),
    )

    assert len(calls) == 1
    assert events == ["decision", "dispatch"]
    assert calls[0].arguments == request.arguments
    assert result.content == '{"id": 1, "resource_type": "diet_record"}'
    assert result.decision is not None
    assert result.decision.action == "allow"


@pytest.mark.asyncio
async def test_gateway_strips_unmentioned_illness_severity_before_dispatch():
    calls = []

    async def dispatch(request):
        calls.append(request.arguments)
        return "ok"

    result = await ToolGateway(_snapshot("记录口腔溃疡")).execute(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments={
                "record_type": "illness",
                "severity": 5,
                "data": {
                    "name": "口腔溃疡",
                    "severity": 5,
                    "status": "active",
                },
            },
            source="structured",
        ),
        dispatch,
    )

    assert result.decision is not None
    assert result.decision.action == "allow"
    assert calls == [
        {
            "record_type": "illness",
            "data": {"name": "口腔溃疡", "status": "active"},
        }
    ]


@pytest.mark.asyncio
async def test_gateway_decision_observer_failure_prevents_dispatch():
    gateway = ToolGateway(_snapshot("记录午餐吃了牛肉面"))
    dispatched = False
    request = ToolExecutionRequest(
        tool_name="health_record",
        arguments={"record_type": "diet", "data": {"food_items": "牛肉面"}},
    )

    async def dispatch(_request):
        nonlocal dispatched
        dispatched = True
        return "unexpected"

    def fail_before_dispatch(_decision):
        raise RuntimeError("private-health-payload")

    with pytest.raises(ToolPreflightError, match="tool_preflight_failed"):
        await gateway.execute(
            request,
            dispatch,
            on_decision=fail_before_dispatch,
        )

    assert dispatched is False


@pytest.mark.asyncio
async def test_gateway_execute_blocks_enforced_denial_without_dispatch():
    gateway = ToolGateway(_snapshot("列出今天的饮食记录"))
    dispatched = False
    request = ToolExecutionRequest(
        tool_name="health_record",
        arguments={"record_type": "diet", "data": {"food_items": "牛肉面"}},
    )

    async def dispatch(_request):
        nonlocal dispatched
        dispatched = True
        return "unexpected"

    result = await gateway.execute(request, dispatch)

    assert dispatched is False
    assert result.decision is not None
    assert result.decision.action == "block"
    payload = json.loads(result.content)
    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False
    assert "工具调用未执行" in payload["message"]


@pytest.mark.asyncio
async def test_gateway_execute_shadow_denial_still_dispatches_once():
    gateway = ToolGateway(_snapshot("列出今天的饮食记录", policy_mode="shadow"))
    calls = []
    request = ToolExecutionRequest(
        tool_name="health_record",
        arguments={"record_type": "diet", "data": {"food_items": "牛肉面"}},
    )

    async def dispatch(normalized_request):
        calls.append(normalized_request)
        return '{"id": 2, "resource_type": "diet_record"}'

    result = await gateway.execute(request, dispatch)

    assert len(calls) == 1
    assert result.decision is not None
    assert result.decision.action == "block"
    assert '"id": 2' in result.content


@pytest.mark.asyncio
async def test_execute_tool_blocks_policy_denied_health_record_before_dispatch(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "今天我的饮食的记录，帮我列个表格出来。"

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {"error": None, "data": args},
    )

    async def should_not_run(*args, **kwargs):
        raise AssertionError("_exec_health_record should not run")

    monkeypatch.setattr(executor, "_exec_health_record", should_not_run)

    result = await executor._execute_tool(
        "health_record",
        json.dumps({"record_type": "diet", "data": {"food_items": "米饭"}}, ensure_ascii=False),
        None,
    )

    payload = json.loads(result)
    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == "write_tool_without_write_intent"

    assert executor._agent_kernel_event_bus is not None
    tool_result = next(
        event
        for event in executor._agent_kernel_event_bus.events
        if event.name == "agent.tool_result"
    )
    assert tool_result.data["success"] is False


@pytest.mark.asyncio
async def test_exact_historical_illness_query_blocks_model_write_before_dispatch(
    db,
    monkeypatch,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = (
        "我上一次口腔溃疡是什么时候 最近半年分别有哪些记录"
    )

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def should_not_run(*args, **kwargs):
        raise AssertionError("_exec_health_record should not run")

    monkeypatch.setattr(executor, "_exec_health_record", should_not_run)
    result = await executor._execute_tool(
        "health_record",
        json.dumps(
            {
                "record_type": "illness",
                "data": {"name": "口腔溃疡", "status": "active"},
            },
            ensure_ascii=False,
        ),
        None,
    )

    payload = json.loads(result)
    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == "write_tool_without_write_intent"


@pytest.mark.asyncio
async def test_execute_tool_decision_failure_is_structured_pre_dispatch_rejection(
    db,
    monkeypatch,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "记录午餐吃了牛肉面"
    dispatched = False

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    def fail_decision_recording(_tool_name, _decision):
        raise RuntimeError("private-health-payload")

    async def dispatch_should_not_run(_request, _token):
        nonlocal dispatched
        dispatched = True
        return '{"id": 1, "resource_type": "diet_record"}'

    monkeypatch.setattr(
        executor,
        "_agent_kernel_record_capability_decision",
        fail_decision_recording,
    )
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch_should_not_run)

    result = await executor._execute_tool(
        "health_record",
        {
            "record_type": "diet",
            "data": {"meal_type": "lunch", "food_items": "牛肉面"},
        },
        None,
    )

    payload = json.loads(result)
    assert dispatched is False
    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == "policy_check_failed"


@pytest.mark.asyncio
async def test_structured_successful_read_result_remains_successful_in_telemetry(
    db,
    monkeypatch,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "查询今天的饮水记录"

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def read_success(_base_url, _headers, _args):
        return '{"status":"success","records":[]}'

    monkeypatch.setattr(executor, "_exec_health_query", read_success)

    result = await executor._execute_tool(
        "health_query",
        {"query_type": "water", "date": "today"},
        None,
    )

    assert json.loads(result)["status"] == "success"
    assert executor._agent_kernel_event_bus is not None
    tool_result = next(
        event
        for event in executor._agent_kernel_event_bus.events
        if event.name == "agent.tool_result"
    )
    assert tool_result.data["success"] is True


@pytest.mark.asyncio
async def test_structured_pending_read_result_is_not_a_tool_failure(
    db,
    monkeypatch,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "查询今天的饮水记录"

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def read_pending(_base_url, _headers, _args):
        return '{"status":"pending","records":[]}'

    monkeypatch.setattr(executor, "_exec_health_query", read_pending)

    await executor._execute_tool(
        "health_query",
        {"query_type": "water", "date": "today"},
        None,
    )

    assert executor._agent_kernel_event_bus is not None
    tool_result = next(
        event
        for event in executor._agent_kernel_event_bus.events
        if event.name == "agent.tool_result"
    )
    assert tool_result.data["success"] is True
    assert "health_query" not in executor._agent_kernel_tool_failure_tools


@pytest.mark.asyncio
async def test_execute_tool_blocks_health_manage_update_in_read_turn(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "列出今天的饮食记录"

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {"error": None, "data": args},
    )

    async def should_not_run(*args, **kwargs):
        raise AssertionError("_exec_health_manage should not run")

    monkeypatch.setattr(executor, "_exec_health_manage", should_not_run)

    result = await executor._execute_tool(
        "health_manage",
        {"record_type": "diet", "operation": "update", "record_id": 1, "data": {"meal_type": "lunch"}},
        None,
    )

    payload = json.loads(result)
    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == "manage_write_without_mutate_intent"


@pytest.mark.asyncio
async def test_execute_tool_allows_explicit_health_record_write(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "记录午餐吃了牛肉面"
    calls = []

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {"error": None, "data": args},
    )

    async def fake_exec(base, headers, args):
        calls.append(args)
        return '{"id": 1, "resource_type": "diet_record", "food_items": "牛肉面"}'

    monkeypatch.setattr(executor, "_exec_health_record", fake_exec)

    result = await executor._execute_tool(
        "health_record",
        {
            "record_type": "diet",
            "data": {"meal_type": "lunch", "food_items": "牛肉面"},
        },
        None,
    )

    assert calls == [{
        "record_type": "diet",
        "data": {
            "meal_type": "lunch",
            "food_items": "牛肉面",
            "source": "agent_text",
        },
    }]
    assert '"id": 1' in result


@pytest.mark.asyncio
async def test_execute_tool_persists_historical_symptom_on_the_authorized_date(
    db,
    monkeypatch,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "typed"
    executor._current_turn_user_message = "记录昨天头痛"
    executor._agent_kernel_snapshot = build_turn_snapshot(
        db,
        user_id=1,
        channel="typed",
        text="记录昨天头痛",
        now_utc=datetime(2026, 7, 17, 4, 0, tzinfo=timezone.utc),
    )

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )
    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return '{"id": 1, "resource_type": "symptom_entry"}'

    monkeypatch.setattr(executor, "_api_post", fake_post)

    await executor._execute_tool(
        "health_record",
        {
            "record_type": "symptom",
            "data": {
                "body_part": "head",
                "description": "头痛",
                "record_date": "2026-07-16",
            },
        },
        None,
    )

    assert captured["url"].endswith("/symptoms")
    assert captured["payload"]["occurred_at"].startswith("2026-07-16T")
    assert "record_date" not in captured["payload"]


@pytest.mark.asyncio
async def test_execute_tool_validates_and_dispatches_the_same_canonical_date_alias(
    db,
    monkeypatch,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "typed"
    executor._current_turn_user_message = "记录昨天体重70kg"
    executor._agent_kernel_snapshot = build_turn_snapshot(
        db,
        user_id=1,
        channel="typed",
        text="记录昨天体重70kg",
        now_utc=datetime(2026, 7, 17, 4, 0, tzinfo=timezone.utc),
    )
    validated = []
    dispatched = []

    def fake_validate(tool_name, args, db, user_id, reference_now=None):
        validated.append(dict(args["data"]))
        return {"error": None, "data": args}

    async def fake_exec(base, headers, args):
        dispatched.append(dict(args["data"]))
        return '{"id": 1, "resource_type": "weight_record"}'

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        fake_validate,
    )
    monkeypatch.setattr(executor, "_exec_health_record", fake_exec)

    await executor._execute_tool(
        "health_record",
        {
            "record_type": "weight",
            "data": {"weight": 70, "date": "2026-07-16"},
        },
        None,
    )

    assert validated[0]["record_date"] == "2026-07-16"
    assert dispatched[0]["record_date"] == "2026-07-16"


@pytest.mark.asyncio
async def test_execute_tool_never_dispatches_conflicting_medication_dose_aliases(
    db,
    monkeypatch,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "typed"
    executor._current_turn_user_message = "记录我吃了阿奇霉素2粒"
    dispatched = []

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def fake_exec(base, headers, args):
        dispatched.append(args)
        return "unexpected"

    monkeypatch.setattr(executor, "_exec_health_record", fake_exec)

    result = await executor._execute_tool(
        "health_record",
        {
            "record_type": "medication",
            "data": {
                "medication_name": "阿奇霉素",
                "dosage": "2粒",
                "dose": "10粒",
            },
        },
        None,
    )

    assert dispatched == []
    assert json.loads(result)["error_code"] == "health_record_target_mismatch"


@pytest.mark.asyncio
async def test_execute_tool_emits_receipt_for_json_encoded_write_arguments(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "记录午餐吃了牛肉面"

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {"error": None, "data": args},
    )

    async def fake_exec(base, headers, args):
        return '{"id": 9, "resource_type": "diet_record", "food_items": "牛肉面"}'

    monkeypatch.setattr(executor, "_exec_health_record", fake_exec)

    await executor._execute_tool(
        "health_record",
        json.dumps(
            {
                "record_type": "diet",
                "data": {"meal_type": "lunch", "food_items": "牛肉面"},
            },
            ensure_ascii=False,
        ),
        None,
    )

    assert executor._agent_kernel_event_bus is not None
    events = executor._agent_kernel_event_bus.events
    receipt = next(event for event in events if event.name == "agent.write_receipt_verified")
    assert receipt.data["operation_id"] == "health_record:diet_record:9"
    assert receipt.data["resource_id"] == "9"


@pytest.mark.asyncio
async def test_recorded_health_write_with_verified_receipt_is_telemetry_success(
    db,
    monkeypatch,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "记录午餐吃了牛肉面"

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def fake_exec(_base, _headers, _args):
        return (
            '{"status":"recorded","id":42,'
            '"resource_type":"diet_record","food_items":"牛肉面"}'
        )

    monkeypatch.setattr(executor, "_exec_health_record", fake_exec)

    await executor._execute_tool(
        "health_record",
        {
            "record_type": "diet",
            "data": {"meal_type": "lunch", "food_items": "牛肉面"},
        },
        None,
    )

    assert executor._agent_kernel_event_bus is not None
    tool_result = next(
        event
        for event in executor._agent_kernel_event_bus.events
        if event.name == "agent.tool_result"
    )
    assert tool_result.data["success"] is True
    assert "health_record" not in executor._agent_kernel_tool_failure_tools


@pytest.mark.asyncio
async def test_shadow_policy_observes_denied_write_without_blocking_dispatch(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "列出今天的饮食记录"
    calls = []
    monkeypatch.setattr("app.services.agent_executor.settings.agent_kernel_policy_mode", "shadow")
    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {"error": None, "data": args},
    )

    async def fake_exec(base, headers, args):
        calls.append(args)
        return '{"id": 10, "resource_type": "diet_record"}'

    monkeypatch.setattr(executor, "_exec_health_record", fake_exec)

    await executor._execute_tool(
        "health_record",
        {"record_type": "diet", "data": {"food_items": "牛肉面"}},
        None,
    )

    assert calls == [{
        "record_type": "diet",
        "data": {"food_items": "牛肉面", "source": "agent_text"},
    }]
    assert executor._agent_kernel_event_bus is not None
    assert "agent.tool_blocked" in [event.name for event in executor._agent_kernel_event_bus.events]


@pytest.mark.asyncio
async def test_agent_media_tool_uses_current_image_and_emits_manual_confirmation_card(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "确认把这张早餐图片发送给百炼，生成 5 秒竖屏短视频"
    executor._current_turn_source_message_id = 88
    executor._current_turn_image_urls = ["/api/v1/upload/files/chat/1/example.jpg"]
    executor._current_turn_conversation_id = 42

    class FakeMediaService:
        requested = None

        def __init__(self, _db):
            pass

        async def issue_confirmation(self, *, user_id, request, conversation_id=None):
            FakeMediaService.requested = (user_id, request, conversation_id)
            return SimpleNamespace(
                id="aigc_confirm_0123456789abcdef0123456789abcdef",
                kind=request.kind,
                source_message_id=request.source_message_id,
                model="happyhorse-1.1-i2v",
                duration_seconds=request.duration_seconds,
                ratio=request.ratio,
            )

    monkeypatch.setattr(
        "app.services.aigc_media_job_service.AIGCMediaJobService",
        FakeMediaService,
    )
    # This focused adapter test uses a synthetic source id instead of a durable
    # AgentMessage. Dispatch checkpoint behavior is covered by executor status
    # tests with a real source row.
    monkeypatch.setattr(
        executor,
        "_persist_current_turn_write_dispatch_started",
        lambda **_kwargs: None,
    )

    result = await executor._execute_tool(
        "draft_aigc_media",
        {
            "kind": "image_to_video",
            "prompt": "做成晨间饮水提醒短视频",
            "duration_seconds": 5,
            "ratio": "9:16",
            "purpose": "hydration_reminder",
        },
        None,
    )

    assert json.loads(result)["resource_type"] == "aigc_media_confirmation"
    assert FakeMediaService.requested[0] == 1
    assert FakeMediaService.requested[1].source_message_id == 88
    assert FakeMediaService.requested[2] == 42
    assert executor._turn_aigc_media_cards == [{
        "type": "aigc_media_confirmation",
        "data": {
            "confirmation_id": "aigc_confirm_0123456789abcdef0123456789abcdef",
            "kind": "image_to_video",
            "title": "短视频草稿",
            "provider": "百炼 HappyHorse",
            "source_attached": True,
            "status": "pending",
            "content_summary": "围绕补水生成健康行动短视频",
            "content_topics": ["补水"],
            "duration_seconds": 5,
            "duration_options": [5, 8, 15],
            "ratio": "9:16",
            "resolution": "720P",
            "generates_audio": True,
        },
        "actions": [{
            "id": "aigc_media.confirm:aigc_confirm_0123456789abcdef0123456789abcdef",
            "label": "确认并生成",
            "action": "aigc_media.confirm",
            "endpoint": "/aigc/media/confirmations/aigc_confirm_0123456789abcdef0123456789abcdef/confirm",
            "requires_manual_confirm": True,
            "capability_id": "aigc_media_confirmation.v1",
            "required_receipt": True,
            "autonomy_tier": "manual_confirm",
            "policy_reason": "manual_confirm_write",
        }],
    }]
    assert executor._agent_kernel_event_bus is not None
    receipt = next(
        event for event in executor._agent_kernel_event_bus.events
        if event.name == "agent.write_receipt_verified"
    )
    assert receipt.data["resource_id"] == (
        "aigc_confirm_0123456789abcdef0123456789abcdef"
    )
    tool_result = next(
        event
        for event in executor._agent_kernel_event_bus.events
        if event.name == "agent.tool_result"
    )
    assert tool_result.data["success"] is True
    assert "draft_aigc_media" not in executor._agent_kernel_tool_failure_tools


def test_aigc_media_preview_exposes_categories_without_raw_health_details():
    from app.services.agent_executor import _aigc_media_content_preview

    preview = _aigc_media_content_preview(
        kind="text_to_video",
        prompt="用今天 95 分睡眠、8200 步和晚餐 580 kcal 生成回顾视频",
    )

    assert preview == {
        "content_summary": "围绕活动、饮食和睡眠生成健康行动短视频",
        "content_topics": ["活动", "饮食", "睡眠"],
    }
    assert "95" not in preview["content_summary"]
    assert "8200" not in preview["content_summary"]
    assert "580" not in preview["content_summary"]
