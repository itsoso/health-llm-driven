# -*- coding: utf-8 -*-
"""GenUI metric_table (latency-roadmap-phase2 rank1) — 后端从**已执行工具结果**确定性
建表, 消除强模型把工具结果重打成大 markdown 表的 decode 税。

覆盖:
  1. 建表器确定性 (单元格逐字来自工具结果字段) + 对抗 (字段缺失 → 绝不编造行)。
  2. strip 护栏覆盖伪造的 metric_table fence (与图表同一 R4 剥离器)。
  3. cap 缺失 → 零 emission + prompt 保持现状 (mac 指令原样); cap 声明 → fence 追加 +
     ≤500字 契约注入 + mac 指令被覆盖。
  4. 伪造 fence 被剥、确定性 fence 保留; kill-switch 关 → 即便声明 cap 也不发。
  5. R4 纪律: LLM 合成抛错 → 表格仍从工具结果确定性建出 (数值不来自 LLM)。

本文件不依赖真实 LLM/provider: e2e 用 monkeypatch 让 _call_llm_stream / _execute_tool
返回受控事件, 直接驱动 AgentExecutor.run_stream。
"""
import inspect
import json

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.genui import (
    GENUI_TABLE_CAP,
    build_table_from_tool_call,
    build_tables_from_tool_calls,
    render_metric_table_block,
    strip_reva_ui_blocks,
    placeholder_reva_ui_blocks,
)


@pytest.fixture(autouse=True)
def _clear_agent_dup_cache():
    from app.api.agent import _RECENT_DUP_CACHE

    _RECENT_DUP_CACHE.clear()
    yield
    _RECENT_DUP_CACHE.clear()


# ---------------------------------------------------------------------------
# helpers: canned tool-result payloads
# ---------------------------------------------------------------------------

def _batch_result(**over):
    payload = {
        "queries": [
            {"dimension": "hrv", "days": 7, "agg": "avg", "value": 58, "unit": "ms", "n": 7},
            {"dimension": "sleep", "days": 7, "agg": "trend", "value": -5, "n": 7, "note": "略降"},
            {"dimension": "diet", "days": 7, "agg": None, "value": None, "data": "…"},
        ],
        "meta": {"executed": 3, "failed": 0},
        "compare": {"a": 0, "b": 1, "op": "diff", "value": 3, "unit": "ms"},
    }
    payload.update(over)
    return json.dumps(payload, ensure_ascii=False)


def _lab_single_result():
    return json.dumps(
        {
            "count": 2,
            "items": [
                {"name": "LDL", "value": 3.4, "unit": "mmol/L", "record_date": "2026-07-01",
                 "is_abnormal": True, "reference_low": 0, "reference_high": 3.3},
                {"name": "LDL", "value": 3.1, "unit": "mmol/L", "record_date": "2026-01-01",
                 "is_abnormal": False, "reference_low": 0, "reference_high": 3.3},
            ],
        },
        ensure_ascii=False,
    )


