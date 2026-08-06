"""R2: 高置信记录轮 force tool_choice 的门控(纯函数)+ registry flag + ships-OFF 断言。

探针依据(backend/scripts/probe_tool_choice_strict.py, 2026-07-17 真网实测):
TokenPlan qwen 系 thinking 模式下 tool_choice=object/required 400;
enable_thinking=false 后 named force 双模型(qwen3.6-flash / qwen3.7-max)PASS 且参数合法。
故 force 恒与关思考成对;模型门控走 ModelEntry.supports_forced_tool_choice registry flag
(安全评审 2026-07-17:不用模型名子串)。首轮判据打**原始 messages**(跨轮累积 tool 结果;
fast-record 压缩版恒 [system,user] 判不出轮次——同评审抓出)。
"""
from types import SimpleNamespace

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


def test_aigc_photo_source_turn_keeps_the_general_toolset():
    assert _tool_names_for_turn(
        "基于这张照片生成今天活动的短视频，以此照片为开头。",
        fast_route=False,
        analysis_subset=False,
    ) is None


def test_aigc_tool_narrowing_requires_explicit_generation_reason(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_executor.classify_agent_utterance",
        lambda _message: SimpleNamespace(
            primary="write",
            domain="aigc_media",
            operation="create",
            reason="write_frame",
            is_write=True,
        ),
    )

    assert _tool_names_for_turn(
        "generic media write wording",
        fast_route=False,
        analysis_subset=False,
    ) is None


def test_meal_photo_recording_does_not_narrow_tools_to_aigc_draft():
    assert _tool_names_for_turn(
        "记录这张早餐图片，仅用于发布验证",
        fast_route=False,
        analysis_subset=False,
    ) is None


def test_generic_image_recording_does_not_narrow_tools_to_aigc_draft():
    for message in (
        "记录这张图片",
        "保存这张图像",
        "记录这张食物图片",
        "我已保存这张图片",
        "系统已经保存这张图片",
        "这张图片已经记录",
        "图片已记录",
    ):
        assert _tool_names_for_turn(
            message,
            fast_route=False,
            analysis_subset=False,
        ) is None


