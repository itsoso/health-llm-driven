# -*- coding: utf-8 -*-
"""Fast-routed 工具决策轮的 lite 消息栈 (延迟优化: ~14k → <4k prefill)。

生产实测: advice/query 回合的**首个工具决策轮**已 fast-route 到 qwen3.6-flash,
但仍背全量栈 (full system prompt 含 8 分析 blob + 最后一条 user 折进的 KB 证据 +
15 轮历史 + 18KB tool schema), flash 白付 6-8s prefill。此特性把**该轮**的消息栈
换成 lite (无分析 blob / 无 KB / 只留最新 user + 折进紧邻 assistant), 合成/答案轮
仍走全量栈。

硬不变量 (本文件钉死):
  1. fast 工具决策轮的 messages 无分析 blob (世界观) 且无 KB 证据;
  2. lite 栈保留紧邻的上一条 assistant 回合 (跟进式消歧, 见
     [[feedback_fast_path_drops_followup_context]]);
  3. 合成/答案轮 (工具后) 的 messages 逐字节 = 现状 (全量栈, 含世界观 + KB);
  4. flag 关 → 每轮全量栈 (逐字节现状), 从不构建 lite;
  5. lite 栈显著小于全量栈 (prefill 预算)。
"""
import copy
from datetime import UTC, datetime

import pytest

from app.services import agent_executor as executor_module
from app.services.agent_executor import AgentExecutor, _build_lite_tool_round_messages
from app.services.llm import model_registry as reg
from tests.conftest import create_authenticated_user

# 全量 system prompt 里**无条件**注入的分析 blob (仅 lite=False), 作为「全量栈」探针。
WORLDVIEW_MARKER = "【健康世界观"
# 每回合折进最后一条 user 的 KB 证据探针 (monkeypatch 注入)。
KB_SENTINEL = "<<KB_LITE_TEST_SENTINEL>>"

# advice/分析 回合: _prefer_fast_record_model=False 且 _is_fast_eligible_turn=False
# → 全量栈回合, 其**首个工具决策轮**会被 fast-route (若 flag 开)。
ADVICE_MSG = "综合分析我最近的睡眠和肝功能趋势，我该怎么调整"


# ──────────────────────────────────────────────────────────────
# 单元级: _build_lite_tool_round_messages (镜像 _build_fast_record_messages 教训)
# ──────────────────────────────────────────────────────────────

def _roles(out):
    return [m["role"] for m in out]


def test_lite_builder_keeps_prior_assistant_turn_for_followup():
    """跟进式回复: 折进紧邻的上一条 assistant 做消歧 (『再来一杯』需上一轮咖啡上下文)。"""
    messages = [
        {"role": "system", "content": "<full twin/kb system prompt 世界观 blob…>"},
        {"role": "user", "content": "我早上喝了一杯美式咖啡"},
        {"role": "assistant", "content": "好的，已记录一杯美式咖啡。需要我分析今天的咖啡因摄入吗？"},
        {"role": "user", "content": "再来一杯，帮我综合分析今天咖啡因会不会超标"},
    ]
    out = _build_lite_tool_round_messages("LITE_SYS", messages)
    assert _roles(out) == ["system", "user"]
    assert out[0]["content"] == "LITE_SYS"
    u = out[-1]["content"]
    # 上一轮咖啡上下文 + 最新回复都在最后那条 user 里 (否则 tool 决策无从消歧)。
    assert "咖啡因" in u and "再来一杯" in u
    # 仍 compact: 不夹带更早的「我早上喝了一杯美式咖啡」那条无关早历史文本主体。
    # (咖啡因语义在折进的助手问句里, 但第一条 user 原文不被搬进来。)
    assert "我早上喝了一杯美式咖啡" not in u


