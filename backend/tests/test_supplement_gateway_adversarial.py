"""End-to-end synthetic regressions for supplement authorization and receipts."""

import json

import httpx
import pytest

from app.services.agent_executor import (
    AgentExecutor,
    _build_deterministic_supplement_record_tool_calls,
    _write_receipt_from_tool_result,
)


async def _execute(
    db,
    *,
    message="记录补剂：营养素甲",
    name="营养素甲",
    existing=False,
    tap=None,
    lookup=None,
    create=None,
    dosage=None,
):
    calls = []

    def respond(request):
        calls.append(
            (
                request.method,
                request.url.path,
                json.loads(request.content) if request.content else None,
            )
        )
        if request.method == "GET":
            body = lookup if lookup is not None else (
                [{"id": 41, "name": name, "is_active": True}]
                if existing
                else []
            )
        elif request.url.path.endswith("/definitions"):
            body = create if create is not None else {
                "id": 73,
                "name": name,
                "user_id": 1,
                "is_active": True,
            }
        else:
            body = tap if tap is not None else {
                "status": "recorded",
                "record_id": 1073,
            }
        return httpx.Response(200, json=body)

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = message
    data = {"supplement_name": name}
    if dosage is not None:
        data["dosage"] = dosage
    args = {"record_type": "supplement", "data": data}
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        executor._http_client = client
        result = await executor._execute_tool(
            "health_record",
            args,
            "synthetic-token",
        )
    receipt = _write_receipt_from_tool_result("health_record", args, result)
    return calls, result, receipt


