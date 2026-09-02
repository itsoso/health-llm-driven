# -*- coding: utf-8 -*-
"""rank8 · 深分析内层工具进程内直调(orchestrator in-process)。

背景(docs/plans/2026-07-13-latency-roadmap-phase2.md §rank8):
对话 Agent 的 health_analysis(analysis_type='orchestrator') 工具原本 POST localhost
/orchestrator/chat(非流式),该 loopback 请求重入整个 FastAPI 中间件栈,含 main.py 的
60s 请求超时中间件 —— 正是历史"内层 60s 连杀"故障类的根。本迁移改为进程内直接
await run_orchestrator(fresh SessionLocal, user_id 显式传),超时由 executor 内显式
asyncio.wait_for 接管;结果与旧 HTTP 响应体 SHAPE-IDENTICAL。

契约钉死:
- shape 一致:进程内返回值 == 旧 HTTP body(synthesis/intent/used_specialists/findings)。
- 用户作用域:user_id 显式传 self._current_user_id,A 的 executor 永不拿到 B 的结果。
- 超时:超过 cap → 干净的 "Error:" 工具错误字符串,回合存活(投影 fail-open 不抛)。
- kill-switch:flag False → 回退旧 HTTP 路径(_api_post),True → 进程内。
- DB 会话纪律:用独立 fresh SessionLocal(非 self.db),成功不显式 commit、finally close,
  异常 rollback + close —— 忠实复刻旧 HTTP 边界的 get_db 会话隔离。
"""
import asyncio
import json

import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.orchestrator.schema import Intent, OrchestratorResponse, SpecialistFinding
from app.services.agent_executor import AgentExecutor, _project_orchestrator_result


def _sample_response(query: str, *, synthesis: str = "睡眠与恢复整体稳定,建议规律作息。") -> OrchestratorResponse:
    return OrchestratorResponse(
        query=query,
        intent=Intent(raw_query=query, categories=["recovery"], keywords=["睡眠"]),
        findings=[
            SpecialistFinding(
                specialist_name="RecoveryCoach",
                category="recovery",
                summary="恢复状态良好",
                findings=[{"severity": 1, "title": "readiness 78", "action": "保持"}],
                raw={"readiness": 78, "detail": "大量原始字段"},
            )
        ],
        synthesis=synthesis,
        used_specialists=["RecoveryCoach"],
        twin_build_ms=12,
        total_ms=345,
    )


class _SpySession:
    """替身 fresh session:run_orchestrator 被 stub 故永不查询,只需记录 rollback/close 生命周期。"""

    def __init__(self):
        self.rolled_back = False
        self.closed = False

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


# ── shape 一致:进程内返回值 == 旧 HTTP body ────────────────────────────────────


async def test_inprocess_result_shape_identical_to_http(db, monkeypatch):
    q = "综合分析一下我的恢复"
    resp = _sample_response(q)

    async def fake_run_orchestrator(_db, _user_id, _req):
        return resp

    monkeypatch.setattr("app.orchestrator.run_orchestrator", fake_run_orchestrator)

    executor = AgentExecutor(db)
    executor._current_user_id = 7
    inproc = await executor._run_orchestrator_in_process(q)

    # 旧 HTTP 路径返回的就是 model_dump(mode="json") 的序列化(见 api/orchestrator.chat)。
    http_body = json.dumps(resp.model_dump(mode="json"), ensure_ascii=False)

    # 工具结果边界逐键一致。
    assert json.loads(inproc) == json.loads(http_body)
    # 上层投影(_project_orchestrator_result)输出也逐字节一致 → 二次合成/shadow 捕获零改动。
    assert _project_orchestrator_result(inproc) == _project_orchestrator_result(http_body)

    # 投影后仍保留 shadow/passthrough 依赖的契约字段。
    projected = json.loads(_project_orchestrator_result(inproc))
    assert projected["synthesis"] == resp.synthesis
    assert projected["used_specialists"] == ["RecoveryCoach"]
    assert projected["intent"]["categories"] == ["recovery"]
    # findings 被投影成精简形,raw 大字段已丢。
    assert projected["findings"][0]["specialist"] == "RecoveryCoach"
    assert "raw" not in projected["findings"][0]


