"""Shared speech-act parser for deterministic health-write authorization."""
from __future__ import annotations

import re
import unicodedata

from app.services.utterance_intent_lexicon import (
    QUESTION_SIGNALS,
    READ_ACTIONS,
    RECORD_NOUN_SUFFIXES,
    STRUCTURAL_WRITE_NEGATIONS,
    WRITE_ACTIONS,
    WRITE_COMMAND_ACTIONS,
    WRITE_COMMAND_PREFIXES,
    WRITE_NEGATION_EXCEPTIONS,
)

_CLAUSE_BOUNDARY_RE = re.compile(
    r"[，,。.!！；;]|但是|但|不过|然而|可是|只是|却|而是|"
    r"是(?=请(?:你)?)|然后|接着|随后|"
    r"(?<=.)(?=请(?:你)?"
    r"(?:记录|记一下|记下|打个卡|打卡|新增|录入|保存|写入|存下来))"
)
_CONTRAST_SCOPE_RE = re.compile(r"但是|但|不过|然而|可是|而是|却")
_LIMITING_WRITE_RE = re.compile(
    r"只(?=(?:请(?:你)?|帮我|替我|为我|给我|麻烦)?"
    r"(?:记录|记一下|记下|打个卡|打卡|新增|录入|保存|写入|存下来))"
)
_CONTEXTUAL_DENIAL_COMMA_RE = re.compile(
    r"((?:没有|没|未|未经|无).{0,12}(?:同意|授权|许可|允许)"
    r".{0,8}(?:情况下|情形下|前提下))[，,]"
)
_CAPABILITY_INQUIRY_PREFIXES = (
    "我想问一下",
    "我想问",
    "想问一下",
    "想问",
    "请问一下",
    "请问",
    "我想知道",
    "想知道",
    "请告诉我",
    "告诉我",
    "我想了解",
    "想了解",
    "我想确认",
    "想确认",
    "请确认",
    "确认",
    "请说明",
    "说明",
)
_CAPABILITY_SUBJECTS = (
    "这个功能",
    "该功能",
    "这个系统",
    "该系统",
    "这个服务",
    "该服务",
    "这个应用",
    "该应用",
    "这个助手",
    "该助手",
    "系统",
    "小巴",
    "应用",
    "平台",
    "这个",
    "它",
)
_CAPABILITY_MODALS = (
    "可不可以",
    "能不能",
    "会不会",
    "是否会",
    "有没有",
    "具不具备",
    "具备",
    "可以",
    "能否",
    "可否",
    "支持",
    "会",
    "能",
)
_NON_NEGATING_MODALS = (
    "可不可以",
    "能不能",
    "该不该",
    "要不要",
    "不得不",
    "不能不",
    "不妨",
)
_NEGATION_LEXICAL_CONTAINERS = (
    "分别",
    "区别",
    "性别",
    "个别",
    "特别",
    "类别",
    "级别",
    "识别",
    "鉴别",
    "告别",
)
_POSITIVE_REMINDER_RE = re.compile(r"(?:不要|别|勿|甭)(?:忘记|忘了|忘)")
_NEGATED_CONTROL_RE = re.compile(
    r"(?:不|没有|没|未曾|未|未经|无).{0,3}"
    r"(?:同意|允许|授权|许可|准许|要求|希望|愿意|乐意|打算|考虑|"
    r"接受|赞成|想|让|叫|肯)"
)
_DIRECT_DENIAL_SCOPE_RE = re.compile(
    r"(?:反对|抗拒|抵制).{0,12}(?:让|由|帮我|替我|为我)"
)
_HISTORY_NOUN_TERMS = ("历史", "列表", "汇总")
_PAST_TIME_TERMS = (
    "以前",
    "上一次",
    "上次",
    "上回",
    "之前",
    "刚才",
    "刚刚",
    "方才",
    "昨天",
    "前天",
    "大前天",
    "上周",
    "上个月",
    "去年",
    "那次",
    "当时",
    "此前",
    "先前",
    "早先",
    "最近一次",
    "既往",
    "曾经",
)
_HISTORY_TERMS = (*_HISTORY_NOUN_TERMS, *_PAST_TIME_TERMS)
_COMPLETED_TAILS = ("了", "过", "没有", "没")
_NON_ASPECT_GUARDS = ("过敏", "过量", "过高", "过低", "过去", "过程")
_COMPLETION_TRAILING_PARTICLES = "?？啊呀呢么嘛吗"
_POST_ACTION_DENIAL_RE = re.compile(
    r"(?:还是)?(?:算了(?:吧)?|取消(?:吧|了|这件事)?|撤销(?:吧|了)?|撤回|"
    r"暂缓|搁置|缓一缓|先缓缓|推迟|等一下再说|先放一放|作罢|就免了|免了|"
    r"先不要了|不要了|未获授权|没有授权|未经授权|不被允许|"
    r"是不允许的?|是不可以的?|不允许|我不同意|不行)"
)
_TRAILING_REVOCATION_ATOM = (
    r"(?:还是)?(?:算了(?:吧)?|取消(?:吧|了|这件事|刚才的请求)?|"
    r"撤销(?:吧|了)?|撤回|暂缓|搁置|缓一缓|先缓缓|推迟|"
    r"等一下再说|稍后再说|先放一放|(?:这件事)?作罢|"
    r"(?:先)?不(?:要)?(?:再)?(?:记|记录|保存|录入|写入|新增|打卡)了|"
    r"别(?:再)?(?:记|记录|保存|录入|写入|新增|打卡)了|"
    r"先不要了|不要了|我不同意|不行|(?:我)?改主意了|(?:这次)?别弄了|"
    r"(?:就)?当(?:我)?没说|(?:先)?保持原样|(?:先)?维持原样|"
    r"(?:先)?(?:不要|别)改了|不改了|"
    r"忽略(?:掉)?(?:刚才|前面|上面|之前)?(?:那|这)?(?:句|条|个)?"
    r"(?:话|请求|指令)?)"
)
_TRAILING_REVOCATION_CLAUSE_RE = re.compile(
    rf"^(?:{_TRAILING_REVOCATION_ATOM})+$"
)
_RESULT_CHECK_LEADS = (
    "确认",
    "核对",
    "查查",
    "检查",
    "验证",
    "查看",
    "看看",
    "查一下",
)
_RESULT_STATE_MARKERS = ("有没有", "是否", "是否已", "是否已经", "已经", "已")
_RESULT_TAIL_MARKERS = ("成功", "完成", "生效", "写进", "写到", "存进", "存到")
_REPORTING_VERBS = (
    "说",
    "表示",
    "称",
    "写着",
    "写道",
    "提到",
    "显示",
    "提示",
    "转告",
    "转述",
    "复述",
    "引用",
    "告诉",
    "告知",
    "透露",
)
_METALANGUAGE_ACTIONS = (
    "原文",
    "原话",
    "转告",
    "转述",
    "复述",
    "翻译",
    "解释这句话",
    "引用",
    "举例",
    "例句",
    "例子",
    "例如",
    "比如",
    "譬如",
    "假设",
    "假定",
    "设想",
    "倘若",
    "模拟场景",
    "这句话",
    "是什么意思",
)
_HYPOTHETICAL_PREFIX_RE = re.compile(
    r"^(?:如果|假如|假使|假设|假定|设想|倘若|若是|要是|万一)"
)
_POLITE_CONDITIONAL_PREFIX_RE = re.compile(
    r"^(?:如果|假如)(?:可以|方便|方便的话|你方便|你可以|你能|小巴可以|小巴能)"
)
_DEFERRED_CONDITION_PREFIX_RE = re.compile(
    r"^(?:"
    r"(?:一旦|只要|除非|等到|待到).{0,64}"
    r"|(?:等|待)(?!一下(?:[，,]|$)|一会儿(?:[，,]|$)|会儿(?:[，,]|$))"
    r".{0,64}(?:时|时候)"
    r"|"
    r"(?:等|待)(?!一下(?:[，,]|$)|一会儿(?:[，,]|$)|会儿(?:[，,]|$))"
    r".{0,48}(?:后|以后|之后)(?:.{0,16}(?:再|才))?"
    r"|.{1,40}(?:后|以后|之后)(?:再|才)(?:帮我|请)?"
    r"(?:记|记录|保存|录入|写入|新增|打卡)"
    r")"
)
_THIRD_PARTY_SUBJECT = (
    r"(?:朋友|同事|医生|家人|妈妈|母亲|爸爸|父亲|妻子|丈夫|"
    r"老公|老婆|孩子|儿子|女儿|室友|同学|领导|老板|客户|"
    r"他|她|别人|患者)"
)
_THIRD_PARTY_ROLE_SUFFIX = (
    r"(?:父|母|爸|妈|妹|姐|兄|弟|妻|夫|友|同事|医生|医师|"
    r"营养师|教练|患者|客户|室友|同学|领导|老板|孩子|儿子|女儿)"
)
_THIRD_PARTY_HEALTH_FACT = (
    r"(?:感冒|流感|发烧|生病|口腔溃疡|湿疹|血压|体重|腰围|"
    r"头痛|头疼|胸痛|腹痛|咳嗽|症状|用药|服药)"
)
_WRITE_ACTION_PATTERN = r"(?:记|记录|保存|录入|写入|新增|打卡)"
_THIRD_PARTY_WRITE_SUBJECT_RE = re.compile(
    rf"(?:(?:给|替|为)(?:我(?:的)?)?{_THIRD_PARTY_SUBJECT}.{{0,12}}"
    rf"{_WRITE_ACTION_PATTERN})|"
    rf"(?:(?:我(?:的)?)?{_THIRD_PARTY_SUBJECT}的)|"
    rf"(?:{_WRITE_ACTION_PATTERN}(?:一下)?(?:我(?:的)?)?"
    rf"{_THIRD_PARTY_SUBJECT}(?:的)?(?={_THIRD_PARTY_HEALTH_FACT}))|"
    rf"(?:(?:我(?:的)?)?{_THIRD_PARTY_SUBJECT}(?:的)?"
    rf"{_THIRD_PARTY_HEALTH_FACT}.{{0,20}}{_WRITE_ACTION_PATTERN})|"
    rf"(?:(?:我(?:的)?)?[\u4e00-\u9fff]{{0,6}}{_THIRD_PARTY_ROLE_SUFFIX}(?:的)?"
    rf"{_THIRD_PARTY_HEALTH_FACT}.{{0,20}}{_WRITE_ACTION_PATTERN})"
)
_THIRD_PARTY_HEALTH_SUBJECT_RE = re.compile(
    rf"(?:我(?:的)?)?[\u4e00-\u9fff]{{0,6}}{_THIRD_PARTY_ROLE_SUFFIX}(?:的)?"
    rf"{_THIRD_PARTY_HEALTH_FACT}"
)
_CORRECTION_MARKER_RE = re.compile(
    r"^(?:嗯|抱歉|不好意思)?(?:不对|错了|说错了|说反了|讲反了|口误|笔误|更正一下)$"
)
_CORRECTION_VALUE_RE = re.compile(
    r"^(?:(?:不对|错了|说错了|更正一下)[，,]?)?"
    r"(?:改成|改为|更正为|应该是|应为|其实是)(?P<value>.+)$"
)
_CORRECTION_PENDING_VALUE_RE = re.compile(
    r"^(?:是|应是|应该是|其实是)(?P<value>.+)$"
)
_WRITE_ATTRIBUTE_CONTINUATION_RE = re.compile(
    r"^(?:(?:备注|注释|说明|严重度|严重程度|剂量|用量|每次)"
    r"(?:是|为|：|:)?\S+|(?:早上|早晨|上午|中午|午间|晚上|晚间|睡前)"
    r"(?:吃|服用)?)"
)
_DIRECT_HEALTH_OBSERVATION_RE = re.compile(
    r"(?:吃了|喝了|服了|服用(?:了)?|用了|刚吃|刚喝|"
    r"(?:早餐|早饭|午餐|午饭|中饭|晚餐|晚饭|加餐|零食|夜宵)吃|"
    r"(?:体重|血压|腰围)\s*\d|"
    r"(?:头痛|头疼|胸痛|腹痛|眼痒|嗓子疼|感冒|流感|发烧|生病)(?:了|中|$)|"
    r"(?:提醒|闹钟|目标|准备开始睡觉|开始睡觉|入睡|起床|"
    r"心情|情绪|排便|大便|便秘|腹泻|俯卧撑|瑜伽|跑步))"
)
_HEALTH_OBSERVATION_PREDICATE_RE = re.compile(
    r"(?:吃了|吃的是|不想吃|食欲|不舒服|(?:不)?严重|喝了|喝水|饮水|"
    r"服了|服用(?:了)?|用了|"
    r"体重|血压|腰围|头痛|头疼|胸痛|腹痛|疼|眼痒|嗓子疼|"
    r"感冒|流感|发烧|生病|口腔溃疡|湿疹|咳嗽|症状|用药|服药)"
)
_CURRENT_USER_SUBJECT_NOISE_RE = re.compile(
    r"(?:(?:\d{4}年)?\d{1,2}月\d{1,2}日|"
    r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|"
    r"今天|今日|刚才|刚刚|方才|现在|目前|早上|早晨|上午|"
    r"中午|下午|晚上|晚间|凌晨|黎明|清晨|傍晚|夜里|夜间|半夜|午夜|"
    r"昨天|前天|昨晚|今早|这次|上次|上回|"
    r"上一次|以前|既往|过程中|这会儿|这几天|最近几天|"
    r"过去(?:一|二|两|三|四|五|六|七|八|九|十|\d+)天|"
    r"最近(?:一|二|两|三|四|五|六|七|八|九|十|\d+)天|"
    r"早餐|早饭|午餐|午饭|中饭|晚餐|晚饭|加餐|零食|夜宵|"
    r"还是有|仍然有|仍有|还有|本人|自己|一下)"
)
_SUBJECT_RELATION_NOISE_RE = re.compile(
    r"(?:\d{1,2}点(?:(?:\d{1,2}分)|半|一刻|三刻)?|"
    r"[零〇一二两三四五六七八九十]{1,3}点"
    r"(?:(?:[零〇一二两三四五六七八九十]{1,3}分)|半|一刻|三刻)?|"
    r"\d+(?:\.\d+)?(?:kg|公斤|千克|斤|cm|厘米|mmhg|毫米汞柱|ml|毫升)?|"
    r"已经|又|还|正|正在|刚|有点|突然|最近|不是很|不太|比较|特别|很|"
    r"痊愈|康复|好转|恢复|同时|然后|并且|而且|另外|还有|以及|"
    r"和|与|及|都|全|全部|了|的|是)"
)
_DIRECT_TARGET_LABEL_RE = re.compile(r"(?:疾病|病情|症状|补剂|内容|数据|数值)")
_DIRECT_BODY_LOCATION_RE = re.compile(
    r"(?:(?:左|右|上|下|内|外|前|后)(?:侧)?)?"
    r"(?:口腔|口|嘴|舌|牙|颚|唇|头|颈|肩|胸|腹|腰|背|"
    r"手|脚|腿|膝|皮肤).{0,48}(?:的)?"
)
_SUBJECT_ACTION_SCOPE_BOUNDARY_RE = re.compile(
    r"(?:[，,；;。.!！?？：:]|但是|但|而是|然后)"
)
_COMPOUND_DIRECT_REQUEST_PREFIX_RE = re.compile(
    r"^(?:请|帮我)?(?:计算|分析|识别|估算|整理|总结).{0,48}"
    r"(?:并|然后|再|同时)$"
)
_POST_ATTRIBUTION_RE = re.compile(
    r"(?:这是|这只是|上面是|前面是).{0,12}(?:说的|写的|提到的)?"
    r"(?:例句|例子|原话|转述|引用|假设)|"
    r"(?:朋友|同事|医生|家人|妈妈|爸爸|文档|报告).{0,8}"
    r"(?:说的|写的|提到的).{0,4}(?:例句|原话|内容|话)"
)
_POST_CURRENT_USER_OWNERSHIP_DENIAL_RE = re.compile(
    r"^(?:这(?:条|个)?(?:记录|数据)?(?:其实|实际上)?)?"
    r"不是(?:我|本人|自己)(?:的)?"
    r"(?:而是|是|而属于|属于|归于|归)(?P<owner>[\u4e00-\u9fff]{1,12})(?:的)?$"
)
_POST_CURRENT_USER_OWNERSHIP_ONLY_DENIAL_RE = re.compile(
    r"^(?:这(?:条|个)?(?:记录|数据)?(?:其实|实际上)?)?"
    r"不是(?:我|本人|自己)(?:的)?$"
)
_POST_OWNERSHIP_RE = re.compile(
    r"^(?:实际上|其实|原来)?"
    r"(?:这(?:条|个)?(?:记录|数据|饮水)?|这杯(?:水)?)?(?:其实|实际上)?"
    r"(?:是|属于|归于|归|给)"
    r"(?P<owner>[\u4e00-\u9fff]{1,12})(?:的)?$"
)
_POST_BARE_OWNER_RE = re.compile(
    r"^(?P<owner>[\u4e00-\u9fff]{2,4})的$"
)
_POST_OWNER_RESOURCE_RE = re.compile(
    r"^(?:这(?:条|个|次)?(?:记录|数据|行程|事件)?(?:其实|实际上)?)?"
    r"(?:是|属于|归于|归|给)(?P<owner>[\u4e00-\u9fff]{1,12})的"
    r"(?:行程|记录|数据|事件|饮水|药|补剂)$"
)
_POST_BARE_OWNER_RESOURCE_RE = re.compile(
    r"^(?P<owner>[\u4e00-\u9fff]{1,12})的"
    r"(?:行程|记录|数据|事件|饮水|药|补剂)$"
)
_POST_WRITE_BENEFICIARY_RE = re.compile(
    r"^(?:记录|记一下|记下|保存|录入|写入|新增|打卡)(?:一下)?"
    r"(?:给|替|为)(?P<owner>[\u4e00-\u9fff]{1,12})(?:的)?$"
)
_CURRENT_OWNER_WORDS = frozenset({
    "我",
    "我的",
    "本人",
    "我本人",
    "自己",
    "我自己",
    "自己的",
    "我自己的",
})
_NON_OWNER_WORDS = frozenset({
    *_CURRENT_OWNER_WORDS,
    "今天",
    "昨天",
    "前天",
    "刚才",
    "刚刚",
    "上次",
    "这次",
})
_UPDATE_ACTION_RE = re.compile(
    r"(?:改成|改为|更正为|修正为|调整为|更新为|修改(?:为|成)?)"
)
_THIRD_PARTY_UPDATE_ORDER_RE = re.compile(
    r"^(?!我(?:要|想|来|自己|本人))"
    r"[\u4e00-\u9fff]{1,12}(?:希望|想|要求|建议|指示|让我|叫我|嘱咐我|让小巴|让系统)"
)
_THIRD_PARTY_UPDATE_BENEFICIARY_RE = re.compile(
    r"^(?:替|给|为)(?!(?:我|本人|自己|我自己)(?:把|将))"
    r"[\u4e00-\u9fff]{1,12}(?:把|将)"
)
_EVENT_ARRIVAL_FACT_RE = re.compile(
    r"^(?P<subject>.*?)到(?P<place>[\u4e00-\u9fff][^，,。.!！；;：:?？]{0,19})"
    r"(?:了|$)"
)
_EVENT_WRITE_SCAFFOLD_RE = re.compile(
    r"^(?:(?:请|请你|麻烦|麻烦你|帮我|请帮我|请你帮我|麻烦帮我|"
    r"可以帮我|能帮我|替我|给我|为我|我想|我要|我希望|我需要))?"
    r"(?:记录|记一下|记下|保存|录入|写入|新增|打卡)(?:一下)?"
    r"(?:生活事件)?[：:]?"
)
_EXTERNAL_PROVENANCE_RE = re.compile(
    r"(?:(?:来自|来源于|摘(?:录)?自|转自|出自)|"
    r"(?:根据|(?<!数)据)).{0,16}"
    r"(?:消息|日志|聊天|群聊|群消息|通知|文本|原文|记录)"
)
_UPDATE_METALANGUAGE_PREFIX_RE = re.compile(
    r"^(?:以下(?:内容|文字)?(?:是|为)?)?"
    r"(?:原文|原话|例句|例子|引用|转述|假设)(?:如下|是|为)?[:：]?"
)
_UPDATE_HYPOTHETICAL_SUFFIX_RE = re.compile(
    r"(?:的话|会不会|是否会|可能会)?.{0,8}"
    r"(?:会怎样|怎么样|怎样|如何|发生什么|有什么影响)[?？]?$"
)
_UPDATE_REVOCATION_RE = re.compile(
    r"(?:撤回|撤销|取消|忽略|作废|停止|不要执行|不执行|不要应用|不应用)"
    r".{0,10}(?:修改|更新|更改|请求|操作)|"
    r"(?:保持|维持).{0,16}(?:原样|不变)|"
    r"(?:还是|恢复成|改回|还原为).{0,16}(?:ml|毫升|原样|不变)(?:吧)?$|"
    r"(?:照旧|别动|不要动|不用动)$"
)
_QUOTE_PAIRS = (
    ('"', '"'),
    ("“", "”"),
    ("「", "」"),
    ("『", "』"),
    ("〈", "〉"),
    ("《", "》"),
    ("【", "】"),
    ("‘", "’"),
    ("'", "'"),
    ("`", "`"),
)
_PARENTHETICAL_PAIRS = (("（", "）"), ("(", ")"))
_UPDATE_CORRECTION_MARKER_PATTERN = (
    r"(?:(?:哦不|不对|错了|说错了|更正一下|等等|等一下|抱歉)[，,]?|不[，,])"
)
_UPDATE_CORRECTION_VALUE_RE = re.compile(
    rf"(?:^|[，,]){_UPDATE_CORRECTION_MARKER_PATTERN}"
    r"(?:应该|应当)?(?:是|为|改成|改为)?"
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ml|毫升|l|升)?"
)
_UPDATE_CORRECTION_MARKER_RE = re.compile(
    rf"(?:^|[，,]){_UPDATE_CORRECTION_MARKER_PATTERN}(?:$|(?=应该|应当|是|为|改))"
)
_WATER_VALUE_TEXT_PATTERN = r"\d+(?:\.\d+)?(?:ml|毫升|l|升)"
_WATER_CORRECTION_VALUE_TEXT_PATTERN = r"\d+(?:\.\d+)?(?:ml|毫升|l|升)?"
_CURRENT_USER_UPDATE_PREFIX_PATTERN = (
    r"(?:(?:请|请你|麻烦|麻烦你|帮我|请帮我|请你帮我|麻烦帮我|"
    r"可以帮我|能帮我|替我|给我|为我|"
    r"我想|我想请你|我要|我希望|我需要))?"
)
_CURRENT_USER_RECORD_OWNER_PATTERN = (
    r"(?:(?:我(?:自己|本人)?|本人|自己)(?:的)?)?"
)
_DIRECT_WATER_UPDATE_RE = re.compile(
    rf"^{_CURRENT_USER_UPDATE_PREFIX_PATTERN}(?:把|将)?"
    rf"{_CURRENT_USER_RECORD_OWNER_PATTERN}"
    rf"(?:"
    rf"(?:刚才|刚刚|上一条|最近一条)(?:的)?"
    rf"|(?:饮水|water)(?:记录|条目)#?\d+(?:的)?"
    rf")"
    rf"[：:]?[（(]?{_WATER_VALUE_TEXT_PATTERN}[）)]?"
    rf"(?:的?(?:饮水量|水量|量))?"
    rf"(?:改成|改为|更正为|修正为|调整为|更新为|修改为|修改成)"
    rf"{_WATER_VALUE_TEXT_PATTERN}"
    rf"(?:[，,]{_UPDATE_CORRECTION_MARKER_PATTERN}"
    rf"(?:应该|应当)?(?:是|为|改成|改为)?"
    rf"{_WATER_CORRECTION_VALUE_TEXT_PATTERN})?$",
    re.IGNORECASE,
)
_DIRECT_WATER_ID_UPDATE_RE = re.compile(
    rf"^{_CURRENT_USER_UPDATE_PREFIX_PATTERN}(?:把|将)?"
    rf"{_CURRENT_USER_RECORD_OWNER_PATTERN}"
    rf"(?:饮水|water)(?:记录|条目)#?\d+"
    rf"(?:改成|改为|更正为|修正为|调整为|更新为|修改为|修改成)"
    rf"{_WATER_VALUE_TEXT_PATTERN}"
    rf"(?:[，,]{_UPDATE_CORRECTION_MARKER_PATTERN}"
    rf"(?:应该|应当)?(?:是|为|改成|改为)?"
    rf"{_WATER_CORRECTION_VALUE_TEXT_PATTERN})?$",
    re.IGNORECASE,
)
_DIRECT_ILLNESS_UPDATE_RE = re.compile(
    rf"^{_CURRENT_USER_UPDATE_PREFIX_PATTERN}"
    r"(?P<statement>[^，,。.!！；;：:?？]{2,120})[，,]"
    rf"{_CURRENT_USER_UPDATE_PREFIX_PATTERN}"
    r"(?:修改|更新|更正)(?:一下)?(?:这条)?记录$"
)
_DIRECT_REMEMBER_AVOID_RE = re.compile(
    r"^(?:请)?(?:帮我)?记住(?:我|我的)?(?P<value>不吃[^，,。.!！；;：:?？]{1,80})$"
)
_DIRECT_REMEMBER_AVOID_TRAILING_RE = re.compile(
    r"^(?:我)?(?P<value>不吃[^，,。.!！；;：:?？]{1,80})"
    r"[，,](?:请)?(?:帮我)?记住(?:一下)?$"
)
_DIRECT_EVENT_ARRIVAL_RE = re.compile(
    r"^(?:我)?(?:已经|刚刚|刚)?到(?P<place>[^，,。.!！；;：:?？]{1,20})了"
    r"(?:[，,]?(?:记录|记一下|打卡)(?:一下)?)?$"
)
_DIRECT_EVENT_RECENT_ARRIVAL_RE = re.compile(
    r"^我(?:刚刚|刚)到(?P<place>[^，,。.!！；;：:?？]{1,20})$"
)
_DIRECT_EVENT_DEPARTURE_RE = re.compile(r"^(?:我)?飞机准备起飞(?:了)?$")
_DIRECT_EVENT_EN_ROUTE_RE = re.compile(
    r"^(?:我)?在去(?P<place>[^，,。.!！；;：:?？]{1,20})路上$"
)
_BACKFILL_DATE_SIGNALS = (
    "发作日期",
    "开始日期",
    "起病日期",
    "发生日期",
    "日期是",
    "日期为",
    "时间是",
    "时间为",
)
_MEAL_SLOT_TERMS = (
    "早餐",
    "早饭",
    "午餐",
    "午饭",
    "中饭",
    "晚餐",
    "晚饭",
    "加餐",
    "零食",
    "夜宵",
)
_NON_FOOD_CONTINUATION_SIGNALS = (
    *READ_ACTIONS,
    *QUESTION_SIGNALS,
    "分析",
    "建议",
    "评估",
    "解释",
    "为什么",
    "怎么",
    "如何",
    "热量",
    "营养",
    "千卡",
    "卡路里",
    "蛋白质",
    "碳水",
    "脂肪",
    "膳食纤维",
    "纤维",
    "转述",
    "复述",
    "引用",
    "例句",
    "例子",
)
_NON_FOOD_ENTITY_SIGNALS = (
    "药",
    "胶囊",
    "补剂",
    "维生素",
    "益生菌",
    "鱼油",
)
_DECLARATIVE_FOOD_CONTINUATION_RE = re.compile(
    r"^(?:我)?(?:吃了|吃的是|吃|有|是).+"
)
_BACKFILL_REQUEST_MARKERS = (
    "请",
    "帮我",
    "把",
    "麻烦",
    "替我",
    "给我",
    "为我",
    "补充",
)
_DIRECT_REQUEST_HELPERS = (
    "别忘了",
    "我想请你",
    "我想让你",
    "我希望你",
    "我需要你",
    "我想请",
    "麻烦帮我",
    "麻烦你",
    "请你",
    "帮我",
    "帮忙",
    "给我",
    "替我",
    "为我",
    "麻烦",
    "劳烦",
    "请",
    "我想",
    "希望",
    "需要",
    "想",
    "能帮我",
    "可以帮我",
)
_DIRECT_REQUEST_MODIFIERS = (
    "可不可以",
    "能不能",
    "不得不",
    "不能不",
    "不妨",
    "可以",
    "能否",
    "可否",
    "能",
    "分别",
    "顺便",
    "现在",
    "立即",
    "马上",
    "主动",
    "务必",
    "然后",
    "再",
    "先",
    "就",
    "你",
)
_VOCATIVE_PREFIXES = ("小巴你", "小巴", "助手你", "助手")
_DENIAL_SCOPE_INTRO_ENDINGS = (
    "执行",
    "执行以下操作",
    "执行如下操作",
    "以下操作",
    "如下操作",
    "这些操作",
    "这项操作",
    "以下行为",
    "如下行为",
    "这些行为",
    "这项行为",
    "以下事项",
    "如下事项",
    "以下内容",
    "如下内容",
    "以下动作",
    "如下动作",
    "这件事",
    "该件事",
    "这回事",
)
_DIRECT_DENIAL_PREDICATES = (
    "禁止",
    "严禁",
    "拒绝",
    "避免",
    "杜绝",
    "停止",
    "暂停",
    "终止",
    "取消",
    "撤销",
    "放弃",
    "谢绝",
)
_ORDERED_WRITE_ACTIONS = tuple(sorted(WRITE_COMMAND_ACTIONS, key=len, reverse=True))
_ORDERED_WRITE_SIGNALS = tuple(sorted(WRITE_ACTIONS, key=len, reverse=True))
_ORDERED_NEGATIONS = tuple(sorted(STRUCTURAL_WRITE_NEGATIONS, key=len, reverse=True))
_ORDERED_NON_NEGATING_MODALS = tuple(
    sorted(_NON_NEGATING_MODALS, key=len, reverse=True)
)