@pytest.mark.parametrize(
    "message",
    (
        "记录补剂：不记录营养素甲",
        "记录补剂：暂缓记录营养素甲",
        "记录补剂：营养素甲不想再吃",
        "记录补剂：营养素甲没有真的吃",
        "记录补剂：营养素甲能吃吗",
        "记录补剂：营养素甲以后吃",
        "记录补剂：营养素甲（尚未）",
        "记录补剂：将要吃营养素甲",
        "记录补剂：不进行记录营养素甲",
        "记录补剂：没来得及吃营养素甲",
        "记录补剂：营养素甲没有实际吃",
        "记录补剂：营养素甲不曾真的吃",
        "记录补剂：明晚吃营养素甲",
        "记录补剂：今晚要吃营养素甲",
        "记录补剂：过会儿吃营养素甲",
        "记录补剂：明早营养素甲",
        "记录补剂：昨晚已服营养素甲",
        "记录补剂：下周开始吃营养素甲",
        "记录补剂：营养素甲作废",
        "记录补剂：营养素甲只考虑",
        "记录补剂：以后再吃营养素甲",
        "记录补剂：营养素甲能否吃",
        "记录补剂：营养素甲（吃过没有）",
        "记录补剂：营养素甲暂停",
        "记录补剂：营养素甲过两小时吃",
        "记录补剂：营养素甲明年吃",
        "记录补剂：次日吃营养素甲",
        "记录补剂：稍晚吃营养素甲",
        "记录补剂：过后吃营养素甲",
        "记录补剂：预备吃营养素甲",
        "记录补剂：预计吃营养素甲",
        "记录补剂：将会吃营养素甲",
        "记录补剂：下次吃营养素甲",
        "记录补剂：No intake of 营养素甲",
        "记录补剂：营养素甲No intake of",
        "记录补剂：营养素甲过两小时服",
        "记录补剂：营养素甲明年服",
        "记录补剂：营养素甲稍晚补",
        "记录补剂：营养素甲将会吞",
        "记录补剂：营养素甲，明天吃",
        "记录补剂：营养素甲，明年晚上吃",
        "记录补剂：营养素甲，过两小时服",
        "记录补剂：营养素甲，已停",
        "记录补剂：营养素甲；明天再吃",
        "记录补剂：营养素甲、明天吃",
        "记录补剂：明天吃、营养素甲",
        "记录补剂：营养素甲、下周再服一片",
        "记录补剂：营养素甲、计划每天两粒",
        "记录补剂：营养素甲、以后再吃一点",
        "记录补剂：营养素甲、no intake",
        "记录补剂：营养素甲、will take later",
        "记录补剂：营养素甲、仅供参考",
        "记录补剂：营养素甲、暂停这次",
        "记录补剂：营养素甲，打算明天再吃",
        "记录补剂：营养素甲、只是举个例子",
        "记录补剂：营养素甲、仅是一个示例",
        "记录补剂：营养素甲、用于演示",
        "记录补剂：营养素甲，这只是举个例子",
        "记录补剂：营养素甲，打算下星期再吃",
        "记录补剂：营养素甲，not taken yet",
        "记录补剂：营养素甲，this is just an example",
        "记录补剂：营养素甲，intend to take next week",
        "记录补剂：营养素甲、计划一天三次",
        "记录补剂：营养素甲，暂停这个",
        "记录补剂：营养素甲，上周吃过",
        "记录补剂：营养素甲、延后处理",
        "记录补剂：营养素甲、仅用于说明",
        "记录补剂：营养素甲，未吃这份营养素",
        "记录补剂：营养素甲，暂停这种营养素",
        "记录补剂：营养素甲，这里只是举例这款营养素",
        "记录补剂：营养素甲，上个月已服",
        "记录补剂：营养素甲，明日开始",
        "记录补剂：营养素甲，每隔三天一粒",
        "记录补剂：营养素甲，didn’t ingest it",
        "记录补剂：营养素甲，这是演示用的维生素片",
        "记录补剂：营养素甲，暂缓这款胶囊",
        "记录补剂：营养素甲，仅用于说明这些营养素",
        "记录补剂：营养素甲，没吃任何维生素片",
        "记录补剂：营养素甲，未吃这种复合营养素",
        "记录补剂：上季度服用了营养素甲",
        "记录补剂：没服上述营养素",
        "记录补剂：didn't ingest 营养素甲",
        "记录补剂：上述营养素",
        "记录补剂：营养素甲从未摄取",
        "记录补剂：上一月已服营养素甲",
        "记录补剂：营养素甲后日安排",
        "记录补剂：定期的沐川鱼油",
        "记录补剂：澄石叶黄素、定期的沐川鱼油、星砂甘氨酸镁",
        "记录补剂：一星期三回的沐川鱼油",
        "记录补剂：澄石叶黄素，一星期三回的沐川鱼油",
        "记录补剂：同一款的甘氨酸镁",
        "记录补剂：澄石叶黄素,同一款的甘氨酸镁",
        "记录补剂：绝非岚珀叶黄素",
        "记录补剂：汀砂甘氨酸镁、毋须岚珀叶黄素",
        "记录补剂：往昔的岚珀叶黄素",
        "记录补剂：汀砂甘氨酸镁、旧时的岚珀叶黄素",
        "记录补剂：拟用岚珀叶黄素",
        "记录补剂：汀砂甘氨酸镁、有空再用岚珀叶黄素",
        "记录补剂：按需的岚珀叶黄素",
        "记录补剂：汀砂甘氨酸镁、三天两粒岚珀叶黄素",
        "记录补剂：若干岚珀叶黄素",
        "记录补剂：汀砂甘氨酸镁、另一种岚珀叶黄素",
        "记录补剂：抄录岚珀叶黄素",
        "记录补剂：汀砂甘氨酸镁、据说岚珀叶黄素",
        "记录补剂：岚珀叶黄素；记录补剂：未服汀砂甘氨酸镁",
        "记录补剂：岚珀叶黄素｡记录补剂：未服汀砂甘氨酸镁",
        "记录补剂：免除霁蓝叶黄素",
        "记录补剂：晴砾甘氨酸镁、大学期间霁蓝叶黄素",
        "记录补剂：待定霁蓝叶黄素",
        "记录补剂：晴砾甘氨酸镁、逢双号霁蓝叶黄素",
        "记录补剂：任一款霁蓝叶黄素",
        "记录补剂：晴砾甘氨酸镁、引文霁蓝叶黄素",
        "记录补剂：霁蓝叶黄素；记录补剂：晴砾甘氨酸镁？",
    ),
)
async def test_non_authorizing_supplement_never_dispatches(db, message):
    plan = _build_deterministic_supplement_record_tool_calls(
        message,
        write_receipts=[],
    )
    names = {"营养素甲"}
    names.update(
        json.loads(call["function"]["arguments"])["data"]["supplement_name"]
        for call in plan
    )
    for name in names:
        calls, _, receipt = await _execute(db, message=message, name=name)
        assert calls == []
        assert receipt is None
    assert plan == []


