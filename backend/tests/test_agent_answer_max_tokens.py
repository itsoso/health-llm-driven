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
