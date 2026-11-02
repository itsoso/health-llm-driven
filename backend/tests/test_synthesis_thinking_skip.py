"""简单查询合成轮关思考（founder「列出胃药」延迟 trace 的修复）。

reasoning 模型(qwen3.7-max)的思考阶段对简单查询/列表是纯浪费:探针实证合成轮 TTFT
~36s→~1.6s(关思考)。修法:_is_fast_eligible_turn 判定的简单回合在合成轮注入
enable_thinking=false;分析/建议/深度分析回合保留完整思考(规避全局思考封顶伤质量的 A/B 否决)。
"""
import pytest

from app.config import settings
from app.services.agent_executor import AgentExecutor, _is_fast_eligible_turn
from app.services.llm.model_registry import get_model


def _mk(db, *, skip_thinking, deep=False, model="qwen3.7-max"):
    ex = AgentExecutor(db)
    ex._current_user_id = 1
    ex._last_effective_model_id = model
    ex._turn_invoked_deep_analysis = deep
    ex._turn_synthesis_skip_thinking = skip_thinking
    return ex


class TestSynthesisThinkingSkip:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("with_tools", [True, False])
    async def test_current_model_control_reaches_answer_transport_only(self, db, monkeypatch, with_tools):
        ex = _mk(db, skip_thinking=True, model="qwen3.8-max")
        seen = []

        class Provider:
            model = "qwen3.8-max"

            async def chat_stream(self, **kwargs):
                seen.append(kwargs)
                yield {"type": "content", "text": "已查询。"}
                yield {"type": "finish", "finish_reason": "stop"}

        tools = [{"type": "function", "function": {"name": "health_query"}}] if with_tools else []
        monkeypatch.setattr(settings, "agent_base_url", None)
        monkeypatch.setattr(settings, "llm_explicit_prompt_cache", False)
        monkeypatch.setattr(settings, "llm_force_record_tool_choice", False)
        monkeypatch.setattr(ex, "_model_tools_for_turn", lambda value: value)
        monkeypatch.setattr(ex, "_resolve_chat_provider", lambda value: (Provider(), value))
        events = [event async for event in ex._call_llm_stream(
            [{"role": "user", "content": "查询今天的饮水总量"}], tools,
        )]
        assert len(seen) == 1
        assert events[-1]["finish_reason"] == "stop"
        if with_tools:
            assert "enable_thinking" not in seen[0]
        else:
            assert seen[0]["enable_thinking"] is False
        assert "thinking_budget" not in seen[0]

    @pytest.mark.parametrize("model", ["qwen3.8-max", "qwen3.8-max-preview"])
    def test_verified_current_model_simple_answer_disables_thinking(self, db, model):
        ex = _mk(db, skip_thinking=True, model=model)
        kw = {}
        ex._maybe_apply_synthesis_thinking_budget(kw)
        assert kw == {"enable_thinking": False}

    @pytest.mark.parametrize("model", ["qwen3.8-max", "qwen3.8-max-preview"])
    def test_disable_only_capability_does_not_enable_budget(self, db, monkeypatch, model):
        monkeypatch.setattr(settings, "synthesis_thinking_budget", 512)
        ex = _mk(db, skip_thinking=False, model=model)
        ex._staged_response_mode = "on"
        ex._staged_answer_task_tier = "balanced"
        kw = {}
        ex._maybe_apply_synthesis_thinking_budget(kw)
        assert kw == {}
        assert get_model(model).supports_thinking_budget is False

    @pytest.mark.parametrize("guard", ["deep", "high_stakes", "recovery"])
    def test_current_model_quality_guards_keep_thinking(self, db, monkeypatch, guard):
        ex = _mk(db, skip_thinking=True, model="qwen3.8-max", deep=guard == "deep")
        if guard == "high_stakes":
            ex._staged_response_mode = "on"
            ex._staged_answer_task_tier = "high_stakes"
        if guard == "recovery":
            monkeypatch.setattr(ex, "_requires_quality_floor", lambda: True)
        kw = {}
        ex._maybe_apply_synthesis_thinking_budget(kw)
        assert kw == {}

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
    def test_medication_lookup_keeps_clinical_quality_floor(self):
        assert _is_fast_eligible_turn("列出我正在吃的胃药", has_images=False, has_file=False) is False

    def test_nonclinical_lookup_remains_simple(self):
        assert _is_fast_eligible_turn("显示我的血压记录", has_images=False, has_file=False) is True

    def test_analysis_intents_are_not_simple(self):
        # 这些保留完整思考(质量优先)
        assert _is_fast_eligible_turn("帮我分析这几种胃药的相互作用", has_images=False, has_file=False) is False
        assert _is_fast_eligible_turn("这些胃药和我的补剂有冲突吗", has_images=False, has_file=False) is False

    def test_images_never_simple(self):
        assert _is_fast_eligible_turn("列出我的胃药", has_images=True, has_file=False) is False