@pytest.mark.parametrize("existing", (False, True))
@pytest.mark.parametrize(
    "tap",
    (
        {"record_id": 1073},
        {"status": "ok", "id": 9},
        {"status": "ok", "record_id": False, "id": 9},
        {"status": "ok", "data": {"record_id": 1073}},
        {"record_id": 1073, "success": 0},
        {"record_id": 1073, "ok": "false"},
        {"status": "ok", "record_id": 1073, "id": [55]},
        {"status": "ok", "record_id": 1073, "resource_type": False},
        {"status": "ok", "record_id": 1073, "data": {"record_id": 77}},
        {"status": "ok", "record_id": 1073, "data": [{"record_id": 77}]},
        {"status": "ok", "record_id": 1073, "data": {"type": "diet_record"}},
        {"status": "ok", "record_id": 1073, "user_id": 2},
        {"status": "ok", "record_id": 1073, "supplement_id": 999},
        {
            "status": "ok",
            "record_id": 1073,
            "data": {"supplement_definition_id": 999},
        },
        {
            "status": "ok",
            "record_id": 1073,
            "resource_type": "supplement_log",
            "type": "diet_record",
        },
        {"status": "ok", "record_id": 1073, "result": [{"status": "failed"}]},
    ),
)
async def test_invalid_tap_cannot_complete(db, existing, tap):
    _, result, receipt = await _execute(db, existing=existing, tap=tap)
    assert receipt is None
    assert "并完成今日打卡" not in result


@pytest.mark.parametrize(
    "create",
    (
        {"id": 73, "name": "营养素乙", "user_id": 1, "is_active": True},
        {"id": 73, "name": "营养素甲", "user_id": 2, "is_active": True},
        {"id": 73, "name": "营养素甲", "user_id": 1, "is_active": False},
        {"id": 73, "name": "营养素甲", "user_id": 1, "is_active": "true"},
        {
            "id": 73,
            "name": "营养素甲",
            "user_id": 1,
            "is_active": True,
            "data": {"id": 99},
        },
        {
            "id": 73,
            "name": "营养素甲",
            "user_id": 1,
            "is_active": True,
            "result": [{"status": "failed"}],
        },
        {
            "id": 73,
            "name": "营养素甲",
            "user_id": 1,
            "is_active": True,
            "resource_type": "diet_record",
        },
        {
            "id": 73,
            "name": "营养素甲",
            "user_id": 1,
            "is_active": True,
            "data": {"is_active": False},
        },
        {
            "id": 73,
            "name": "营养素甲",
            "user_id": 1,
            "is_active": True,
            "resource_type": "supplement_definition",
            "type": "diet_record",
        },
    ),
)
async def test_create_definition_must_match_authorized_target(db, create):
    calls, _, receipt = await _execute(db, create=create)
    assert not any(path.endswith("/tap") for _, path, _ in calls)
    assert receipt is None


@pytest.mark.parametrize("existing", (False, True))
async def test_explicit_successful_tap_is_verified_without_private_logs(
    db,
    existing,
    caplog,
):
    calls, _, receipt = await _execute(db, existing=existing)
    assert receipt and receipt["verified"] is True
    assert any(path.endswith("/tap") for _, path, _ in calls)
    assert "营养素" not in caplog.text


