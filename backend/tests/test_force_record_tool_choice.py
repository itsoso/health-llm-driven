"""R2: 高置信记录轮 force tool_choice 的门控(纯函数)+ registry flag + ships-OFF 断言。

探针依据(backend/scripts/probe_tool_choice_strict.py, 2026-07-17 真网实测):
TokenPlan qwen 系 thinking 模式下 tool_choice=object/required 400;
enable_thinking=false 后 named force 双模型(qwen3.6-flash / qwen3.7-max)PASS 且参数合法。
故 force 恒与关思考成对;模型门控走 ModelEntry.supports_forced_tool_choice registry flag
(安全评审 2026-07-17:不用模型名子串)。首轮判据打**原始 messages**(跨轮累积 tool 结果;
fast-record 压缩版恒 [system,user] 判不出轮次——同评审抓出)。
"""
from app.services.agent_executor import (
    _should_force_explicit_aigc_media_tool_choice,
    _should_force_record_tool_choice,
    _tool_names_for_turn,
)

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

CLINICIAN_FALLBACK_NONWRITE_MESSAGES = (
    "医生让我记录每天腰痛情况",
    "医生叫我记录每天腰痛情况",
    "大夫交代我记录每天腰痛情况",
    "我让医生记录每天腰痛情况",
    "家属叫医生记录每天腰痛情况",
    "医生说让我记录每天腰痛情况。请记录医生诊断：臀肌无力",
    "医生告诉我记录每天腰痛情况。请记录医生诊断：臀肌无力",
    "医生嘱咐你记录每天腰痛情况。请记录医生诊断：臀肌无力",
    "医生告诉我让我记录每天腰痛情况。请记录医生诊断：臀肌无力",
    "医生要求记录每天腰痛情况。请记录医生诊断：臀肌无力",
    "医生说请记录每天腰痛情况。请记录医生诊断：臀肌无力",
    "不要保存医生诊断",
    "不要写入医生反馈",
    "不需要保存医生诊断",
    "请先不要保存医生诊断",
    "请不要再保存医生诊断",
    "请不要帮我保存医生诊断",
    "不要写入医生体重",
    "不要不保存医生诊断",
    "根据医生诊断删除昨天用药记录",
    "依据医生意见调整用药剂量",
    "按照医生建议同步健康数据",
    "根据 医生 诊断 删除昨天用药记录",
    "根据医生诊断不要删除昨天用药记录",
    "根据医生诊断删除昨天用药记录并停药",
    "根据医 生诊断删除昨天用药记录",
    "按照医生建议同 步健康数据",
    "根据医，生诊断删除昨天用药记录",
    "根据医：生诊断调整体重",
    "依据医、师意见同步健康数据",
    "按照物理治，疗师建议删除记录",
    "根据医,生诊断删除昨天用药记录",
    "依据医/师意见同步健康数据",
    "按照物理治.疗师建议删除记录",
)


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


def test_explicit_aigc_photo_turn_exposes_only_the_draft_tool():
    assert _tool_names_for_turn(
        "基于这张照片生成今天活动的短视频，以此照片为开头。",
        fast_route=False,
        analysis_subset=False,
    ) == ("draft_aigc_media",)


def test_explicit_aigc_photo_turn_forces_only_the_draft_tool_on_first_round():
    tools = [{"type": "function", "function": {"name": "draft_aigc_media"}}]

    assert _should_force_explicit_aigc_media_tool_choice(
        "基于这张照片生成今天活动的短视频，以此照片为开头。",
        _FIRST_ROUND,
        tools,
        True,
    ) is True
    assert _should_force_explicit_aigc_media_tool_choice(
        "基于这张照片生成今天活动的短视频，以此照片为开头。",
        _LATER_ROUND,
        tools,
        True,
    ) is False


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


def test_clinician_attribution_never_uses_fast_record_model():
    for message in (
        "医生诊断是大腿和臀部肌肉无力导致腰肌代偿进而导致腰肌痛",
        "医生告诉我是臀肌无力导致腰痛",
        "主治医生告诉我是臀肌无力导致腰痛",
        "大夫告知是臀肌无力导致腰痛",
        "请记录医生诊断：臀肌无力导致腰肌代偿",
        "医生说是臀肌无力。请记录医生诊断：臀肌无力导致腰痛",
    ):
        assert not _prefer_fast_record(message), message


def test_clinician_attribution_is_not_extracted_as_a_self_symptom():
    import app.services.agent_executor as ae

    for message in (
        "医生诊断是大腿和臀部肌肉无力导致腰肌代偿进而导致腰肌痛",
        "医生认为是臀肌无力导致腰痛",
        "医生评估为臀肌无力导致腰痛",
        "康复师认为是臀肌无力导致腰痛",
        "医生的诊断是臀肌无力导致腰痛",
        "检查提示腰肌劳损导致疼痛",
        "大夫说是臀肌无力导致腰痛",
        "医生告诉我是臀肌无力导致腰痛",
        "主治医生告诉我是臀肌无力导致腰痛",
        "大夫告知是臀肌无力导致腰痛",
    ):
        assert ae._extract_clear_symptom_record(message) is None, message


def test_every_clinician_guard_kind_stays_out_of_fast_record_choke_points():
    import app.services.agent_executor as ae

    messages = (
        "医生诊断是大腿和臀部肌肉无力导致腰肌代偿进而导致腰肌痛",
        "医生认为是臀肌无力导致腰痛，我该怎么处理？",
        "请记录医生诊断：臀肌无力导致腰肌代偿",
        "请记录医生诊断：臀肌无力并删除旧记录",
    )

    for message in messages:
        assert ae._extract_clear_symptom_record(message) is None, message
        assert (
            ae._build_deterministic_symptom_tool_call(
                message,
                write_receipts=(),
            )
            is None
        ), message
        prefer_fast_record = ae._has_fast_record_write_intent(message)
        assert prefer_fast_record is False, message
        assert (
            _should_force_record_tool_choice(
                prefer_fast_record,
                _FIRST_ROUND,
                _TOOLS,
                True,
            )
            is False
        ), message


def test_clinician_fallback_cases_disable_every_fast_write_path():
    import app.services.agent_executor as ae

    for message in CLINICIAN_FALLBACK_NONWRITE_MESSAGES:
        assert ae._extract_clear_symptom_record(message) is None, message
        assert (
            ae._build_deterministic_symptom_tool_call(
                message,
                write_receipts=(),
            )
            is None
        ), message
        prefer_fast_record = ae._has_fast_record_write_intent(message)
        assert prefer_fast_record is False, message
        assert ae._has_explicit_text_record_intent(message) is False, message
        assert (
            ae._is_fast_eligible_turn(
                message,
                has_images=False,
                has_file=False,
            )
            is False
        ), message
        assert (
            _should_force_record_tool_choice(
                prefer_fast_record,
                _FIRST_ROUND,
                _TOOLS,
                True,
            )
            is False
        ), message


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
