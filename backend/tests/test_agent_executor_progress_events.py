"""P0-1 流式进度事件 (accepted / tool / synthesis) — AgentExecutor.run_stream.

回复"憋大招"的后端半: 卡片只在 done 插入、首 token 前 8s 无进度、多轮 tool call 无
中间状态。新增一个 **flat 契约** 的 additive 进度事件家族 (与既有 {"event":"status",
"data":{...}} 家族独立、纯附加):

    {"type":"status","stage":"accepted"}                    — 流一打开立刻发 (任何 LLM 之前)
    {"type":"status","stage":"tool","round":N,"label":"…"}  — 每轮工具执行前发
    {"type":"status","stage":"synthesis"}                   — 最终答案开始生成前发

label 来自确定性映射表 _TOOL_PROGRESS_LABEL (完整人话动词短语), 未映射兜底"正在处理…"。
本文件断言事件序列 accepted → tool(round=1..n) → synthesis → done, 镜像既有
test_agent_executor_status_events.py 的 mock 接线。
"""
import pytest

from app.services.agent_executor import (
    AgentExecutor,
    _phase_one_acknowledgement,
    _tool_progress_label,
    _TOOL_PROGRESS_FALLBACK,
)


@pytest.mark.parametrize(
    "message,expected",
    [
        (
            "昨晚睡得怎样，今天是否适合锻炼？",
            "我先读取睡眠和恢复数据，再判断今天适合的运动强度。",
        ),
        (
            "结合我的用药和肝功能判断今天能否锻炼",
            "我先核对用药和检查信息，再按安全边界给出判断。",
        ),
        (
            "记录午餐吃了牛肉面",
            "我先核对餐食和份量，再给出可确认的营养结果。",
        ),
        (
            "删除刚才错误的两餐",
            "我先核对要处理的记录，确认目标后再执行。",
        ),
        (
            "记录今天运动30分钟",
            "收到，我先核对记录内容，确认后写入。",
        ),
        (
            "记录今天锻炼了半小时",
            "收到，我先核对记录内容，确认后写入。",
        ),
        (
            "记录睡眠7小时",
            "收到，我先核对记录内容，确认后写入。",
        ),
        (
            "这个能多吃一颗吗",
            "我先核对用药和剂量信息，再按安全边界处理。",
        ),
        (
            "心跳突然很乱还能运动吗",
            "我先核对你描述的症状和风险信号，再给出安全建议。",
        ),
        (
            "胸口像有人坐着还能跑步吗",
            "我先核对你描述的症状和风险信号，再给出安全建议。",
        ),
        (
            "吸不进气还能训练吗",
            "我先核对你描述的症状和风险信号，再给出安全建议。",
        ),
        (
            "一侧胳膊抬不起来",
            "我先核对你描述的症状和风险信号，再给出安全建议。",
        ),
        (
            "记录午餐吃了富含维生素C的橙子",
            "我先核对餐食和份量，再给出可确认的营养结果。",
        ),
        (
            "记录午餐吃了药膳鸡汤",
            "我先核对餐食和份量，再给出可确认的营养结果。",
        ),
        (
            "早餐吃了两片面包",
            "我先核对餐食和份量，再给出可确认的营养结果。",
        ),
        (
            "阿司匹林怎么吃",
            "我先核对用药和剂量信息，再按安全边界处理。",
        ),
        (
            "布洛芬和阿司匹林能一起吃吗",
            "我先核对用药和剂量信息，再按安全边界处理。",
        ),
        (
            "记录我吃了它",
            "我先核对用药和剂量信息，再按安全边界处理。",
        ),
        (
            "记录吸入了两揿哮喘气雾剂",
            "我先核对用药和剂量信息，再按安全边界处理。",
        ),
        (
            "记录吃了矿物质一粒",
            "我先核对用药和剂量信息，再按安全边界处理。",
        ),
        (
            "记录吃了富含维生素C一粒",
            "我先核对用药和剂量信息，再按安全边界处理。",
        ),
        (
            "记录吃了高血糖指数一片",
            "我先核对用药和剂量信息，再按安全边界处理。",
        ),
        (
            "午餐吃了一粒矿物质补充剂和一个苹果",
            "我先核对用药和剂量信息，再按安全边界处理。",
        ),
        (
            "午餐吃了一粒钙片和一个苹果",
            "我先核对用药和剂量信息，再按安全边界处理。",
        ),
        (
            "午餐吃了维生素C一粒和橙子",
            "我先核对用药和剂量信息，再按安全边界处理。",
        ),
        (
            "记录用了鼻喷剂两下",
            "我先核对用药和剂量信息，再按安全边界处理。",
        ),
        (
            "记录用了气雾剂两下",
            "我先核对用药和剂量信息，再按安全边界处理。",
        ),
        (
            "记录喷了两下哮喘喷雾",
            "我先核对用药和剂量信息，再按安全边界处理。",
        ),
        (
            "记录用了哮喘吸入器两下",
            "我先核对用药和剂量信息，再按安全边界处理。",
        ),
        (
            "午餐吃了一粒维C和一个苹果",
            "我先核对用药和剂量信息，再按安全边界处理。",
        ),
        (
            "记录用了吸入器两下",
            "我先核对用药和剂量信息，再按安全边界处理。",
        ),
        (
            "吃了药膳鸡汤",
            "我先核对餐食和份量，再给出可确认的营养结果。",
        ),
        (
            "那颗苹果还能吃吗",
            "我先核对餐食和份量，再给出可确认的营养结果。",
        ),
        (
            "继续用这个训练计划吗",
            "我先读取睡眠和恢复数据，再判断今天适合的运动强度。",
        ),
        (
            "这个贴纸怎么贴",
            "收到，我先梳理这个问题，再给你完整结果。",
        ),
        (
            "这个喷壶怎么喷",
            "收到，我先梳理这个问题，再给你完整结果。",
        ),
        (
            "这个面膜怎么贴",
            "收到，我先梳理这个问题，再给你完整结果。",
        ),
    ],
)
def test_phase_one_acknowledgement_is_specific_without_health_claims(
    message, expected
):
    assert _phase_one_acknowledgement(
        message,
        has_attachments=False,
    ) == expected