def test_lite_builder_no_prior_assistant_stays_raw():
    messages = [
        {"role": "system", "content": "x"},
        {"role": "user", "content": ADVICE_MSG},
    ]
    out = _build_lite_tool_round_messages("LITE_SYS", messages)
    assert _roles(out) == ["system", "user"]
    assert out[-1]["content"] == ADVICE_MSG
    assert "上一轮助手" not in out[-1]["content"]


def test_lite_builder_truncates_long_prior_assistant():
    long = "咖啡因说明" + "啰嗦" * 1000
    messages = [
        {"role": "assistant", "content": long},
        {"role": "user", "content": ADVICE_MSG},
    ]
    out = _build_lite_tool_round_messages("LITE_SYS", messages)
    assert "啰嗦" * 1000 not in out[-1]["content"]
    assert out[-1]["content"].count("啰嗦") <= 400


def test_lite_builder_skips_empty_assistant():
    messages = [
        {"role": "assistant", "content": "   "},
        {"role": "user", "content": ADVICE_MSG},
    ]
    out = _build_lite_tool_round_messages("LITE_SYS", messages)
    assert out[-1]["content"] == ADVICE_MSG
    assert "上一轮助手" not in out[-1]["content"]


def test_lite_builder_picks_most_recent_assistant():
    messages = [
        {"role": "assistant", "content": "旧助手回合-无关"},
        {"role": "user", "content": "嗯"},
        {"role": "assistant", "content": "要不要我分析今天的咖啡因摄入?"},
        {"role": "user", "content": ADVICE_MSG},
    ]
    out = _build_lite_tool_round_messages("LITE_SYS", messages)
    u = out[-1]["content"]
    assert "咖啡因" in u and "无关" not in u


def test_lite_builder_multimodal_returns_none():
    """多模态 (list content) 无法字符串折叠 → None = 调用方 fail-open 到全量栈。"""
    messages = [
        {"role": "system", "content": "x"},
        {"role": "user", "content": [{"type": "text", "text": "hi"}, {"type": "image_url"}]},
    ]
    assert _build_lite_tool_round_messages("LITE_SYS", messages) is None


def test_lite_builder_no_user_returns_none():
    assert _build_lite_tool_round_messages("LITE_SYS", [{"role": "system", "content": "x"}]) is None


# ──────────────────────────────────────────────────────────────
# 端到端: 在 provider.chat_stream seam 捕获每轮 messages
# ──────────────────────────────────────────────────────────────

def _wire(executor, monkeypatch, provider_factory, *, user_provider, kb_sentinel=True):
    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr(
        "app.services.agent_executor.get_health_tools",
        lambda **k: [{
            "type": "function",
            "function": {
                "name": "health_analysis",
                "description": "analyze",
                "parameters": {"type": "object", "properties": {}},
            },
        }],
    )
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id", provider_factory
    )
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_user",
        lambda uid, db, **k: user_provider,
    )
    # KB 证据: monkeypatch 成固定 sentinel → 全量栈的最后一条 user 里出现; lite 栈不含。
    monkeypatch.setattr(
        executor,
        "_build_system_knowledge_prompt_context",
        (lambda user_id, message: f"## 系统知识库依据\n{KB_SENTINEL}") if kb_sentinel
        else (lambda user_id, message: ""),
    )


class _RecordingProvider:
    """按 model 分支: fast(qwen3.6-flash) 吐 tool_call; 强模型吐医疗正文。记录每轮 messages。"""

    def __init__(self, model_id, records):
        self.model = model_id
        self._records = records

    async def chat_stream(self, **kwargs):
        self._records.append({
            "model": self.model,
            "has_tools": bool(kwargs.get("tools")),
            "messages": copy.deepcopy(kwargs.get("messages")),
        })
        if self.model == "qwen3.6-flash":
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "r1", "type": "function",
                "function": {"name": "health_analysis", "arguments": "{}"},
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
            return
        yield {"type": "content", "text": "STRONG SYNTHESIS"}
        yield {"type": "finish", "finish_reason": "stop"}

    async def chat(self, **kwargs):
        self._records.append({
            "model": self.model,
            "has_tools": bool(kwargs.get("tools")),
            "messages": copy.deepcopy(kwargs.get("messages")),
            "nonstream": True,
        })
        return {"content": "STRONG SYNTHESIS", "finish_reason": "stop"}