async def test_inprocess_result_json_parseable_with_synthesis(db, monkeypatch):
    """shadow 捕获路径(5117 行 json.loads → 读 synthesis)必须能解析进程内返回值。"""
    q = "帮我看看代谢"
    resp = _sample_response(q, synthesis="代谢指标稳定。")

    async def fake_run_orchestrator(_db, _user_id, _req):
        return resp

    monkeypatch.setattr("app.orchestrator.run_orchestrator", fake_run_orchestrator)

    executor = AgentExecutor(db)
    executor._current_user_id = 7
    result = await executor._run_orchestrator_in_process(q)

    parsed = json.loads(result)  # 不得抛
    assert parsed["synthesis"] == "代谢指标稳定。"


# ── 用户作用域:A 的 executor 永不拿到 B 的结果 ─────────────────────────────────


async def test_user_scoping_passes_current_user_id(db, monkeypatch):
    seen_user_ids: list[int] = []

    async def fake_run_orchestrator(_db, user_id, req):
        seen_user_ids.append(user_id)
        # synthesis 编码收到的 user_id,证明结果确实按用户产生。
        return _sample_response(req.query, synthesis=f"user={user_id}")

    monkeypatch.setattr("app.orchestrator.run_orchestrator", fake_run_orchestrator)

    executor_a = AgentExecutor(db)
    executor_a._current_user_id = 111
    result_a = await executor_a._run_orchestrator_in_process("A 的问题")

    executor_b = AgentExecutor(db)
    executor_b._current_user_id = 222
    result_b = await executor_b._run_orchestrator_in_process("B 的问题")

    assert seen_user_ids == [111, 222]
    parsed_a = json.loads(result_a)
    assert parsed_a["query"] == "A 的问题"
    assert parsed_a["synthesis"] == "user=111"
    assert json.loads(result_b)["synthesis"] == "user=222"
    # 对抗:A 的业务结果绝不含 B 的身份标记。不要扫描整个 JSON 中的裸数字：
    # created_at 等无关时间戳也可能随机包含相同的三位数字。
    assert "user=222" not in result_a


async def test_missing_user_id_fails_loud_no_orchestrator_call(db, monkeypatch):
    called = {"n": 0}

    async def fake_run_orchestrator(_db, _user_id, _req):
        called["n"] += 1
        return _sample_response("x")

    monkeypatch.setattr("app.orchestrator.run_orchestrator", fake_run_orchestrator)

    executor = AgentExecutor(db)
    executor._current_user_id = None  # 无身份
    result = await executor._run_orchestrator_in_process("匿名深分析")

    assert result.startswith("Error:")
    assert "用户身份" in result
    assert called["n"] == 0  # 无身份绝不调 orchestrator(不会误用别人 session)


# ── DB 会话纪律:独立 fresh SessionLocal,与 self.db 隔离 ───────────────────────


async def test_uses_fresh_session_not_self_db_and_closes(db, monkeypatch):
    spy = _SpySession()
    monkeypatch.setattr("app.database.SessionLocal", lambda: spy)

    captured = {}

    async def fake_run_orchestrator(_db, _user_id, _req):
        captured["db"] = _db
        return _sample_response("q")

    monkeypatch.setattr("app.orchestrator.run_orchestrator", fake_run_orchestrator)

    executor = AgentExecutor(db)
    executor._current_user_id = 7
    await executor._run_orchestrator_in_process("q")

    # run_orchestrator 收到的是 fresh session(spy),不是 executor 的事务 session。
    assert captured["db"] is spy
    assert captured["db"] is not executor.db
    # 成功路径:不显式 commit(副作用写各自内部 commit),finally close;不 rollback。
    assert spy.closed is True
    assert spy.rolled_back is False


async def test_real_fresh_session_is_distinct_session_object(db, monkeypatch):
    """不打桩 SessionLocal 时,run_orchestrator 收到的仍是一个真实 Session 且 != self.db。"""
    captured = {}

    async def fake_run_orchestrator(_db, _user_id, _req):
        captured["db"] = _db
        return _sample_response("q")

    monkeypatch.setattr("app.orchestrator.run_orchestrator", fake_run_orchestrator)

    executor = AgentExecutor(db)
    executor._current_user_id = 7
    await executor._run_orchestrator_in_process("q")

    assert isinstance(captured["db"], Session)
    assert captured["db"] is not executor.db


