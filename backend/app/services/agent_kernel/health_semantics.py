"""Closed semantic evidence for user-owned health entities.

This module deliberately separates three questions that used to be conflated
in routing regexes:

* does the text name a health entity;
* is that entity owned by the current user; and
* is it a durable entity or only a pointer into prior discourse.

The result is used only to narrow tool authority.  Unknown or ambiguous input
never becomes permission to read or write health data.
"""

from __future__ import annotations

import re
import unicodedata


CURRENT_USER_OWNERS = frozenset({"我", "我的", "本人", "本人的", "自己", "自己的"})

# This is an authorization vocabulary, not a diagnostic ontology.  It contains
# entities supported by the illness-record product contract plus ambiguous
# eponyms whose surface form cannot safely be distinguished from a person's
# name by morphology alone.  New product entities belong here (or in a future
# versioned terminology service), never in scattered routing regexes.
CANONICAL_ILLNESS_ENTITIES = frozenset(
    {
        "sle",
        "感冒",
        "流感",
        "甲流",
        "copd",
        "发烧",
        "口腔溃疡",
        "复发性口腔溃疡",
        "舌尖溃疡",
        "嘴唇起泡",
        "湿疹",
        "麦粒肿",
        "甲沟炎",
        "带状疱疹",
        "烫伤",
        "水泡",
        "伤口",
        "痘痘发作",
        "脑梗",
        "脑梗死",
        "偏头痛",
        "偏头疼",
        "慢性疼痛",
        "高血压",
        "低血压",
        "妊娠高血压",
        "哮喘",
        "运动性哮喘",
        "糖尿病",
        "1型糖尿病",
        "2型糖尿病",
        "痛风",
        "房颤",
        "癫痫",
        "帕金森病",
        "克罗恩病",
        "肺癌",
        "乳腺癌",
        "甲亢",
        "甲减",
        "红斑狼疮",
        "iga肾病",
        "b型肝炎",
        "β地中海贫血",
        "her2阳性乳腺癌",
        "covid-19肺炎",
        "h1n1流感",
        "hiv感染",
        "睡眠呼吸暂停",
        "睡眠呼吸暂停综合征",
        "能量代谢异常",
        "压力性尿失禁",
        "运动障碍",
        "体重相关性闭经",
        "运动诱发过敏",
        "睡眠相关磨牙",
        "体重相关脂肪肝",
        "运动性血尿",
        "behçet病",
        "马凡综合征",
        "马方综合征",
        "白塞病",
        "阿尔茨海默病",
        "小儿麻痹症",
        "张力性气胸",
        "高原病",
        "高山病",
        "胡桃夹综合征",
        "何杰金淋巴瘤",
        "何杰金病",
        "李斯特菌病",
        "马拉色菌毛囊炎",
        "小细胞肺癌",
        "雷诺病",
        "范可尼贫血",
        "史蒂文斯-约翰逊综合征",
        "夏科-马里-图斯病",
        "李-佛美尼综合征",
        "杜氏肌营养不良症",
        "林奇综合征",
        "高胱氨酸尿症",
        "贾第虫病",
        "阿狄森病",
        "孟乔森综合征",
        "肺结核",
        "活动性肺结核",
        "钱币状湿疹",
        "毛细血管炎",
    }
)

# A standalone disease suffix is strong evidence that a preceding span is a
# separate subject/modifier.  Whole known diseases are checked before this
# split, preserving eponyms and clinically meaningful compounds.
STANDALONE_ILLNESS_SUFFIXES = tuple(
    sorted(
        {
            "covid-19肺炎",
            "iga肾病",
            "肺结核",
            "1型糖尿病",
            "2型糖尿病",
            "帕金森病",
            "克罗恩病",
            "红斑狼疮",
            "偏头痛",
            "高血压",
            "低血压",
            "糖尿病",
            "乳腺癌",
            "脂肪肝",
            "子宫内膜异位症",
            "哮喘",
            "感冒",
            "流感",
            "脑梗",
            "肺癌",
            "痛风",
            "房颤",
            "癫痫",
            "湿疹",
            "甲亢",
            "甲减",
            "肝炎",
            "贫血",
            "感染",
            "疼痛",
            "震颤",
            "闭经",
            "过敏",
            "瘫痪",
            "晕厥",
            "血尿",
            "便秘",
            "磨牙",
            "气胸",
            "结石",
            "息肉",
            "出血",
            "结核",
            "卒中",
            "新冠",
            "白癜风",
            "溃疡",
            "综合征",
        },
        key=len,
        reverse=True,
    )
)