@pytest.mark.parametrize(
    "message",
    (
        "记录补剂：营养素乙、没来得及吃营养素甲",
        "记录补剂：营养素乙、没来得及吃正官庄红参液",
        "记录补剂：营养素乙、没服上述营养素",
        "记录补剂：营养素乙、暂停同款补剂",
        "记录补剂：营养素乙、前述补剂下个月再吃",
    ),
)
async def test_mixed_authority_batch_is_atomic_and_never_dispatches(db, message):
    plan = _build_deterministic_supplement_record_tool_calls(
        message,
        write_receipts=[],
    )
    assert plan == []
    for name in ("营养素甲", "营养素乙", "正官庄红参液"):
        calls, _, receipt = await _execute(db, message=message, name=name)
        assert calls == []
        assert receipt is None


@pytest.mark.parametrize(
    "definitions",
    (
        [
            {"id": 41, "name": "营养素甲", "is_active": True},
            {"id": 41, "name": "营养素乙", "is_active": True},
        ],
        [
            {"id": 41, "name": "营养素甲", "is_active": True},
            {"id": 42, "name": " 营养素甲 ", "is_active": True},
        ],
    ),
)
async def test_ambiguous_definitions_never_select_arbitrary_id(db, definitions):
    calls, _, receipt = await _execute(db, lookup=definitions)
    assert not any(method == "POST" for method, _, _ in calls)
    assert receipt is None


@pytest.mark.parametrize(
    "message",
    tuple(f"记录补剂：待定短验{suffix}硒。" for suffix in "甲乙丙丁戊己庚辛"),
)
async def test_deferred_short_name_never_plans_or_dispatches(db, message):
    assert _build_deterministic_supplement_record_tool_calls(
        message,
        write_receipts=[],
    ) == []
    calls, _, receipt = await _execute(
        db,
        message=message,
        name=message.removeprefix("记录补剂：").removesuffix("。"),
    )
    assert calls == []
    assert receipt is None


@pytest.mark.parametrize(
    ("message", "name"),
    (
        ("记录补剂：一粒“明澈镇静组合补剂”。", "明澈镇静组合补剂"),
        ("记录补剂：一粒\"甲乙丙丁戊己庚\"。", "甲乙丙丁戊己庚"),
        ("记录补剂：一粒「月白复合营养胶囊」。", "月白复合营养胶囊"),
        ("记录补剂：一粒【远山矿物组合片】。", "远山矿物组合片"),
    ),
)
async def test_explicit_quoted_long_name_plans_and_dispatches(db, message, name):
    plan = _build_deterministic_supplement_record_tool_calls(
        message,
        write_receipts=[],
    )
    assert len(plan) == 1
    assert json.loads(plan[0]["function"]["arguments"])["data"][
        "supplement_name"
    ] == name
    assert json.loads(plan[0]["function"]["arguments"])["data"]["dosage"] == "1粒"

    calls, _, receipt = await _execute(
        db,
        message=message,
        name=name,
        dosage="1粒",
    )
    assert any(path.endswith("/tap") for _, path, _ in calls)
    assert receipt and receipt["verified"] is True


@pytest.mark.parametrize(
    "message",
    (
        "记录补剂：一粒\u201c超长引用补剂名甲甲乙丙丁\u201d。",
        "记录补剂：一粒\u201c待定长名字补剂甲乙丙丁\u201d。",
        "记录补剂：一粒\u201c暂定长名字补剂甲乙丙丁\u201d。",
        "记录补剂：一粒\u201c预留长名字补剂甲乙丙丁\u201d。",
        "记录补剂：一粒\u201c待议长名字补剂甲乙丙丁\u201d。",
        "记录补剂：暂定新验甲硒。",
        "记录补剂：预留新验甲硒。",
        "记录补剂：待议新验甲硒。",
    ),
)
async def test_quoted_grammar_fragments_never_plan_or_dispatch(db, message):
    assert _build_deterministic_supplement_record_tool_calls(
        message,
        write_receipts=[],
    ) == []
    calls, _, receipt = await _execute(db, message=message, name="不应使用")
    assert calls == []
    assert receipt is None