# ── 超时:超过 cap → 干净工具错误字符串,回合存活 ──────────────────────────────


async def test_timeout_returns_clean_tool_error_turn_survives(db, monkeypatch):
    spy = _SpySession()
    monkeypatch.setattr("app.database.SessionLocal", lambda: spy)

    async def slow_run_orchestrator(_db, _user_id, _req):
        await asyncio.sleep(5)  # 远超 cap
        return _sample_response("q")

    monkeypatch.setattr("app.orchestrator.run_orchestrator", slow_run_orchestrator)

    executor = AgentExecutor(db)
    executor._current_user_id = 7
    executor.ORCHESTRATOR_IN_PROCESS_TIMEOUT_S = 0.05  # 收紧 cap 让超时可测

    result = await executor._run_orchestrator_in_process("q")

    assert result.startswith("Error:")
    assert "超时" in result
    # 回合存活:投影层对 "Error:" 字符串 fail-open(不抛,原样返回),下游把它当工具结果。
    assert _project_orchestrator_result(result) == result
    # 超时路径:fresh session rollback + close(不泄漏)。
    assert spy.rolled_back is True
    assert spy.closed is True


async def test_orchestrator_exception_returns_sanitized_tool_error(db, monkeypatch):
    spy = _SpySession()
    monkeypatch.setattr("app.database.SessionLocal", lambda: spy)

    async def boom(_db, _user_id, _req):
        raise RuntimeError("provider key sk-secret-should-not-leak exploded")

    monkeypatch.setattr("app.orchestrator.run_orchestrator", boom)

    executor = AgentExecutor(db)
    executor._current_user_id = 7
    result = await executor._run_orchestrator_in_process("q")

    assert result.startswith("Error:")
    # 异常路径同样 rollback + close。
    assert spy.rolled_back is True
    assert spy.closed is True


# ── kill-switch:flag False → 旧 HTTP 路径,True → 进程内 ────────────────────────


async def test_kill_switch_false_uses_http_path(db, monkeypatch):
    calls = {}

    async def fake_api_post(url, headers, data):
        calls["http"] = {"url": url, "data": data}
        return json.dumps(_sample_response(data["query"]).model_dump(mode="json"), ensure_ascii=False)

    async def fake_inproc(question):
        calls["inproc"] = question
        return "{}"

    monkeypatch.setattr(settings, "orchestrator_in_process", False, raising=False)

    executor = AgentExecutor(db)
    executor._current_user_id = 7
    executor._api_post = fake_api_post
    executor._run_orchestrator_in_process = fake_inproc

    result = await executor._exec_health_analysis(
        "http://localhost:8000/api/v1", {}, {"analysis_type": "orchestrator", "question": "深分析我"}
    )

    assert "http" in calls
    assert "inproc" not in calls  # 进程内路径未被走
    assert calls["http"]["url"].endswith("/orchestrator/chat")
    assert calls["http"]["data"] == {"query": "深分析我"}
    # 结果仍经 _project_orchestrator_result 投影,synthesis 保留。
    assert json.loads(result)["synthesis"]


async def test_kill_switch_true_uses_inprocess_path(db, monkeypatch):
    calls = {}

    async def fake_api_post(url, headers, data):
        calls["http"] = {"url": url, "data": data}
        return "{}"

    async def fake_inproc(question):
        calls["inproc"] = question
        return json.dumps(_sample_response(question).model_dump(mode="json"), ensure_ascii=False)

    monkeypatch.setattr(settings, "orchestrator_in_process", True, raising=False)

    executor = AgentExecutor(db)
    executor._current_user_id = 7
    executor._api_post = fake_api_post
    executor._run_orchestrator_in_process = fake_inproc

    result = await executor._exec_health_analysis(
        "http://localhost:8000/api/v1", {}, {"analysis_type": "orchestrator", "question": "深分析我"}
    )

    assert "inproc" in calls
    assert "http" not in calls  # HTTP 路径未被走
    assert calls["inproc"] == "深分析我"
    assert json.loads(result)["synthesis"]
