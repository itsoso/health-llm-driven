"""GenUI 确定性护栏测试 — LLM 永远不能吐出 / 复现 reva-ui 图表 block。

背景 (R4): reva-ui 图表 block 的数值只能来自 `app.services.genui` 的确定性 DB 查询短路。
LLM 见过历史里的 reva-ui block 会**模仿**格式并**编造**数据 (实测: 编 "多源合并:
Apple Watch + Garmin + RingConn")。护栏分三层:
  1. 共享 helper `strip_reva_ui_blocks` / `placeholder_reva_ui_blocks` (单一真源)。
  2. 历史 strip: 喂回 LLM 的历史里, 助手消息的 block 换占位符 (LLM 无从模仿)。
  3. 输出 strip: LLM 生成文本落库前整块剥掉 (防御纵深)。
确定性短路自身产出的 block 走独立更早返回路径 → 不受任何 strip 影响 (回归测试)。
"""

import json
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.usefixtures("consenting_agent_user")

from app.models.daily_health import GarminData
from app.orchestrator import OrchestratorRequest, run_orchestrator
from app.services.genui import (
    placeholder_reva_ui_blocks,
    render_reva_ui_block,
    strip_reva_ui_blocks,
)

from tests.conftest import create_authenticated_user


@pytest.fixture(autouse=True)
def _clear_agent_dup_cache():
    from app.api.agent import _RECENT_DUP_CACHE
    _RECENT_DUP_CACHE.clear()
    yield
    _RECENT_DUP_CACHE.clear()


# ---------------------------------------------------------------------------
# strip_reva_ui_blocks — 纯函数单测
# ---------------------------------------------------------------------------

_FAKE_BLOCK = (
    '```reva-ui\n'
    '{"v":1,"component":"line_chart","x":["1","2"],'
    '"series":[{"name":"多源合并：Apple Watch + Garmin + RingConn",'
    '"points":[120,130]}]}\n'
    '```'
)
_FAKE_BLOCK_2 = (
    '```reva-ui\n{"v":1,"component":"metric_line_chart","metric":"bp_systolic"}\n```'
)


def test_strip_single_closed_block():
    text = f"这是你的血压趋势：\n\n{_FAKE_BLOCK}\n\n仅供参考。"
    out = strip_reva_ui_blocks(text)
    assert "reva-ui" not in out
    assert "多源合并" not in out
    assert "这是你的血压趋势：" in out
    assert "仅供参考。" in out


def test_strip_multiple_blocks():
    text = f"上：\n{_FAKE_BLOCK}\n中间散文\n{_FAKE_BLOCK_2}\n下。"
    out = strip_reva_ui_blocks(text)
    assert "reva-ui" not in out
    assert "中间散文" in out
    assert "上：" in out
    assert "下。" in out


def test_strip_unclosed_block_removes_to_end():
    """未闭合 opener (缺尾 ```) → 从 opener 删到结尾, 半个伪造 block 也不泄漏。"""
    text = (
        "血压趋势如下：\n\n"
        '```reva-ui\n{"v":1,"component":"line_chart","series":[{"name":"编造'
    )
    out = strip_reva_ui_blocks(text)
    assert "reva-ui" not in out
    assert "编造" not in out
    assert "血压趋势如下：" in out


def test_strip_block_amid_prose_keeps_prose():
    text = f"开头\n{_FAKE_BLOCK}\n结尾"
    out = strip_reva_ui_blocks(text)
    assert out.startswith("开头")
    assert out.endswith("结尾")
    assert "reva-ui" not in out


def test_strip_preserves_json_fence():
    """```json 等其它语言 fence 必须原样保留 (只吃 reva-ui)。"""
    text = (
        "这里有个 JSON 示例：\n\n"
        '```json\n{"foo": "bar"}\n```\n\n'
        f"以及一张伪造图：\n{_FAKE_BLOCK}\n"
    )
    out = strip_reva_ui_blocks(text)
    assert "```json" in out
    assert '{"foo": "bar"}' in out
    assert "reva-ui" not in out


def test_strip_no_block_unchanged():
    text = "普通回答，没有任何图表块。\n\n```python\nprint(1)\n```"
    assert strip_reva_ui_blocks(text) == text


def test_strip_empty_and_none_safe():
    assert strip_reva_ui_blocks("") == ""
    assert strip_reva_ui_blocks(None) is None


def test_strip_collapses_blank_runs():
    """剥离后残留的多空行压回单空行。"""
    text = f"上文\n\n\n{_FAKE_BLOCK}\n\n\n下文"
    out = strip_reva_ui_blocks(text)
    assert "\n\n\n" not in out
    assert "上文" in out and "下文" in out


# ---------------------------------------------------------------------------
# placeholder_reva_ui_blocks — 历史占位
# ---------------------------------------------------------------------------