# ──── tool → progress label map ────

@pytest.mark.parametrize("name,label", [
    ("health_query", "查看健康数据…"),
    ("health_query_batch", "汇总健康数据…"),
    ("health_record", "正在记录…"),
    ("health_manage", "整理健康记录…"),
    ("health_analysis", "深度分析中…"),
    ("environment_check", "查看天气与环境…"),
    ("supplement_guide", "查阅补剂方案…"),
    ("upload_genetic_txt", "导入基因数据…"),
    ("query_genetic_profile", "查阅基因数据…"),
    ("upload_medical_exam_text", "录入体检报告…"),
    ("query_lab_indicators", "查看化验指标…"),
    ("intervention_cycle", "整理干预周期…"),
    ("knowledge_search", "检索知识库…"),
    ("realtime_search", "联网搜索中…"),
    ("manage_plan", "整理健康计划…"),
    # specialist 分析工具 (flag 开时才注册, label 表也覆盖)
    ("analyze_recovery", "评估恢复状态…"),
    ("analyze_longevity", "解读表型年龄…"),
])
def test_tool_progress_label_covers_all_tool_names(name, label):
    assert _tool_progress_label(name) == label


def test_tool_progress_label_unknown_falls_back():
    assert _tool_progress_label("some_future_tool") == _TOOL_PROGRESS_FALLBACK
    assert _tool_progress_label(None) == _TOOL_PROGRESS_FALLBACK
    assert _TOOL_PROGRESS_FALLBACK == "正在处理…"