class _RoundCountingProvider:
    """按轮次分支 (与 model 无关): 首轮吐 tool_call, 后续轮吐正文。记录每轮 messages。

    用于 flag-off (工具轮也在强模型上) 与 byte-identical 对比: 保证两次运行的轮结构对称。
    """

    def __init__(self, model_id, records, round_counter):
        self.model = model_id
        self._records = records
        self._rc = round_counter

    async def chat_stream(self, **kwargs):
        self._records.append({
            "model": self.model,
            "has_tools": bool(kwargs.get("tools")),
            "messages": copy.deepcopy(kwargs.get("messages")),
        })
        self._rc["n"] += 1
        if self._rc["n"] == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "r1", "type": "function",
                "function": {"name": "health_analysis", "arguments": "{}"},
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
            return
        yield {"type": "content", "text": "STRONG SYNTHESIS"}
        yield {"type": "finish", "finish_reason": "stop"}

    async def chat(self, **kwargs):
        self._records.append({
            "model": self.model,
            "has_tools": bool(kwargs.get("tools")),
            "messages": copy.deepcopy(kwargs.get("messages")),
            "nonstream": True,
        })
        return {"content": "STRONG SYNTHESIS", "finish_reason": "stop"}


async def _tool_result(name, args, token):
    import json
    return json.dumps({"summary": "睡眠/肝功能分析结果"}, ensure_ascii=False)


async def _run(executor, message, user_id, conversation_id=None):
    return [
        event
        async for event in executor.run_stream(
            user_id=user_id,
            message=message,
            user_auth_token="test-token",
            conversation_id=conversation_id,
        )
    ]


def _msgs_text(messages):
    """把一轮 messages 全部内容拼成一个可搜索字符串 (content 可能是 str 或 list)。"""
    out = []
    for m in messages or []:
        c = m.get("content")
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, list):
            out.append(str(c))
    return "\n".join(out)


@pytest.mark.asyncio
async def test_fast_tool_round_uses_lite_stack_synthesis_uses_full(db, monkeypatch):
    """核心: flag 开, advice 回合 → 首个工具决策轮 messages = lite (无世界观/无 KB, system=lite);
    工具后合成轮 messages = 全量栈 (含世界观 + KB)。"""
    user, _ = create_authenticated_user(db)
    executor = AgentExecutor(db)
    records: list = []

    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", True)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "qwen3.6-flash")
    _wire(
        executor, monkeypatch,
        lambda mid: _RecordingProvider(mid, records),
        user_provider=_RecordingProvider("qwen3.7-max", records),
    )
    monkeypatch.setattr(executor, "_execute_tool", _tool_result)

    events = await _run(executor, ADVICE_MSG, user.id)
    rendered = "".join(
        e["data"].get("content", "") for e in events if e.get("event") == "token"
    )

    assert len(records) >= 2, records
    fast_round = records[0]
    synth_round = records[1]

    # 首轮 = fast(qwen3.6-flash) 决策工具, 用 lite 栈。
    assert fast_round["model"] == "qwen3.6-flash"
    fast_text = _msgs_text(fast_round["messages"])
    # (1) 无分析 blob (世界观)。
    assert WORLDVIEW_MARKER not in fast_text, "fast tool round leaked analysis blob (worldview)"
    # (1) 无 KB 证据。
    assert KB_SENTINEL not in fast_text, "fast tool round leaked KB evidence"
    # lite 栈就是 [system, user] 两条。
    assert _roles(fast_round["messages"]) == ["system", "user"]
    # system 是 lite (含记录规则人格骨架, 但无世界观)。
    assert "你是用户的 AI 健康助理" in fast_round["messages"][0]["content"]
    # 用户原话仍在。
    assert ADVICE_MSG in fast_text

    # 工具后合成轮 = 强模型, 全量栈 (含世界观 + KB)。
    assert synth_round["model"] == "qwen3.7-max"
    synth_text = _msgs_text(synth_round["messages"])
    assert WORLDVIEW_MARKER in synth_text, "synthesis round must carry full stack (worldview)"
    assert KB_SENTINEL in synth_text, "synthesis round must carry KB evidence"
    # 医疗正文来自强模型合成轮。
    assert rendered == "STRONG SYNTHESIS"