def _lab_batch_result():
    return json.dumps(
        {
            "batch": True,
            "count": 3,
            "queried": ["LDL", "ALT"],
            "by_name": {
                "LDL": {"count": 2, "items": [
                    {"name": "LDL", "value": 3.4, "unit": "mmol/L", "record_date": "2026-07-01",
                     "is_abnormal": True, "reference_low": 0, "reference_high": 3.3},
                    {"name": "LDL", "value": 3.1, "unit": "mmol/L", "record_date": "2026-01-01"},
                ]},
                "ALT": {"count": 1, "items": [
                    {"name": "ALT", "value": 22, "unit": "U/L", "record_date": "2026-07-01",
                     "is_abnormal": False},
                ]},
            },
            "truncated": False,
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# A. builder determinism — every cell traces to a tool-result field
# ---------------------------------------------------------------------------

def test_batch_cells_trace_to_fields():
    block = build_table_from_tool_call("health_query_batch", {}, _batch_result())
    assert block is not None
    assert block["type"] == "metric_table" and block["v"] == 1
    rows = block["rows"]
    # 3 valid rows: hrv, sleep (both have scalar value), + compare. diet(null) dropped.
    assert len(rows) == 3
    hrv = rows[0]
    assert hrv["metric"] == "HRV"
    assert hrv["value"] == "58 ms"          # value + unit, verbatim
    assert "近7天平均" in hrv["note"] and "7天数据" in hrv["note"]
    sleep = rows[1]
    assert sleep["value"] == "-5" and "略降" in sleep["note"]  # note field verbatim
    cmp_row = rows[2]
    assert cmp_row["value"] == "3 ms" and "差值" in cmp_row["metric"]


def test_batch_drops_null_value_rows_no_invention():
    """agg 省略/空数据/不可聚合 (value=None) → 不落行, 绝不编造单元格。"""
    result = json.dumps({"queries": [
        {"dimension": "diet", "days": 7, "agg": None, "value": None, "data": "x"},
        {"dimension": "hrv", "days": 7, "agg": "avg", "value": 60, "unit": "ms"},
    ]}, ensure_ascii=False)
    block = build_table_from_tool_call("health_query_batch", {}, result)
    assert block is not None
    assert len(block["rows"]) == 1
    assert block["rows"][0]["metric"] == "HRV" and block["rows"][0]["value"] == "60 ms"


def test_batch_all_null_builds_nothing():
    result = json.dumps({"queries": [
        {"dimension": "diet", "agg": None, "value": None},
        {"dimension": "medication", "agg": None, "value": None},
    ]}, ensure_ascii=False)
    assert build_table_from_tool_call("health_query_batch", {}, result) is None


def test_lab_single_history_table():
    block = build_table_from_tool_call("query_lab_indicators", {}, _lab_single_result())
    assert block is not None
    assert [c["key"] for c in block["columns"]] == ["metric", "value", "note"]
    assert len(block["rows"]) == 2
    r0 = block["rows"][0]
    assert r0["value"] == "3.4 mmol/L"          # value + unit
    assert "0–3.3" in r0["note"] and "异常" in r0["note"]  # reference + is_abnormal


def test_lab_batch_latest_per_indicator():
    block = build_table_from_tool_call("query_lab_indicators", {}, _lab_batch_result())
    assert block is not None
    metrics = {r["metric"]: r["value"] for r in block["rows"]}
    assert metrics["LDL"] == "3.4 mmol/L"       # latest item (items[0])
    assert metrics["ALT"] == "22 U/L"
    assert len(block["rows"]) == 2               # one row per queried indicator


def test_lab_items_without_value_skipped():
    result = json.dumps({"count": 1, "items": [
        {"name": "X", "value": None, "unit": "mg"},
    ]}, ensure_ascii=False)
    assert build_table_from_tool_call("query_lab_indicators", {}, result) is None


def test_weight_table_fat_column_kept_when_all_present():
    result = json.dumps([
        {"record_date": "2026-07-01", "weight": 70.5, "body_fat_percentage": 18.2},
        {"record_date": "2026-06-01", "weight": 71.0, "body_fat_percentage": 18.8},
    ], ensure_ascii=False)
    block = build_table_from_tool_call("health_query", {"dimension": "weight"}, result)
    assert [c["key"] for c in block["columns"]] == ["date", "weight", "fat"]
    assert block["rows"][0] == {"date": "2026-07-01", "weight": "70.5 kg", "fat": "18.2 %"}


def test_weight_fat_column_dropped_when_partial():
    """任一行缺 body_fat → 整列丢弃 (绝不用占位值冒充数据)。"""
    result = json.dumps([
        {"record_date": "2026-07-01", "weight": 70.5, "body_fat_percentage": 18.2},
        {"record_date": "2026-06-01", "weight": 71.0, "body_fat_percentage": None},
    ], ensure_ascii=False)
    block = build_table_from_tool_call("health_query", {"dimension": "weight"}, result)
    assert [c["key"] for c in block["columns"]] == ["date", "weight"]
    assert "fat" not in block["rows"][0]


def test_bp_table_with_pulse():
    result = json.dumps([
        {"record_date": "2026-07-01", "systolic": 120, "diastolic": 80, "pulse": 62},
        {"record_date": "2026-06-30", "systolic": 118, "diastolic": 78, "pulse": 60},
    ], ensure_ascii=False)
    block = build_table_from_tool_call("health_query", {"dimension": "blood_pressure"}, result)
    assert [c["key"] for c in block["columns"]] == ["date", "bp", "pulse"]
    assert block["rows"][0] == {"date": "2026-07-01", "bp": "120/80 mmHg", "pulse": "62 bpm"}


def test_bp_row_missing_systolic_skipped():
    result = json.dumps([
        {"record_date": "2026-07-01", "systolic": None, "diastolic": 80},
    ], ensure_ascii=False)
    assert build_table_from_tool_call("health_query", {"dimension": "blood_pressure"}, result) is None


def test_water_table():
    result = json.dumps(
        {"record_date": "2026-07-13", "total_amount": 1500, "target_amount": 2000, "records": []},
        ensure_ascii=False,
    )
    block = build_table_from_tool_call("health_query", {"dimension": "water"}, result)
    assert block["rows"] == [
        {"item": "今日饮水", "value": "1500 ml"},
        {"item": "目标", "value": "2000 ml"},
    ]


def test_water_missing_total_builds_nothing():
    result = json.dumps({"record_date": "2026-07-13", "records": []}, ensure_ascii=False)
    assert build_table_from_tool_call("health_query", {"dimension": "water"}, result) is None


# ---------------------------------------------------------------------------
# A2. adversarial / fail-open
# ---------------------------------------------------------------------------

def test_error_string_builds_nothing():
    assert build_table_from_tool_call("health_query_batch", {}, "Error: 未知维度") is None


def test_unparseable_result_builds_nothing():
    assert build_table_from_tool_call("health_query_batch", {}, "让我查一下…（不是JSON）") is None


def test_truncated_list_suffix_recovered():
    """_api_get 会给超长 list 加 '...(仅显示前10条)' 尾注 → 剥掉后仍能解析。"""
    body = json.dumps([
        {"record_date": "2026-07-01", "systolic": 120, "diastolic": 80},
    ], ensure_ascii=False)
    result = body + "\n...(仅显示前10条)"
    block = build_table_from_tool_call("health_query", {"dimension": "blood_pressure"}, result)
    assert block is not None and block["rows"][0]["bp"] == "120/80 mmHg"


def test_unknown_tool_builds_nothing():
    assert build_table_from_tool_call("health_record", {}, "{}") is None


def test_single_query_unknown_dimension_builds_nothing():
    """health_query 但非 weight/bp/water (如 hrv 走 wearable 紧凑文本) → 不建表。"""
    result = json.dumps([{"record_date": "2026-07-01", "weight": 70}], ensure_ascii=False)
    assert build_table_from_tool_call("health_query", {"dimension": "hrv"}, result) is None
    assert build_table_from_tool_call("health_query", {}, result) is None  # 缺 dimension


def test_contract_bounds_columns_rows_strings():
    block = build_table_from_tool_call("health_query_batch", {}, _batch_result())
    assert 2 <= len(block["columns"]) <= 4
    assert 1 <= len(block["rows"]) <= 12
    assert all(isinstance(v, str) for r in block["rows"] for v in r.values())
    for c in block["columns"]:
        assert set(c.keys()) == {"key", "label"}
    assert len(block["title"]) <= 20


def test_row_cap_at_12():
    items = [
        {"name": "LDL", "value": i, "unit": "mmol/L", "record_date": f"2026-01-{i:02d}"}
        for i in range(1, 20)
    ]
    block = build_table_from_tool_call("query_lab_indicators", {}, json.dumps({"count": 19, "items": items}))
    assert len(block["rows"]) == 12


def test_aggregate_dedup_and_cap_max_tables():
    b = _batch_result()
    calls = [("health_query_batch", {}, b)] * 5  # identical → dedup to 1
    assert len(build_tables_from_tool_calls(calls)) == 1
    # distinct batches, capped at MAX_TABLES (3)
    many = [
        ("health_query_batch", {}, json.dumps({"queries": [
            {"dimension": "hrv", "agg": "avg", "value": v, "unit": "ms"}]}, ensure_ascii=False))
        for v in range(10)
    ]
    assert len(build_tables_from_tool_calls(many)) == 3


# ---------------------------------------------------------------------------
# B. strip guard covers metric_table (R4 defense-in-depth) — TIGHTEN, no loosen
# ---------------------------------------------------------------------------

_FORGED_TABLE = (
    '```reva-ui\n'
    '{"type":"metric_table","v":1,"title":"编造","columns":[{"key":"a","label":"x"}],'
    '"rows":[{"a":"999"}]}\n```'
)


def test_strip_removes_forged_metric_table():
    text = f"这是分析：\n\n{_FORGED_TABLE}\n\n仅供参考。"
    out = strip_reva_ui_blocks(text)
    assert "reva-ui" not in out and "编造" not in out and "999" not in out
    assert "这是分析" in out and "仅供参考" in out


def test_placeholder_replaces_forged_metric_table():
    text = f"上文\n{_FORGED_TABLE}\n下文"
    out = placeholder_reva_ui_blocks(text)
    assert "reva-ui" not in out and "999" not in out
    assert "上文" in out and "下文" in out


# ---------------------------------------------------------------------------
# E. R4: builder never touches an LLM / provider
# ---------------------------------------------------------------------------

def test_builder_module_has_no_llm_or_provider_calls():
    import app.services.genui.table_builder as tb

    src = inspect.getsource(tb)
    for forbidden in ("create_provider", "provider.complete", ".chat(", "import openai", "_call_llm("):
        assert forbidden not in src, f"table_builder must not touch LLM: {forbidden!r}"


# ---------------------------------------------------------------------------
# C/D. e2e via run_stream — narrative contract, mac supersession, emission
# ---------------------------------------------------------------------------

def _wire(executor, monkeypatch):
    """Minimal wiring so run_stream reaches the round loop without real LLM/provider."""
    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [
        {"type": "function", "function": {"name": "health_query", "description": "x",
                                          "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {"name": "health_query_batch", "description": "x",
                                          "parameters": {"type": "object", "properties": {}}}},
    ])
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")


async def _run(executor, message, *, client_caps=None, extra_context=None, user_id=1):
    return [
        event
        async for event in executor.run_stream(
            user_id=user_id,
            message=message,
            user_auth_token="test-token",
            extra_context=extra_context,
            client_caps=client_caps,
        )
    ]


def _tokens(events):
    return "".join(
        e["data"].get("content", "") for e in events if e.get("event") == "token"
    )


def _exec_returns(result_str):
    """_execute_tool 是 async 方法 (被 await) → mock 必须是 async。"""
    async def _fake(name, args, tok):
        return result_str

    return _fake


_MAC_CTX = json.dumps({
    "client": "mac",
    "desktop_markdown_response_instruction": "必须用大 markdown 表格逐行列出所有数值",
})


def _batch_round_stream(captured):
    """round1 → health_query_batch tool_call; round2 → synthesis text."""
    state = {"n": 0}

    async def fake_stream(messages, round_tools):
        state["n"] += 1
        captured.append([m.get("content") for m in messages])
        if state["n"] == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "b1",
                "function": {"name": "health_query_batch",
                             "arguments": '{"queries":[{"dimension":"hrv","days":7,"agg":"avg"}]}'},
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "结论：HRV 处于个人常态区间，继续保持。"}
            yield {"type": "finish", "finish_reason": "stop"}

    return fake_stream