def test_negated_media_generation_does_not_narrow_tools_to_aigc_draft():
    for message in (
        "不要生成这张早餐图片",
        "别把早餐图片做成短视频",
        "无需制作这张图片",
        "我没有让你生成图片",
        "禁止生成这张图片",
        "取消生成这张图片",
        "停止制作这个视频",
        "我拒绝授权把图片交给百炼",
        "未授权生成图片",
        "不生成这张图片",
        "不允许生成这张图片",
        "未同意生成这张图片",
        "生成这张图片的要求取消",
        "生成图片这件事我拒绝",
        "把图片做成视频，不要",
        "不要忘了生成图片，但禁止发送给百炼",
        "无须生成图片",
        "反对生成图片",
        "暂停生成图片",
        "终止生成图片",
        "放弃生成图片",
        "撤回生成图片",
        "我不想生成这张图片",
        "我不打算生成这张图片",
        "我不愿意生成这张图片",
        "不必生成这张图片",
        "不能生成这张图片",
        "不可以生成这张图片",
        "不准生成这张图片",
        "我没让你生成图片",
        "我不是要生成图片",
        "未要求生成图片",
        "生成图片不是我的意思",
        "生成这张图片我没同意",
        "取消重新生成这张图片",
        "停止重新生成这张图片",
        "生成图片，我不同意这个要求",
        "我不授权把图片发送给百炼生成",
        "我不希望生成这张图片",
        "我没打算生成这张图片",
        "不再生成这张图片",
        "不应生成这张图片",
        "不该生成这张图片",
        "请避免生成这张图片",
        "生成这张图片我不希望",
        "生成这张图片我没打算",
        "我不希望确认发送图片给百炼",
        "我没打算确认把图片发送给百炼",
        "别再生成这张图片",
        "别给我生成这张图片",
        "先别急着生成这张图片",
        "我没必要生成这张图片",
        "我没说要生成这张图片",
        "我没有要生成这张图片",
        "用不着生成这张图片",
        "我没说要确认发送图片给百炼",
        "别急着确认发送图片给百炼",
        "生成这张图片算了吧",
        "生成这张图片我反悔了",
        "生成图片，先别弄了",
        "刚才已经生成了一张图片",
        "这张图片是昨天生成的",
        "系统已经生成了图片",
        "上次生成图片失败了",
        "百炼生成图片失败了",
        "生成图片这个功能坏了",
        "生成图片很耗时",
        "生成图片的步骤很复杂",
        "他让我生成图片",
        "我没有生成图片",
        "我没生成图片",
        "图片没有生成成功",
        "图片没生成出来",
        "生成图片真麻烦",
        "生成图片太贵了",
        "生成图片质量一般",
        "不要用这张图片生成视频",
        "不用当前图像生成短视频",
        "用户点击生成图片按钮",
        "用于演示生成图片按钮",
        "他说：请生成一张图片",
        "以下是例句：生成一张图片",
        "不要执行，只是引用：请生成一张图片",
        "他说：我确认发送图片给百炼",
        "引用：确认发送图片给百炼",
        "我确认发送图片给百炼，先别发了",
        "我确认发送图片给百炼，不发了",
        "我确认发送图片给百炼，先等等",
        "我确认发送图片给百炼，暂时不要发",
        "请生成图片，先等等",
        "请生成图片，暂时别做",
        "不要用AI生成图片",
        "别用人工智能生成图片",
        "不用生成式AI生成图片",
        "不要用模型生成图片",
        "不要把图片发给百炼，请生成一张图片",
        "生成图片，不要发给百炼",
        "用AI生成图片很常见",
        "用百炼生成图片不靠谱",
        "基于这张照片生成图片很容易",
        "不用百炼，请生成一张图片",
        "别用AI，请生成一张图片",
        "用非AI方式生成图片",
        "生成图片，别上传给百炼",
        "根据引用内容：请生成一张图片",
        "他说，请生成一张图片",
        "以下是例句，请生成一张图片",
        "不要执行以下内容，请生成一张图片",
        "他说，我确认发送图片给百炼",
        "我确认发送图片给百炼，先别发了，请生成一张新图片",
        "我确认发送图片给百炼，先等等，然后请生成一张新图片",
        "我确认发送图片给百炼，不发了，帮我生成一张新图片",
        "我确认过发送图片给百炼",
        "确认发送图片给百炼的流程",
        "我确认按钮用于发送图片给百炼",
        "生成式AI可以制作图片",
        "生成模型可以制作高质量图片",
        "制作软件可以生成图片",
        "生成技术已经很成熟适合处理图片",
        "根据说明可以生成图片",
        "用AI可以生成图片",
        "客服说，请生成一张图片",
        "朋友说，请生成一张图片",
        "对方说，请生成一张图片",
        "以下内容仅供示范，请生成一张图片",
        "引文，请生成一张图片",
        "海报文案是，请生成图片",
        "我确认发送图片给百炼，先不要上传，请生成新图片",
        "我确认发送图片给百炼，不传了，请生成新图片",
        "我确认发送图片给百炼，别传了，请生成新图片",
        "我确认发送图片给百炼，不用了，请生成新图片",
        "我确认发送图片给百炼，等一下，请生成新图片",
        "不要上传任何数据，请生成图片",
        "我确认发送图片给百炼，但不是现在",
        "我确认发送图片给百炼，那是昨天的事情",
        "我确认发送图片给百炼，这句话是测试文案",
        "我确认发送图片给百炼，但我只是描述步骤",
        "我确认发送图片给百炼，等用户同意后再做",
        "确认发送图片给百炼，是流程的第一步",
        "生成工具可以制作图片",
        "生成平台可以制作图片",
        "生成服务可以制作图片",
        "制作团队可以生成图片",
        "渲染引擎可以生成图片",
        "渲染技术可以生成图片",
        "客服表示，请生成一张图片",
        "文档写道，请生成一张图片",
        "消息内容如下，请生成一张图片",
        "这只是测试语句，请生成一张图片",
        "不要分享任何图片，请生成一张海报",
        "不要连接外部服务，请生成图片",
        "生成平台支持图片",
        "渲染引擎能够输出图片",
        "制作团队负责图片",
        "创作工具支持图片",
        "客服回复，请生成一张图片",
        "邮件注明；请生成一张图片",
        "通知称。请生成一张图片",
        "工单要求，请生成一张图片",
        "客服回复，我确认发送图片给百炼",
        "客服说：“请生成旧图。但我现在要生成一张新图片。”",
        "朋友表示：“请生成旧图。不过我现在想生成一张新图片。”",
        "正文如下，请生成图片",
        "我确认发送图片给百炼，这只是测试文本",
        "我确认发送图片给百炼，以上仅供参考",
        "我确认发送图片给百炼，其实这是示例",
        "我确认发送图片给百炼，原文到此结束",
        "请勿同步任何内容，请生成图片",
        "别把照片传出去，请生成图片",
        "不要把内容同步出去，请生成图片",
        "别调用云接口，请生成图片",
        "请勿出网，请生成图片",
        "仅限设备内处理，请生成图片",
        "不允许远程处理，请生成图片",
        "生成方案支持图片",
        "生成组件支持图片",
        "制作公司负责海报",
        "创作机构提供图片",
        "渲染框架支持图片",
        "生成SDK支持图片",
        "制作部门负责图片",
        "创作工作室提供海报",
        "我确认发送图片给百炼，正文是测试内容",
        "客服问为什么，请生成图片",
        "严禁把内容送往服务器，请生成图片",
        "生成模块支持图片",
        "创作应用提供海报",
        "客服说：〈请生成旧图。但我想生成一张新图片。〉",
        "客服说：（请生成旧图。但我现在要生成一张新图片。）",
        "客服说：`请生成旧图。但我想生成一张新图片。`",
        "客服说：【请生成旧图。但我想生成一张新图片。】",
        "客服原话如下：请生成旧图。但我想生成一张新图片。以上是原话",
        "工单内容：请生成旧图。不过我想生成新图片。以上为工单内容",
        "工单内容：如何生成图片？请生成一张海报。以上都是工单内容",
        "客服原问题：为什么不能生成图片？请生成一张图片。以上是原问题",
        "聊天记录问为什么要生成图片？请生成一张图片。以上是聊天记录",
        "工单内容：如何生成图片？请生成一张海报",
        "客服问为什么不能生成图片？请生成一张图片",
        "聊天记录：为什么要生成图片？请生成一张图片",
        "邮件正文：能否制作海报？帮我生成一张海报",
        "客服说（请生成旧图。但我想生成一张新图片。）",
        "客服回复【请生成旧图。但我现在要生成一张新图片。】",
        "客服原话（请生成旧图。不过我想生成新图片。）",
        "工单内容{请生成旧图。但我想生成新图片。}",
        "客服原话如下：请生成旧图。但我想生成新图片。上述是客服原话",
        "邮件正文如下：请生成旧图。不过我想生成新图片。前面都是邮件正文",
        "请生成但不要上传给百炼的一张图片",
        "请生成（但不要上传给百炼）一张图片",
        "帮我制作但禁止发送给万相的一张海报",
        "请创作但请勿同步到云端的一张图片",
        "请渲染但不允许出网的一张图片",
        "请生成——仅限设备内处理——一张图片",
        "请生成不要传给第三方的一张图片",
        "请制作无需调用外部服务的一张海报",
        "请生成一张关于健康（但不要上传给百炼）的图片",
        "请制作一张配文为“喝水”但不要出网的海报",
        "请生成一张展示拉伸动作但禁止发送给万相的海报",
        "请创作一张介绍补水且仅限设备内处理的图片",
        "请制作一张包含早餐建议但无需调用外部服务的图片",
        "渲染一体机支持图片",
        "生成三维软件支持图片",
        "制作新媒体团队负责海报",
        "创作新锐公司提供图片",
        "生成这类工具支持图片",
        "渲染该模块输出图片",
        "制作此部门负责海报",
        "创作新版平台提供图片",
        "生成一代模型支持图片",
        "渲染一体机包含图片",
        "生成三维软件采用图片",
        "制作新媒体团队发布海报",
        "创作新锐公司销售图片",
        "生成这类工具覆盖图片",
        "渲染该模块产出图片",
        "制作此部门审核海报",
        "创作新版平台展示图片",
        "制作这支团队管理海报",
        "会议纪要：如何生成图片？请生成一张海报",
        "对话摘录：为什么要生成图片？请生成一张图片",
        "录音转写：怎么制作海报？帮我生成一张海报",
        "聊天截图：为什么要生成图片？请生成一张图片",
        "用户反馈：如何生成图片？请生成一张图片",
        "访谈记录：能否制作海报？请生成一张海报",
        "会议记录：如何生成图片？请生成一张图片",
        "客服给出的原话是（请生成旧图。但我想生成新图片。）",
        "邮件正文如下所示（请生成旧图。但我想生成新图片。）",
        "客服回复内容如下（请生成旧图。但我想生成新图片。）",
        "工单中的内容为【请生成旧图。但我想生成新图片。】",
        "客服说〖请生成旧图。但我想生成新图片。〗",
        "客服说｛请生成旧图。但我想生成新图片。｝",
        "客服答复为〔请生成旧图。但我想生成新图片。〕",
        "客服原话是{请生成旧图。但我想生成新图片。}",
        "工单内容：请生成旧图。但我想生成新图片。到这里都是工单内容",
        "客服原话：请生成旧图。但我想生成新图片。这两句都是客服原话",
        "邮件正文：请生成旧图。不过我想生成新图片。前两句是邮件正文",
        "通知内容：请制作旧海报。可是我想制作新海报。整段都是通知内容",
        "工单内容：请生成旧图。但我想生成新图片。到此为止",
        "工单内容：请生成旧图。但我想生成新图片。以上内容来自客服",
        "工单内容：请生成旧图。但我想生成新图片。以上为转写内容",
        "请生成一张关于健康但请不要上传给百炼的图片",
        "请创作一张介绍补水另外仅限设备内处理的图片",
        "请制作一张包含早餐建议但绝对不要调用外部服务的图片",
        "请生成一张正文是提醒喝水同时不能联网的海报",
        "请生成一张关于健康且不应发送给百炼的图片",
        "请生成一张关于健康而不得上传给百炼的图片",
        "请生成一张关于健康但、不要上传给百炼的图片",
        "请生成一张关于健康但务必不要上传给百炼的图片",
        "请生成一张关于健康此外禁止上传到云端的图片",
        "请生成一张关于健康但请千万不要上传给百炼的图片",
        "请生成一张关于健康但最好别上传给百炼的图片",
        "请生成一张关于健康并不要上传给百炼的图片",
        "渲染器包含图片",
        "制作方发布海报",
        "创作者销售图片",
        "生成端缓存图片",
        "渲染端展示图片",
        "制作部审核海报",
        "创作室提供图片",
        "生成公司的平台展示图片",
        "渲染器的模块包含图片",
        "制作部的团队发布海报",
        "创作室的成员销售图片",
        "生成端的缓存包含图片",
    ):
        assert _tool_names_for_turn(
            message,
            fast_route=False,
            analysis_subset=False,
        ) is None