@pytest.mark.asyncio
async def test_lite_round_much_smaller_than_full(db, monkeypatch):
    """prefill 预算: fast lite 轮的消息总字节显著小于合成轮的全量栈。"""
    user, _ = create_authenticated_user(db)
    executor = AgentExecutor(db)
    records: list = []

    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", True)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "qwen3.6-flash")
    _wire(
        executor, monkeypatch,
        lambda mid: _RecordingProvider(mid, records),
        user_provider=_RecordingProvider("qwen3.7-max", records),
    )
    monkeypatch.setattr(executor, "_execute_tool", _tool_result)

    await _run(executor, ADVICE_MSG, user.id)

    lite_chars = len(_msgs_text(records[0]["messages"]))
    full_chars = len(_msgs_text(records[1]["messages"]))
    # lite 严格小于全量栈。注意: 空数据测试用户的 8 个分析 blob 多为空, 且 18KB tool
    # schema 走 tools kwarg (不在 messages 里), 故这里的 full 只 ~4.5k —— 现网真实用户
    # (populated blobs + 真 KB 证据 + 15 轮历史) full ~10k+, lite 削减更显著。
    assert lite_chars < full_chars, (lite_chars, full_chars)
    # 绝对预算: lite 工具轮消息 < 4k 字符 (task 目标)。
    assert lite_chars < 4000, f"lite tool round too large ({lite_chars} chars)"
    # lite 至少省掉全量-lite 的差值 (世界观 blob + KB 证据 + turn-context), 非零裁剪。
    assert full_chars - lite_chars > 500, (lite_chars, full_chars)


@pytest.mark.asyncio
async def test_synthesis_round_byte_identical_flag_off_vs_on(db, monkeypatch):
    """合成轮 messages 在 flag 关 vs 开下逐字节相同 — 只有工具决策轮不同。

    两次运行用**同一个用户** (同一 user_id → 同一 Twin/健康上下文, 免本地 Redis Twin 缓存
    跨用户污染, 见 [[project_backend_test_redis_pollution]]), 各自新对话 (历史隔离), 同一条
    消息, 同一 mock 工具结果 → 合成轮累积的 messages ([full_system, KB-user,
    assistant_toolcall, tool_result]) 必须相同。工具决策轮: flag 开 = lite, flag 关 = 全量 → 不同。
    """
    user, _ = create_authenticated_user(db)
    original_build_turn_snapshot = executor_module.build_turn_snapshot

    def build_snapshot_with_fixed_clock(*args, **kwargs):
        kwargs.setdefault("now_utc", datetime(2026, 7, 17, 4, 0, tzinfo=UTC))
        return original_build_turn_snapshot(*args, **kwargs)

    monkeypatch.setattr(
        executor_module, "build_turn_snapshot", build_snapshot_with_fixed_clock
    )

    def _run_once(flag_on):
        executor = AgentExecutor(db)
        records: list = []
        rc = {"n": 0}
        monkeypatch.setattr(
            "app.services.agent_executor.settings.task_tiered_routing", flag_on
        )
        monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "qwen3.6-flash")
        _wire(
            executor, monkeypatch,
            lambda mid: _RoundCountingProvider(mid, records, rc),
            user_provider=_RoundCountingProvider("qwen3.7-max", records, rc),
        )
        monkeypatch.setattr(executor, "_execute_tool", _tool_result)
        return records, executor

    # flag OFF (新对话, conversation_id=None → run_stream 建新会话, 历史仅当前轮)。
    records_off, ex_off = _run_once(False)
    await _run(ex_off, ADVICE_MSG, user.id)

    # flag ON (同用户, 另一新对话)。
    records_on, ex_on = _run_once(True)
    await _run(ex_on, ADVICE_MSG, user.id)

    assert len(records_off) >= 2 and len(records_on) >= 2, (records_off, records_on)

    # 合成轮 (第 2 轮) messages 逐字节相同 (全量栈两边一致)。
    assert records_off[1]["messages"] == records_on[1]["messages"], (
        "synthesis-round messages drifted between flag off/on"
    )
    # 工具决策轮 (第 1 轮) 不同: flag 关 = 全量(含世界观), flag 开 = lite(无世界观)。
    off_tool = _msgs_text(records_off[0]["messages"])
    on_tool = _msgs_text(records_on[0]["messages"])
    assert WORLDVIEW_MARKER in off_tool, "flag-off tool round must be full stack"
    assert WORLDVIEW_MARKER not in on_tool, "flag-on tool round must be lite"
    assert records_off[0]["messages"] != records_on[0]["messages"]


