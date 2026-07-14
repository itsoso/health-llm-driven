"""Wave 2 · 慢工具通用 fail-loud:心跳 + per-tool 超时 + 读路径诚实。

- _run_tool_with_progress:慢工具执行期间吐 status 心跳(保活+进度)、超预算 fail-loud
  中止、工具抛异常 → fail-loud 串;快工具零心跳。
- _fallback_text_from_tool_results(C3):全部工具结果都是 Error 时,返回规范化诚实失败
  而非空串(空串被上层兜成通用"没拿到有效模型回复",遮盖真因)。
"""
import asyncio

import pytest

import app.services.agent_executor as ae
from app.services.agent_executor import AgentExecutor, _fallback_text_from_tool_results


async def _drain(gen):
    hbs, result = [], None
    async for kind, val in gen:
        if kind == "heartbeat":
            hbs.append(val)
        else:
            result = val
    return hbs, result


def _executor():
    return AgentExecutor(db=object())


# ── 心跳 helper ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_fast_tool_no_heartbeat_returns_result():
    ex = _executor()
    async def fast(_n, _a, _t):
        return '{"ok": 1}'
    ex._execute_tool = fast
    hbs, result = await _drain(ex._run_tool_with_progress("health_query", "{}", None, "查看…"))
    assert hbs == []           # 快工具不该发心跳
    assert result == '{"ok": 1}'


@pytest.mark.asyncio
async def test_slow_tool_emits_heartbeats_then_result(monkeypatch):
    monkeypatch.setattr(ae, "_TOOL_HEARTBEAT_INTERVAL_S", 0.02)
    monkeypatch.setattr(ae, "_TOOL_TIMEOUT_DEFAULT_S", 1.0)  # 充裕,不会超时
    ex = _executor()
    async def slow(_n, _a, _t):
        await asyncio.sleep(0.05)
        return "DONE"
    ex._execute_tool = slow
    hbs, result = await _drain(ex._run_tool_with_progress("health_query", "{}", None, "查看健康数据…"))
    assert result == "DONE"
    assert len(hbs) >= 1
    # 心跳形状与既有 stage=tool status 契约同源
    ev = hbs[0]
    assert ev["event"] == "status"
    assert ev["data"]["stage"] == "tool"
    assert ev["data"]["label"] == "查看健康数据…"


@pytest.mark.asyncio
async def test_tool_timeout_fails_loud_and_cancels(monkeypatch):
    monkeypatch.setattr(ae, "_TOOL_HEARTBEAT_INTERVAL_S", 0.02)
    monkeypatch.setattr(ae, "_TOOL_TIMEOUT_DEFAULT_S", 0.06)
    ex = _executor()
    cancelled = {"v": False}
    async def hang(_n, _a, _t):
        try:
            await asyncio.sleep(5)
            return "SHOULD NOT REACH"
        except asyncio.CancelledError:
            cancelled["v"] = True
            raise
    ex._execute_tool = hang
    hbs, result = await _drain(ex._run_tool_with_progress("health_query", "{}", None, "查看健康数据…"))
    assert result.startswith("Error:")
    assert "耗时过长" in result
    assert len(hbs) >= 1
    await asyncio.sleep(0.01)  # 让取消传播
    assert cancelled["v"] is True   # 底层 task 确被取消,不泄漏


@pytest.mark.asyncio
async def test_tool_exception_fails_loud():
    ex = _executor()
    async def boom(_n, _a, _t):
        raise RuntimeError("upstream 500")
    ex._execute_tool = boom
    hbs, result = await _drain(ex._run_tool_with_progress("health_query", "{}", None, "查看健康数据…"))
    assert result.startswith("Error:")
    assert "执行失败" in result
    assert "upstream 500" not in result   # 不泄漏原始异常内部细节


@pytest.mark.asyncio
async def test_health_analysis_gets_longer_budget():
    # health_analysis 走进程内 orchestrator(自有 120s wait_for)→ override 135s
    assert ae._TOOL_TIMEOUT_OVERRIDES.get("health_analysis", 0) > ae._TOOL_TIMEOUT_DEFAULT_S


# ── C3 读路径诚实 ────────────────────────────────────────────────────────
def _tool_msg(content):
    return {"role": "tool", "tool_call_id": "x", "content": content}


def test_all_errors_returns_honest_failure_not_empty():
    msgs = [_tool_msg("Error: API 返回 500: <内部细节>"), _tool_msg("Error: 查询超时")]
    out = _fallback_text_from_tool_results(msgs)
    assert out                      # 非空 —— 不再 silent-green
    assert "没有成功" in out or "没能" in out
    assert "500" not in out         # 不泄漏原始 error 内部细节


def test_good_result_wins_over_earlier_error():
    # 有可展示人话时仍优先返回它(行为不变),不因见过 error 就吞掉
    msgs = [_tool_msg("Error: 一步失败"), _tool_msg('{"message": "步数 8000"}')]
    out = _fallback_text_from_tool_results(msgs)
    assert out == "步数 8000"


def test_no_error_no_content_still_empty():
    # 无错误、无可展示人话 → 仍返回空串,交回既有重试链(行为不变)
    msgs = [_tool_msg('{"id": 5}')]  # id-only,无回执 → ''
    out = _fallback_text_from_tool_results(msgs, has_verified_write=False)
    assert out == ""