def test_placeholder_replaces_block_with_marker():
    text = f"你的趋势：\n\n{_FAKE_BLOCK}"
    out = placeholder_reva_ui_blocks(text)
    assert "reva-ui" not in out
    assert "多源合并" not in out
    assert "［图表已展示］" in out
    assert "你的趋势：" in out


def test_placeholder_multiple_blocks():
    text = f"{_FAKE_BLOCK}\n散文\n{_FAKE_BLOCK_2}"
    out = placeholder_reva_ui_blocks(text)
    assert "reva-ui" not in out
    assert out.count("［图表已展示］") == 2
    assert "散文" in out


def test_placeholder_no_block_unchanged():
    text = "没有图表的普通历史消息"
    assert placeholder_reva_ui_blocks(text) == text


# ---------------------------------------------------------------------------
# 输出 strip (agent_executor) — LLM 生成文本落库前剥离
# ---------------------------------------------------------------------------


def test_agent_output_strip_helper_removes_fabricated_block():
    """agent_executor 的输出 strip helper 剥掉 LLM 伪造 block。"""
    from app.services.agent_executor import _strip_reva_ui_from_llm_text

    llm_text = f"根据你的数据：\n\n{_FAKE_BLOCK}\n\n注意休息。"
    out = _strip_reva_ui_from_llm_text(llm_text)
    assert "reva-ui" not in out
    assert "多源合并" not in out
    assert "根据你的数据：" in out
    assert "注意休息。" in out


def test_agent_history_placeholder_helper():
    """agent_executor 的历史 placeholder helper 把 block 换占位符。"""
    from app.services.agent_executor import _placeholder_reva_ui_in_history

    prior = f"上一轮给过图：\n{_FAKE_BLOCK}"
    out = _placeholder_reva_ui_in_history(prior)
    assert "reva-ui" not in out
    assert "［图表已展示］" in out