def normalize_write_scope_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return "".join(normalized.split()).lower()


def _is_clock_colon(value: str, position: int) -> bool:
    hour_match = re.search(r"(?<!\d)(?P<hour>\d{1,2})$", value[:position])
    minute_match = re.match(r"(?P<minute>\d{2})(?!\d)", value[position + 1:])
    if hour_match is None or minute_match is None:
        return False
    return (
        0 <= int(hour_match.group("hour")) <= 23
        and 0 <= int(minute_match.group("minute")) <= 59
    )


def split_write_clauses(value: str) -> tuple[str, ...]:
    text = normalize_write_scope_text(value)
    text = _CONTEXTUAL_DENIAL_COMMA_RE.sub(r"\1", text)
    colon_scoped: list[str] = []
    current = ""
    for position, character in enumerate(text):
        if character not in ("：", ":"):
            current += character
            continue
        clock_colon = _is_clock_colon(text, position)
        if (
            clock_colon
            or _colon_extends_denial_scope(current)
            or _colon_extends_write_target(current)
        ):
            if clock_colon:
                current += character
            continue
        if current:
            colon_scoped.append(current)
        current = ""
    if current:
        colon_scoped.append(current)
    decimal_sentinel = "\ue001"
    clauses: list[str] = []
    for segment in colon_scoped:
        protected = re.sub(r"(?<=\d)\.(?=\d)", decimal_sentinel, segment)
        clauses.extend(
            clause.replace(decimal_sentinel, ".")
            for clause in _CLAUSE_BOUNDARY_RE.split(protected)
            if clause
        )
    return tuple(clauses)