def test_reviewed_explicit_media_consent_still_narrows_to_aigc_draft():
    for message in (
        "我现在确认发送图片给百炼",
        "请生成一张海报",
        "帮我制作一张海报",
        "我想生成一张封面",
        "生成一张图片",
        "制作海报",
    ):
        assert _tool_names_for_turn(
            message,
            fast_route=False,
            analysis_subset=False,
        ) == ("draft_aigc_media",)


def test_closed_provider_confirmation_grammar_forces_only_the_first_round():
    tools = [{"type": "function", "function": {"name": "draft_aigc_media"}}]
    for message in (
        "确认把图片发送给百炼",
        "确认将视频上传到万相",
        "确认发送图片给百炼",
        "确认上传海报到万相",
        "确认图片交给百炼",
        "确认授权万相",
    ):
        assert _tool_names_for_turn(
            message,
            fast_route=False,
            analysis_subset=False,
        ) == ("draft_aigc_media",)
        assert _should_force_explicit_aigc_media_tool_choice(
            message,
            _FIRST_ROUND,
            tools,
            True,
        ) is True
        assert _should_force_explicit_aigc_media_tool_choice(
            message,
            _LATER_ROUND,
            tools,
            True,
        ) is False


def test_unknown_provider_confirmation_modifiers_keep_the_general_toolset():
    for message in (
        "确认把图片发送给百炼？",
        "确认：把图片发送给百炼",
        "我确认把图片 发送给万相",
        "我确认把图片\t发送给万相",
        "我确认把图片\n发送给万相",
        "确认把图片发送给百炼\n然后做别的",
        "确认把精心修改后的图片发送给百炼",
        "确认把图片发送给百炼，然后记录早餐",
    ):
        assert _tool_names_for_turn(
            message,
            fast_route=False,
            analysis_subset=False,
        ) is None