MEDICAL_MORPHOLOGY_RE = re.compile(
    r"(?:病|病症|症|综合征|炎|癌|瘤|淋巴瘤|疹|感染|溃疡|感冒|流感|"
    r"疱疹|烫伤|水泡|伤口|脑梗|梗死|栓塞|偏头痛|疼痛|高血压|"
    r"低血压|哮喘|障碍|闭经|过敏|贫血|呼吸暂停|瘫痪|晕厥|"
    r"脂肪肝|血尿|便秘|失禁|异常|头疼|痛风|甲亢|甲减|房颤|癫痫|"
    r"磨牙|气胸|结石|息肉|出血|结核|卒中|新冠|帕金森(?:病)?|"
    r"红斑狼疮|白癜风|震颤)$",
    re.IGNORECASE,
)

NON_ILLNESS_ENTITIES = frozenset(
    {
        "alt",
        "ast",
        "crp",
        "cpu",
        "nasa",
        "http-500",
        "order",
        "invoice",
        "server",
        "cache",
        "email",
        "movie",
        "flight",
        "stock",
        "hotel",
        "weather",
        "report",
        "camera",
        "photo",
        "map",
        "code",
        "血糖",
        "体脂率",
        "肌肉量",
        "骨量",
        "呼吸率",
        "最大摄氧量",
        "卡路里",
    }
)

NON_HEALTH_ROOTS = frozenset(
    {
        "服务器",
        "代码",
        "订单",
        "股票",
        "电影",
        "工资",
        "网络",
        "电池",
        "会议",
        "发票",
        "天气",
        "停车",
        "相册",
        "邮件",
        "新闻",
        "地图",
        "歌词",
        "菜谱",
        "课程",
        "作业",
        "航班",
        "酒店",
        "账单",
        "快递",
        "优惠券",
        "联系人",
        "购物车",
        "书单",
        "日程",
        "汇率",
        "票据",
        "文档",
        "接口",
        "缓存",
        "键盘",
        "鼠标",
        "编译器",
        "数据库",
        "容器",
        "进程",
        "电脑",
        "支付",
        "飞机",
        "火车",
        "汽车",
    }
)

THIRD_PARTY_ROLE_RE = re.compile(
    r"^(?:我(?:的)?)?(?:家人|亲戚|朋友|同事|同学|室友|舍友|邻居|"
    r"父母|爸爸|妈妈|父亲|母亲|爷爷|奶奶|外公|外婆|祖父|祖母|"
    r"岳父|岳母|岳丈|公公|婆婆|叔叔|堂叔|婶婶|舅舅|舅妈|姑姑|姑父|"
    r"堂兄|堂弟|堂姐|堂妹|表哥|表弟|表姐|表妹|兄弟|姐妹|"
    r"哥哥|姐姐|弟弟|妹妹|妻子|丈夫|老公|老婆|爱人|伴侣|孩子|"
    r"儿子|女儿|患者|病人|老板|导师|老师|班主任|助教|教练|队友|"
    r"队长|裁判|客户|秘书|司机|快递员|房东|租客|保姆|阿姨|"
    r"医生|护士|值班护士|主治医生|物业经理|前台|厨师|合伙人|"
    r"hr|ceo|网友|前任)(?:的)?",
    re.IGNORECASE,
)

CLINICAL_MODIFIER_RE = re.compile(
    r"(?:急性|慢性|复发性|原发性|继发性|遗传性|特发性|"
    r"运动性|运动诱发|睡眠相关|体重相关(?:性)?|妊娠|小儿|"
    r"新生儿|老年性|青少年|职业性|季节性|过敏性|病毒性|"
    r"细菌性|真菌性|免疫性|自身免疫性|代谢性|神经性|"
    r"缺血性|出血性|阻塞性|感染性|药物性|创伤性|"
    r"活动性|压力性|睡眠|饮食相关)$"
)

BODY_OR_TIME_OWNER_RE = re.compile(
    r"(?:今天|昨天|前天|近期|最近|过去.+|近.+|本周|上周|本月|"
    r"头|头部|颅脑|脑部|胸部|腹部|腰椎|颈椎|肩|左肩|右肩|"
    r"膝|左膝|右膝|膝盖|髋|手|脚|皮肤|口腔|鼻|眼|心脏)$"
)