def _colon_extends_denial_scope(left: str) -> bool:
    if any(predicate in left for predicate in _DIRECT_DENIAL_PREDICATES):
        return True
    if not any(negation in left for negation in _ORDERED_NEGATIONS):
        return False
    return left.endswith(_DENIAL_SCOPE_INTRO_ENDINGS)


def _colon_extends_write_target(left: str) -> bool:
    if left.endswith(
        (
            "创建目标",
            "设定目标",
            "设置目标",
            "新增目标",
            "记录目标",
            "记录事件",
            "记录生活事件",
        )
    ):
        return True
    action = _last_write_signal_in_clause(left)
    if action is None:
        return False
    signal, _start = action
    return left.endswith(signal)


def _clean_negation_clause(raw_clause: str) -> str:
    clause = raw_clause
    for exception in WRITE_NEGATION_EXCEPTIONS:
        clause = clause.replace(exception, "")
    clause = _POSITIVE_REMINDER_RE.sub("", clause)
    for container in _NEGATION_LEXICAL_CONTAINERS:
        clause = clause.replace(container, "")
    for modal in _ORDERED_NON_NEGATING_MODALS:
        clause = clause.replace(modal, "")
    return clause


def _last_action_in_clause(clause: str) -> tuple[str, int] | None:
    context: tuple[str, int] | None = None
    for action in _ORDERED_WRITE_ACTIONS:
        start = clause.rfind(action)
        if start < 0:
            continue
        if context is None or start > context[1]:
            context = (action, start)
    return context