@pytest.mark.asyncio
async def test_flag_off_never_builds_lite_stack(db, monkeypatch):
    """flag 关 → 从不构建 lite 栈; 每轮全量栈 (逐字节现状)。"""
    user, _ = create_authenticated_user(db)
    executor = AgentExecutor(db)
    records: list = []
    rc = {"n": 0}

    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", False)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "qwen3.6-flash")
    _wire(
        executor, monkeypatch,
        lambda mid: _RoundCountingProvider(mid, records, rc),
        user_provider=_RoundCountingProvider("qwen3.7-max", records, rc),
    )
    monkeypatch.setattr(executor, "_execute_tool", _tool_result)

    await _run(executor, ADVICE_MSG, user.id)

    assert executor._lite_tool_round_messages is None
    # 每轮都携带全量栈 (世界观在)。
    for rec in records:
        assert WORLDVIEW_MARKER in _msgs_text(rec["messages"])


@pytest.mark.asyncio
async def test_followup_advice_fast_round_carries_prior_assistant(db, monkeypatch):
    """跟进式 advice (端到端): 预置一轮咖啡对话 → 跟进「再来一杯，综合分析会不会超标」的
    fast 工具决策轮 messages 里带上一轮助手的咖啡因上下文 (消歧, 见 memory 教训)。"""
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = create_authenticated_user(db)
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title="coffee")
    svc.save_message(conv.id, "user", "我早上喝了一杯美式咖啡")
    svc.save_message(
        conv.id, "assistant",
        "好的，已记录一杯美式咖啡（约120mg咖啡因）。需要我分析今天的咖啡因摄入吗？",
    )

    executor = AgentExecutor(db)
    records: list = []
    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", True)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "qwen3.6-flash")
    _wire(
        executor, monkeypatch,
        lambda mid: _RecordingProvider(mid, records),
        user_provider=_RecordingProvider("qwen3.7-max", records),
        kb_sentinel=False,
    )
    monkeypatch.setattr(executor, "_execute_tool", _tool_result)

    await _run(
        executor, "再来一杯，帮我综合分析今天咖啡因会不会超标", user.id,
        conversation_id=conv.id,
    )

    fast_round = records[0]
    assert fast_round["model"] == "qwen3.6-flash"
    fast_text = _msgs_text(fast_round["messages"])
    # 上一轮助手的咖啡因上下文被折进 fast 轮 (否则「再来一杯」无从消歧)。
    assert "咖啡因" in fast_text
    assert "上一轮助手" in fast_text
    # 仍是 lite (无世界观)。
    assert WORLDVIEW_MARKER not in fast_text
