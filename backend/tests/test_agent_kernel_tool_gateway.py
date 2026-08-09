import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
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
from app.services.agent_kernel.types import (
    ActionableReference,
    AgentEnvelope,
    ExecutionContext,
    ToolExecutionRequest,
    TurnSnapshot,
)
from app.services.utterance_intent_lexicon import WRITE_COMMAND_ACTIONS


def _snapshot(
    text: str,
    *,
    policy_mode: str = "enforce",
    channel: str = "chat",
) -> TurnSnapshot:
    envelope = AgentEnvelope(user_id=1, channel=channel, text=text)
    context = ExecutionContext.for_test(user_id=1, channel=channel)
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
@pytest.mark.parametrize(
    ("message", "record_args"),
    (
        (
            "记录饮水300ml，嗯，我改主意了，这次别弄了",
            {"record_type": "water", "data": {"amount_ml": 300}},
        ),
        (
            "营养师透露我喝了300ml水",
            {"record_type": "water", "data": {"amount_ml": 300}},
        ),
        (
            "假使我喝了300ml水，就帮我记录饮水300ml",
            {"record_type": "water", "data": {"amount_ml": 300}},
        ),
        (
            "表妹体重71kg，记录一下",
            {"record_type": "weight", "data": {"weight": 71}},
        ),
        (
            "岳父感冒了，帮忙记录感冒",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
        (
            "护士提及：帮我记录感冒",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
        (
            "客服转达的原话是：帮我记录感冒",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
        (
            "护士提及帮我记录感冒",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
        (
            "客服转达原话帮我记录感冒",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
        (
            "一旦我确诊感冒，就记录感冒",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
        (
            "等我有空的时候，帮我记录感冒",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
        (
            "记录饮水300ml，当我没说",
            {"record_type": "water", "data": {"amount": 300}},
        ),
        (
            "记录饮水300ml，忽略刚才那句",
            {"record_type": "water", "data": {"amount": 300}},
        ),
        (
            "我对象体重71kg，记录一下",
            {"record_type": "weight", "data": {"weight": 71}},
        ),
        (
            "邻居感冒了，帮忙记录感冒",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
        (
            "小明感冒了，帮忙记录感冒",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
        (
            "张三体重71kg，记录一下",
            {"record_type": "weight", "data": {"weight": 71}},
        ),
        (
            "王五喝了300ml水，记录一下",
            {"record_type": "water", "data": {"amount": 300}},
        ),
        (
            "我的同事李雷吃了米饭，记录午餐",
            {
                "record_type": "diet",
                "data": {"meal_type": "lunch", "food_items": "米饭"},
            },
        ),
        (
            "记录张三体重71kg",
            {"record_type": "weight", "data": {"weight": 71}},
        ),
        (
            "请记录小明体重71kg",
            {"record_type": "weight", "data": {"weight": 71}},
        ),
        (
            "记录小明感冒",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
        (
            "记录邻居感冒",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
        (
            "我感冒了同时小明体重71kg帮我记录一下",
            {"record_type": "weight", "data": {"weight": 71}},
        ),
        (
            "医生建议我记录体重71kg",
            {"record_type": "weight", "data": {"weight": 71}},
        ),
        (
            "小明让我记录体重71kg",
            {"record_type": "weight", "data": {"weight": 71}},
        ),
        (
            "记录疾病：张三感冒",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
        (
            "记录上官婉儿感冒",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
        (
            "记录左丘明体重71kg",
            {"record_type": "weight", "data": {"weight": 71}},
        ),
    ),
)
async def test_gateway_exact_semantic_non_authority_cases_never_reach_dispatch(
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
    ("message", "superseded_args", "corrected_args"),
    (
        (
            "记录体重71kg，不对，改成70kg",
            {"record_type": "weight", "data": {"weight": 71}},
            {"record_type": "weight", "data": {"weight": 70}},
        ),
        (
            "记录口腔溃疡，不对，应该是感冒",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
        (
            "记录体重71kg，口误，是70kg",
            {"record_type": "weight", "data": {"weight": 71}},
            {"record_type": "weight", "data": {"weight": 70}},
        ),
        (
            "记录感冒，抱歉说反了，是口腔溃疡",
            {"record_type": "illness", "data": {"name": "感冒"}},
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
        ),
    ),
)
async def test_gateway_correction_dispatches_only_replacement_target(
    message, superseded_args, corrected_args
):
    calls = []

    async def dispatch(request):
        calls.append(request.arguments)
        return "ok"

    gateway = ToolGateway(_snapshot(message))
    superseded = await gateway.execute(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments=superseded_args,
            source="structured",
        ),
        dispatch,
    )
    corrected = await gateway.execute(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments=corrected_args,
            source="structured",
        ),
        dispatch,
    )

    assert superseded.decision is not None
    assert superseded.decision.action == "block"
    assert corrected.decision is not None
    assert corrected.decision.action == "allow"
    assert calls == [corrected_args]


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
                "record_date": "2026-07-16",
            },
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "record_args",
    (
        {"record_type": "water", "data": {"amount": 300}},
        {"record_type": "water", "data": {"amount_ml": 300}},
        {"record_type": "water", "amount": 300},
    ),
)
async def test_gateway_dispatches_one_canonical_water_payload(record_args):
    calls = []

    async def dispatch(request):
        calls.append(request.arguments)
        return "ok"

    result = await ToolGateway(_snapshot("记录饮水300ml")).execute(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments=record_args,
            source="structured",
        ),
        dispatch,
    )

    assert result.decision is not None
    assert result.decision.action == "allow"
    assert calls == [{"record_type": "water", "data": {"amount": 300}}]


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
            {
                "record_type": "diet",
                "data": {"meal_type": "breakfast", "food_items": "米饭"},
            },
            {
                "record_type": "diet",
                "data": {"meal_type": "lunch", "food_items": "米饭"},
            },
        ),
        (
            "不要记录喝水300ml但记录晚餐吃了米饭",
            {"record_type": "water", "data": {"amount_ml": 300}},
            {
                "record_type": "diet",
                "data": {"meal_type": "dinner", "food_items": "米饭"},
            },
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
    assert calls == [authorized.decision.normalized_args]


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
async def test_gateway_projects_unmentioned_supplement_definition_fields():
    calls = []

    async def dispatch(request):
        calls.append(request.arguments)
        return "ok"

    result = await ToolGateway(_snapshot("记录鱼油")).execute(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments={
                "record_type": "supplement",
                "data": {
                    "supplement_name": "鱼油",
                    "dosage": "4粒",
                    "timing": "bedtime",
                    "category": "药物",
                    "description": "治疗高血压",
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
            "record_type": "supplement",
            "data": {"supplement_name": "鱼油"},
        }
    ]


@pytest.mark.asyncio
async def test_gateway_preserves_only_explicit_supplement_definition_fields():
    calls = []

    async def dispatch(request):
        calls.append(request.arguments)
        return "ok"

    result = await ToolGateway(_snapshot("记录鱼油，剂量2粒，晚上吃")).execute(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments={
                "record_type": "supplement",
                "data": {
                    "supplement_name": "鱼油",
                    "dosage": "2粒",
                    "timing": "evening",
                    "category": "invented",
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
            "record_type": "supplement",
            "data": {
                "supplement_name": "鱼油",
                "dosage": "2粒",
                "timing": "evening",
            },
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "记录口腔溃疡，不，还是别记录了",
        "记录口腔溃疡，先等等，别记了",
        "记录我朋友感冒",
        "我朋友感冒了，记录一下",
        "记录妈妈感冒",
        "我妈妈感冒了，记录一下",
    ),
)
async def test_gateway_never_dispatches_fillers_or_implicit_third_party_subjects(
    message,
):
    calls = []

    async def dispatch(request):
        calls.append(request.arguments)
        return "unexpected"

    result = await ToolGateway(_snapshot(message)).execute(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments={"record_type": "illness", "data": {"name": "感冒"}},
            source="structured",
        ),
        dispatch,
    )

    assert calls == []
    assert result.decision is not None
    assert result.decision.action == "block"
    assert json.loads(result.content)["dispatch_started"] is False


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
async def test_gateway_execute_shadow_health_write_denial_is_hard_blocked():
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

    assert calls == []
    assert result.decision is not None
    assert result.decision.action == "block"
    assert json.loads(result.content)["dispatch_started"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("policy_mode", ("enforce", "shadow"))
async def test_gateway_update_intent_blocks_health_record_recreate_fallback(
    policy_mode,
):
    gateway = ToolGateway(_snapshot("把刚才 300ml 改成 350ml", policy_mode=policy_mode))
    dispatched = False
    request = ToolExecutionRequest(
        tool_name="health_record",
        arguments={"record_type": "water", "data": {"amount": 350}},
    )

    async def dispatch(_request):
        nonlocal dispatched
        dispatched = True
        return "unexpected"

    result = await gateway.execute(request, dispatch)

    assert dispatched is False
    assert result.decision is not None
    assert result.decision.action == "block"
    assert result.decision.reason == "write_tool_without_write_intent"
    payload = json.loads(result.content)
    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False


@pytest.mark.asyncio
async def test_gateway_never_dispatches_update_outside_owner_scoped_exact_evidence():
    snapshot = replace(
        _snapshot("把刚才 300ml 改成 350ml"),
        actionable_references=(
            ActionableReference(
                kind="owner_scoped_health_manage_list",
                data={
                    "record_type": "water",
                    "records": ({"id": 718, "amount": 300},),
                },
            ),
        ),
    )
    gateway = ToolGateway(snapshot)
    calls = []

    async def dispatch(request):
        calls.append(request)
        return "unexpected"

    result = await gateway.execute(
        ToolExecutionRequest(
            tool_name="health_manage",
            arguments={
                "record_type": "illness",
                "operation": "update",
                "record_id": 999999,
                "data": {"status": "resolved"},
            },
        ),
        dispatch,
    )

    assert calls == []
    assert result.decision is not None
    assert result.decision.action == "block"
    assert result.decision.reason == "update_requires_exact_target_evidence"


@pytest.mark.asyncio
@pytest.mark.parametrize("policy_mode", ("enforce", "shadow"))
@pytest.mark.parametrize(
    "message",
    (
        "小明让我把刚才300ml改成350ml",
        "假设把刚才300ml改成350ml",
        "我说“把刚才300ml改成350ml”只是举例",
        "原文如下：把刚才300ml改成350ml",
        "要是把刚才300ml改成350ml会怎样",
        "老婆希望把刚才300ml改成350ml",
        "把刚才300ml改成350ml，先保持原样",
        "把刚才300ml改成350ml，哦不，是400ml",
        "原文是把刚才300ml改成350ml",
        "〈把刚才300ml改成350ml〉是例句",
        "把刚才300ml改成350ml的话会怎样",
        "把刚才300ml改成350ml，这杯是给小明的",
        "把刚才300ml改成350ml，撤回这个修改",
        "把刚才300ml改成350ml，忽略这个修改",
        "把刚才300ml改成350ml，保持300ml不变",
        "把刚才300ml改成350ml，先不要执行这个修改",
        "‘把刚才300ml改成350ml’",
        "'把刚才300ml改成350ml'",
        "`把刚才300ml改成350ml`",
        "（把刚才300ml改成350ml）",
        "请解释：把刚才300ml改成350ml",
        "请解释1：300ml改成350ml",
        "把刚才300ml改成350ml会怎样",
        "替小明把刚才300ml改成350ml",
        "替我朋友把刚才300ml改成350ml",
        "帮小明把刚才300ml改成350ml",
        "帮小明把饮水记录718改成350ml",
        "我帮小明把刚才300ml改成350ml",
        "代小明把刚才300ml改成350ml",
        "有人提议把刚才300ml改成350ml",
        "有人提议把饮水记录718改成350ml",
        "群里让把刚才300ml改成350ml",
        "小明那杯刚才300ml，改成350ml",
        "示例（把刚才300ml改成350ml）",
        "把刚才300ml改成350ml，还是300ml吧",
        "把刚才300ml改成350ml，照旧",
        "把刚才300ml改成350ml，别动",
        "把刚才300ml改成350ml，恢复成300ml",
        "把刚才300ml改成350ml，这次不改",
        "把刚才300ml改成350ml，先别这么改",
        "把刚才300ml改成350ml，撤掉这次修改",
        "把刚才300ml改成350ml，不用做这个更改",
        "把刚才300ml改成350ml，等等，是400ml",
        "把刚才300ml改成350ml，不，是400ml",
        "把刚才300ml改成350ml，抱歉，是400ml",
        "把饮水记录999和饮水记录718的300ml改成350ml",
        "把饮水记录718和719的300ml改成350ml",
        "把饮水记录718、719的300ml改成350ml",
        "把刚才300ml改成350ml，哦不，400ml",
        "把刚才300ml改成350ml，哦不，是400",
        "把刚才300ml改成350ml，这是小明的",
        "把刚才300ml改成350ml，不是我的，是小明的",
        "把刚才300ml改成350ml，这杯水属于小明",
    ),
)
async def test_gateway_update_semantic_denials_never_dispatch(
    policy_mode,
    message,
):
    snapshot = replace(
        _snapshot(message, policy_mode=policy_mode),
        actionable_references=(
            ActionableReference(
                kind="owner_scoped_health_manage_list",
                data={
                    "record_type": "water",
                    "records": ({"id": 718, "amount": 300},),
                },
            ),
        ),
    )
    gateway = ToolGateway(snapshot)
    calls = []

    async def dispatch(request):
        calls.append(request)
        return "unexpected"

    result = await gateway.execute(
        ToolExecutionRequest(
            tool_name="health_manage",
            arguments={
                "record_type": "water",
                "operation": "update",
                "record_id": 718,
                "data": {"amount": 350},
            },
        ),
        dispatch,
    )

    assert calls == []
    assert result.decision is not None
    assert result.decision.reason in {
        "update_requires_exact_target_evidence",
        "manage_write_without_mutate_intent",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("policy_mode", ("enforce", "shadow"))
@pytest.mark.parametrize(
    "message",
    (
        "记录感冒，这个其实是小明的",
        "记录感冒，这条其实属于小明",
        "记录感冒，这不是我的而是小明的",
        "记录感冒，这其实是我孩子的",
    ),
)
async def test_gateway_posterior_third_party_owner_never_dispatches_health_write(
    policy_mode,
    message,
):
    gateway = ToolGateway(_snapshot(message, policy_mode=policy_mode))
    calls = []

    async def dispatch(request):
        calls.append(request)
        return "unexpected"

    result = await gateway.execute(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments={"record_type": "illness", "data": {"name": "感冒"}},
        ),
        dispatch,
    )

    assert calls == []
    assert result.decision is not None
    assert result.decision.action == "block"


@pytest.mark.asyncio
async def test_gateway_current_user_posterior_owner_keeps_health_write_authority():
    gateway = ToolGateway(_snapshot("记录感冒，这是我本人的"))
    calls = []

    async def dispatch(request):
        calls.append(request.arguments)
        return '{"id": 1}'

    result = await gateway.execute(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments={"record_type": "illness", "data": {"name": "感冒"}},
        ),
        dispatch,
    )

    assert result.decision is not None
    assert result.decision.action == "allow"
    assert calls == [{"record_type": "illness", "data": {"name": "感冒"}}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "arguments"),
    (
        (
            "小明早上的药都吃了，记录一下",
            {"record_type": "supplement_group", "data": {"timing": "morning"}},
        ),
        (
            "早上的药都吃完了，这是小明的，记录一下",
            {"record_type": "supplement_group", "data": {"timing": "morning"}},
        ),
        (
            "早上的药都吃了，记录给小明",
            {"record_type": "supplement_group", "data": {"timing": "morning"}},
        ),
        (
            "记住小明不吃香菜",
            {
                "record_type": "remember",
                "data": {"predicate": "忌口", "object_value": "不吃香菜"},
            },
        ),
        (
            "记住不吃香菜的是小明",
            {
                "record_type": "remember",
                "data": {"predicate": "忌口", "object_value": "不吃香菜的是小明"},
            },
        ),
        (
            "记住不吃香菜，这是小明的，记录一下",
            {
                "record_type": "remember",
                "data": {"predicate": "忌口", "object_value": "不吃香菜"},
            },
        ),
        (
            "小明到杭州了",
            {"record_type": "event", "data": {"title": "到达杭州"}},
        ),
        (
            "到杭州了，这是小明的，记一下",
            {"record_type": "event", "data": {"title": "到达杭州"}},
        ),
        (
            "到杭州了，这是小明的行程",
            {"record_type": "event", "data": {"title": "到达杭州"}},
        ),
        (
            "小明到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
        ),
        (
            "他到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
        ),
    ),
)
async def test_gateway_public_record_contract_never_borrows_third_party_subject(
    message,
    arguments,
):
    calls = []
    gateway = ToolGateway(_snapshot(message))

    async def dispatch(request):
        calls.append(request)
        return "unexpected"

    result = await gateway.execute(
        ToolExecutionRequest(tool_name="health_record", arguments=arguments),
        dispatch,
    )

    assert calls == []
    assert result.decision is not None
    assert result.decision.action == "block"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "把刚才300ml改成350ml，哦不，是400ml",
        "把刚才300ml改成350ml，哦不，400ml",
        "把刚才300ml改成350ml，哦不，是400",
        "把刚才300ml改成350ml，等等，是400ml",
        "把刚才300ml改成350ml，不，是400ml",
        "把刚才300ml改成350ml，抱歉，是400ml",
        "把刚才300ml改成350ml，哦不，是0.4升",
    ),
)
async def test_gateway_update_self_correction_authorizes_only_final_value(message):
    snapshot = replace(
        _snapshot(message),
        actionable_references=(
            ActionableReference(
                kind="owner_scoped_health_manage_list",
                data={
                    "record_type": "water",
                    "records": ({"id": 718, "amount": 300},),
                },
            ),
        ),
    )
    calls = []

    async def dispatch(request):
        calls.append(request.arguments)
        return '{"id": 718, "record_id": 718, "resource_type": "water_record"}'

    result = await ToolGateway(snapshot).execute(
        ToolExecutionRequest(
            tool_name="health_manage",
            arguments={
                "record_type": "water",
                "operation": "update",
                "record_id": 718,
                "data": {"amount": 400},
            },
        ),
        dispatch,
    )

    assert result.decision is not None
    assert result.decision.action == "allow"
    assert calls == [
        {
            "record_type": "water",
            "operation": "update",
            "record_id": 718,
            "data": {"amount": 400},
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("policy_mode", ("enforce", "shadow"))
async def test_executor_quoted_update_never_reaches_real_water_put(
    db,
    monkeypatch,
    policy_mode,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "typed"
    executor._current_turn_user_message = "原文如下：把刚才300ml改成350ml"
    calls = []

    async def fake_get(url, _headers):
        calls.append(("GET", url, None))
        return '[{"id": 718, "amount": 300}]'

    async def fake_put(url, _headers, payload):
        calls.append(("PUT", url, payload))
        return "unexpected"

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_kernel_policy_mode", policy_mode
    )
    monkeypatch.setattr(executor, "_api_get", fake_get)
    monkeypatch.setattr(executor, "_api_put", fake_put)

    await executor._execute_tool(
        "health_manage",
        {"record_type": "water", "operation": "list"},
        "test-token",
    )
    result = await executor._execute_tool(
        "health_manage",
        {
            "record_type": "water",
            "operation": "update",
            "record_id": 718,
            "data": {"amount": 350},
        },
        "test-token",
    )

    assert [method for method, _url, _payload in calls] == ["GET"]
    assert json.loads(result)["dispatch_started"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("policy_mode", ("enforce", "shadow"))
@pytest.mark.parametrize(
    "message",
    (
        "原文是把刚才300ml改成350ml",
        "〈把刚才300ml改成350ml〉是例句",
        "把刚才300ml改成350ml的话会怎样",
        "把刚才300ml改成350ml，这杯是给小明的",
        "把刚才300ml改成350ml，撤回这个修改",
        "把刚才300ml改成350ml，忽略这个修改",
        "把刚才300ml改成350ml，保持300ml不变",
        "把刚才300ml改成350ml，先不要执行这个修改",
        "替我朋友把刚才300ml改成350ml",
        "帮小明把刚才300ml改成350ml",
        "帮小明把饮水记录718改成350ml",
        "我帮小明把刚才300ml改成350ml",
        "代小明把刚才300ml改成350ml",
        "有人提议把刚才300ml改成350ml",
        "有人提议把饮水记录718改成350ml",
        "群里让把刚才300ml改成350ml",
        "小明那杯刚才300ml，改成350ml",
        "示例（把刚才300ml改成350ml）",
        "把刚才300ml改成350ml，这次不改",
        "把刚才300ml改成350ml，先别这么改",
        "把刚才300ml改成350ml，撤掉这次修改",
        "把刚才300ml改成350ml，不用做这个更改",
        "请解释1：300ml改成350ml",
    ),
)
async def test_executor_non_authorizing_update_never_reaches_real_water_put(
    db,
    monkeypatch,
    policy_mode,
    message,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "typed"
    executor._current_turn_user_message = message
    calls = []

    async def fake_get(url, _headers):
        calls.append(("GET", url, None))
        return '[{"id": 718, "amount": 300}]'

    async def fake_put(url, _headers, payload):
        calls.append(("PUT", url, payload))
        return "unexpected"

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_kernel_policy_mode", policy_mode
    )
    monkeypatch.setattr(executor, "_api_get", fake_get)
    monkeypatch.setattr(executor, "_api_put", fake_put)

    await executor._execute_tool(
        "health_manage",
        {"record_type": "water", "operation": "list"},
        "test-token",
    )
    result = await executor._execute_tool(
        "health_manage",
        {
            "record_type": "water",
            "operation": "update",
            "record_id": 718,
            "data": {"amount": 350},
        },
        "test-token",
    )

    assert [method for method, _url, _payload in calls] == ["GET"]
    assert json.loads(result)["dispatch_started"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("policy_mode", ("enforce", "shadow"))
@pytest.mark.parametrize(
    "message",
    (
        "把刚才300ml改成350ml，哦不，400ml",
        "把刚才300ml改成350ml，哦不，是400",
        "把刚才300ml改成350ml，等等，是400ml",
        "把刚才300ml改成350ml，不，是400ml",
        "把刚才300ml改成350ml，抱歉，是400ml",
        "把刚才300ml改成350ml，哦不，是0.4升",
    ),
)
async def test_executor_water_correction_dispatches_only_final_value(
    db,
    monkeypatch,
    policy_mode,
    message,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "typed"
    executor._current_turn_user_message = message
    calls = []

    async def fake_get(url, _headers):
        calls.append(("GET", url, None))
        return '[{"id": 718, "amount": 300}]'

    async def fake_put(url, _headers, payload):
        calls.append(("PUT", url, payload))
        return '{"id":718,"amount":400}'

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_kernel_policy_mode", policy_mode
    )
    monkeypatch.setattr(executor, "_api_get", fake_get)
    monkeypatch.setattr(executor, "_api_put", fake_put)

    await executor._execute_tool(
        "health_manage",
        {"record_type": "water", "operation": "list"},
        "test-token",
    )
    rejected = await executor._execute_tool(
        "health_manage",
        {
            "record_type": "water",
            "operation": "update",
            "record_id": 718,
            "data": {"amount": 350},
        },
        "test-token",
    )
    accepted = await executor._execute_tool(
        "health_manage",
        {
            "record_type": "water",
            "operation": "update",
            "record_id": 718,
            "data": {"amount": 400},
        },
        "test-token",
    )
    wrong_unit = await executor._execute_tool(
        "health_manage",
        {
            "record_type": "water",
            "operation": "update",
            "record_id": 718,
            "data": {"amount": 0.4},
        },
        "test-token",
    )

    assert json.loads(rejected)["dispatch_started"] is False
    assert json.loads(wrong_unit)["dispatch_started"] is False
    assert [call for call in calls if call[0] == "PUT"] == [
        ("PUT", "http://localhost:8000/api/v1/water/records/718", {"amount": 400})
    ]
    assert json.loads(accepted)["amount"] == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("policy_mode", ("enforce", "shadow"))
@pytest.mark.parametrize(
    "message",
    (
        "把刚才300ml改成350ml",
        "请把饮水记录718（300ml）修改为350ml",
        "请把我的饮水记录718改成350ml",
        "请把我自己的饮水记录718改成350ml",
        "请把我个人的饮水记录718改成350ml",
        "请把属于我的饮水记录718改成350ml",
    ),
)
async def test_executor_direct_water_update_syntax_dispatches_canonical_value(
    db,
    monkeypatch,
    policy_mode,
    message,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "typed"
    executor._current_turn_user_message = message
    calls = []

    async def fake_get(url, _headers):
        calls.append(("GET", url, None))
        return '[{"id": 718, "amount": 300}]'

    async def fake_put(url, _headers, payload):
        calls.append(("PUT", url, payload))
        return '{"id":718,"amount":350}'

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_kernel_policy_mode",
        policy_mode,
    )
    monkeypatch.setattr(executor, "_api_get", fake_get)
    monkeypatch.setattr(executor, "_api_put", fake_put)

    await executor._execute_tool(
        "health_manage",
        {"record_type": "water", "operation": "list"},
        "test-token",
    )
    result = await executor._execute_tool(
        "health_manage",
        {
            "record_type": "water",
            "operation": "update",
            "record_id": 718,
            "data": {"amount": 350},
        },
        "test-token",
    )

    assert [method for method, _url, _payload in calls] == ["GET", "PUT"]
    assert calls[-1][2] == {"amount": 350}
    assert json.loads(result)["amount"] == 350


@pytest.mark.asyncio
@pytest.mark.parametrize("policy_mode", ("enforce", "shadow"))
@pytest.mark.parametrize(
    ("message", "proposed_amount"),
    (
        ("把刚才300ml改成350ml，不是400ml", 400),
        ("把刚才300ml改成350ml，不，是300ml", 300),
    ),
)
async def test_executor_negated_or_noop_water_correction_never_reaches_real_put(
    db,
    monkeypatch,
    policy_mode,
    message,
    proposed_amount,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "typed"
    executor._current_turn_user_message = message
    calls = []

    async def fake_get(url, _headers):
        calls.append(("GET", url, None))
        return '[{"id": 718, "amount": 300}]'

    async def fake_put(url, _headers, payload):
        calls.append(("PUT", url, payload))
        return "unexpected"

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_kernel_policy_mode",
        policy_mode,
    )
    monkeypatch.setattr(executor, "_api_get", fake_get)
    monkeypatch.setattr(executor, "_api_put", fake_put)

    await executor._execute_tool(
        "health_manage",
        {"record_type": "water", "operation": "list"},
        "test-token",
    )
    result = await executor._execute_tool(
        "health_manage",
        {
            "record_type": "water",
            "operation": "update",
            "record_id": 718,
            "data": {"amount": proposed_amount},
        },
        "test-token",
    )

    assert [method for method, _url, _payload in calls] == ["GET"]
    assert json.loads(result)["dispatch_started"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("policy_mode", ("enforce", "shadow"))
@pytest.mark.parametrize(
    "message",
    (
        "舌尖溃疡昨天并没有好转，修改记录",
        "舌尖溃疡昨天并非好转，修改记录",
        "舌尖溃疡昨天好转但今天加重了，修改记录",
        "舌尖溃疡昨天好了又发作了，修改记录",
        "舌尖溃疡昨天痊愈后今天复发，修改记录",
        "舌尖溃疡记录999昨天好了，修改记录",
        "舌尖溃疡昨天并无好转，修改记录",
        "舌尖溃疡昨天尚无好转，修改记录",
        "舌尖溃疡昨天绝非好转，修改记录",
        "舌尖溃疡昨天算不上好转，修改记录",
        "舌尖溃疡昨天好转不了，修改记录",
        "舌尖溃疡记录编号999昨天好了，修改记录",
        "舌尖溃疡记录ID999昨天好了，修改记录",
        "舌尖溃疡昨天看不出好转，修改记录",
        "舌尖溃疡昨天似乎好转，修改记录",
        "舌尖溃疡昨天好了今天又犯了，修改记录",
        "舌尖溃疡昨天好转同时今天更严重了，修改记录",
        "舌尖溃疡没有证据表明已经康复，修改记录",
        "舌尖溃疡第999号记录昨天好了，修改记录",
        "舌尖溃疡记录编号为999昨天好了，修改记录",
        "舌尖溃疡第999条疾病记录昨天好了，修改记录",
        "舌尖溃疡疾病记录第999号昨天好了，修改记录",
        "舌尖溃疡未见好转，修改记录",
        "舌尖溃疡没有出现好转，修改记录",
        "舌尖溃疡康复尚未证实，修改记录",
        "舌尖溃疡没有理由认为已经康复，修改记录",
        "舌尖溃疡大概正在逐步好转，修改记录",
        "舌尖溃疡不代表已经好转，修改记录",
        "舌尖溃疡昨天好了今天又疼了，修改记录",
        "舌尖溃疡尚未观察到好转，修改记录",
        "舌尖溃疡不能说明已经康复，修改记录",
        "舌尖溃疡据说已经好转，修改记录",
        "舌尖溃疡好转存疑，修改记录",
        "舌尖溃疡还没好只是猜测，修改记录",
        "舌尖溃疡正在发作中尚未确认，修改记录",
    ),
)
async def test_executor_unauthorized_or_ambiguous_illness_update_never_reaches_real_put(
    db,
    monkeypatch,
    policy_mode,
    message,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "typed"
    executor._current_turn_user_message = message
    calls = []

    async def fake_exec(_base, _headers, arguments):
        calls.append(arguments)
        if arguments["operation"] == "list":
            return json.dumps(
                [{"id": 71, "name": "舌尖溃疡", "status": "active"}],
                ensure_ascii=False,
            )
        return "unexpected"

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_kernel_policy_mode",
        policy_mode,
    )
    monkeypatch.setattr(executor, "_exec_health_manage", fake_exec)

    await executor._execute_tool(
        "health_manage",
        {"record_type": "illness", "operation": "list"},
        "test-token",
    )
    result = await executor._execute_tool(
        "health_manage",
        {
            "record_type": "illness",
            "operation": "update",
            "record_id": 71,
            "data": {"status": "improving"},
        },
        "test-token",
    )

    assert [call["operation"] for call in calls] == ["list"]
    assert json.loads(result)["dispatch_started"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("policy_mode", ("enforce", "shadow"))
async def test_executor_clear_active_illness_update_reaches_real_adapter(
    db,
    monkeypatch,
    policy_mode,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "typed"
    executor._current_turn_user_message = "舌尖溃疡还没好，修改记录"
    calls = []

    async def fake_exec(_base, _headers, arguments):
        calls.append(arguments)
        if arguments["operation"] == "list":
            return json.dumps(
                [{"id": 71, "name": "舌尖溃疡", "status": "improving"}],
                ensure_ascii=False,
            )
        return json.dumps({"id": 71, "status": "active"}, ensure_ascii=False)

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_kernel_policy_mode",
        policy_mode,
    )
    monkeypatch.setattr(executor, "_exec_health_manage", fake_exec)

    await executor._execute_tool(
        "health_manage",
        {"record_type": "illness", "operation": "list"},
        "test-token",
    )
    result = await executor._execute_tool(
        "health_manage",
        {
            "record_type": "illness",
            "operation": "update",
            "record_id": 71,
            "data": {"status": "active"},
        },
        "test-token",
    )

    assert [call["operation"] for call in calls] == ["list", "update"]
    assert calls[-1]["data"] == {"status": "active"}
    assert json.loads(result)["status"] == "active"


@pytest.mark.asyncio
@pytest.mark.parametrize("policy_mode", ("enforce", "shadow"))
@pytest.mark.parametrize(
    "message",
    (
        "舌尖溃疡已经明显改善，修改记录",
        "舌尖溃疡未用药就好转，修改记录",
        "舌尖溃疡没有加重反而明显改善，修改记录",
    ),
)
async def test_executor_clear_improvement_paraphrase_reaches_real_adapter(
    db,
    monkeypatch,
    policy_mode,
    message,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "typed"
    executor._current_turn_user_message = message
    calls = []

    async def fake_exec(_base, _headers, arguments):
        calls.append(arguments)
        if arguments["operation"] == "list":
            return json.dumps(
                [{"id": 71, "name": "舌尖溃疡", "status": "active"}],
                ensure_ascii=False,
            )
        return json.dumps({"id": 71, "status": "improving"}, ensure_ascii=False)

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_kernel_policy_mode",
        policy_mode,
    )
    monkeypatch.setattr(executor, "_exec_health_manage", fake_exec)

    await executor._execute_tool(
        "health_manage",
        {"record_type": "illness", "operation": "list"},
        "test-token",
    )
    result = await executor._execute_tool(
        "health_manage",
        {
            "record_type": "illness",
            "operation": "update",
            "record_id": 71,
            "data": {"status": "improving"},
        },
        "test-token",
    )

    assert [call["operation"] for call in calls] == ["list", "update"]
    assert calls[-1]["data"] == {"status": "improving"}
    assert json.loads(result)["status"] == "improving"


@pytest.mark.asyncio
@pytest.mark.parametrize("policy_mode", ("enforce", "shadow"))
@pytest.mark.parametrize(
    "message",
    (
        "舌尖溃疡并非还在发作中，修改记录",
        "舌尖溃疡可能还没好，修改记录",
    ),
)
async def test_executor_uncertain_or_negated_active_illness_never_puts(
    db,
    monkeypatch,
    policy_mode,
    message,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "typed"
    executor._current_turn_user_message = message
    calls = []

    async def fake_exec(_base, _headers, arguments):
        calls.append(arguments)
        if arguments["operation"] == "list":
            return json.dumps(
                [{"id": 71, "name": "舌尖溃疡", "status": "improving"}],
                ensure_ascii=False,
            )
        return "unexpected"

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_kernel_policy_mode",
        policy_mode,
    )
    monkeypatch.setattr(executor, "_exec_health_manage", fake_exec)

    await executor._execute_tool(
        "health_manage",
        {"record_type": "illness", "operation": "list"},
        "test-token",
    )
    result = await executor._execute_tool(
        "health_manage",
        {
            "record_type": "illness",
            "operation": "update",
            "record_id": 71,
            "data": {"status": "active"},
        },
        "test-token",
    )

    assert [call["operation"] for call in calls] == ["list"]
    assert json.loads(result)["dispatch_started"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("policy_mode", ("enforce", "shadow"))
@pytest.mark.parametrize(
    "message",
    (
        "原文：到杭州了",
        "原话：到杭州了",
        "例句：到杭州了",
        "消息内容：到杭州了",
        "示例文本：到杭州了",
        "老婆发来消息：到杭州了",
        "群消息：到杭州了",
        "日志23:45，到杭州了",
        "记录小明到杭州了，记录生活事件：到达杭州",
        "今天到杭州了（这是小明的行程），记录生活事件：到达杭州",
        "今天到杭州了（小明的行程），记录生活事件：到达杭州",
        "今天到杭州了，来自群消息，记录生活事件：到达杭州",
        "今天到杭州了，摘录自群消息，记录生活事件：到达杭州",
        "今天到杭州了，据群消息，记录生活事件：到达杭州",
        "今天到杭州了，据日志，记录生活事件：到达杭州",
        "今天到杭州了，按群消息，记录生活事件：到达杭州",
        "今天到杭州了，按照群消息，记录生活事件：到达杭州",
        "今天到杭州了（转发消息），记录生活事件：到达杭州",
        "今天到杭州了（小明行程），记录生活事件：到达杭州",
        "今天到杭州了（行程归小明），记录生活事件：到达杭州",
        "今天到杭州了（行程属于小明），记录生活事件：到达杭州",
        "今天到杭州了，参照群消息，记录生活事件：到达杭州",
        "今天到杭州了，照群消息，记录生活事件：到达杭州",
        "今天到杭州了，基于群消息，记录生活事件：到达杭州",
        "今天到杭州了，参考群消息，记录生活事件：到达杭州",
        "今天到杭州了（行程归Alex），记录生活事件：到达杭州",
        "今天到杭州了（这趟行程归小明），记录生活事件：到达杭州",
        "今天到杭州了（小明的这次行程），记录生活事件：到达杭州",
        "今天到杭州了，记录生活事件（本次行程属于小明）",
        "今天到杭州了（朋友转达），记录生活事件：到达杭州",
        "今天到杭州了（群消息截图），记录生活事件：到达杭州",
        "今天到杭州了（取自群聊），记录生活事件：到达杭州",
        "今天到杭州了（微信截图），记录生活事件：到达杭州",
        "今天到杭州了（朋友说的），记录生活事件：到达杭州",
        "今天到杭州了（本次旅程属于Alex），记录生活事件：到达杭州",
        "今天到杭州了（这次出行归小明），记录生活事件：到达杭州",
    ),
)
async def test_executor_metalinguistic_event_never_reaches_real_event_post(
    db,
    monkeypatch,
    policy_mode,
    message,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "typed"
    executor._current_turn_user_message = message
    calls = []

    async def fake_post(url, _headers, payload):
        calls.append((url, payload))
        return "unexpected"

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_kernel_policy_mode", policy_mode
    )
    monkeypatch.setattr(executor, "_api_post", fake_post)

    result = await executor._execute_tool(
        "health_record",
        {"record_type": "event", "data": {"title": "到达杭州"}},
        "test-token",
    )

    assert calls == []
    assert json.loads(result)["dispatch_started"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("policy_mode", ("enforce", "shadow"))
@pytest.mark.parametrize(
    ("message", "arguments"),
    (
        (
            "记住不吃香菜的是小明",
            {
                "record_type": "remember",
                "data": {"predicate": "忌口", "object_value": "不吃香菜的是小明"},
            },
        ),
        (
            "小明到杭州了",
            {"record_type": "event", "data": {"title": "到达杭州"}},
        ),
        (
            "小明早上的药都吃了，记录一下",
            {"record_type": "supplement_group", "data": {"timing": "morning"}},
        ),
        (
            "早上的药都吃完了，这是小明的，记录一下",
            {"record_type": "supplement_group", "data": {"timing": "morning"}},
        ),
        (
            "早上的药都吃了，记录给小明",
            {"record_type": "supplement_group", "data": {"timing": "morning"}},
        ),
        (
            "记住不吃香菜，这是小明的，记录一下",
            {
                "record_type": "remember",
                "data": {"predicate": "忌口", "object_value": "不吃香菜"},
            },
        ),
        (
            "到杭州了，这是小明的，记一下",
            {"record_type": "event", "data": {"title": "到达杭州"}},
        ),
        (
            "到杭州了，这是小明的行程",
            {"record_type": "event", "data": {"title": "到达杭州"}},
        ),
        (
            "小明到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
        ),
        (
            "他到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
        ),
    ),
)
async def test_executor_third_party_public_contract_never_posts(
    db,
    monkeypatch,
    policy_mode,
    message,
    arguments,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "typed"
    executor._current_turn_user_message = message
    calls = []

    async def fake_post(url, _headers, payload):
        calls.append((url, payload))
        return "unexpected"

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_kernel_policy_mode", policy_mode
    )
    monkeypatch.setattr(executor, "_api_post", fake_post)

    result = await executor._execute_tool("health_record", arguments, "test-token")

    assert calls == []
    assert json.loads(result)["dispatch_started"] is False


@pytest.mark.asyncio
async def test_gateway_explicit_update_id_without_owner_candidate_never_dispatches():
    gateway = ToolGateway(_snapshot("把饮水记录999999的300ml改成350ml"))
    calls = []

    async def dispatch(request):
        calls.append(request)
        return "unexpected"

    result = await gateway.execute(
        ToolExecutionRequest(
            tool_name="health_manage",
            arguments={
                "record_type": "water",
                "operation": "update",
                "record_id": 999999,
                "data": {"amount": 350},
            },
        ),
        dispatch,
    )

    assert calls == []
    assert result.decision is not None
    assert result.decision.reason == "update_requires_exact_target_evidence"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "arguments", "expected_data"),
    (
        (
            "记一下我鞋码42.5",
            {
                "record_type": "remember",
                "data": {
                    "predicate": "鞋码",
                    "object_value": "42.5",
                    "subject": "模型",
                },
            },
            {"subject": "用户", "predicate": "鞋码", "object_value": "42.5"},
        ),
        (
            "记录生活事件：落地北京",
            {"record_type": "event", "data": {"title": "落地北京", "notes": "模型"}},
            {"title": "落地北京"},
        ),
        (
            "早上的补剂都吃了，记录一下",
            {"record_type": "supplement_group", "data": {"timing": "morning"}},
            {"timing": "morning"},
        ),
        (
            "早上的药都吃了，记录一下",
            {"record_type": "supplement_group", "data": {"timing": "morning"}},
            {"timing": "morning"},
        ),
        (
            "早上的药都吃完了，记录一下",
            {"record_type": "supplement_group", "data": {"timing": "morning"}},
            {"timing": "morning"},
        ),
        (
            "我早上的药全吃完了，帮我记一下",
            {"record_type": "supplement_group", "data": {"timing": "morning"}},
            {"timing": "morning"},
        ),
        (
            "记住我不吃香菜",
            {
                "record_type": "remember",
                "data": {"predicate": "忌口", "object_value": "不吃香菜"},
            },
            {"subject": "用户", "predicate": "忌口", "object_value": "不吃香菜"},
        ),
        (
            "请帮我记住我不吃香菜",
            {
                "record_type": "remember",
                "data": {"predicate": "忌口", "object_value": "不吃香菜"},
            },
            {"subject": "用户", "predicate": "忌口", "object_value": "不吃香菜"},
        ),
        (
            "我不吃香菜，帮我记住",
            {
                "record_type": "remember",
                "data": {"predicate": "忌口", "object_value": "不吃香菜"},
            },
            {"subject": "用户", "predicate": "忌口", "object_value": "不吃香菜"},
        ),
        (
            "到杭州了",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            {"title": "到达杭州"},
        ),
        (
            "我到杭州了，记录一下",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            {"title": "到达杭州"},
        ),
        (
            "我刚到杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            {"title": "到达杭州"},
        ),
        (
            "今天到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            {"title": "到达杭州"},
        ),
        (
            "昨天早上到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            {"title": "到达杭州"},
        ),
        (
            "昨天下午三点到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            {
                "title": "到达杭州",
                "occurred_at": "2026-07-16T15:00:00+08:00",
            },
        ),
        (
            "昨天下午3点半到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            {
                "title": "到达杭州",
                "occurred_at": "2026-07-16T15:30:00+08:00",
            },
        ),
        (
            "昨天下午3点一刻到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            {
                "title": "到达杭州",
                "occurred_at": "2026-07-16T15:15:00+08:00",
            },
        ),
        (
            "昨天中午一点半到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            {
                "title": "到达杭州",
                "occurred_at": "2026-07-16T13:30:00+08:00",
            },
        ),
        (
            "今天凌晨到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            {"title": "到达杭州"},
        ),
        (
            "今天傍晚到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            {"title": "到达杭州"},
        ),
        (
            "昨天到杭州了（我的行程），记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            {"title": "到达杭州"},
        ),
        (
            "昨天凌晨三点半到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            {
                "title": "到达杭州",
                "occurred_at": "2026-07-16T03:30:00+08:00",
            },
        ),
        (
            "昨天凌晨三点一刻到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            {
                "title": "到达杭州",
                "occurred_at": "2026-07-16T03:15:00+08:00",
            },
        ),
        (
            "今天零点到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            {
                "title": "到达杭州",
                "occurred_at": "2026-07-17T00:00:00+08:00",
            },
        ),
        (
            "昨天下午三点半钟到杭州了，记录生活事件：到达杭州",
            {
                "record_type": "event",
                "data": {
                    "title": "到达杭州",
                    "occurred_at": "昨天15:30",
                },
            },
            {
                "title": "到达杭州",
                "occurred_at": "2026-07-16T15:30:00+08:00",
            },
        ),
        (
            "记录跑步30分钟5公里",
            {
                "record_type": "exercise",
                "data": {"exercise_type": "跑步", "duration": 30, "distance": 5},
            },
            {"exercise_type": "跑步", "duration": 30, "distance": 5},
        ),
    ),
)
async def test_gateway_dispatches_supported_family_canonical_projection(
    message,
    arguments,
    expected_data,
):
    gateway = ToolGateway(_snapshot(message))
    calls = []

    async def dispatch(request):
        calls.append(request.arguments)
        return '{"id": 1}'

    result = await gateway.execute(
        ToolExecutionRequest(tool_name="health_record", arguments=arguments),
        dispatch,
    )

    assert result.decision is not None
    assert result.decision.action == "allow"
    assert calls == [{"record_type": arguments["record_type"], "data": expected_data}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "arguments", "expected_path", "expected_payload"),
    (
        (
            "早上的药都吃了，记录一下",
            {"record_type": "supplement_group", "data": {"timing": "morning"}},
            "/nfc/tap",
            {"action": "supplement_group", "timing": "morning"},
        ),
        (
            "我早上的药全吃完了，帮我记一下",
            {"record_type": "supplement_group", "data": {"timing": "morning"}},
            "/nfc/tap",
            {"action": "supplement_group", "timing": "morning"},
        ),
        (
            "早上的药都吃完了，记录一下",
            {"record_type": "supplement_group", "data": {"timing": "morning"}},
            "/nfc/tap",
            {"action": "supplement_group", "timing": "morning"},
        ),
        (
            "记住我不吃香菜",
            {
                "record_type": "remember",
                "data": {"predicate": "忌口", "object_value": "不吃香菜"},
            },
            "/memory-facts",
            {
                "tier": "semantic",
                "subject": "用户",
                "predicate": "忌口",
                "object_value": "不吃香菜",
                "object_unit": None,
                "confidence": 0.9,
                "is_sensitive": False,
            },
        ),
        (
            "请帮我记住我不吃香菜",
            {
                "record_type": "remember",
                "data": {"predicate": "忌口", "object_value": "不吃香菜"},
            },
            "/memory-facts",
            {
                "tier": "semantic",
                "subject": "用户",
                "predicate": "忌口",
                "object_value": "不吃香菜",
                "object_unit": None,
                "confidence": 0.9,
                "is_sensitive": False,
            },
        ),
        (
            "我不吃香菜，帮我记住",
            {
                "record_type": "remember",
                "data": {"predicate": "忌口", "object_value": "不吃香菜"},
            },
            "/memory-facts",
            {
                "tier": "semantic",
                "subject": "用户",
                "predicate": "忌口",
                "object_value": "不吃香菜",
                "object_unit": None,
                "confidence": 0.9,
                "is_sensitive": False,
            },
        ),
        (
            "到杭州了",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            "/episodes/life-event",
            {"title": "到达杭州"},
        ),
        (
            "我到杭州了，记录一下",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            "/episodes/life-event",
            {"title": "到达杭州"},
        ),
        (
            "我刚到杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            "/episodes/life-event",
            {"title": "到达杭州"},
        ),
        (
            "今天到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            "/episodes/life-event",
            {"title": "到达杭州"},
        ),
        (
            "昨天早上到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            "/episodes/life-event",
            {"title": "到达杭州"},
        ),
        (
            "昨天下午三点到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            "/episodes/life-event",
            {
                "title": "到达杭州",
                "occurred_at": "2026-07-16T15:00:00+08:00",
            },
        ),
        (
            "昨天下午3点半到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            "/episodes/life-event",
            {
                "title": "到达杭州",
                "occurred_at": "2026-07-16T15:30:00+08:00",
            },
        ),
        (
            "昨天下午3点一刻到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            "/episodes/life-event",
            {
                "title": "到达杭州",
                "occurred_at": "2026-07-16T15:15:00+08:00",
            },
        ),
        (
            "昨天中午一点半到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            "/episodes/life-event",
            {
                "title": "到达杭州",
                "occurred_at": "2026-07-16T13:30:00+08:00",
            },
        ),
        (
            "今天凌晨到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            "/episodes/life-event",
            {"title": "到达杭州"},
        ),
        (
            "今天傍晚到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            "/episodes/life-event",
            {"title": "到达杭州"},
        ),
        (
            "昨天到杭州了（我的行程），记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            "/episodes/life-event",
            {"title": "到达杭州"},
        ),
        (
            "昨天凌晨三点半到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            "/episodes/life-event",
            {
                "title": "到达杭州",
                "occurred_at": "2026-07-16T03:30:00+08:00",
            },
        ),
        (
            "昨天凌晨三点一刻到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            "/episodes/life-event",
            {
                "title": "到达杭州",
                "occurred_at": "2026-07-16T03:15:00+08:00",
            },
        ),
        (
            "今天零点到杭州了，记录生活事件：到达杭州",
            {"record_type": "event", "data": {"title": "到达杭州"}},
            "/episodes/life-event",
            {
                "title": "到达杭州",
                "occurred_at": "2026-07-17T00:00:00+08:00",
            },
        ),
        (
            "昨天下午三点半钟到杭州了，记录生活事件：到达杭州",
            {
                "record_type": "event",
                "data": {
                    "title": "到达杭州",
                    "occurred_at": "昨天15:30",
                },
            },
            "/episodes/life-event",
            {
                "title": "到达杭州",
                "occurred_at": "2026-07-16T15:30:00+08:00",
            },
        ),
    ),
)
async def test_executor_dispatches_public_record_contract_through_real_gateway(
    db,
    monkeypatch,
    message,
    arguments,
    expected_path,
    expected_payload,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "typed"
    executor._current_turn_user_message = message
    executor._current_turn_recent_messages = []
    if "occurred_at" in expected_payload:
        executor._agent_kernel_snapshot = _snapshot(message, channel="typed")
    calls = []

    async def fake_post(url, _headers, payload):
        calls.append((url, payload))
        return '{"id": 91, "record_id": 91, "status": "recorded"}'

    monkeypatch.setattr(executor, "_api_post", fake_post)

    result = await executor._execute_tool("health_record", arguments, "test-token")

    assert calls and calls[0][0].endswith(expected_path)
    assert calls[0][1] == expected_payload
    assert json.loads(result)["id"] == 91


@pytest.mark.asyncio
@pytest.mark.parametrize("policy_mode", ("enforce", "shadow"))
async def test_executor_ambiguous_related_event_times_never_post(
    db,
    monkeypatch,
    policy_mode,
):
    message = "昨天下午三点到杭州了，今天下午四点到杭州了，记录生活事件：到达杭州"
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "typed"
    executor._current_turn_user_message = message
    executor._agent_kernel_snapshot = _snapshot(message, channel="typed")
    calls = []

    async def fake_post(url, _headers, payload):
        calls.append((url, payload))
        return "unexpected"

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_kernel_policy_mode",
        policy_mode,
    )
    monkeypatch.setattr(executor, "_api_post", fake_post)

    result = await executor._execute_tool(
        "health_record",
        {"record_type": "event", "data": {"title": "到达杭州"}},
        "test-token",
    )

    assert calls == []
    assert json.loads(result)["dispatch_started"] is False


@pytest.mark.asyncio
async def test_executor_lists_owner_illness_before_exact_resolution_update(
    db,
    monkeypatch,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "typed"
    executor._current_turn_user_message = "舌尖溃疡昨天好了，修改记录"
    expected_end_date = (
        executor._agent_kernel_reference_now().date() - timedelta(days=1)
    ).isoformat()
    calls = []

    async def fake_exec(_base, _headers, arguments):
        calls.append(arguments)
        if arguments["operation"] == "list":
            return json.dumps(
                [{"id": 71, "name": "舌尖溃疡", "status": "active"}],
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "id": 71,
                "record_id": 71,
                "resource_type": "illness_episode",
                "status": "resolved",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(executor, "_exec_health_manage", fake_exec)

    await executor._execute_tool(
        "health_manage",
        {"record_type": "illness", "operation": "list"},
        "test-token",
    )
    result = await executor._execute_tool(
        "health_manage",
        {
            "record_type": "illness",
            "operation": "update",
            "record_id": 71,
            "data": {"status": "resolved", "end_date": expected_end_date},
        },
        "test-token",
    )

    assert [call["operation"] for call in calls] == ["list", "update"]
    assert calls[-1] == {
        "record_type": "illness",
        "operation": "update",
        "record_id": 71,
        "data": {"status": "resolved", "end_date": expected_end_date},
    }
    assert json.loads(result)["record_id"] == 71


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected_reason"),
    (
        ("把刚才 300ml 改成 350ml", "manage_operation_mismatch"),
        (
            "删除上一条饮水记录",
            "delete_requires_explicit_whole_record_intent",
        ),
    ),
)
async def test_gateway_execute_shadow_hard_destructive_denial_never_dispatches(
    message,
    expected_reason,
):
    gateway = ToolGateway(_snapshot(message, policy_mode="shadow"))
    dispatched = False
    request = ToolExecutionRequest(
        tool_name="health_manage",
        arguments={
            "record_type": "water",
            "operation": "delete",
            "record_id": 718,
        },
    )

    async def dispatch(_request):
        nonlocal dispatched
        dispatched = True
        return "unexpected"

    result = await gateway.execute(request, dispatch)

    assert dispatched is False
    assert result.decision is not None
    assert result.decision.reason == expected_reason
    payload = json.loads(result.content)
    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "arguments"),
    (
        (
            "记录感冒",
            {
                "record_type": "illness",
                "data": {"name": "感冒", "severity": 9, "notes": "MODEL"},
            },
        ),
        (
            "记录跑步30分钟",
            {"record_type": "illness", "data": {"name": "流感"}},
        ),
    ),
)
async def test_gateway_shadow_never_dispatches_rejected_health_record_targets(
    message,
    arguments,
):
    gateway = ToolGateway(_snapshot(message, policy_mode="shadow"))
    calls = []

    async def dispatch(request):
        calls.append(request)
        return "unexpected"

    result = await gateway.execute(
        ToolExecutionRequest(tool_name="health_record", arguments=arguments),
        dispatch,
    )

    assert calls == []
    assert result.decision is not None
    assert result.decision.action == "block"
    assert result.decision.reason == "health_record_target_mismatch"
    assert json.loads(result.content)["dispatch_started"] is False


@pytest.mark.asyncio
async def test_gateway_execute_unknown_policy_mode_fails_closed_before_dispatch():
    gateway = ToolGateway(_snapshot("记录午餐吃了牛肉面", policy_mode="enfroce"))
    dispatched = False
    request = ToolExecutionRequest(
        tool_name="health_record",
        arguments={"record_type": "diet", "data": {"food_items": "牛肉面"}},
    )

    async def dispatch(_request):
        nonlocal dispatched
        dispatched = True
        return "unexpected"

    with pytest.raises(ToolPreflightError, match="tool_preflight_failed"):
        await gateway.execute(request, dispatch)

    assert dispatched is False


@pytest.mark.asyncio
async def test_execute_tool_blocks_policy_denied_health_record_before_dispatch(
    db, monkeypatch
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "今天我的饮食的记录，帮我列个表格出来。"

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
            {"record_type": "diet", "data": {"food_items": "米饭"}}, ensure_ascii=False
        ),
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
@pytest.mark.parametrize(
    "proposed_args",
    (
        {"dimension": "illness"},
        {"dimension": "illness", "keyword": "感冒", "days": 7},
        {"dimension": "comprehensive"},
        {"dimension": "sleep", "days": 7},
    ),
)
async def test_historical_illness_query_is_projected_to_turn_entity_and_window(
    proposed_args,
):
    gateway = ToolGateway(_snapshot("最近半年口腔溃疡有哪些记录？"))
    calls = []

    async def dispatch(request):
        calls.append(request.arguments)
        return "[]"

    result = await gateway.execute(
        ToolExecutionRequest(
            tool_name="health_query",
            arguments=proposed_args,
            source="structured",
        ),
        dispatch,
    )

    assert result.decision is not None
    assert result.decision.action == "allow"
    assert calls == [
        {
            "dimension": "illness",
            "keyword": "口腔溃疡",
            "days": 183,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "proposed_args", "expected_args"),
    (
        (
            "我上一次扁桃体炎是什么时候 最近半年分别有哪些记录",
            {"dimension": "illness"},
            {"dimension": "illness", "keyword": "扁桃体炎", "days": 183},
        ),
        (
            "我上一次哮喘是什么时候 最近半年分别有哪些记录",
            {"dimension": "illness"},
            {"dimension": "illness", "keyword": "哮喘", "days": 183},
        ),
        (
            "我上一次扁桃体炎是什么时候 最近半年分别有哪些记录",
            {"dimension": "illness", "keyword": "感冒", "days": 7},
            {"dimension": "illness", "keyword": "扁桃体炎", "days": 183},
        ),
        (
            "最近一年口腔溃疡有哪些记录？",
            {"dimension": "illness", "keyword": "口腔溃疡", "days": 365},
            {"dimension": "illness", "keyword": "口腔溃疡", "days": 365},
        ),
        (
            "最近两年口腔溃疡有哪些记录？",
            {"dimension": "illness", "keyword": "口腔溃疡", "days": 730},
            {"dimension": "illness", "keyword": "口腔溃疡", "days": 730},
        ),
    ),
)
async def test_historical_illness_query_projects_arbitrary_entity_and_year_window(
    message,
    proposed_args,
    expected_args,
):
    gateway = ToolGateway(_snapshot(message))
    calls = []

    async def dispatch(request):
        calls.append(request.arguments)
        return "[]"

    result = await gateway.execute(
        ToolExecutionRequest(
            tool_name="health_query",
            arguments=proposed_args,
            source="structured",
        ),
        dispatch,
    )

    assert result.decision is not None
    assert result.decision.action == "allow"
    assert calls == [expected_args]


@pytest.mark.asyncio
async def test_multi_entity_illness_query_never_falls_back_to_model_scope():
    gateway = ToolGateway(_snapshot("最近半年口腔溃疡和湿疹有哪些记录？"))
    calls = []

    async def dispatch(request):
        calls.append(request.arguments)
        return "unexpected"

    result = await gateway.execute(
        ToolExecutionRequest(
            tool_name="health_query",
            arguments={"dimension": "comprehensive", "days": 7},
            source="structured",
        ),
        dispatch,
    )

    assert calls == []
    assert result.decision is not None
    assert result.decision.action == "block"
    assert result.decision.reason == "illness_query_entity_requires_clarification"


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
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def should_not_run(*args, **kwargs):
        raise AssertionError("_exec_health_manage should not run")

    monkeypatch.setattr(executor, "_exec_health_manage", should_not_run)

    result = await executor._execute_tool(
        "health_manage",
        {
            "record_type": "diet",
            "operation": "update",
            "record_id": 1,
            "data": {"meal_type": "lunch"},
        },
        None,
    )

    payload = json.loads(result)
    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == "manage_write_without_mutate_intent"


@pytest.mark.asyncio
async def test_execute_tool_blocks_health_manage_delete_in_update_turn(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "把刚才 300ml 改成 350ml"

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def should_not_run(*args, **kwargs):
        raise AssertionError("_exec_health_manage should not run")

    monkeypatch.setattr(executor, "_exec_health_manage", should_not_run)

    result = await executor._execute_tool(
        "health_manage",
        {"record_type": "water", "operation": "delete", "record_id": 718},
        None,
    )

    payload = json.loads(result)
    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == "manage_operation_mismatch"
    assert "保留现有记录" in payload["recovery_guidance"]
    assert "用户明确要求的操作" in payload["recovery_guidance"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "把上一条饮水记录里的备注去掉",
        "把上一条饮水记录备注删掉",
        "从上一条饮水记录里把备注去掉",
        "从上一条饮水记录中把说明删掉",
        "把备注在上一条饮水记录里去掉",
        "把上一条饮水记录里的单位去掉",
        "把上一条运动记录里的距离去掉",
        "把来源从上一条饮水记录里删除",
        "把上一条运动记录中的速度删掉",
        "删除上一条不是饮水的记录",
        "删除上一条饮水以外的记录",
        "删除上一条非饮水记录",
        "删除上一条除饮水外的记录",
        "删除上一条不含饮水的记录",
        "删除饮水记录 718 的备注",
        "撤销删除饮水记录 718",
        "删除饮水记录 718 并改成 350ml",
    ),
)
async def test_execute_tool_blocks_field_removal_from_deleting_record(
    db,
    monkeypatch,
    message,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = message

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def should_not_run(*args, **kwargs):
        raise AssertionError("_exec_health_manage should not run")

    monkeypatch.setattr(executor, "_exec_health_manage", should_not_run)

    result = await executor._execute_tool(
        "health_manage",
        {"record_type": "water", "operation": "delete", "record_id": 718},
        None,
    )

    payload = json.loads(result)
    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == "delete_requires_explicit_whole_record_intent"
    assert "保留整条记录" in payload["recovery_guidance"]
    assert "仅移除字段" in payload["recovery_guidance"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "record_type", "record_id"),
    (
        ("删除上一条饮水记录", "medication", 718),
        ("删除上一条饮水记录", "water", 718),
        ("清掉记录 718", "medication", 718),
        ("清掉记录 718", "water", 718),
        ("清掉记录 718", "water", 719),
        ("删除饮水记录 718", "weight", 718),
        ("删除饮水记录 718", "water", 719),
        ("删除第一条记录", "water", 718),
        ("删除两条饮水记录", "water", 718),
        ("删除饮水或用药记录 718", "water", 718),
        ("删除饮水用药记录 718", "water", 718),
        ("删除第1条或第2条饮水记录", "water", 718),
        ("删除所有饮水记录 718", "water", 718),
        ("删除上一条非饮水记录", "water", 718),
        ("删除上一条除饮水外的记录", "water", 718),
        ("删除上一条不含饮水的记录", "water", 718),
    ),
)
async def test_execute_tool_blocks_delete_when_text_does_not_bind_target(
    db,
    monkeypatch,
    message,
    record_type,
    record_id,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = message

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def should_not_run(*args, **kwargs):
        raise AssertionError("_exec_health_manage should not run")

    monkeypatch.setattr(executor, "_exec_health_manage", should_not_run)

    result = await executor._execute_tool(
        "health_manage",
        {
            "record_type": record_type,
            "operation": "delete",
            "record_id": record_id,
        },
        None,
    )

    payload = json.loads(result)
    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == "delete_requires_explicit_whole_record_intent"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "record_type"),
    (
        ("删除饮水记录 718", "water"),
        ("请帮我删除体重记录 718", "weight"),
        ("把饮食记录 718 删了", "diet"),
        ("请您删除用药记录 718", "medication"),
        ("删除 meal 记录 718", "diet"),
    ),
)
async def test_execute_tool_dispatches_closed_grammar_record_delete(
    db,
    monkeypatch,
    message,
    record_type,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = message
    calls = []

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def fake_exec(base, headers, args):
        calls.append(args)
        return json.dumps(
            {
                "id": args["record_id"],
                "record_id": args["record_id"],
                "resource_type": f"{record_type}_record",
                "message": "删除成功",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(executor, "_exec_health_manage", fake_exec)

    result = await executor._execute_tool(
        "health_manage",
        {"record_type": record_type, "operation": "delete", "record_id": 718},
        None,
    )

    assert calls == [
        {
            "record_type": record_type,
            "operation": "delete",
            "record_id": 718,
        }
    ]
    assert '"record_id": 718' in result


@pytest.mark.asyncio
async def test_execute_tool_allows_explicit_health_record_write(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "记录午餐吃了牛肉面"
    calls = []

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
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

    assert calls == [
        {
            "record_type": "diet",
            "data": {
                "meal_type": "lunch",
                "food_items": "牛肉面",
                "source": "agent_text",
            },
        }
    ]
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
async def test_execute_tool_emits_receipt_for_json_encoded_write_arguments(
    db, monkeypatch
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
    receipt = next(
        event for event in events if event.name == "agent.write_receipt_verified"
    )
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
async def test_shadow_policy_hard_blocks_denied_health_write(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "列出今天的饮食记录"
    calls = []
    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_kernel_policy_mode", "shadow"
    )
    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
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

    assert calls == []
    assert executor._agent_kernel_event_bus is not None
    assert "agent.tool_blocked" in [
        event.name for event in executor._agent_kernel_event_bus.events
    ]


@pytest.mark.asyncio
async def test_agent_media_tool_uses_current_image_and_emits_manual_confirmation_card(
    db, monkeypatch
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = (
        "确认把这张早餐图片发送给百炼，生成 5 秒竖屏短视频"
    )
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
    assert executor._turn_aigc_media_cards == [
        {
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
            "actions": [
                {
                    "id": "aigc_media.confirm:aigc_confirm_0123456789abcdef0123456789abcdef",
                    "label": "确认并生成",
                    "action": "aigc_media.confirm",
                    "endpoint": "/aigc/media/confirmations/aigc_confirm_0123456789abcdef0123456789abcdef/confirm",
                    "requires_manual_confirm": True,
                    "capability_id": "aigc_media_confirmation.v1",
                    "required_receipt": True,
                    "autonomy_tier": "manual_confirm",
                    "policy_reason": "manual_confirm_write",
                }
            ],
        }
    ]
    assert executor._agent_kernel_event_bus is not None
    receipt = next(
        event
        for event in executor._agent_kernel_event_bus.events
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