def _last_write_signal_in_clause(clause: str) -> tuple[str, int] | None:
    context: tuple[str, int] | None = None
    for signal in _ORDERED_WRITE_SIGNALS:
        start = clause.rfind(signal)
        if start < 0:
            continue
        if context is None or start > context[1]:
            context = (signal, start)
    return context


def _last_write_action_context(value: str) -> tuple[str, str, int] | None:
    last_context: tuple[str, str, int] | None = None
    for clause in split_write_clauses(value):
        action_context = _last_action_in_clause(clause)
        if action_context is not None:
            action, start = action_context
            last_context = (clause, action, start)
    return last_context


def _starts_with_completed_aspect(after_action: str) -> bool:
    if after_action.startswith("了"):
        return True
    return after_action.startswith("过") and not after_action.startswith(
        _NON_ASPECT_GUARDS
    )


def _write_clause_denials(value: str) -> tuple[bool, ...]:
    text = normalize_write_scope_text(value)
    if not text:
        return ()
    limiting_matches = tuple(_LIMITING_WRITE_RE.finditer(text))
    if limiting_matches:
        text = text[limiting_matches[-1].end():]

    denials: list[bool] = []
    for raw_clause in split_write_clauses(text):
        clause = _clean_negation_clause(raw_clause)
        action_context = _last_write_signal_in_clause(clause)
        if action_context is None:
            if (
                denials
                and _TRAILING_REVOCATION_CLAUSE_RE.fullmatch(clause)
            ):
                denials[-1] = True
            continue
        _action, action_position = action_context
        before_action = clause[:action_position]
        after_action = clause[action_position:]
        denials.append(
            bool(
                any(
                    clause.find(negation, 0, action_position) >= 0
                    for negation in _ORDERED_NEGATIONS
                )
                or _NEGATED_CONTROL_RE.search(before_action)
                or _DIRECT_DENIAL_SCOPE_RE.search(before_action)
                or _POST_ACTION_DENIAL_RE.search(after_action)
            )
        )
    return tuple(denials)