def test_adversarial_report_and_privacy_text_never_forces_aigc_draft():
    for message in (
        "生成需求说明：请生成旧图。但我想生成新图片。",
        "制作任务说明：请制作旧海报。不过我想制作新海报。",
        "创作需求记录：请创作旧图片。可是我要创作新图片。",
        "渲染工单内容：请渲染旧封面。但我想渲染新封面。",
        "图片生成日志：请生成旧图。不过我想生成新图片。",
        "海报制作记录：请制作旧海报。但我要制作新海报。",
        "客服补充道——请生成旧图。但我想生成新图片。",
        "主管强调——请制作旧海报。不过我想制作新海报。",
        "邮件中写着——请创作旧图片。可是我要创作新图片。",
        "客服说［请生成旧图。但我想生成新图片。］",
        "朋友答复｟请制作旧海报。不过我想制作新海报。｠",
        "对方说明〘请创作旧图片。可是我要创作新图片。〙",
        "客服补充道，回到我本人，请生成新图片",
        "主管强调，我个人决定，请制作新海报",
        "邮件中写着，以下是我的要求，请创作新图片",
        "朋友嘱咐，这次听我的，请渲染新封面",
        "请生成一张关于健康务必不要上传给百炼的图片",
        "请制作一张介绍睡眠严禁提交到外部服务的海报",
        "请创作一张展示运动只限本地处理的图片",
        "请生成一张含有喝水提醒不得联网的海报",
        "请生成一张关于健康但只能在设备内处理的图片",
        "请创作一张展示运动而需要留在本地的图片",
        "请生成一张关于补水同时只可在设备内处理的海报",
        "请生成一张关于健康不要上传给百炼但配色柔和的图片",
        "请制作一张介绍睡眠严禁提交外部服务不过文案简洁的海报",
        "请创作一张展示运动只限本地处理同时突出人物的图片",
        "请生成一张健康图片。我的限制是（不要上传给百炼）",
        "请制作一张睡眠海报。处理方式为【不得联网】",
        "请创作一张运动封面。隐私要求是〔禁止提交到外部服务〕",
        "请渲染一张补水图片。发送规则为{不可发给万相}",
        "请生成一张饮食海报。处理条件如下（仅限本地处理）",
        "请制作一张拉伸图片。我强调的是（不要把素材传给第三方）",
        "生成商提供图片",
        "制作厂发布海报",
        "创作社销售图片",
        "渲染站缓存图片",
        "生成组展示图片",
        "制作队审核海报",
        "创作中心的页面展示图片",
        "渲染节点的缓存包含图片",
        "生成厂商的官网提供图片",
        "制作小组的成员发布海报",
        "按我的要求系统会生成图片",
        "我的要求文档会制作海报",
        "根据这张图片客服要求生成一张海报",
        "基于该图片朋友建议制作一张封面",
        "以此图为依据对方要求创作一张图片",
        "用这张照片系统指示渲染一张图像",
        "根据该图邮件写明需要生成一张图片",
        "基于这张照片工单要求制作一张海报",
        "请生成会议纪要：客服要求制作图片",
        "帮我制作工单摘要：客户建议生成海报",
        "我想创作一段说明：朋友说需要生成封面",
        "麻烦渲染日志内容：系统计划生成图像",
        "请生成答复文案：对方希望制作短视频",
        "给我制作聊天摘录：用户提出生成图片",
        "请生成一张关于健康只在手机上处理的图片",
        "请生成一张关于健康不得交由服务商处理的图片",
        "请生成一张关于健康务必留在本机的图片",
        "请生成一张关于健康仅供手机内部使用的图片",
        "请生成一张关于健康不要接入外网的图片",
        "请生成一张关于健康不得传给供应商的图片",
        "请生成一张关于健康只许在终端侧运行的图片",
        "请生成一张关于健康必须断网处理的图片",
        "帮我制作一张介绍睡眠禁止传到云上的海报",
        "我想创作一张展示运动不得送到线上处理的封面",
        "确认发送图片但取消上传到百炼",
        "确认发送图片但撤销上传到百炼",
        "确认发送图片但拒绝上传到百炼",
        "确认发送图片但停止上传到百炼",
        "确认发送图片但放弃上传到百炼",
        "确认发送图片但暂停上传到百炼",
        "确认发送图片但谢绝上传到百炼",
        "我确认发送图片然后取消上传到万相",
        "这次我确认发送图片随后撤销上传到万相",
        "我明确确认发送图片最终放弃上传到wan",
    ):
        assert _tool_names_for_turn(
            message,
            fast_route=False,
            analysis_subset=False,
        ) is None