def test_tool_progress_label_covers_every_registry_tool():
    """护栏: tool_schema_registry 的每个工具名都有一条真实映射 (非兜底)。

    新增工具但忘了加 label → 这里直接红, 逼迫同 PR 补映射 (契约要求"写全")。
    """
    from app.services.tool_schema_registry import get_tool_names

    for name in get_tool_names():
        assert _tool_progress_label(name) != _TOOL_PROGRESS_FALLBACK, (
            f"工具 {name!r} 缺 _TOOL_PROGRESS_LABEL 映射"
        )


# ──── shared wiring (镜像 test_agent_executor_status_events._wire_min) ────

def _progress(events):
    """Extract flat progress events {type:status,...} in emit order → (stage, round, label)."""
    out = []
    for e in events:
        if e.get("type") == "status":
            out.append((e.get("stage"), e.get("round"), e.get("label")))
    return out


async def _run(executor, message, images=None, extra_context=None, user_id=1):
    return [
        event
        async for event in executor.run_stream(
            user_id=user_id,
            message=message,
            user_auth_token="test-token",
            images=images,
            extra_context=extra_context,
        )
    ]


def _wire_min(executor, monkeypatch):
    """Minimal wiring so run_stream reaches the round loop without real LLM/provider."""
    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    # Keep legacy-event assertions independent from the developer's local .env;
    # staged-response tests below opt in explicitly.
    monkeypatch.setattr("app.services.agent_executor.settings.staged_response_mode", "off")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [{
        "type": "function",
        "function": {"name": "health_query", "description": "x",
                     "parameters": {"type": "object", "properties": {}}},
    }])
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")


# ──── accepted is always the very first wire event ────

@pytest.mark.asyncio
async def test_accepted_is_first_event_plain_turn(db, auth_user_and_headers, monkeypatch):
    """流一打开 → accepted 是第一个 yield 的事件 (任何 LLM/agent_start 之前)。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)

    async def fake_stream(messages, round_tools):
        yield {"type": "content", "text": "你好呀"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)

    events = await _run(executor, "你好呀", user_id=user.id)

    # 第一个事件就是 flat accepted (不是 agent_start / status.event)。
    first = events[0]
    assert first == {"type": "status", "stage": "accepted"}
    # 且 accepted 恰好出现一次。
    assert sum(1 for e in events if e.get("type") == "status" and e.get("stage") == "accepted") == 1


@pytest.mark.asyncio
async def test_staged_response_on_adds_immediate_ack_label(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    monkeypatch.setattr(
        "app.services.agent_executor.settings.staged_response_mode", "on"
    )

    async def fake_stream(messages, round_tools):
        yield {"type": "content", "text": "结论"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(
        executor,
        "昨晚睡得怎样，今天是否适合锻炼？",
        user_id=user.id,
    )

    assert events[0] == {
        "type": "status",
        "stage": "accepted",
        "label": "我先读取睡眠和恢复数据，再判断今天适合的运动强度。",
    }


@pytest.mark.asyncio
async def test_staged_response_plan_request_does_not_promise_a_write(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    monkeypatch.setattr(
        "app.services.agent_executor.settings.staged_response_mode", "on"
    )

    async def fake_stream(messages, round_tools):
        yield {"type": "content", "text": "结论"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(
        executor,
        "帮我制定一个适合久坐上班族的20分钟晚间拉伸计划，说明动作顺序和注意事项。",
        user_id=user.id,
    )

    assert events[0] == {
        "type": "status",
        "stage": "accepted",
        "label": "我先拆解目标和约束，再给出可执行的完整方案。",
    }


@pytest.mark.asyncio
async def test_staged_response_shadow_keeps_user_visible_event_unchanged(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    monkeypatch.setattr(
        "app.services.agent_executor.settings.staged_response_mode", "shadow"
    )

    async def fake_stream(messages, round_tools):
        yield {"type": "content", "text": "结论"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(
        executor,
        "昨晚睡得怎样，今天是否适合锻炼？",
        user_id=user.id,
    )

    assert events[0] == {"type": "status", "stage": "accepted"}


@pytest.mark.asyncio
async def test_progress_sequence_tool_turn(db, auth_user_and_headers, monkeypatch):
    """带工具的一回合 → 契约序列: accepted → tool(round=1) → synthesis → done。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)

    calls = {"round": 0}

    async def fake_stream(messages, round_tools):
        calls["round"] += 1
        if calls["round"] == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "c1",
                "function": {"name": "health_query", "arguments": "{}"},
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "查到了。"}
            yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)

    async def fake_exec(name, args, token):
        return "今天步数 8000"

    monkeypatch.setattr(executor, "_execute_tool", fake_exec)
    # 工具跑过后强制走确定性 synthesis 轮 (round-2 = synthesis 而非 thinking)。
    orig = executor._should_synthesize_with_requested_model_after_tools
    monkeypatch.setattr(
        executor,
        "_should_synthesize_with_requested_model_after_tools",
        lambda n: n > 0 or orig(n),
    )

    events = await _run(executor, "看看我今天的步数", user_id=user.id)
    seq = _progress(events)

    # flat 进度事件的精确有序契约。
    assert seq == [
        ("accepted", None, None),
        ("tool", 1, "查看健康数据…"),
        ("synthesis", None, None),
    ]

    # done 事件在 synthesis 之后 (整条链 accepted→tool→synthesis→done)。
    done_idx = next(i for i, e in enumerate(events) if e.get("event") == "done")
    synth_idx = next(
        i for i, e in enumerate(events)
        if e.get("type") == "status" and e.get("stage") == "synthesis"
    )
    tool_idx = next(
        i for i, e in enumerate(events)
        if e.get("type") == "status" and e.get("stage") == "tool"
    )
    accepted_idx = 0
    assert accepted_idx < tool_idx < synth_idx < done_idx