_REFERENCE_NUMBER = r"(?:[0-9零〇一二两三四五六七八九十百千廿卅]+)"
UNRESOLVED_HEALTH_REFERENCE_RE = re.compile(
    rf"(?:"
    rf"(?:倒数)?第{_REFERENCE_NUMBER}|倒{_REFERENCE_NUMBER}|往前第{_REFERENCE_NUMBER}|"
    rf"上+一?|前+一?|最近一|最后一|最新(?:那)?|最末一?|末|"
    rf"末次(?:那)?|上次(?:那)?|上回(?:那)?|前次(?:那)?|前回(?:那)?|曾经(?:那)?|"
    rf"较早(?:那)?|刚提及的|先前提及的|本次|本份|该回|前序|后续|"
    rf"列表(?:顶部|底部)|排序(?:首位|末位)|历史第{_REFERENCE_NUMBER}|"
    rf"之前展示的|之前提及的|再前一|旧列表第{_REFERENCE_NUMBER}"
    rf")(?:的)?(?:个|条|项|次|份|张|种)?(?:"
    rf"病|疾病|病症|症状|记录|病历|病例|MRI|核磁|磁共振|CT|"
    rf"检查|报告|影像|结果"
    rf")(?:检查|报告|影像|结果)?",
    re.IGNORECASE,
)

DISCOURSE_HEALTH_REFERENCE_RE = re.compile(
    r"(?:它|它们|其|前者|后者|这些|那些|前述|上述|"
    r"之前|此前|先前|前面|上面|刚才|刚刚|方才)(?:说的|提的|提到的|展示的)?"
    r"(?:这|那|此|该)?(?:一)?(?:个|条|项|次|份|张|种)?(?:"
    r"病|疾病|病症|症状|记录|病历|病例|MRI|核磁|磁共振|CT|"
    r"检查|报告|影像|结果)",
    re.IGNORECASE,
)

BARE_DEICTIC_REFERENCE_RE = re.compile(
    r"^(?:"
    r"(?:这|那|此|该)(?:一)?(?:个|些|条|项|次|份|张|种)?"
    r"(?:病|疾病|病症|症状|记录|病历|病例)?|"
    r"(?:刚才|刚刚|之前|此前|先前|前面|上面)(?:说的|提的|提到的)?"
    r"(?:这|那)?(?:一)?(?:个|条|项|次|份|张|种)?"
    r"(?:病|疾病|病症|症状|记录|病历|病例)?|"
    r"(?:上一|前一|最后一)(?:个|条|项|次|份|张|种)?"
    r"(?:病|疾病|病症|症状|记录|病历|病例)?|"
    r"最后那个|前一个疾病|该条记录|它|它们|前者|后者"
    r")$",
    re.IGNORECASE,
)

READ_VERB_RE = re.compile(
    r"(?:查询(?:一下)?|查找(?:一下)?|查看(?:一下)?|查到|查下|查(?:一下|一查)?|"
    r"改查|找出|找一下|回顾(?:一下)?|回看(?:一下)?|检索(?:一下)?|列出|"
    r"比较|对比|翻查(?:一下)?|翻看(?:一下)?|翻一下|看(?:一下|一看|一眼|下)?|"
    r"搜索(?:一下)?|搜(?:一下)?|调取|调出|调阅|打开|展示(?:一下)?|"
    r"拉出来|发我|发给我|呈现)",
    re.IGNORECASE,
)

READ_CANCELLATION_RE = re.compile(
    r"(?:"
    r"(?:搁置|作废|取消|撤销|撤掉|停掉|停止|停下|(?<!呼吸)暂停|中止|中断|"
    r"终止|终结|放弃|算了|放一边)[^,.!，。！？?;；、]{0,32}"
    r"(?:查询|查找|查看|搜索|检索|翻查|翻看|查|搜|看|记录)|"
    r"(?:查询|查找|查看|搜索|检索|翻查|翻看|查|搜|看|记录)"
    r"[^,.!，。！？?;；、]{0,32}(?:作废|取消|撤销|停掉|停止|停下|"
    r"(?<!呼吸)暂停|中止|中断|终止|终结|算了|放一边|别再翻了)"
    r")",
    re.IGNORECASE,
)


def normalize_entity(value: str) -> str:
    """Normalize for comparison without changing the user-visible spelling."""
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def is_unresolved_health_reference(value: str) -> bool:
    normalized = "".join(normalize_entity(value).split()).strip(
        "的了，,。.!！；;：:?？ "
    )
    scoped = re.sub(
        r"^(?:请|麻烦你?|帮我|给我|替我|为我|把)*",
        "",
        normalized,
    )
    scoped = READ_VERB_RE.sub("", scoped, count=1).strip("的，,。.!！；;：:?？ ")
    return bool(
        UNRESOLVED_HEALTH_REFERENCE_RE.fullmatch(scoped)
        or DISCOURSE_HEALTH_REFERENCE_RE.search(normalized)
        or BARE_DEICTIC_REFERENCE_RE.fullmatch(normalized)
    )


def _known_illness(value: str) -> bool:
    return normalize_entity(value).casefold() in CANONICAL_ILLNESS_ENTITIES