@pytest.mark.asyncio
async def test_cap_on_injects_500_contract_and_supersedes_mac(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _batch_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_batch_result()))

    await _run(executor, "对比我这周和上周的 HRV", client_caps=[GENUI_TABLE_CAP],
               extra_context=_MAC_CTX, user_id=user.id)

    prompt = "\n".join(c for msgs in captured for c in msgs if isinstance(c, str))
    assert "数据回答格式要求" in prompt and "不超过 500 字" in prompt
    # mac 大表指令被覆盖: 声明了 cap → 不注入桌面端 markdown 表格强制指令
    assert "必须用大 markdown 表格逐行列出所有数值" not in prompt
    assert "桌面端回复格式要求" not in prompt


@pytest.mark.asyncio
async def test_cap_off_preserves_mac_instruction_no_contract(db, auth_user_and_headers, monkeypatch):
    """cap 缺失 → 现状: mac 指令原样注入, 无 ≤500字 契约 (prompt 未被本特性改动)。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _batch_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_batch_result()))

    events = await _run(executor, "对比我这周和上周的 HRV", client_caps=[],
                        extra_context=_MAC_CTX, user_id=user.id)

    prompt = "\n".join(c for msgs in captured for c in msgs if isinstance(c, str))
    assert "必须用大 markdown 表格逐行列出所有数值" in prompt  # mac 指令保留
    assert "数据回答格式要求" not in prompt and "不超过 500 字" not in prompt
    assert "reva-ui" not in _tokens(events)  # 零 emission


@pytest.mark.asyncio
async def test_cap_on_emits_metric_table_after_synthesis(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _batch_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_batch_result()))

    events = await _run(executor, "对比我这周和上周的 HRV", client_caps=[GENUI_TABLE_CAP], user_id=user.id)
    rendered = _tokens(events)

    # 叙事在前、卡片在后
    assert "结论：HRV" in rendered
    assert "```reva-ui" in rendered and '"type":"metric_table"' in rendered
    assert rendered.index("结论") < rendered.index("reva-ui")
    # 数值来自工具结果 (58 ms), 不来自 LLM 文本
    assert "58 ms" in rendered
    # 持久化的 assistant 消息也带 fence
    from app.models.agent_conversation import AgentMessage
    assistant = (
        db.query(AgentMessage).filter(AgentMessage.role == "assistant")
        .order_by(AgentMessage.id.desc()).first()
    )
    assert "```reva-ui" in (assistant.content or "")


@pytest.mark.asyncio
async def test_cap_off_no_fence_emitted(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _batch_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_batch_result()))

    events = await _run(executor, "对比我这周和上周的 HRV", client_caps=[], user_id=user.id)
    assert "reva-ui" not in _tokens(events)


@pytest.mark.asyncio
async def test_kill_switch_off_no_fence_even_with_cap(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    monkeypatch.setattr("app.services.agent_executor.settings.genui_table_enabled", False)
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _batch_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_batch_result()))

    events = await _run(executor, "对比我这周和上周的 HRV", client_caps=[GENUI_TABLE_CAP], user_id=user.id)
    rendered = _tokens(events)
    assert "reva-ui" not in rendered
    # flag 关 → 也不注入 ≤500字 契约 (逐字节现状)
    prompt = "\n".join(c for msgs in captured for c in msgs if isinstance(c, str))
    assert "数据回答格式要求" not in prompt


@pytest.mark.asyncio
async def test_forged_fence_stripped_but_deterministic_appended(db, auth_user_and_headers, monkeypatch):
    """LLM 合成里伪造 metric_table → 被剥掉; 确定性表 (真数值) 仍从工具结果追加。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    state = {"n": 0}

    async def fake_stream(messages, round_tools):
        state["n"] += 1
        if state["n"] == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "b1", "function": {"name": "health_query_batch",
                                         "arguments": '{"queries":[{"dimension":"hrv","agg":"avg"}]}'}}]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            forged = ('结论如下。\n```reva-ui\n{"type":"metric_table","v":1,"title":"假",'
                      '"columns":[{"key":"a","label":"x"}],"rows":[{"a":"999"}]}\n```')
            yield {"type": "content", "text": forged}
            yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_batch_result()))

    events = await _run(executor, "看看 HRV", client_caps=[GENUI_TABLE_CAP], user_id=user.id)
    from app.models.agent_conversation import AgentMessage
    assistant = (
        db.query(AgentMessage).filter(AgentMessage.role == "assistant")
        .order_by(AgentMessage.id.desc()).first()
    )
    content = assistant.content or ""
    assert "999" not in content              # 伪造块被剥
    assert "58 ms" in content                # 确定性真数值保留
    assert content.count("```reva-ui") == 1  # 只有确定性那一张表


