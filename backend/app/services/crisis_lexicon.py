# -*- coding: utf-8 -*-
"""轻生 / 自伤意念的确定性识别词库与服务端危机支持文案 —— 只做识别,不做诊断。

覆盖不含「自杀 / 伤害自己」字面的**被动意念**(不想活了、活着没意思、不想醒来、
想死……),以及少量高精度的主动意念、方法、过量服药与英文表达。task_routing 高风险
地板、orchestrator 意图、MentalHealthCompanion 危机提示与 AgentExecutor 路由 / 回复
兜底共用这一份判定与热线。

取舍:危机筛查宁可多报 —— 误报代价是更强的模型加一次温和的热线提示,漏报不可逆。
所以「想死 / 不如死」用**排除表**(只排除想念、复合词与体力类夸张),不只认句末;
俗语夸张(累死了 / 想死你了 / 练腿练到想死)与子串陷阱(不想活动 / 减轻生活 / 思想
死板)必须排除,否则日常对话会被持续打扰。

隐私:只返回布尔值;调用方不得记录或回显命中的原文片段。
"""
from __future__ import annotations

import re
import unicodedata

_CLAUSE = r"[^,，。.!！?？;；]"
_CLAUSE_END = r"(?=$|[了啊吧呀呢啦哦嘛,，.。!！?？;；…~～])"
_CLAUSE_SEPARATORS = re.compile(r"[,，。.!！?？;；]")

# 「想死」:排除前面的 不想死 与 思想 / 理想等复合词,以及后面的想念对象(想死你了 /
# 想死我了 / 想死老婆了)与复合词(死磕 / 死板 / 死记 / 死心 / 死亡 / 死马当活马医);
# 其余任何后续(怎么办 / 救救我 / 但是不敢…)都按意愿表达。
_XIANG_SI = re.compile(
    r"(?<![不没别思理梦幻联回感构设猜妄空遐冥预料畅])想(?:要)?(?:去)?死"
    # 想念对象只在后接「了 / 啦」时排除(想死他们了),否则无标点连写的下一句
    # (我想死大家都讨厌我)会被误当成想念。
    r"(?!(?:你|您|他|她|它|我|人|宝宝?|宝贝|亲|大家|咱|老(?:婆|公|妈|爸|爷|奶|娘|家|师|板|朋友)"
    r"|妈妈?|爸爸?|爷爷?|奶奶?|姐姐?|哥哥?|弟弟?|妹妹?|儿子|女儿|[男女]朋友)(?:们)?(?:了|啦|啊|呀)"
    r"|您|磕|守|板|心(?:了|吧|塌地)|记|党|扛|撑|缠|马当活马|去活来)"
)
# 体力 / 运动 / 冷热 / 饥饱类程度补语是夸张(练腿练到想死 / 累得想死),判「想死」前先
# 剔除;情绪、认知与疼痛类(绝望得 / 觉得 / 疼得想死)不在此列。
_EFFORT_HYPERBOLE = re.compile(
    r"(?:累|饿|热|冷|困|忙|撑|渴|练|跑|爬|游|蹲|骑|跳|做|举|酸|晒|冻|等|笑|挤|堵)"
    r"(?:得|到)(?:快|都)?(?:要)?想(?:要)?(?:去)?死"
)
# 「希望 / 但愿……不用再醒来」:排除第三方(宝宝)与夜醒语境(半夜 / 起夜)。
_WAKE_WISH = re.compile(
    r"(?:希望|但愿|宁愿|宁可)(" + _CLAUSE + r"{0,6}?)"
    r"(?:不用|不要|不必|别|不再|再也不)(?:再)?醒(?:来|过来)" + _CLAUSE_END
)
_WAKE_WISH_EXCLUDED = (
    "宝宝", "孩子", "娃", "他", "她", "半夜", "夜里", "晚上", "凌晨", "中途", "起夜",
)
# 划 / 割:自伤须排除意外(切菜 / 被纸划破)与游泳划船;手臂类还须有刀 / 血等语境。
_SELF_CUT = re.compile(r"(?<!小心)(?:划|割)(?:伤|破)?(?:了)?自己")
_LIMB_CUT = re.compile(r"(?:划|割)(?:伤|破|了)*(?:手臂|胳膊|手腕)")
_CUT_CONTEXT = ("刀", "血", "伤口", "忍不住", "控制不住", "又开始", "又划", "又割")
_CUT_NOT_SELF_HARM = (
    "泳", "划水", "划船", "桨", "不小心", "切菜", "做饭", "削", "被纸", "被刀", "被玻璃",
    "碰到", "摔",
)
# 喝农药 / 老鼠药:排除宠物、孩子等第三方误食(按分句判)。
_POISON = re.compile(
    r"(?:喝|吃|吞)(?:了|下)?(?:一?(?:瓶|口|点|些))?(?:农药|百草枯|敌敌畏|老鼠药|鼠药)"
)
_THIRD_PARTY = ("狗", "猫", "宠物", "孩子", "宝宝", "娃", "他", "她", "它", "邻居", "别人")