def has_negated_write_scope(value: str) -> bool:
    """Return whether the governing write-bearing clause denies authorization.

    Contrast clauses are evaluated in order. A later positive write clause can
    supersede an earlier refusal, while a trailing revocation applies to the
    most recent write clause.
    """
    denials = _write_clause_denials(value)
    return bool(denials and denials[-1])


def has_mixed_write_polarity(value: str) -> bool:
    """Return true when denied and authorized write clauses coexist."""
    denials = _write_clause_denials(value)
    return any(denials) and any(not denied for denied in denials)


def is_write_capability_question(value: str) -> bool:
    """Recognize product-capability questions without treating them as requests."""
    context = _last_write_action_context(value)
    if context is None:
        return False
    clause, action, action_position = context
    before_action = clause[:action_position]
    after_action = clause[action_position + len(action):]
    has_inquiry_cue = any(
        cue in before_action for cue in _CAPABILITY_INQUIRY_PREFIXES
    )
    subject_match = min(
        (
            (position, candidate)
            for candidate in _CAPABILITY_SUBJECTS
            if (position := before_action.find(candidate)) >= 0
        ),
        default=None,
    )
    if subject_match is None:
        return has_inquiry_cue and (
            any(signal.lower() in clause for signal in QUESTION_SIGNALS)
            or any(modal in before_action for modal in _CAPABILITY_MODALS)
        )
    subject_position, subject = subject_match
    after_subject = clause[subject_position + len(subject):]
    subject_action_position = after_subject.find(action)
    if subject_action_position < 0:
        return False
    before_subject_action = after_subject[:subject_action_position]
    if (
        subject == "小巴"
        and not has_inquiry_cue
        and (
            "你能帮我" in before_action
            or "你可以帮我" in before_action
            or after_action.startswith(("一下", "下来"))
        )
    ):
        return False
    return has_inquiry_cue or any(
        modal in before_subject_action for modal in _CAPABILITY_MODALS
    )


def _is_explicit_dated_backfill(value: str) -> bool:
    text = normalize_write_scope_text(value)
    if not any(term in text for term in _HISTORY_TERMS):
        return False
    if not (
        any(signal in text for signal in _BACKFILL_DATE_SIGNALS)
        or any(term in text for term in _PAST_TIME_TERMS)
    ):
        return False
    if any(signal in text for signal in QUESTION_SIGNALS):
        return False
    for clause in split_write_clauses(text):
        candidates: list[tuple[int, str]] = []
        for action in _ORDERED_WRITE_ACTIONS:
            start = clause.find(action)
            while start >= 0:
                candidates.append((start, action))
                start = clause.find(action, start + len(action))
        for action_position, action in sorted(candidates):
            before_action = clause[:action_position]
            after_action = clause[action_position + len(action):]
            if action == "记录" and (
                after_action.startswith(RECORD_NOUN_SUFFIXES)
                or (
                    not after_action
                    and any(
                        earlier_position < action_position
                        for earlier_position, _earlier_action in candidates
                    )
                )
            ):
                continue
            if (
                action_position == 0
                or before_action.endswith(_BACKFILL_REQUEST_MARKERS)
                or after_action.startswith(("一下", "下来"))
            ):
                return True
    return False


def is_historical_write_reference(value: str) -> bool:
    """Recognize completion and historical/list noun frames for the last action."""
    if _is_explicit_dated_backfill(value):
        return False
    context = _last_write_action_context(value)
    if context is None:
        return False
    normalized = normalize_write_scope_text(value)
    if (
        any(term in normalized for term in ("补剂", "药"))
        and any(term in normalized for term in ("都吃了", "全吃了", "全部吃了", "都服了", "全部服了"))
        and context[2] > normalized.find("补剂")
    ):
        return False
    clause, action, start = context
    after = clause[start + len(action):]
    if _starts_with_completed_aspect(after):
        return True
    completed_tail = after.rstrip(_COMPLETION_TRAILING_PARTICLES)
    if completed_tail.endswith(_COMPLETED_TAILS):
        return True
    if any(term in clause for term in _HISTORY_NOUN_TERMS):
        return True
    has_question = any(signal.lower() in clause for signal in QUESTION_SIGNALS)
    return any(
        (term_position := clause.find(term)) >= 0
        and (term_position < start or has_question)
        for term in _PAST_TIME_TERMS
    )


def is_read_action_write_reference(value: str) -> bool:
    """Return true when a read verb governs a later write-action noun."""
    context = _last_write_action_context(value)
    if context is None:
        return False
    clause, _action, start = context
    return any(
        (read_position := clause.find(read_action)) >= 0 and read_position < start
        for read_action in READ_ACTIONS
    )


def is_write_result_check(value: str) -> bool:
    """Recognize checks of an earlier write's completion or persistence state."""
    context = _last_write_action_context(value)
    if context is None:
        return False
    clause, action, start = context
    before_action = clause[:start]
    after_action = clause[start + len(action):]
    has_check_lead = any(cue in before_action for cue in _RESULT_CHECK_LEADS)
    has_state = any(marker in before_action for marker in _RESULT_STATE_MARKERS)
    has_result_tail = any(marker in after_action for marker in _RESULT_TAIL_MARKERS)
    return (has_check_lead and (has_state or has_result_tail)) or (
        has_result_tail and any(signal in clause for signal in QUESTION_SIGNALS)
    )


def is_reported_write_reference(value: str) -> bool:
    """Recognize attributed, quoted, or metalinguistic write language."""
    text = normalize_write_scope_text(value)
    if _is_fully_parenthesized(text):
        return True
    if any(opening in text and closing in text for opening, closing in _QUOTE_PAIRS):
        return True

    clauses = split_write_clauses(text)
    if not clauses:
        return False
    signal_index = next(
        (
            index
            for index in range(len(clauses) - 1, -1, -1)
            if _last_write_signal_in_clause(clauses[index]) is not None
        ),
        len(clauses) - 1,
    )
    candidate_indices = (signal_index - 1, signal_index)
    for index in candidate_indices:
        if index < 0:
            continue
        segment = clauses[index]
        signal = (
            _last_write_signal_in_clause(segment)
            if index == signal_index
            else None
        )
        before_signal = segment[:signal[1]] if signal is not None else segment
        if any(action in before_signal for action in _METALANGUAGE_ACTIONS):
            return True
        for verb in _REPORTING_VERBS:
            verb_position = before_signal.find(verb)
            if verb_position < 0:
                continue
            subject = before_signal[:verb_position]
            if (
                subject
                and not any(negation in subject for negation in _ORDERED_NEGATIONS)
                and _strip_direct_request_prefix(subject)
            ):
                return True
    return False


def _is_fully_parenthesized(value: str) -> bool:
    text = normalize_write_scope_text(value).strip("，,。.!！；;：:?？")
    return any(
        text.startswith(opening) and text.endswith(closing)
        for opening, closing in _PARENTHETICAL_PAIRS
    )


