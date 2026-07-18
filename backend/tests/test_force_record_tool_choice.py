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


# ── 否定守卫(2026-07-17 生产 20 轮召回测试实测:「别记录」被 force 逼出记录 + 谎报已记)──

def _prefer_fast_record(msg: str) -> bool:
    """复现 run_stream 里 _prefer_fast_record_model 的确定性门(四条排除),独立于模型选择。"""
    import app.services.agent_executor as ae
    return ae._has_fast_record_write_intent(msg)


def test_query_noun_record_suppresses_prefer_fast_record():
    """「饮食记录/列表格」里的记录是名词,必须走查询,不能进 fast-record 写入门。"""
    import app.services.agent_executor as ae

    for msg in [
        "今天我的饮食的记录，帮我列个表格出来。",
        "不是记录，是列出我今天吃的所有东西。",
        "查询我今天的饮食记录",
    ]:
        assert _prefer_fast_record(msg) is False, msg
        assert ae._is_fast_eligible_turn(msg, has_images=False, has_file=False) is True


def test_negation_suppresses_prefer_fast_record():
    """「别记录/记在心里」→ 不走 fast-record → 不被 R2 force 逼出记录(降级全模型自裁量)。"""
    for msg in [
        "我的健身房储物柜密码是蓝色的4731,记在心里就行别记录",
        "这个不用记录",
        "算了别记了",
        "别写进去",
    ]:
        assert _prefer_fast_record(msg) is False, msg


def test_negation_guard_allows_genuine_records():
    """误命中成本必须为零:想记的说法(不要记错/别忘了记录/别记成)绝不被守卫误杀。"""
    from app.services.utterance_intent_classifier import classify_agent_utterance

    for msg in [
        "记录喝水500ml",
        "帮我记录午饭鳕鱼50g",
        "别忘了记录我今天的体重",   # 命令式:要记
        "记录晚饭，别记成午饭",       # 改归类:仍是明确写入
    ]:
        assert classify_agent_utterance(msg).primary == "write", msg


def test_negation_blocks_recovered_textual_record_authorization():
    """弱模型把 health_record 吐成文本时,「别记录」也不授权恢复执行(绕 fast-path 的第二道门)。"""
    import app.services.agent_executor as ae
    assert ae._has_explicit_text_record_intent("储物柜密码4731别记录") is False
    assert ae._has_explicit_text_record_intent("记录体重71.4kg") is True


def test_negation_excludes_fast_eligible_turn():
    """三条 fast 路径统一排除的第二条:否定轮不降 fast 模型 → 留强模型可靠拒记(生产实测:
    降到 qwen3.6-flash 时 health_record 仍在工具集,软护栏不牢)。真记录/查询仍 fast-eligible。"""
    import app.services.agent_executor as ae
    assert ae._is_fast_eligible_turn("记在心里就行别记录", has_images=False, has_file=False) is False
    assert ae._is_fast_eligible_turn("这个不用记录", has_images=False, has_file=False) is False
    # 未被误杀:真记录 + 简单查询仍走 fast
    assert ae._is_fast_eligible_turn("记录喝水500ml", has_images=False, has_file=False) is True
    assert ae._is_fast_eligible_turn("我今天喝了多少水", has_images=False, has_file=False) is True
