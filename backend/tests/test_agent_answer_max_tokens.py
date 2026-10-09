"""回归: 最终用户回复不应被 4000 token 截断。

根因 (2026-06 用户截图): Opus 4.7 长养护方案被 max_tokens=4000 硬截,
用户需手动点"继续"。修复: 统一 ANSWER_MAX_TOKENS=8000, 用于 _call_llm /
fallback / direct / 多模型综合 四处最终回复生成。
"""
from app.services import agent_executor as ae


def test_answer_max_tokens_is_generous():
    """常量存在且 >=8000 (覆盖长健康方案)。"""
    assert hasattr(ae, "ANSWER_MAX_TOKENS")
    assert ae.ANSWER_MAX_TOKENS >= 8000


def test_no_4000_token_cap_left_in_final_answer_paths():
    """源码里最终回复生成处不应再出现裸 4000 上限 (防回退)。

    允许 perspective 成员仍用 4000(中间产物), 但 _call_llm 主回复 / fallback /
    direct / 综合 必须走 ANSWER_MAX_TOKENS。
    """
    import inspect, re
    src = inspect.getsource(ae)
    # _call_llm 主路径: provider chat 的 max_tokens 必须是常量, 不是 4000 字面量
    # 用关键上下文定位 _call_llm 内的 chat_kwargs
    m = re.search(r'chat_kwargs\s*=\s*\{.*?\}', src, re.S)
    assert m, "chat_kwargs 块未找到"
    assert "ANSWER_MAX_TOKENS" in m.group(0), "主回复 chat_kwargs 仍是裸 max_tokens"
    assert '"max_tokens": 4000' not in m.group(0)


async def test_closed_html_request_keeps_document_budget_in_actual_provider_call(db, monkeypatch):
    executor = ae.AgentExecutor(db)
    executor._current_turn_user_message = '今天是否适合运动？给我推荐适合我的运动的方式以及运动的强度，最终生成一个HTML页面。'
    executor._fast_route_simple_turn = True
    executor._staged_response_mode = 'on'
    executor._staged_answer_task_tier = 'balanced'
    captured = []
    class Provider:
        model = 'synthetic-budget'
        async def chat_stream(self, **kwargs):
            captured.append(kwargs['max_tokens'])
            yield {'type':'content', 'text':'synthetic'}
            yield {'type':'finish', 'finish_reason':'stop'}
    monkeypatch.setattr(executor, '_resolve_chat_provider', lambda tools: (Provider(), tools))
    monkeypatch.setattr(ae.settings, 'agent_base_url', None)
    monkeypatch.setattr(ae.settings, 'agent_api_key', None)
    for tools in [[], [{'type':'function','function':{'name':'knowledge_search'}}]]:
        _ = [event async for event in executor._call_llm_stream([{'role':'user','content':'synthetic'}],tools)]
    assert captured == [ae.ANSWER_MAX_TOKENS, ae.ANSWER_MAX_TOKENS]


def test_html_word_outside_closed_contract_does_not_expand_fast_budget(db):
    executor = ae.AgentExecutor(db)
    executor._fast_route_simple_turn = True
    for message in ['HTML是什么意思', '查一下今天喝水量', '帮我制定未来十天的锻炼计划']:
        executor._current_turn_user_message = message
        assert executor._answer_max_tokens() == ae.FAST_ROUTE_ANSWER_MAX_TOKENS
