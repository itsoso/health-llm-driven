# -*- coding: utf-8 -*-
"""Agent executor provider 失败回退回归。

钉:用户选定的 provider(如 langbridge 商用网关 GPT-5.5)在 tool-calling
chat() 上报错(网关浏览器适配器只支持流式 → 500 "adapter has no chat() method:
TokenPlanAdapter")时,_call_llm 应回退到稳定的 tokenplan provider,而不是
把 500 直接抛给用户(截图里的 "Agent 执行遇到问题: Error code: 500 ...")。
"""


class _Raising:
    model = "gpt-5.5"

    async def chat(self, **kwargs):
        raise RuntimeError(
            "Error code: 500 - {'error': {'message': "
            "'adapter has no chat() method: TokenPlanAdapter', 'type': 'server_error'}}"
        )


class _Ok:
    model = "tokenplan-fallback"

    def __init__(self):
        self.calls = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        return {"content": "fallback ok", "finish_reason": "stop"}


async def test_call_llm_fails_over_to_tokenplan_on_provider_error(db, monkeypatch):
    import app.services.llm.factory as factory
    import app.services.llm.pii_scrub as pii
    import app.services.llm.usage_tracker as tracker
    from app.services.agent_executor import AgentExecutor, settings as ax_settings

    # 不走 AGENT_BASE_URL 直连分支 → 走用户 provider 路径
    monkeypatch.setattr(ax_settings, "agent_base_url", None, raising=False)
    monkeypatch.setattr(ax_settings, "agent_api_key", None, raising=False)

    ok = _Ok()
    monkeypatch.setattr(factory, "create_provider_for_user", lambda uid, dbs: _Raising())
    monkeypatch.setattr(factory, "create_llm_provider", lambda kind: ok)
    # 包装层在测试里走直通,避免依赖真实 usage/pii 包装细节
    monkeypatch.setattr(pii, "wrap_provider_pii_scrub", lambda p: p)
    monkeypatch.setattr(tracker, "wrap_provider", lambda p: p)

    ex = AgentExecutor(db)
    ex._current_user_id = 1

    resp = await ex._call_llm([{"role": "user", "content": "hi"}], None)

    assert resp["content"] == "fallback ok"
    assert ok.calls, "回退 provider 应被实际调用"
    assert ex._last_provider_model_name in ("tokenplan-fallback", "tokenplan(fallback)")


async def test_call_llm_no_fallback_when_primary_ok(db, monkeypatch):
    import app.services.llm.factory as factory
    import app.services.llm.pii_scrub as pii
    import app.services.llm.usage_tracker as tracker
    from app.services.agent_executor import AgentExecutor, settings as ax_settings

    monkeypatch.setattr(ax_settings, "agent_base_url", None, raising=False)
    monkeypatch.setattr(ax_settings, "agent_api_key", None, raising=False)

    primary = _Ok()
    fb = _Ok()
    monkeypatch.setattr(factory, "create_provider_for_user", lambda uid, dbs: primary)
    monkeypatch.setattr(factory, "create_llm_provider", lambda kind: fb)
    monkeypatch.setattr(pii, "wrap_provider_pii_scrub", lambda p: p)
    monkeypatch.setattr(tracker, "wrap_provider", lambda p: p)

    ex = AgentExecutor(db)
    ex._current_user_id = 1
    resp = await ex._call_llm([{"role": "user", "content": "hi"}], None)

    assert resp["content"] == "fallback ok"
    assert primary.calls and not fb.calls, "主 provider 正常时不应触发回退"
