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

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal


HEALTH_SEMANTICS_CONTRACT_VERSION = "health-semantics-v1"


@dataclass(frozen=True)
class HealthEntityResolution:
    """Closed resolution used by every health-read authorization route."""

    status: Literal[
        "exact",
        "not_applicable",
        "nonhealth",
        "nonself",
        "unresolved",
        "cancelled",
        "ambiguous",
    ]
    entity: str | None = None


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
        "帕金森",
        "新冠",
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
        "格林-巴利综合征",
        "吉兰-巴雷综合征",
        "埃勒斯-当洛斯综合征",
        "库欣综合征",
        "抗磷脂综合征",
        "rett综合征",
        "goodpasture综合征",
        "shwachman-diamond综合征",
        "brugada综合征",
        "lambert-eaton综合征",
        "韦格纳肉芽肿",
        "肠易激综合征",
        "缺铁性贫血",
        "幽门螺杆菌感染",
        "阵发性房颤",
        "重症肌无力",
        "多发性硬化症",
        "胶质母细胞瘤",
        "脑膜炎",
        "皮肌炎",
        "系统性硬化症",
        "黑色素瘤",
        "强直性脊柱炎",
        "心肌炎",
        "白血病",
        "神经炎",
        "骨髓炎",
        "干燥综合征",
        "代谢综合征",
        "溃疡性结肠炎",
        "类风湿关节炎",
        "桥本甲状腺炎",
        "特发性肺纤维化",
        "肌萎缩侧索硬化症",
        "扁桃体炎",
        "玫瑰糠疹",
        "耳石症",
        "白癜风",
    }
)