_CRISIS_PATTERNS: tuple[re.Pattern[str], ...] = (
    # 不想活了 / 不想再活下去 / 不愿意活;排除 活动 / 活跃 / 活在别人眼光里 / 活成…
    re.compile(r"不(?:太|怎么|再)?(?:想|愿意|愿)(?:再|继续)?活(?![动跃泼络儿计蹦在成])"),
    re.compile(r"不(?:想|愿意|愿)(?:再)?活在(?:这个?)?世(?:界|上)"),
    # 活着没(什么)意思 / 活得真没意义 / 活着有什么意思 / 活着有什么用
    re.compile(
        r"活(?:着|得|的)(?:真的|实在|真|太|都|也|还|就|挺|好|很)?"
        r"(?:没有|没)(?:什么|啥|任何|一点|多大)?(?:意思|意义|盼头)"
    ),
    re.compile(r"活(?:着|得|的)(?:还)?有(?:什么|啥)(?:意思|意义|盼头|用)"),
    re.compile(
        r"活够了|一死百了|不配活(?![动跃])|"
        r"(?:找不到|没有|失去(?:了)?)活下去的(?:理由|意义|勇气|动力)"
    ),
    # 不想(再)醒来 / 永远不要醒来 / 想一直睡下去再也不起来
    re.compile(r"不(?:太)?想(?:再)?醒(?:来|过来)"),
    re.compile(r"(?:永远|再也)(?:都)?(?:不要|不想|不用|别)(?:再)?醒(?:来|过来)"),
    re.compile(
        r"(?:一直|永远)睡下去" + _CLAUSE + r"{0,2}(?:再也|永远)(?:都)?不(?:想|要)?(?:再)?(?:醒|起来)"
    ),
    re.compile(r"(?:想|希望|但愿|宁愿)(?:就这样)?一睡不醒"),
    # 想结束自己(的生命) / 想结束生命 / 了结自己 / 自我了断 / 一死了之;
    # 排除「结束自己的工作 / 结束自己熬夜的习惯 / 细胞结束生命」
    re.compile(
        r"结束(?:掉)?(?:我)?自己(?:的(?:生命|性命|一生)|"
        r"(?=$|[了吧啊呀,，.。!！?？;；…~～]))"
    ),
    re.compile(
        r"(?:想|要|打算|准备|决定)(?:要)?结束(?:我的|自己的|这条)?(?:生命|性命)"
        r"|结束(?:我的|自己的)(?:生命|性命)"
    ),
    re.compile(r"了(?:结|断)(?:掉)?(?:我)?自己|自我了(?:结|断)|一死了之"),
    re.compile(r"死" + _CLAUSE + r"{0,3}一了百了"),
    # 活不下去 / 没法活下去
    re.compile(r"活不下去|(?:没法|无法)(?:再)?活下去"),
    # 轻生;排除 年轻生命 / 年纪轻轻生病 / 减轻生活 / 轻生酮
    re.compile(r"(?<![年减轻])轻生(?![活酮])"),
    # 不如死了算了 / 还不如死去 / 死了算了;排除 不如死磕 / 死心 / 死马当活马医
    re.compile(r"不如(?:去)?死(?![磕心守板扛撑缠马]|去活来)"),
    re.compile(r"死了算了"),
    # 假设自己消失 / 不在了;离开后别人会轻松;自我累赘感
    re.compile(r"(?:如果|要是|假如|哪天)我(?:突然)?(?:消失|不在|死)了"),
    re.compile(r"我(?:不在|死)了" + _CLAUSE + r"{0,8}(?:轻松|解脱)"),
    re.compile(
        r"(?:我|自己)(?:就|只|真|简直|真的)?是(?:" + _CLAUSE + r"{0,4}的)?"
        r"(?:个|一个)?(?:累赘|拖累)|(?:我|自己)只会拖累"
    ),
    # 囤安眠药 / 过量服药
    re.compile(r"攒" + _CLAUSE + r"{0,6}安眠药|安眠药" + _CLAUSE + r"{0,10}(?:攒|囤|数好|存够)"),
    re.compile(r"(?:吞|吃|喝)(?:了|下)?(?:一)?整(?:瓶|盒)" + _CLAUSE + r"{0,6}药"),
    re.compile(
        r"(?:一)?整(?:瓶|盒)" + _CLAUSE + r"{0,6}药" + _CLAUSE + r"{0,3}(?:吃|吞|喝)(?:了|下|掉)"
    ),
    re.compile(
        r"(?:吃|吞|服)(?:了|下)?(?:[2-9]\d|\d{3,}|几十)(?:片|粒|颗)"
        + _CLAUSE + r"{0,2}(?:安眠药|助眠药|镇静药|安定)"
    ),
    # 自杀 / 自伤的明确表达与方法(自杀、伤害自己 同时是 task_routing 字面标记)
    re.compile(r"自杀|伤害自己|割腕|自残(?![疾联障])"),
    re.compile(r"我(?:的)?(?:遗书|遗言)|(?:遗书|遗言)(?:已经|都)?(?:写好|留好)"
               r"|我(?:已经|都)?(?:把)?后事(?:都)?(?:已经)?安排好"),
    re.compile(r"想(?:要)?(?:跳楼(?!价)|跳河|跳江|跳海|上吊|烧炭|卧轨|开煤气)"),
)