def governing_authorized_write_clause(value: str) -> str | None:
    """Return the concrete current clause that owns health-write authority.

    The result is intentionally clause-scoped.  It never returns quoted,
    reported, historical, denied, result-check, or revoked language.  Callers
    can classify this clause to bind a tool request to its concrete target
    instead of inheriting a boolean authorization from the whole turn.
    """
    clauses = authorized_health_record_clauses(value)
    return clauses[-1] if clauses else None


def _has_untrusted_colon_command(value: str) -> bool:
    """Return whether a colon introduces a command without direct authority.

    A colon after a direct write action remains part of that action's target
    (``记录疾病：感冒``). A colon whose left side has no write action is a
    quotation/provenance boundary, so a command on the right cannot inherit
    current-user authority from the surrounding turn.
    """
    for match in re.finditer(r"[:：]", value):
        if _is_clock_colon(value, match.start()):
            continue
        left = value[:match.start()]
        right = value[match.end():]
        if any(action in left for action in _METALANGUAGE_ACTIONS):
            return True
        if (
            _last_write_signal_in_clause(left) is not None
            and _observation_has_non_current_subject(right)
        ):
            return True
        if _colon_extends_write_target(left):
            continue
        if (
            _HEALTH_OBSERVATION_PREDICATE_RE.search(left)
            and not _observation_has_non_current_subject(left)
        ):
            continue
        if (
            _last_write_signal_in_clause(left) is None
            and _last_write_signal_in_clause(right) is not None
        ):
            return True
        if (
            _UPDATE_ACTION_RE.search(left) is None
            and _UPDATE_ACTION_RE.search(right) is not None
        ):
            return True
        if direct_event_values(right) is not None:
            return True
    return False


def _observation_has_non_current_subject(clause: str) -> bool:
    """Fail closed when a health observation names an unowned subject.

    This deliberately does not try to enumerate kinship roles or names. The
    prefix governing the health predicate must reduce to the current user (or
    a subjectless shorthand); otherwise a later ``记录一下`` cannot turn that
    fact into the current user's record.
    """
    matches = tuple(_HEALTH_OBSERVATION_PREDICATE_RE.finditer(clause))
    if not matches:
        return False
    if direct_supplement_group_values(clause) is not None:
        return False
    if clause.startswith(
        ("创建目标", "设定目标", "设置目标", "新增目标", "记录目标")
    ):
        return False
    if (
        any(term in clause for term in ("提醒", "闹钟"))
        and (
            _last_write_signal_in_clause(clause) is not None
            or re.search(r"(?:设置|设定|创建|新增|安排)", clause)
        )
    ):
        # A phrase such as ``饮水提醒`` names the reminder topic, not the
        # owner of a health observation. Reminder title/time identity is bound
        # separately by CapabilityPolicy before dispatch.
        return False
    previous_end = 0
    for match in matches:
        prefix = clause[previous_end:match.start()]
        if previous_end and re.search(r"(?:备注|注释|说明|描述)", prefix):
            previous_end = match.end()
            continue
        action_context = _last_write_signal_in_clause(prefix)
        if action_context is not None:
            action, action_start = action_context
            initiator = _SUBJECT_ACTION_SCOPE_BOUNDARY_RE.split(
                prefix[:action_start]
            )[-1]
            if _strip_direct_request_prefix(initiator).strip(
                "，,。.!！；;：: "
            ) not in {"", "我"}:
                return True
            prefix = prefix[action_start + len(action):]
        prefix = prefix.lstrip("把将")
        if _DIRECT_BODY_LOCATION_RE.fullmatch(prefix):
            prefix = ""
        reduced = _CURRENT_USER_SUBJECT_NOISE_RE.sub("", prefix)
        reduced = _DIRECT_TARGET_LABEL_RE.sub("", reduced)
        reduced = _SUBJECT_RELATION_NOISE_RE.sub("", reduced)
        reduced = reduced.strip("、，,。.!！；;：:?？ ")
        reduced = re.sub(
            r"^(?:我(?:的)?|本人(?:的)?|自己(?:的)?)",
            "",
            reduced,
        )
        if _DIRECT_BODY_LOCATION_RE.fullmatch(reduced):
            reduced = ""
        if reduced not in {"", "我", "我的", "本人", "自己", "自己的"}:
            return True
        previous_end = match.end()
    return False


def _segment_has_non_current_subject(segment: str) -> bool:
    """Carry subject ownership across clauses, excluding denied observations."""
    for clause in split_write_clauses(segment):
        if _event_fact_has_non_current_subject(clause):
            return True
        if (
            has_negated_write_scope(clause)
            or _WRITE_ATTRIBUTE_CONTINUATION_RE.fullmatch(clause)
        ):
            continue
        if _observation_has_non_current_subject(clause):
            return True
    return False


def _event_fact_has_non_current_subject(clause: str) -> bool:
    """Resolve an arrival fact's subject after removing time/aspect phrases."""
    if "目标" in clause and re.search(
        r"(?:达到|降到|减到|升到|调整到)",
        clause,
    ):
        # ``达到目标值`` is a goal predicate, not the arrival verb ``到``.
        # Let the goal compiler decide whether the target is complete enough.
        return False
    match = _EVENT_ARRIVAL_FACT_RE.fullmatch(clause)
    if match is None:
        return False
    subject = _EVENT_WRITE_SCAFFOLD_RE.sub("", match.group("subject"), count=1)
    reduced = _CURRENT_USER_SUBJECT_NOISE_RE.sub("", subject)
    reduced = _SUBJECT_RELATION_NOISE_RE.sub("", reduced)
    reduced = re.sub(r"(?:终于|平安|顺利|安全)", "", reduced)
    reduced = reduced.strip("的，,。.!！；;：:?？ ")
    reduced = re.sub(r"^(?:我(?:本人|自己)?|本人|自己)$", "", reduced)
    return bool(reduced)


def _segment_has_untrusted_provenance_or_owner(segment: str) -> bool:
    """Reject sourced facts and parenthetical ownership transfers as authority."""
    if _EXTERNAL_PROVENANCE_RE.search(segment):
        return True
    for opening, closing in _PARENTHETICAL_PAIRS:
        for match in re.finditer(
            rf"{re.escape(opening)}(?P<content>.*?){re.escape(closing)}",
            segment,
        ):
            if _is_post_attributed_to_non_current_owner(match.group("content")):
                return True
    return False


