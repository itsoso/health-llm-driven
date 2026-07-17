"""R2: 高置信记录轮 force tool_choice 的门控(纯函数)+ ships-OFF 断言。

探针依据(backend/scripts/probe_tool_choice_strict.py, 2026-07-17 真网实测):
TokenPlan qwen 系 thinking 模式下 tool_choice=object/required 400;
enable_thinking=false 后 named force 双模型(qwen3.6-flash / qwen3.7-max)PASS 且参数合法。
故 force 恒与关思考成对,且仅 qwen 系生效。
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
_LATER_ROUND = _FIRST_ROUND + [
    {"role": "assistant", "content": None, "tool_calls": [{}]},
    {"role": "tool", "content": '{"id": 1}'},
]


def test_forces_on_first_round_qwen():
    assert _should_force_record_tool_choice(True, _FIRST_ROUND, _TOOLS, "qwen3.6-flash") is True


def test_never_forces_later_rounds():
    """有 tool 结果的后续轮再 force = 每轮被迫再调工具 → 无限循环,永远到不了合成。"""
    assert _should_force_record_tool_choice(True, _LATER_ROUND, _TOOLS, "qwen3.6-flash") is False


def test_never_forces_non_qwen():
    """未探针验证的家族不带 kwarg(镜像显式缓存'验证过的模型才开'纪律)。"""
    for model in ("MiniMax-M2.5", "deepseek-v4-flash", "commercial/Claude-Opus-4.7", None):
        assert _should_force_record_tool_choice(True, _FIRST_ROUND, _TOOLS, model) is False


def test_never_forces_without_health_record_tool():
    """工具子集里没有 health_record 时 force 不存在的工具 = 400。"""
    only_query = [{"type": "function", "function": {"name": "health_query"}}]
    assert _should_force_record_tool_choice(True, _FIRST_ROUND, only_query, "qwen3.7-max") is False
    assert _should_force_record_tool_choice(True, _FIRST_ROUND, None, "qwen3.7-max") is False


def test_never_forces_without_record_intent():
    assert _should_force_record_tool_choice(False, _FIRST_ROUND, _TOOLS, "qwen3.6-flash") is False


def test_ships_off_by_default():
    from app.config import Settings
    assert Settings.model_fields["llm_force_record_tool_choice"].default is False
