"""R2: 高置信记录轮 force tool_choice 的门控(纯函数)+ registry flag + ships-OFF 断言。

探针依据(backend/scripts/probe_tool_choice_strict.py, 2026-07-17 真网实测):
TokenPlan qwen 系 thinking 模式下 tool_choice=object/required 400;
enable_thinking=false 后 named force 双模型(qwen3.6-flash / qwen3.7-max)PASS 且参数合法。
故 force 恒与关思考成对;模型门控走 ModelEntry.supports_forced_tool_choice registry flag
(安全评审 2026-07-17:不用模型名子串)。首轮判据打**原始 messages**(跨轮累积 tool 结果;
fast-record 压缩版恒 [system,user] 判不出轮次——同评审抓出)。
"""
from app.services.agent_executor import _should_force_record_tool_choice

_TOOLS = [
    {"type": "function", "function": {"name": "health_record"}},
    {"type": "function", "function": {"name": "health_query"}},
]
_FIRST_ROUND = [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "喝了300ml水"},
]
# 原始 messages 在后续轮真实累积的形态(run_stream 主循环 append tool 结果)
_LATER_ROUND = _FIRST_ROUND + [
    {"role": "assistant", "content": None, "tool_calls": [{}]},
    {"role": "tool", "content": '{"id": 1}'},
]


def test_forces_on_first_round_verified_model():
    assert _should_force_record_tool_choice(True, _FIRST_ROUND, _TOOLS, True) is True


def test_never_forces_later_rounds():
    """原始 messages 含 tool 结果 = 非首轮;再 force = 每轮被迫再调工具 → 无限循环。"""
    assert _should_force_record_tool_choice(True, _LATER_ROUND, _TOOLS, True) is False


def test_never_forces_unverified_model():
    """ModelEntry.supports_forced_tool_choice=False(未探针验证)不带 kwarg。"""
    assert _should_force_record_tool_choice(True, _FIRST_ROUND, _TOOLS, False) is False


def test_registry_flags_match_probe_verified_models():
    """registry 真源断言:恰好两个探针验证过的模型置 True(新增模型须各自跑探针)。"""
    from app.services.llm.model_registry import MODELS
    flagged = sorted(m.id for m in MODELS if getattr(m, "supports_forced_tool_choice", False))
    assert flagged == ["qwen3.6-flash", "qwen3.7-max"], flagged


def test_never_forces_without_health_record_tool():
    """工具子集里没有 health_record 时 force 不存在的工具 = 400。"""
    only_query = [{"type": "function", "function": {"name": "health_query"}}]
    assert _should_force_record_tool_choice(True, _FIRST_ROUND, only_query, True) is False
    assert _should_force_record_tool_choice(True, _FIRST_ROUND, None, True) is False


def test_never_forces_without_record_intent():
    assert _should_force_record_tool_choice(False, _FIRST_ROUND, _TOOLS, True) is False


def test_ships_off_by_default():
    from app.config import Settings
    assert Settings.model_fields["llm_force_record_tool_choice"].default is False
