"""简单查询合成轮关思考（founder「列出胃药」延迟 trace 的修复）。

reasoning 模型(qwen3.7-max)的思考阶段对简单查询/列表是纯浪费:探针实证合成轮 TTFT
~36s→~1.6s(关思考)。修法:_is_fast_eligible_turn 判定的简单回合在合成轮注入
enable_thinking=false;分析/建议/深度分析回合保留完整思考(规避全局思考封顶伤质量的 A/B 否决)。
"""
from app.services.agent_executor import AgentExecutor, _is_fast_eligible_turn


def _mk(db, *, skip_thinking, deep=False, model="qwen3.7-max"):
    ex = AgentExecutor(db)
    ex._current_user_id = 1
    ex._last_effective_model_id = model
    ex._turn_invoked_deep_analysis = deep
    ex._turn_synthesis_skip_thinking = skip_thinking
    return ex


class TestSynthesisThinkingSkip:
    def test_simple_query_turn_disables_thinking(self, db):
        ex = _mk(db, skip_thinking=True)
        kw: dict = {}
        ex._maybe_apply_synthesis_thinking_budget(kw)
        assert kw.get("enable_thinking") is False  # 关思考 → TTFT 塌到 ~1.6s

    def test_analysis_turn_keeps_thinking(self, db):
        # 非简单回合(建议/分析)+ 全局封顶默认关 → 不碰思考, 保留质量
        ex = _mk(db, skip_thinking=False)
        kw: dict = {}
        ex._maybe_apply_synthesis_thinking_budget(kw)
        assert "enable_thinking" not in kw
        assert "thinking_budget" not in kw

    def test_deep_analysis_keeps_thinking_even_if_simple_flag(self, db):
        # 本轮调了 health_analysis → 即便简单标志被置, 也 fail-closed 保留完整思考
        ex = _mk(db, skip_thinking=True, deep=True)
        kw: dict = {}
        ex._maybe_apply_synthesis_thinking_budget(kw)
        assert "enable_thinking" not in kw

    def test_unsupported_model_not_touched(self, db):
        # 未验证 thinking 参数的模型(supports_thinking_budget=False)不注入 → 免端点 400
        ex = _mk(db, skip_thinking=True, model="qwen3.6-flash")
        kw: dict = {}
        ex._maybe_apply_synthesis_thinking_budget(kw)
        assert "enable_thinking" not in kw
        assert "thinking_budget" not in kw


class TestFastEligibleClassificationForThinkingSkip:
    def test_list_and_lookup_intents_are_simple(self):
        assert _is_fast_eligible_turn("列出我正在吃的胃药", has_images=False, has_file=False) is True
        assert _is_fast_eligible_turn("显示我的血压记录", has_images=False, has_file=False) is True

    def test_analysis_intents_are_not_simple(self):
        # 这些保留完整思考(质量优先)
        assert _is_fast_eligible_turn("帮我分析这几种胃药的相互作用", has_images=False, has_file=False) is False
        assert _is_fast_eligible_turn("这些胃药和我的补剂有冲突吗", has_images=False, has_file=False) is False

    def test_images_never_simple(self):
        assert _is_fast_eligible_turn("列出我的胃药", has_images=True, has_file=False) is False