def authorized_health_record_clauses(value: str) -> tuple[str, ...]:
    """Return every direct clause that may own one concrete health write.

    Authorization is intentionally a set rather than a whole-turn boolean:
    separate positive clauses can each authorize one target, while reported,
    hypothetical, denied and later-revoked language contributes no authority.
    The capability policy still has to classify each returned clause and bind
    the actual tool payload to its type, selectors and values.
    """
    text = normalize_write_scope_text(value)
    if not text:
        return ()
    limiting_matches = tuple(_LIMITING_WRITE_RE.finditer(text))
    if limiting_matches:
        text = text[limiting_matches[-1].end():]

    # An unclosed quotation has no trustworthy return to the user's own voice.
    quote_pairs = _QUOTE_PAIRS[1:]
    if any(text.count(opening) > text.count(closing) for opening, closing in quote_pairs):
        return ()
    if text.count('"') % 2:
        return ()

    authorized: list[str] = []
    for contrast_segment in _CONTRAST_SCOPE_RE.split(text):
        if not contrast_segment:
            continue
        if _has_untrusted_colon_command(contrast_segment):
            continue
        if _segment_has_untrusted_provenance_or_owner(contrast_segment):
            continue
        segment_start = len(authorized)
        reported_scope = False
        hypothetical_scope = False
        raw_clauses = split_write_clauses(contrast_segment)
        clauses: list[str] = []
        correction_pending = False
        for raw_clause in raw_clauses:
            if _CORRECTION_MARKER_RE.fullmatch(raw_clause):
                correction_pending = True
                continue
            correction_match = _CORRECTION_VALUE_RE.fullmatch(raw_clause)
            if correction_match is None and correction_pending:
                correction_match = _CORRECTION_PENDING_VALUE_RE.fullmatch(raw_clause)
            if correction_match is not None and (correction_pending or clauses):
                if clauses:
                    clauses[-1] = _corrected_write_clause(
                        clauses[-1], correction_match.group("value")
                    )
                correction_pending = False
                continue
            correction_pending = False
            raw_action = _last_action_in_clause(raw_clause)
            bare_followup_write = False
            if raw_action is not None:
                action, action_start = raw_action
                after_action = raw_clause[action_start + len(action):]
                bare_followup_write = after_action in {"", "一下", "下来", "一条"}
            if (
                clauses
                and any(signal in raw_clause for signal in _BACKFILL_DATE_SIGNALS)
                and _last_write_signal_in_clause(raw_clause) is None
            ):
                clauses[-1] = f"{clauses[-1]}，{raw_clause}"
            elif (
                clauses
                and _is_meal_food_write_clause(clauses[-1])
                and (
                    _is_safe_food_continuation(raw_clause)
                    or _is_safe_declarative_food_continuation(raw_clause)
                )
            ):
                clauses[-1] = f"{clauses[-1]}，{raw_clause}"
            elif (
                clauses
                and bare_followup_write
                and not _is_post_attributed_to_non_current_owner(clauses[-1])
            ):
                clauses[-1] = f"{clauses[-1]}，{raw_clause}"
            elif clauses and _WRITE_ATTRIBUTE_CONTINUATION_RE.fullmatch(raw_clause):
                clauses[-1] = f"{clauses[-1]}，{raw_clause}"
            else:
                clauses.append(raw_clause)
        third_party_scope = False
        for clause in clauses:
            if _is_post_attributed_to_non_current_owner(clause):
                # Ownership stated later in the same semantic segment governs
                # the earlier health fact too.  It must be able to revoke a
                # provisional ``记录感冒`` authorization instead of being
                # appended as a harmless follow-up clause.
                del authorized[segment_start:]
                third_party_scope = True
                continue
            if _TRAILING_REVOCATION_CLAUSE_RE.fullmatch(clause):
                while authorized:
                    candidate = authorized.pop()
                    if (
                        _last_write_signal_in_clause(candidate) is not None
                        or _DIRECT_HEALTH_OBSERVATION_RE.search(candidate)
                    ):
                        break
                continue

            polite_condition = bool(_POLITE_CONDITIONAL_PREFIX_RE.search(clause))
            if (
                _DEFERRED_CONDITION_PREFIX_RE.search(clause)
                or (
                    _HYPOTHETICAL_PREFIX_RE.search(clause)
                    and not polite_condition
                )
            ):
                hypothetical_scope = True

            reported_clause = is_reported_write_reference(clause)
            if reported_clause:
                reported_scope = True
                if _POST_ATTRIBUTION_RE.search(clause):
                    del authorized[segment_start:]

            clause_negated = has_negated_write_scope(clause)
            if not clause_negated and (
                _THIRD_PARTY_WRITE_SUBJECT_RE.search(clause)
                or _THIRD_PARTY_HEALTH_SUBJECT_RE.search(clause)
                or _event_fact_has_non_current_subject(clause)
                or _observation_has_non_current_subject(clause)
            ):
                third_party_scope = True

            if (
                reported_scope
                or hypothetical_scope
                or third_party_scope
            ):
                continue
            if (
                is_write_capability_question(clause)
                or is_historical_write_reference(clause)
                or is_read_action_write_reference(clause)
                or is_write_result_check(clause)
                or clause_negated
            ):
                continue

            action = _last_action_in_clause(clause)
            if action is not None and not has_explicit_authorizing_write_request(clause):
                continue
            if (
                action is None
                and direct_event_values(clause) is not None
                and direct_event_values(contrast_segment) is None
            ):
                continue
            authorized.append(clause)
    return tuple(authorized)


def _is_post_attributed_to_non_current_owner(clause: str) -> bool:
    normalized = clause.strip("，,。.!！；;：: ")
    if _POST_CURRENT_USER_OWNERSHIP_ONLY_DENIAL_RE.fullmatch(normalized):
        return True
    denial_match = _POST_CURRENT_USER_OWNERSHIP_DENIAL_RE.fullmatch(normalized)
    match = (
        denial_match
        or _POST_OWNER_RESOURCE_RE.fullmatch(normalized)
        or _POST_BARE_OWNER_RESOURCE_RE.fullmatch(normalized)
        or _POST_WRITE_BENEFICIARY_RE.fullmatch(normalized)
        or _POST_OWNERSHIP_RE.fullmatch(normalized)
        or _POST_BARE_OWNER_RE.fullmatch(normalized)
    )
    if match is None:
        return False
    owner = match.group("owner").strip().removesuffix("的")
    if owner in _CURRENT_OWNER_WORDS:
        return False
    if owner in _NON_OWNER_WORDS:
        return False
    if owner.startswith(("我朋友", "我的朋友", "我孩子", "我的孩子")):
        return True
    if re.search(_THIRD_PARTY_SUBJECT, owner):
        return True
    # A short Han name after an explicit ownership predicate is an owner, not
    # a health attribute.  Longer free text remains unresolved and therefore
    # does not receive this specialized classification.
    return 2 <= len(owner.removesuffix("的")) <= 4


def has_explicit_authorizing_update_request(value: str) -> bool:
    """Authorize only a direct current-user correction speech act.

    Mutation intent from the classifier is necessary but not sufficient: a
    quoted example, hypothetical, third-party instruction, or later ownership
    correction must not lend authority to an otherwise parseable value patch.
    """
    normalized = normalize_write_scope_text(value)
    normalized_statement = normalized.strip("。.!！?？")
    direct_water_update = any(
        pattern.fullmatch(normalized_statement) is not None
        for pattern in (_DIRECT_WATER_UPDATE_RE, _DIRECT_WATER_ID_UPDATE_RE)
    )
    if not _UPDATE_ACTION_RE.search(normalized):
        return False
    if _UPDATE_METALANGUAGE_PREFIX_RE.search(normalized):
        return False
    if _is_fully_parenthesized(normalized):
        return False
    if any(mark in normalized for pair in _QUOTE_PAIRS for mark in pair):
        return False
    if _UPDATE_HYPOTHETICAL_SUFFIX_RE.search(normalized):
        return False
    if _UPDATE_REVOCATION_RE.search(normalized):
        return False
    if (
        _DEFERRED_CONDITION_PREFIX_RE.search(normalized)
        or _THIRD_PARTY_UPDATE_ORDER_RE.search(normalized)
        or _THIRD_PARTY_UPDATE_BENEFICIARY_RE.search(normalized)
        or _THIRD_PARTY_WRITE_SUBJECT_RE.search(normalized)
        or (
            _segment_has_non_current_subject(normalized)
            and not direct_water_update
        )
        or (
            _HYPOTHETICAL_PREFIX_RE.search(normalized)
            and not _POLITE_CONDITIONAL_PREFIX_RE.search(normalized)
        )
        or is_reported_write_reference(normalized)
        or _has_untrusted_colon_command(normalized)
    ):
        return False
    clauses = split_write_clauses(normalized)
    if any(_is_post_attributed_to_non_current_owner(clause) for clause in clauses):
        return False
    if any(_TRAILING_REVOCATION_CLAUSE_RE.fullmatch(clause) for clause in clauses):
        return False
    if any(
        re.search(r"(?:不要|不用|无需|先别|暂不|勿|甭|禁止|拒绝|停止).{0,24}", clause)
        and _UPDATE_ACTION_RE.search(clause)
        for clause in clauses
    ):
        return False
    return bool(
        direct_water_update
        or _DIRECT_ILLNESS_UPDATE_RE.fullmatch(normalized_statement)
    )


def direct_remember_fact_values(value: str) -> dict[str, str] | None:
    """Compile a direct stable-profile fact from user-owned text."""
    normalized = normalize_write_scope_text(value).strip("，,。.!！；;：:?？")
    match = _DIRECT_REMEMBER_AVOID_RE.fullmatch(normalized)
    if match is None:
        match = _DIRECT_REMEMBER_AVOID_TRAILING_RE.fullmatch(normalized)
    if match is None:
        return None
    if any(marker in match.group("value") for marker in ("的是", "属于", "归于")):
        return None
    return {"predicate": "忌口", "object_value": match.group("value")}


def direct_event_values(value: str) -> dict[str, str] | None:
    """Compile subjectless/current-user lifecycle events from public examples."""
    normalized = normalize_write_scope_text(value).strip("，,。.!！；;：:?？")
    if match := _DIRECT_EVENT_ARRIVAL_RE.fullmatch(normalized):
        return {"title": f"到达{match.group('place')}"}
    if match := _DIRECT_EVENT_RECENT_ARRIVAL_RE.fullmatch(normalized):
        return {"title": f"到达{match.group('place')}"}
    if _DIRECT_EVENT_DEPARTURE_RE.fullmatch(normalized):
        return {"title": "航班起飞"}
    if match := _DIRECT_EVENT_EN_ROUTE_RE.fullmatch(normalized):
        return {"title": f"前往{match.group('place')}途中"}
    return None