# ---------------------------------------------------------------------------
# 历史 strip e2e — 喂给 LLM 的 messages 里, 历史助手 block 变占位符
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_reva_ui_replaced_before_reaching_llm(db, monkeypatch):
    """历史里助手带 reva-ui block; 下一轮 LLM 收到的 messages 必须是占位符, 不是格式本身。"""
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = create_authenticated_user(db)
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title="趋势")
    # 上一轮: 用户问 + 助手回复带一个真 reva-ui block (确定性短路曾产出的历史)
    svc.save_message(conv.id, "user", "画一下我的血压趋势")
    svc.save_message(conv.id, "assistant", f"这是你的趋势：\n\n{_FAKE_BLOCK}")

    captured = {}

    async def _capture_llm_stream(self, messages, tools, **kwargs):  # noqa: ANN001
        captured["messages"] = messages
        # 立刻结束这一轮: 无 tool_calls, 出一句普通回答。
        yield {"type": "content", "text": "血压整体平稳。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(AgentExecutor, "_call_llm_stream", _capture_llm_stream)

    executor = AgentExecutor(db)
    async for _evt in executor.run_stream(user.id, "那我该注意什么？", conversation_id=conv.id):
        pass

    assert "messages" in captured, "LLM stream 应被调用"
    joined = json.dumps(captured["messages"], ensure_ascii=False)
    # 关键: LLM 看到的历史里没有 reva-ui 格式可模仿, 只有占位符。
    assert "reva-ui" not in joined
    assert "多源合并" not in joined
    assert "［图表已展示］" in joined


@pytest.mark.asyncio
async def test_fabricated_llm_block_stripped_before_persist(db, monkeypatch):
    """LLM 吐出伪造 reva-ui block → 落库的 assistant 消息里被整块剥掉。"""
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = create_authenticated_user(db)

    async def _fabricating_llm_stream(self, messages, tools, **kwargs):  # noqa: ANN001
        # 模拟弱模型模仿历史格式编造图表。
        yield {"type": "content", "text": f"根据分析：\n\n{_FAKE_BLOCK}\n\n请遵医嘱。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(AgentExecutor, "_call_llm_stream", _fabricating_llm_stream)

    executor = AgentExecutor(db)
    async for _evt in executor.run_stream(user.id, "分析我的血压", conversation_id=None):
        pass

    svc = AgentConversationService(db)
    convs = svc.get_conversations(user.id, limit=5)
    assert convs
    detail = svc.get_conversation_detail(user.id, convs[0].id)
    assistant_msgs = [m for m in detail.messages if m.role == "assistant"]
    assert assistant_msgs
    for m in assistant_msgs:
        assert "reva-ui" not in (m.content or ""), "落库消息不得含伪造 reva-ui block"
        assert "多源合并" not in (m.content or "")
    # 散文仍保留 (只剥 block)。
    assert any("请遵医嘱。" in (m.content or "") for m in assistant_msgs)


# ---------------------------------------------------------------------------
# 输出 strip (orchestrator) — synthesis 里的 LLM 伪造 block 被剥
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_llm_fabricated_block_stripped(db, monkeypatch):
    """orchestrator synthesis: LLM 编 reva-ui block → run_orchestrator 输出里被剥掉。

    用非图表意图的 query + 无 caps, 确保**不**走确定性短路, 真正走 LLM synthesis 路径。
    """
    user, _ = create_authenticated_user(db)

    async def _fabricating_llm(*args, **kwargs):  # noqa: ANN001
        return f"综合来看：\n\n{_FAKE_BLOCK}\n\n多喝水。"

    monkeypatch.setattr("app.orchestrator.orchestrator._call_llm", _fabricating_llm)

    req = OrchestratorRequest(
        query="帮我综合分析一下最近的健康状况",
        client_caps=[],  # 不触发 genui 短路
        stream=False,
    )
    resp = await run_orchestrator(db, user.id, req)
    assert "reva-ui" not in resp.synthesis
    assert "多源合并" not in resp.synthesis
    assert "综合来看" in resp.synthesis or "多喝水" in resp.synthesis


# ---------------------------------------------------------------------------
# 回归: 确定性短路自身产出的 block 必须存活 (护栏不得吃掉它)
# ---------------------------------------------------------------------------


def _seed_hrv_months(db, user_id):
    from statistics import mean
    base = date.today().replace(day=1)
    for offset, vals in {0: [70, 80, 90], 1: [50, 60, 55], 2: [40, 42, 44]}.items():
        month_start = base
        for _ in range(offset):
            month_start = (month_start - timedelta(days=1)).replace(day=1)
        for i, v in enumerate(vals):
            db.add(GarminData(user_id=user_id, record_date=month_start + timedelta(days=i + 1), hrv=v))
    db.commit()


@pytest.fixture
def _explode_llm(monkeypatch):
    async def _boom(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("LLM must NOT be called on the GenUI short-circuit (R4)")

    monkeypatch.setattr("app.orchestrator.orchestrator._call_llm", _boom)


@pytest.mark.asyncio
async def test_orchestrator_short_circuit_block_survives_guard(db, _explode_llm):
    """确定性短路 (caps=genui-v1 + 图表意图 + 真数据) 产出的 reva-ui block 必须完整存活。

    _explode_llm 证明这条路径根本不进 LLM → 护栏的输出 strip (只作用于 LLM 文本)
    不在这条路径上, block 不被吃。
    """
    user, _ = create_authenticated_user(db)
    _seed_hrv_months(db, user.id)

    req = OrchestratorRequest(
        query="帮我绘制最近半年的HRV曲线",
        client_caps=["genui-v1"],
        stream=False,
    )
    resp = await run_orchestrator(db, user.id, req)
    assert "```reva-ui" in resp.synthesis, "确定性短路的 block 必须存活"
    inner = resp.synthesis.split("```reva-ui\n", 1)[1].rsplit("```", 1)[0].strip()
    block = json.loads(inner)
    assert block["component"] == "line_chart"
    non_null = [p for p in block["series"][0]["points"] if p is not None]
    assert non_null and all(40.0 <= p <= 90.0 for p in non_null)


def _read_sse_body(resp) -> str:
    return resp.text


@pytest.fixture
def _explode_agent_run_stream(monkeypatch):
    async def _boom(*args, **kwargs):  # noqa: ANN001
        raise AssertionError(
            "AgentExecutor.run_stream must NOT be called on the GenUI short-circuit (R4)"
        )
        yield  # pragma: no cover

    monkeypatch.setattr("app.services.agent_executor.AgentExecutor.run_stream", _boom)


def test_agent_stream_short_circuit_block_survives_guard(
    client, db, auth_user_and_headers, _explode_agent_run_stream
):
    """agent/stream 确定性短路: reva-ui block 出现在 SSE 且持久化, 不被输出 strip 吃掉。"""
    user, headers = auth_user_and_headers
    _seed_hrv_months(db, user.id)

    resp = client.post(
        "/api/v1/agent/stream",
        json={"message": "绘制我最近半年的HRV曲线"},
        headers={**headers, "X-Reva-Client-Caps": "genui-v1"},
    )
    assert resp.status_code == 200
    body = _read_sse_body(resp)
    assert "reva-ui" in body
    assert "line_chart" in body

    # 持久化的 assistant 消息仍含 reva-ui block (短路路径不经输出 strip)。
    from app.services.agent_conversation_service import AgentConversationService

    convs = AgentConversationService(db).get_conversations(user.id, limit=10)
    assert convs
    detail = AgentConversationService(db).get_conversation_detail(user.id, convs[0].id)
    assistant_msgs = [m for m in detail.messages if m.role == "assistant"]
    assert any("reva-ui" in (m.content or "") for m in assistant_msgs), (
        "短路产出的 block 必须存活于落库消息"
    )