# 英文按单词匹配(保留空格);排除 want to diet / end my lifestyle。
_ENGLISH_CRISIS = re.compile(
    r"\bsuicid|\bkill(?:ing)? myself\b|\bwant(?:s|ed)? to die\b"
    r"|\bend(?:ing)? my (?:own )?life\b|\bwish i (?:was|were) dead\b"
)


def _mentions(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _matches_chinese(text: str) -> bool:
    if any(pattern.search(text) for pattern in _CRISIS_PATTERNS):
        return True
    if _XIANG_SI.search(_EFFORT_HYPERBOLE.sub("，", text)):
        return True
    if any(
        not _mentions(match.group(1), _WAKE_WISH_EXCLUDED)
        for match in _WAKE_WISH.finditer(text)
    ):
        return True
    if _SELF_CUT.search(text) and not _mentions(text, _CUT_NOT_SELF_HARM):
        return True
    if (
        _LIMB_CUT.search(text)
        and _mentions(text, _CUT_CONTEXT)
        and not _mentions(text, _CUT_NOT_SELF_HARM)
    ):
        return True
    return any(
        _POISON.search(clause) and not _mentions(clause, _THIRD_PARTY)
        for clause in _CLAUSE_SEPARATORS.split(text)
    )


def contains_crisis_language(text: str | None) -> bool:
    """文本含轻生 / 自伤意念表达时返回 True。纯函数,不记录、不回显原文。"""
    tokens = unicodedata.normalize("NFKC", str(text or "")).lower().split()
    if not tokens:
        return False
    if _ENGLISH_CRISIS.search(" ".join(tokens)):
        return True
    # 去空白防「不 想 活 了」绕过;空白按分句处理防下一句粘到短语上误触排除表
    # (「想死 老是睡不着」)。任一形态命中即算,只会多报不会少报。
    return any(_matches_chinese(form) for form in {"".join(tokens), "，".join(tokens)})


# ─────────────── 服务端危机支持文案(经核对的号码,唯一真源) ───────────────

# 2026-09-30 核对:12356 为国家卫健委全国统一心理援助热线(各地每日不少于 18 小时,
# 不写 24 小时);希望24热线与北京心理危机研究与干预中心均为 24 小时人工接听。
CRISIS_HOTLINES: tuple[dict[str, str], ...] = (
    {"name": "全国统一心理援助热线", "number": "12356"},
    {"name": "希望24热线", "number": "400-161-9995", "note": "24 小时"},
    {"name": "北京心理危机研究与干预中心", "number": "010-82951332", "note": "24 小时"},
)

CRISIS_SUPPORT_LEAD = (
    "如果你正在经历很难熬的时刻，你不需要独自扛着。"
    "如果此刻有伤害自己的打算或已处于危险中，请立即拨打 120 或 110，"
    "或请身边的人陪你去最近的急诊；也可以现在就拨打心理援助热线："
)

# 急救电话须在「拨打 / 呼叫」语境里,避免把 血压120/80、心率110 当成已给出急救指引;
# 热线只认本模块发布的号码。
_EMERGENCY_CALL = re.compile(
    r"(?:拨打|拨|打|呼叫|联系)\s*(?:120|110)(?!\d)|(?<!\d)(?:120|110)\s*(?:急救|报警|求助)"
)
_VERIFIED_HOTLINE_NUMBER = re.compile(
    r"(?<!\d)(?:12356|400[-\s]?161[-\s]?9995|010[-\s]?82951332)(?!\d)"
)


def _hotline_label(hotline: dict[str, str]) -> str:
    note = hotline.get("note")
    return f"{hotline['name']} {hotline['number']}" + (f"（{note}）" if note else "")


def crisis_hotline_summary() -> str:
    """一行热线清单,供 specialist 的 action 等纯文本字段使用。"""
    return "、".join(_hotline_label(hotline) for hotline in CRISIS_HOTLINES)


def crisis_support_block() -> str:
    lines = "\n".join(f"- {_hotline_label(hotline)}" for hotline in CRISIS_HOTLINES)
    return f"{CRISIS_SUPPORT_LEAD}\n{lines}"


def has_crisis_support(reply: str | None) -> bool:
    """回复里同时有急救电话(120/110)与至少一条本模块发布的心理援助热线。"""
    text = str(reply or "")
    return bool(_EMERGENCY_CALL.search(text) and _VERIFIED_HOTLINE_NUMBER.search(text))


def with_crisis_support(
    message: str | None,
    reply: str | None,
    *,
    emitted_prefix: str = "",
) -> str:
    """危机回合的最终回复必须带经核对的急救电话与热线;已带则原样返回。

    ``emitted_prefix`` 是已先行推送给客户端的内容(如图表卡片),危机提示插在它之后,
    避免重复推送。
    """
    text = reply or ""
    if not contains_crisis_language(message) or has_crisis_support(text):
        return text
    prefix = emitted_prefix if emitted_prefix and text.startswith(emitted_prefix) else ""
    rest = text[len(prefix):].strip("\n")
    return "\n\n".join(
        part for part in (prefix, crisis_support_block(), rest) if part.strip()
    )