def _nonhealth_root(value: str) -> bool:
    normalized = normalize_entity(value).casefold()
    return normalized in NON_ILLNESS_ENTITIES or any(
        normalized.startswith(root.casefold()) for root in NON_HEALTH_ROOTS
    )


def illness_entity_has_medical_semantics(value: str) -> bool:
    """Return health meaning backed by the terminology/morphology contract."""
    normalized = normalize_entity(value).strip("的，,。.!！；;：:?？ ")
    if not 2 <= len(normalized) <= 80:
        return False
    if _known_illness(normalized):
        return True
    if normalized.casefold() in NON_ILLNESS_ENTITIES or _nonhealth_root(normalized):
        return False
    if re.fullmatch(r"[A-Z][A-Z0-9-]{1,15}", normalized):
        return False
    if is_unresolved_health_reference(normalized):
        return False
    if re.match(r"^(?:他|她|他们|她们|其)(?:的)?.+", normalized):
        return False
    if THIRD_PARTY_ROLE_RE.match(normalized):
        return False
    possessive = re.fullmatch(r"(?P<owner>.+?)的(?P<entity>.+)", normalized)
    if possessive is not None and possessive.group("owner") not in CURRENT_USER_OWNERS:
        return False
    return bool(MEDICAL_MORPHOLOGY_RE.search(normalized))


def illness_target_is_unowned_or_referential(value: str) -> bool:
    """Fail closed for third-party, non-health or discourse-only targets."""
    candidate = normalize_entity(value).strip("的了，,。.!！；;：:?？ ")
    if not candidate or is_unresolved_health_reference(candidate):
        return True
    if _known_illness(candidate):
        return False
    if _nonhealth_root(candidate):
        return True
    if re.match(r"^(?:他|她|他们|她们|其)(?:的)?.+", candidate):
        return True
    if THIRD_PARTY_ROLE_RE.match(candidate):
        return True
    possessive = re.fullmatch(r"(?P<owner>.+?)的(?P<entity>.+)", candidate)
    if possessive is not None and possessive.group("owner") not in CURRENT_USER_OWNERS:
        return True
    folded = candidate.casefold()
    for suffix in STANDALONE_ILLNESS_SUFFIXES:
        if not folded.endswith(suffix.casefold()) or len(candidate) <= len(suffix):
            continue
        prefix = candidate[: len(candidate) - len(suffix)].strip("-· ")
        if not prefix:
            continue
        if CLINICAL_MODIFIER_RE.fullmatch(prefix):
            return False
        return True
    return False


def health_read_has_nonself_subject(text: str) -> bool:
    """Detect an explicit non-current-user subject for any health read domain."""
    normalized = "".join(normalize_entity(text).split()).strip("，,。.!！；;：:?？ ")
    read_match = READ_VERB_RE.search(normalized)
    body = normalized[read_match.end() :] if read_match is not None else normalized
    body = re.sub(r"(?:的)?(?:记录|病史|病历|病例|历史).*$", "", body, count=1)
    if not body:
        return False
    possessives = tuple(re.finditer(r"(?P<owner>[^,.!，。！？?;；、]{1,40}?)的", body))
    for possessive in possessives:
        owner = re.sub(
            r"^(?:把|请|请帮我|帮我|给我|替我|为我)",
            "",
            possessive.group("owner"),
        )
        remainder = body[possessive.end() :]
        if not re.search(
            r"(?:MRI|核磁|磁共振|CT|X光|B超|检查|报告|影像|"
            r"病|症|炎|癌|瘤|疹|感冒|哮喘|痛风|房颤|癫痫|"
            r"高血压|偏头痛|脑梗|湿疹|贫血|疼痛)",
            remainder,
            re.IGNORECASE,
        ):
            continue
        if (
            owner in CURRENT_USER_OWNERS
            or BODY_OR_TIME_OWNER_RE.fullmatch(owner)
            or re.fullmatch(r"(?:最近|近期|刚刚|刚才)?(?:上传|导入|生成|保存)", owner)
        ):
            continue
        return True
    return False


def health_read_cancelled(text: str) -> bool:
    """Identify a cancelled read unless a later clause starts a new read."""
    normalized = normalize_entity(text)
    matches = tuple(READ_CANCELLATION_RE.finditer(normalized))
    if not matches:
        return False
    last = matches[-1]
    suffix = normalized[last.end() :]
    for positive in READ_VERB_RE.finditer(suffix):
        if re.search(
            r"(?:，|,|；|;|。|!|！|\?|？|但|不过|而是|改查|然后)",
            suffix[: positive.start()],
        ):
            return False
    return True