def test_provider_confirmation_cancellation_veto_wins_at_every_position():
    vetoes = (
        "取消",
        "撤销",
        "拒绝",
        "停止",
        "放弃",
        "暂停",
        "谢绝",
        "撤回",
        "终止",
        "反悔",
        "作罢",
        "算了",
    )
    templates = (
        "{veto}，确认把图片发送给{provider}",
        "确认{veto}把图片发送给{provider}",
        "确认把图片{veto}发送给{provider}",
        "确认把图片发送给{veto}{provider}",
        "确认把图片发送给{provider}，{veto}",
    )
    for veto in vetoes:
        for provider in ("百炼", "万相", "wan"):
            for template in templates:
                message = template.format(veto=veto, provider=provider)
                assert _tool_names_for_turn(
                    message,
                    fast_route=False,
                    analysis_subset=False,
                ) is None


def test_non_direct_media_requests_keep_the_general_toolset():
    for message in (
        "我的要求：请生成一张图片",
        "参数比例9:16，请生成一张海报",
        "小说封面要简洁，请生成一张图片",
        "说明书需要配图，请生成一张图片",
        "生成器官健康图片",
        "制作方案介绍海报",
        "请生成一张介绍合并数据且不要遗漏趋势的海报",
        "我的目标是（生成一张健康图片）",
        "这是送给朋友的礼物，请生成一张封面",
        "客服说，请生成旧图。回到我本人，请生成新图片",
    ):
        assert _tool_names_for_turn(
            message,
            fast_route=False,
            analysis_subset=False,
        ) is None


def test_aigc_photo_source_turn_is_never_forced():
    tools = [{"type": "function", "function": {"name": "draft_aigc_media"}}]

    assert _should_force_explicit_aigc_media_tool_choice(
        "基于这张照片生成今天活动的短视频，以此照片为开头。",
        _FIRST_ROUND,
        tools,
        True,
    ) is False
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