def direct_supplement_group_values(value: str) -> dict[str, str] | None:
    """Compile the public batch-intake phrase without treating 药 as one drug."""
    normalized = normalize_write_scope_text(value)
    if not re.fullmatch(
        r"(?:我)?(?:早上|早晨|上午|中午|午间|晚上|晚间|睡前|临睡)的?"
        r"(?:补剂|药)(?:都|全|全部)(?:吃|服)(?:完)?(?:了)?"
        r"(?:[，,]?(?:(?:记录|打卡)(?:一下)?|(?:帮我)?记一下))?",
        normalized.strip("，,。.!！；;：:?？"),
    ):
        return None
    timing = next(
        (
            canonical
            for terms, canonical in (
                (("睡前", "临睡"), "bedtime"),
                (("晚上", "晚间"), "evening"),
                (("中午", "午间"), "noon"),
                (("早上", "早晨", "上午"), "morning"),
            )
            if any(term in normalized for term in terms)
        ),
        "",
    )
    return {"timing": timing} if timing else None


def corrected_water_update_value(value: str) -> float | None:
    """Return the user's final value after an explicit self-correction."""
    matches = tuple(
        _UPDATE_CORRECTION_VALUE_RE.finditer(normalize_write_scope_text(value))
    )
    if not matches:
        return None
    match = matches[-1]
    amount = float(match.group("value"))
    return amount * 1000 if (match.group("unit") or "").lower() in {"l", "升"} else amount


def has_water_update_correction(value: str) -> bool:
    """Return whether the user superseded an earlier proposed water value."""
    return _UPDATE_CORRECTION_MARKER_RE.search(
        normalize_write_scope_text(value)
    ) is not None


def _corrected_write_clause(previous: str, corrected_value: str) -> str:
    """Replace a superseded target while retaining only necessary type context."""
    action_context = _last_action_in_clause(previous)
    if action_context is None:
        return corrected_value
    action, _position = action_context
    value = corrected_value.strip("的了，,。.!！；;：: ")
    metric_prefix = next(
        (
            metric
            for metric in ("体重", "腰围", "血压", "高压", "低压")
            if metric in previous and metric not in value
        ),
        "",
    )
    return f"{action}{metric_prefix}{value}"


def _is_meal_slot_write_clause(clause: str) -> bool:
    action = _last_write_signal_in_clause(clause)
    if action is None:
        return False
    meal_positions = tuple(
        (clause.rfind(term), term)
        for term in _MEAL_SLOT_TERMS
        if term in clause
    )
    if not meal_positions:
        return False
    position, meal = max(meal_positions)
    trailing = clause[position + len(meal):].strip("的一餐饭 ")
    return trailing == ""


def _is_meal_food_write_clause(clause: str) -> bool:
    return (
        _last_write_signal_in_clause(clause) is not None
        and any(term in clause for term in _MEAL_SLOT_TERMS)
    )


def _is_safe_food_continuation(clause: str) -> bool:
    if not clause or len(clause) > 1000:
        return False
    if _last_write_signal_in_clause(clause) is not None:
        return False
    if any(term in clause for term in _MEAL_SLOT_TERMS):
        return False
    if any(signal in clause for signal in _NON_FOOD_CONTINUATION_SIGNALS):
        return False
    if _HYPOTHETICAL_PREFIX_RE.search(clause) or is_reported_write_reference(clause):
        return False
    return not has_negated_write_scope(clause)


def _is_safe_declarative_food_continuation(clause: str) -> bool:
    """Accept a food observation as detail of an explicit meal write.

    Chinese users naturally say ``记录早餐，吃了……``.  The completed-event
    wording must not authorize a write by itself, but it may fill the food
    selector of the immediately preceding explicit meal command.  Medication
    and supplement wording stays outside this narrow continuation grammar.
    """
    if not clause or len(clause) > 1000:
        return False
    if not _DECLARATIVE_FOOD_CONTINUATION_RE.fullmatch(clause):
        return False
    if any(term in clause for term in (*_MEAL_SLOT_TERMS, *_NON_FOOD_ENTITY_SIGNALS)):
        return False
    from app.services.drug_lexicon import contains_drug_name

    if contains_drug_name(clause):
        return False
    if any(signal in clause for signal in _NON_FOOD_CONTINUATION_SIGNALS):
        return False
    if _HYPOTHETICAL_PREFIX_RE.search(clause) or is_reported_write_reference(clause):
        return False
    return not has_negated_write_scope(clause)


def has_write_action_mention(value: str) -> bool:
    """Return whether user text mentions a registered health-write action."""
    text = normalize_write_scope_text(value)
    return any(action in text for action in _ORDERED_WRITE_ACTIONS)


def _strip_direct_request_prefix(clause: str) -> str:
    remainder = clause
    for vocative in _VOCATIVE_PREFIXES:
        if remainder.startswith(vocative):
            remainder = remainder[len(vocative):]
            break
    tokens = tuple(
        sorted(
            (
                token
                for token in (
                *_DIRECT_REQUEST_HELPERS,
                *_DIRECT_REQUEST_MODIFIERS,
                *WRITE_COMMAND_PREFIXES,
                )
                if token != "把"
            ),
            key=len,
            reverse=True,
        )
    )
    for _ in range(12):
        matched = next((token for token in tokens if remainder.startswith(token)), None)
        if matched is None:
            break
        remainder = remainder[len(matched):]
    return remainder


def _helper_owner_is_current_user(before_action: str) -> bool:
    """Validate the subject governing a trailing direct-request helper."""
    if _COMPOUND_DIRECT_REQUEST_PREFIX_RE.fullmatch(before_action):
        return True
    helpers = tuple(
        sorted((*_DIRECT_REQUEST_HELPERS, *WRITE_COMMAND_PREFIXES), key=len, reverse=True)
    )
    helper = next(
        (candidate for candidate in helpers if before_action.endswith(candidate)),
        None,
    )
    if helper is None:
        return False
    owner_context = before_action[:-len(helper)]
    if not owner_context:
        return True
    if _HEALTH_OBSERVATION_PREDICATE_RE.search(owner_context):
        return not _observation_has_non_current_subject(owner_context)
    return False


def has_explicit_authorizing_write_request(value: str) -> bool:
    """Require a positive, direct speech act before authorizing health writes.

    The classifier and final tool gate share this positive predicate. Mentions,
    questions, reported text, completed-state checks, and denied clauses are
    fail-closed instead of becoming authorized merely because no veto matched.
    """
    context = _last_write_action_context(value)
    if context is None:
        return False
    normalized = normalize_write_scope_text(value)
    contrast_segments = tuple(
        segment for segment in _CONTRAST_SCOPE_RE.split(normalized) if segment
    )
    governing_segment = contrast_segments[-1] if contrast_segments else context[0]
    if (
        _DEFERRED_CONDITION_PREFIX_RE.search(normalized)
        or _THIRD_PARTY_WRITE_SUBJECT_RE.search(normalized)
        or _has_untrusted_colon_command(normalized)
        or _segment_has_non_current_subject(governing_segment)
        or any(
            _is_post_attributed_to_non_current_owner(clause)
            for clause in split_write_clauses(governing_segment)
        )
        or (
            _HYPOTHETICAL_PREFIX_RE.search(normalized)
            and not _POLITE_CONDITIONAL_PREFIX_RE.search(normalized)
        )
    ):
        return False
    if has_negated_write_scope(value):
        return False
    if (
        is_write_capability_question(value)
        or is_historical_write_reference(value)
        or is_read_action_write_reference(value)
        or is_write_result_check(value)
        or is_reported_write_reference(value)
    ):
        return False
    if _is_explicit_dated_backfill(value):
        return True

    clause, action, start = context
    after_action = clause[start + len(action):]
    if action == "记录" and after_action.startswith(RECORD_NOUN_SUFFIXES):
        return False
    if _starts_with_completed_aspect(after_action):
        return False
    direct_clause = _strip_direct_request_prefix(clause)
    if direct_clause.startswith(action):
        return True
    if direct_clause.startswith(("把", "将")) and action in direct_clause:
        return action != "记录" or after_action.startswith(("下来", "到", "为"))
    before_action = clause[:start]
    return start == 0 or _helper_owner_is_current_user(before_action)