# A complete disease tail is strong evidence that an unknown preceding span is
# a separate subject. Generic morphology such as ``综合征`` is deliberately not
# included: eponyms are resolved by terminology, while clinical compounds use
# the compositional modifier grammar below.
OWNER_BOUNDARY_DISEASE_TAILS = tuple(
    sorted(
        {
            "covid-19肺炎",
            "iga肾病",
            "多发性硬化症",
            "胶质母细胞瘤",
            "系统性硬化症",
            "强直性脊柱炎",
            "幽门螺杆菌感染",
            "罕见神经炎",
            "脑膜炎",
            "皮肌炎",
            "黑色素瘤",
            "心肌炎",
            "白血病",
            "神经炎",
            "骨髓炎",
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
    r"hr(?![a-z0-9])|ceo(?![a-z0-9])|网友|前任)(?:的)?",
    re.IGNORECASE,
)

CLINICAL_MODIFIER_RE = re.compile(
    r"(?:急性|慢性|复发性|原发性|继发性|遗传性|特发性|罕见|重症|"
    r"阵发性|系统性|多发性|缺铁性|溶血性|抗磷脂|"
    r"运动性|运动诱发|睡眠相关|体重相关(?:性)?|妊娠|小儿|"
    r"新生儿|老年性|青少年|职业性|季节性|过敏性|病毒性|"
    r"细菌性|真菌性|免疫性|自身免疫性|代谢性|神经性|"
    r"缺血性|出血性|阻塞性|感染性|药物性|创伤性|"
    r"活动性|压力性|睡眠|饮食相关)$"
)

CLINICAL_MORPHEME_RE = re.compile(
    r"(?:脑|颅|心|肺|肝|胆|胰|肾|胃|肠|血|骨|骨髓|肌|神经|皮肤|"
    r"关节|脊柱|甲状腺|乳腺|子宫|卵巢|前列腺|幽门|螺杆菌|"
    r"扁桃体|耳石|玫瑰糠|"
    r"免疫|磷脂|胶质|黑色素|淋巴|代谢|饮食|呼吸|尿|蛋白|血管|"
    r"细胞|细菌|病毒|真菌|遗传|缺铁|溶血|阵发|纤维化|肉芽肿|"
    r"硬化|肌无力|萎缩|白血|脑膜|皮肌|心肌|骨髓)",
    re.IGNORECASE,
)

HEALTH_METRIC_ENTITY_RE = re.compile(
    r"^(?:ALT|AST|CRP|HRV|BMI|血糖|血压|心率|静息心率|呼吸率|"
    r"体重|体脂率|肌肉量|骨量|卡路里|最大摄氧量|血氧|体温)"
    r"(?:偏高|偏低|升高|降低|异常|障碍|疼痛|震颤)?$",
    re.IGNORECASE,
)

BODY_OR_TIME_OWNER_RE = re.compile(
    r"(?:今天|昨天|前天|近期|最近|过去.+|近.+|本周|上周|本月|"
    r"头|头部|颅脑|脑部|胸部|腹部|腰椎|颈椎|肩|左肩|右肩|"
    r"膝|左膝|右膝|膝盖|髋|手|脚|皮肤|口腔|鼻|眼|心脏)$"
)

_REFERENCE_NUMBER = r"(?:[0-9零〇一二两三四五六七八九十百千廿卅]+)"
_REFERENCE_OBJECT = (
    r"(?:病|疾病|病症|症状|记录|病历|病例|MRI|核磁|磁共振|CT|"
    r"检查|报告|影像|结果)"
)
GENERALIZED_INDEXED_HEALTH_REFERENCE_RE = re.compile(
    rf"(?:"
    rf"(?:第[^，,。.!！?？；;、]{{1,10}}(?:个|条|项|次|份|张|种))|"
    rf"(?:倒数|倒着|从后往前|往前|前面数来|后面数来|"
    rf"最上面|最下面|最前面|最后面|头一)"
    rf"[^，,。.!！?？；;、]{{0,12}}(?:个|条|项|次|份|张|种)?"
    rf")"
    rf"(?:新|旧)?(?:的)?{_REFERENCE_OBJECT}",
    re.IGNORECASE,
)
STRUCTURAL_HEALTH_REFERENCE_RE = re.compile(
    rf"(?:"
    rf"(?:它|它们|其)(?:的)?(?={_REFERENCE_OBJECT})|"
    rf"(?:这|那|此|该)(?:一)?(?:个|条|项|次|份|张|种)?{_REFERENCE_OBJECT}|"
    rf"(?:最后那个|前一个)(?:病|疾病|症状|记录)?|"
    rf"(?:上{{1,4}}一?|前{{1,4}}一?|最近一|最后一)(?:个|条|项|份|张)"
    rf"(?:修改|更新|删除|展示|提及|提到)?(?:过)?(?:的)?"
    rf"[^，,。.!！?？；;、]{{0,8}}{_REFERENCE_OBJECT}|"
    rf"(?:刚才|刚刚|之前|此前|先前|前面|上面)"
    rf"(?:修改|更新|删除|展示|提及|提到|说)?(?:过)?(?:的)?"
    rf"(?:这|那)?(?:个|条|项|份|张)?{_REFERENCE_OBJECT}|"
    rf"曾经(?:的)?(?:这|那)(?:一)?(?:个|条|项|次|份|张)?{_REFERENCE_OBJECT}"
    rf")",
    re.IGNORECASE,
)
UNRESOLVED_HEALTH_REFERENCE_RE = re.compile(
    rf"(?:"
    rf"(?:倒数)?第{_REFERENCE_NUMBER}|倒{_REFERENCE_NUMBER}|往前第{_REFERENCE_NUMBER}|"
    rf"上+一?|前+一?|最近一|最后一|最新(?:那)?|最末一?|末|"
    rf"末次(?:那)?|上次(?:那)?|上回(?:那)?|前次(?:那)?|前回(?:那)?|曾经(?:那)?|"
    rf"较早(?:那)?|刚提及的|先前提及的|本次|本份|该回|前序|后续|"
    rf"列表(?:顶部|底部)|排序(?:首位|末位)|历史第{_REFERENCE_NUMBER}|"
    rf"之前展示的|之前提及的|再前一|旧列表第{_REFERENCE_NUMBER}"
    rf")(?:的)?(?:个|条|项|次|份|张|种)?{_REFERENCE_OBJECT}"
    rf"(?:检查|报告|影像|结果)?",
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
    r"改查|找出|找一下|找|回顾(?:一下)?|回看(?:一下)?|检索(?:一下)?|列出|"
    r"比较|对比|翻查(?:一下)?|翻看(?:一下)?|翻一下|看看|看(?:一下|一看|一眼|下)?|"
    r"搜索(?:一下)?|搜(?:一下)?|调取|调出|调阅|打开|展示(?:一下)?|"
    r"拉出来|发我|发给我|呈现)",
    re.IGNORECASE,
)

HEALTH_ENTITY_CONNECTOR_RE = re.compile(
    r"(?:还有|以及|并且|加上|外加|兼有|连同|伴有|伴随|并伴|合并|联合|"
    r"同时有|同时出现|并发|并存|伴发|共存|共患|同患|再加|且|兼患|并患|"
    r"同时患有|相比|相对|对比|除以|占|比(?!(?:率|例|较))|是|"
    r"[vV][sS]|[、，,；;+/／|｜&＆和与及或跟—–])"
)

READ_CANCELLATION_RE = re.compile(
    r"(?:"
    r"(?:搁置|作废|取消|撤销|撤掉|停掉|停止|停下|(?<!呼吸)暂停|中止|中断|"
    r"终止|终结|放弃|算了|放一边)[^,.!，。！？?;；、]{0,32}"
    r"(?:查询|查找|查看|搜索|检索|翻查|翻看|调取|调出|调阅|打开|"
    r"展示|发我|发给我|查|搜|看|记录)|"
    r"(?:查询|查找|查看|搜索|检索|翻查|翻看|调取|调出|调阅|打开|"
    r"展示|发我|发给我|查|搜|看|记录)"
    r"[^,.!，。！？?;；、]{0,32}(?:作废|取消|撤销|停掉|停止|停下|"
    r"(?<!呼吸)暂停|中止|中断|终止|终结|算了|放一边|别再翻了)"
    r")",
    re.IGNORECASE,
)

_NEGATED_READ_PREFIX_PATTERN = (
    r"(?:(?:我)?(?:不要|别|不用|无需|不必|请勿|勿|甭|不想|不打算|"
    r"取消|不需要|不希望|停止|撤销|暂停|终止|放弃|"
    r"不(?=查询|查找|查看|查到|查下|查|找出|找一下|找|回顾|回看|检索|"
    r"列出|比较|对比|翻看|翻一下|看|搜索|搜|调取|调出)))"
)
_NEGATED_READ_INTERPOSER_PATTERN = (
    r"(?:(?:帮我|给我|替我|为我|麻烦你?|请你?|让你|你|再|去)){0,6}"
)
NEGATED_HEALTH_ACTION_RE = re.compile(
    rf"{_NEGATED_READ_PREFIX_PATTERN}{_NEGATED_READ_INTERPOSER_PATTERN}"
    rf"(?:记录|保存|新增|录入|写入|更新|修改|打卡|记一下|记下|"
    rf"{READ_VERB_RE.pattern})",
    re.IGNORECASE,
)


_EXAM_MODALITY_PATTERN = r"(?:MRI|核磁|磁共振|CT|X光|B超|胃镜)"
_EXAM_ANATOMY_PATTERN = (
    r"(?:(?:左|右|双侧)?(?:头|头颅|颅脑|脑|脑部|胸|胸部|腹|腹部|盆腔|"
    r"颈|颈椎|腰|腰椎|肩|膝|膝盖|膝关节|髋|肘|腕|踝|手|脚|眼|鼻|耳|"
    r"心|心脏|肺|肝|胆|胰|肾|胃|肠|脊柱))"
)
_EXAM_SEQUENCE_PATTERN = (
    r"(?:DWI|ADC|FLAIR|GRE|PD|FS|SWI|MRA|MRV|STIR|DTI|"
    r"T[12]\*?|[CLST]\d+(?:[-/](?:[CLST])?\d+)?|\d+(?:\.\d+)?T)"
)
EXACT_MEDICAL_EXAM_ENTITY_RE = re.compile(
    rf"^(?:(?:{_EXAM_MODALITY_PATTERN})|(?:{_EXAM_ANATOMY_PATTERN})|"
    rf"(?:{_EXAM_SEQUENCE_PATTERN})|[\s+./*\-])+$",
    re.IGNORECASE,
)
_READ_SCOPE_BOUNDARY_RE = re.compile(
    r"(?:[\n\r，,；;。.!！?？、]|但|不过|然而|而是|却|可是|然后|改为|改查)"
)


def normalize_entity(value: str) -> str:
    """Normalize for comparison without changing the user-visible spelling."""
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def active_health_read_clause(text: str) -> str:
    """Return the later positive read clause after the last read cancellation."""
    normalized = str(text or "").strip()
    cancellations = tuple(READ_CANCELLATION_RE.finditer(normalized)) + tuple(
        NEGATED_HEALTH_ACTION_RE.finditer(normalized)
    )
    if not cancellations:
        return normalized
    last_cancellation = max(cancellations, key=lambda match: match.end())
    suffix = normalized[last_cancellation.end() :]
    for positive in READ_VERB_RE.finditer(suffix):
        if _READ_SCOPE_BOUNDARY_RE.search(suffix[: positive.start()]):
            return suffix[positive.start() :].strip("，,。.!！；;：:?？ ")
    return ""


def health_read_cancelled(text: str) -> bool:
    """Identify a cancelled read unless a later clause starts a new read."""
    normalized = str(text or "")
    has_cancellation = bool(
        READ_CANCELLATION_RE.search(normalized)
        or NEGATED_HEALTH_ACTION_RE.search(normalized)
    )
    return has_cancellation and not active_health_read_clause(normalized)


def has_explicit_health_read_request(text: str) -> bool:
    """Return a positive active read act, excluding observation uses of 看."""
    scoped = active_health_read_clause(text)
    if not scoped:
        return False
    for match in READ_VERB_RE.finditer(scoped):
        if match.group() == "看" and re.match(
            r"(?:似|来|着|上去|起来|不(?:出|到|见|清)|得出)",
            scoped[match.end() :],
        ):
            continue
        return True
    return False


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
        GENERALIZED_INDEXED_HEALTH_REFERENCE_RE.search(normalized)
        or STRUCTURAL_HEALTH_REFERENCE_RE.search(normalized)
        or UNRESOLVED_HEALTH_REFERENCE_RE.fullmatch(scoped)
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


def _strip_current_user_owner(value: str) -> tuple[str, bool]:
    match = re.match(r"^(?:我自己(?:的)?|我(?:的)?|本人(?:的)?|自己(?:的)?)", value)
    if match is None:
        return value, False
    return value[match.end() :], True


def resolve_illness_entity(value: str) -> HealthEntityResolution:
    """Resolve one illness label without treating broad suffixes as authority."""
    candidate = "".join(normalize_entity(value).split()).strip(
        "的了，,。.!！；;：:?？ "
    )
    if not candidate:
        return HealthEntityResolution("ambiguous")
    if is_unresolved_health_reference(candidate):
        return HealthEntityResolution("unresolved")
    candidate, _explicit_self = _strip_current_user_owner(candidate)
    if not 2 <= len(candidate) <= 80:
        return HealthEntityResolution("ambiguous")
    if _known_illness(candidate):
        return HealthEntityResolution("exact", candidate)
    if HEALTH_METRIC_ENTITY_RE.fullmatch(candidate) or _nonhealth_root(candidate):
        return HealthEntityResolution("nonhealth")
    if re.match(r"^(?:他|她|他们|她们|其)(?:的)?.+", candidate):
        return HealthEntityResolution("nonself")
    if THIRD_PARTY_ROLE_RE.match(candidate):
        return HealthEntityResolution("nonself")
    possessive = re.fullmatch(r"(?P<owner>.+?)的(?P<entity>.+)", candidate)
    if possessive is not None:
        owner = possessive.group("owner")
        entity_resolution = resolve_illness_entity(possessive.group("entity"))
        if owner not in CURRENT_USER_OWNERS and entity_resolution.status == "exact":
            return HealthEntityResolution("nonself")
        return entity_resolution
    folded = candidate.casefold()
    for suffix in OWNER_BOUNDARY_DISEASE_TAILS:
        if not folded.endswith(suffix.casefold()) or len(candidate) <= len(suffix):
            continue
        prefix = candidate[: len(candidate) - len(suffix)].strip("-· ")
        if not prefix:
            continue
        if CLINICAL_MODIFIER_RE.fullmatch(prefix):
            return HealthEntityResolution("exact", candidate)
        return HealthEntityResolution("nonself")
    if re.fullmatch(r"[A-Z][A-Z0-9-]{1,15}", candidate):
        return HealthEntityResolution("nonhealth")
    if not MEDICAL_MORPHOLOGY_RE.search(candidate):
        return HealthEntityResolution("nonhealth")
    if CLINICAL_MORPHEME_RE.search(candidate):
        return HealthEntityResolution("exact", candidate)
    return HealthEntityResolution("ambiguous")


def illness_entity_has_medical_semantics(value: str) -> bool:
    """Return health meaning backed by the terminology/morphology contract."""
    return resolve_illness_entity(value).status == "exact"


def illness_target_is_unowned_or_referential(value: str) -> bool:
    """Fail closed unless one durable current-user illness entity is exact."""
    return resolve_illness_entity(value).status != "exact"


def _strip_exam_request_scaffolding(value: str) -> str:
    candidate = value.strip("，,。.!！；;：:?？ ")
    prefix_re = re.compile(
        r"^(?:然后|但|不过|而是|方便的话|请问|请您|烦请|劳烦|劳驾|"
        r"拜托|请|麻烦你?|能不能|可不可以|能否|可否|我想(?:在)?|"
        r"想(?:在)?|给我|帮我|帮忙|替我|为我|把)"
    )
    while candidate:
        reduced = prefix_re.sub("", candidate, count=1).lstrip()
        reduced = re.sub(
            rf"^(?:{READ_VERB_RE.pattern})",
            "",
            reduced,
            count=1,
            flags=re.IGNORECASE,
        ).lstrip()
        if reduced == candidate:
            break
        candidate = reduced
    return candidate


def resolve_medical_exam_query(text: str) -> HealthEntityResolution:
    """Resolve an exact current-user imaging/exam keyword from one active read."""
    scoped = active_health_read_clause(text)
    if not scoped:
        return HealthEntityResolution("cancelled")
    if re.search(_EXAM_MODALITY_PATTERN, scoped, re.IGNORECASE) is None:
        return HealthEntityResolution("not_applicable")
    if is_unresolved_health_reference(scoped):
        return HealthEntityResolution("unresolved")
    candidate = _strip_exam_request_scaffolding(scoped)
    if re.search(
        r"(?:检查报告|检查结果|影像报告|影像结果|扫描报告|扫描结果)记录$",
        candidate,
        re.IGNORECASE,
    ):
        return HealthEntityResolution("ambiguous")
    candidate = re.sub(
        r"^(?:最近|近|过去|前)(?:[0-9一二三四五六七八九十半]+)"
        r"(?:天|周|个月|月|年)(?:内|里|中|的)?",
        "",
        candidate,
    )
    candidate = re.sub(r"(?:记录|历史)$", "", candidate)
    candidate = re.sub(
        r"^(?:最近|近期|刚刚|刚才)?(?:上传|导入|生成|保存)的",
        "",
        candidate,
    )
    candidate, _explicit_self = _strip_current_user_owner(candidate)
    candidate = re.sub(
        r"(?:拉出来|发给我|发我|给我看看|给我看|找出来|查出来|"
        r"列出来|调出来|打开|调出|调阅|展示(?:一下)?|看看)$",
        "",
        candidate,
    ).strip()
    exam_suffix_re = re.compile(
        r"(?:检查报告|检查结果|影像结果|扫描结果|影像报告|"
        r"检查|报告|影像|结果|扫描|图像|成像|片子|片)$",
        re.IGNORECASE,
    )
    previous = None
    while candidate and candidate != previous:
        previous = candidate
        candidate = exam_suffix_re.sub("", candidate).strip()
    if not candidate or len(candidate) > 80:
        return HealthEntityResolution("ambiguous")
    if re.search(_EXAM_MODALITY_PATTERN, candidate, re.IGNORECASE) is None:
        return HealthEntityResolution("ambiguous")
    if EXACT_MEDICAL_EXAM_ENTITY_RE.fullmatch(candidate) is None:
        exam_parts = tuple(
            part.strip()
            for part in HEALTH_ENTITY_CONNECTOR_RE.split(candidate)
            if part.strip()
        )
        if len(exam_parts) > 1 and all(
            EXACT_MEDICAL_EXAM_ENTITY_RE.fullmatch(part) is not None
            for part in exam_parts
        ):
            return HealthEntityResolution("ambiguous")
        return HealthEntityResolution("nonself")
    return HealthEntityResolution("exact", candidate)


def _health_read_entity_expression(text: str) -> str:
    scoped = active_health_read_clause(text)
    if not scoped:
        return ""
    candidate = _strip_exam_request_scaffolding(scoped)
    candidate = re.sub(
        r"(?:最近|近|过去|前)(?:[0-9一二两三四五六七八九十半]+)"
        r"(?:个)?(?:天|周|月|年)(?:内|里|中|的)?",
        "",
        candidate,
    )
    candidate = _strip_exam_request_scaffolding(candidate)
    candidate = re.sub(
        r"^(?:上一次|最近一次|最后一次)(?:的)?",
        "",
        candidate,
    )
    candidate = re.sub(
        r"(?:的)?(?:记录|病史|病历|病例|历史).*$", "", candidate, count=1
    )
    candidate = re.sub(
        r"(?:是什么时候|在什么时候|什么时候|何时|在何时|是哪天|哪天|"
        r"日期|时间|分别有哪些|有哪些|怎么样|怎样|如何)$",
        "",
        candidate,
    )
    return candidate.strip("的，,。.!！；;：:?？ ")


def health_read_has_nonself_subject(text: str) -> bool:
    """Detect explicit or concatenated non-current-user health subjects."""
    exam = resolve_medical_exam_query(text)
    if exam.status == "nonself":
        return True
    entity = _health_read_entity_expression(text)
    if not entity:
        return False
    entity, _explicit_self = _strip_current_user_owner(entity)
    entity = re.sub(r"^(?:在|关于|有关)", "", entity)
    entity = _strip_exam_request_scaffolding(entity)
    entity = re.sub(
        r"^(?:(?:上一次|最近一次|最后一次)(?:的)?|最近|近来)",
        "",
        entity,
    )
    parts = HEALTH_ENTITY_CONNECTOR_RE.split(entity)
    return any(
        resolve_illness_entity(part).status == "nonself"
        for part in parts
        if part.strip()
    )


def health_semantics_contract_payload() -> dict[str, str]:
    """Return versioned static evidence included in the capability digest."""
    content = {
        "illness_entities": sorted(CANONICAL_ILLNESS_ENTITIES),
        "owner_boundary_tails": list(OWNER_BOUNDARY_DISEASE_TAILS),
        "medical_morphology": MEDICAL_MORPHOLOGY_RE.pattern,
        "clinical_morphemes": CLINICAL_MORPHEME_RE.pattern,
        "clinical_modifiers": CLINICAL_MODIFIER_RE.pattern,
        "non_health_roots": sorted(NON_HEALTH_ROOTS),
        "health_metrics": HEALTH_METRIC_ENTITY_RE.pattern,
        "read_verbs": READ_VERB_RE.pattern,
        "read_cancellation": READ_CANCELLATION_RE.pattern,
        "negated_health_action": NEGATED_HEALTH_ACTION_RE.pattern,
        "entity_connectors": HEALTH_ENTITY_CONNECTOR_RE.pattern,
        "generalized_reference": GENERALIZED_INDEXED_HEALTH_REFERENCE_RE.pattern,
        "structural_reference": STRUCTURAL_HEALTH_REFERENCE_RE.pattern,
        "discourse_reference": DISCOURSE_HEALTH_REFERENCE_RE.pattern,
        "exam_entity": EXACT_MEDICAL_EXAM_ENTITY_RE.pattern,
    }
    encoded = json.dumps(
        content,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "version": HEALTH_SEMANTICS_CONTRACT_VERSION,
        "content_digest": hashlib.sha256(encoded).hexdigest(),
    }
