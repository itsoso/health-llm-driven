"""Token 优化第一批(2026-07-11)契约测试。

#2 fast 回合工具白名单子集:固定 big-3, 不随消息变(保前缀缓存);
#3 orchestrator 结果投影:二次合成只吃 synthesis+精简 findings, 契约字段(perf)保留。
"""
import json

from app.services.tool_schema_registry import (
    FAST_TURN_TOOL_NAMES,
    HEALTH_TOOLS,
    get_health_tools,
)
from app.services.agent_executor import _project_orchestrator_result


def test_fast_subset_returns_exactly_big3_in_stable_order():
    subset = get_health_tools(subset=list(FAST_TURN_TOOL_NAMES))
    names = [t["function"]["name"] for t in subset]
    assert set(names) == {"health_record", "health_query", "health_manage"}
    # 顺序=HEALTH_TOOLS 定义序(字节稳定 → 前缀缓存友好), 两次调用完全一致
    assert names == [t["function"]["name"] for t in get_health_tools(subset=list(FAST_TURN_TOOL_NAMES))]


def test_full_toolset_unchanged_by_subset_param():
    assert get_health_tools() == HEALTH_TOOLS
    assert len(get_health_tools()) == len(HEALTH_TOOLS)


def test_subset_saves_majority_of_schema_bytes():
    full = len(json.dumps(get_health_tools(), ensure_ascii=False))
    small = len(json.dumps(get_health_tools(subset=list(FAST_TURN_TOOL_NAMES)), ensure_ascii=False))
    assert small < full * 0.55  # 实测 ~37%, 松断言防 schema 演化误红


def _fake_orchestrator_json() -> str:
    return json.dumps({
        "intent": "recovery",
        "synthesis": "今晚早睡半小时, 明天以恢复性运动为主。",
        "used_specialists": ["recovery_coach", "safety_guardian"],
        "perf": {"llm_ttft_ms": 1200},
        "findings": [
            {
                "specialist_name": "recovery_coach",
                "category": "recovery",
                "summary": "HRV 低于 7 日均值, 建议降负荷。",
                "findings": [
                    {"severity": "medium", "title": "HRV 下降", "action": "恢复走路 20 分钟", "raw_series": [1, 2, 3]},
                ],
                "raw": {"huge": "x" * 5000},
                "ms_elapsed": 812,
            },
        ],
    }, ensure_ascii=False)


def test_projection_keeps_contract_fields_and_drops_raw():
    raw = _fake_orchestrator_json()
    projected = json.loads(_project_orchestrator_result(raw))

    assert projected["synthesis"] == "今晚早睡半小时, 明天以恢复性运动为主。"
    assert projected["perf"] == {"llm_ttft_ms": 1200}          # round loop 透传契约
    assert projected["used_specialists"] == ["recovery_coach", "safety_guardian"]
    f = projected["findings"][0]
    assert f["specialist"] == "recovery_coach" and f["summary"].startswith("HRV")
    assert f["items"][0]["severity"] == "medium"
    assert "raw" not in json.dumps(projected)                   # 大头被丢
    assert len(_project_orchestrator_result(raw)) < len(raw) * 0.4


def test_projection_fails_open_on_non_orchestrator_payloads():
    # 非 JSON / 无 synthesis 的 JSON → 原样返回, 绝不丢内容
    assert _project_orchestrator_result("Error: 上游超时") == "Error: 上游超时"
    other = json.dumps({"items": [1, 2, 3]})
    assert _project_orchestrator_result(other) == other