@pytest.mark.asyncio
async def test_progress_tool_event_carries_round_and_label(
    db, auth_user_and_headers, monkeypatch
):
    """多轮 tool call → 每轮 tool 进度事件带正确 round + 确定性 label。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)

    calls = {"round": 0}

    async def fake_stream(messages, round_tools):
        calls["round"] += 1
        if calls["round"] <= 2:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": f"c{calls['round']}",
                "function": {"name": "health_query", "arguments": "{}"},
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "综合完了。"}
            yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)

    async def fake_exec(name, args, token):
        return "data"

    monkeypatch.setattr(executor, "_execute_tool", fake_exec)

    events = await _run(executor, "查两轮数据", user_id=user.id)
    tool_events = [
        e for e in events
        if e.get("type") == "status" and e.get("stage") == "tool"
    ]

    assert len(tool_events) == 2
    assert tool_events[0] == {"type": "status", "stage": "tool", "round": 1, "label": "查看健康数据…"}
    assert tool_events[1] == {"type": "status", "stage": "tool", "round": 2, "label": "查看健康数据…"}


@pytest.mark.asyncio
async def test_existing_status_family_unchanged(db, auth_user_and_headers, monkeypatch):
    """纯附加护栏: 新进度事件不动既有 {"event":"status","data":{...}} 家族。

    一个纯文本回合仍恰好发一条既有 thinking status (round=1), 且新 accepted 是 flat
    (无 data 包裹), 二者不混。
    """
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)

    async def fake_stream(messages, round_tools):
        yield {"type": "content", "text": "在的"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)

    events = await _run(executor, "在吗", user_id=user.id)

    # 既有家族: {"event":"status","data":{stage,detail,round}} — 不受影响。
    legacy = [e for e in events if e.get("event") == "status"]
    assert legacy == [{"event": "status", "data": {"stage": "thinking", "detail": None, "round": 1}}]

    # 新家族: flat {"type":"status",...} — 有 accepted, 无 data 键。
    flat = [e for e in events if e.get("type") == "status"]
    assert {"type": "status", "stage": "accepted"} in flat
    for e in flat:
        assert "data" not in e
        assert "event" not in e