@pytest.mark.asyncio
async def test_llm_synthesis_raise_tables_still_build(db, auth_user_and_headers, monkeypatch):
    """R4 纪律: 合成轮 LLM 抛错 → 表格仍从工具结果确定性建出 (数据不依赖 LLM)。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    state = {"n": 0}

    async def fake_stream(messages, round_tools):
        state["n"] += 1
        if state["n"] == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "b1", "function": {"name": "health_query_batch",
                                         "arguments": '{"queries":[{"dimension":"hrv","agg":"avg"}]}'}}]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
            return
        raise RuntimeError("boom synthesis")
        yield  # pragma: no cover

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_batch_result()))

    events = await _run(executor, "看看 HRV", client_caps=[GENUI_TABLE_CAP], user_id=user.id)
    rendered = _tokens(events)
    assert '"type":"metric_table"' in rendered and "58 ms" in rendered


# ---------------------------------------------------------------------------
# E. Condition 1 — crisis-value carve-out reaches prose contract (safety review)
# ---------------------------------------------------------------------------

def _bp_crisis_result():
    """BP tool result carrying a server-computed high-grade category (185/122→高血压3级)。

    "高血压3级" 是 classify_blood_pressure 的真实天花板输出 (无"危象"档), 用它而非合成词。
    """
    return json.dumps([
        {"record_date": "2026-07-01", "systolic": 185, "diastolic": 122,
         "pulse": 92, "category": "高血压3级"},
    ], ensure_ascii=False)


def _bp_round_stream(captured):
    """round1 → health_query blood_pressure tool_call; round2 → synthesis text。"""
    state = {"n": 0}

    async def fake_stream(messages, round_tools):
        state["n"] += 1
        captured.append([m.get("content") for m in messages])
        if state["n"] == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "bp1",
                "function": {"name": "health_query",
                             "arguments": '{"dimension":"blood_pressure"}'},
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "结论：你的血压处于高血压3级水平，请及时就医。"}
            yield {"type": "finish", "finish_reason": "stop"}

    return fake_stream


# 安全例外的判别性片段 (仅本 carve-out 产出, 不会被 safety alert / mac 指令巧合命中)。
_CARVEOUT_MARKER = "必须在正文中明确说出具体数值"


@pytest.mark.asyncio
async def test_cap_on_crisis_bp_injects_carveout(db, auth_user_and_headers, monkeypatch):
    """Condition 1: cap on + BP 高分级结果 → ≤500字 契约携带"危急值必须复述"安全例外,
    且既有"不复述数值行"与"安全边界照常表达"两行未被削弱; BP 路径仍确定性出卡片。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _bp_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_bp_crisis_result()))

    events = await _run(executor, "看看我的血压", client_caps=[GENUI_TABLE_CAP], user_id=user.id)

    prompt = "\n".join(c for msgs in captured for c in msgs if isinstance(c, str))
    assert "数据回答格式要求" in prompt and "不超过 500 字" in prompt
    assert _CARVEOUT_MARKER in prompt and "安全例外" in prompt        # 安全例外落进 prompt
    assert "高血压2-3级" in prompt                                    # 例外示例用真实分级词
    # 既有边界不被削弱: 两行原样保留
    assert "绝不逐行复述表格中的数值行" in prompt
    assert "不确定性与安全边界照常表达" in prompt
    # "以系统标注为准"锚句在场 (防模型对系统判正常的数值自加危急判断)
    assert "以系统安全提示" in prompt and "不要给系统标注为正常的数值自行加危急判断" in prompt
    # BP 高分级结果确实经确定性建表路径出卡片 (卡片内 category relay 由 Condition 2 单测覆盖)
    assert '"type":"metric_table"' in _tokens(events)


@pytest.mark.asyncio
async def test_cap_off_no_carveout(db, auth_user_and_headers, monkeypatch):
    """对称: cap 缺失 → ≤500字 契约整体不注入, 因此安全例外碎片也不存在。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire(executor, monkeypatch)
    captured: list = []
    monkeypatch.setattr(executor, "_call_llm_stream", _bp_round_stream(captured))
    monkeypatch.setattr(executor, "_execute_tool", _exec_returns(_bp_crisis_result()))

    await _run(executor, "看看我的血压", client_caps=[], user_id=user.id)

    prompt = "\n".join(c for msgs in captured for c in msgs if isinstance(c, str))
    assert "数据回答格式要求" not in prompt
    assert _CARVEOUT_MARKER not in prompt        # 契约缺失 → 无安全例外碎片
    assert "高血压2-3级" not in prompt            # 例外示例词也随契约整体缺席 (present iff cap on)
