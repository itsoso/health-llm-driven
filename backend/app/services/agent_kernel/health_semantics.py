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
import inspect
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal


HEALTH_SEMANTICS_CONTRACT_VERSION = "health-semantics-v7"


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


@dataclass(frozen=True)
class HealthReadActResolution:
    """Resolved state of the user's read speech act."""

    status: Literal["active", "cancelled", "none"]
    active_clause: str = ""


CURRENT_USER_OWNERS = frozenset(
    {"我", "我的", "我自己", "我自己的", "本人", "本人的", "自己", "自己的"}
)

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
        "结节性多动脉炎",
        "遗传性血管性水肿",
        "阵发性睡眠性血红蛋白尿",
        "成人斯蒂尔病",
        "原发性醛固酮增多症",
        "克雅氏病",
        "特发性血小板减少性紫癜",
        "贝赫切特病",
        "法布雷病",
        "戈谢病",
        "庞贝病",
        "威尔逊病",
        "美尼尔病",
        "still病",
        "nmo谱系病",
        "cadasil病",
        "原发性胆汁性胆管炎",
        "桥本氏甲状腺炎",
        "运动神经元病",
        "饮食失调症",
        # Eponyms cannot be authorized from morphology alone. They live in the
        # versioned terminology set while compositional entities use the
        # biomedical grammar below.
        "亨廷顿病",
        "脊髓小脑性共济失调",
        "显微镜下多血管炎",
        "免疫球蛋白a肾病",
        "igg4相关性疾病",
        "hla-b27相关脊柱关节炎",
        "bcr::abl1阳性白血病",
        "β2微球蛋白淀粉样变性",
        "mog抗体相关疾病",
        "eb病毒感染",
        "sjögren综合征",
        "guillain-barré综合征",
        "α1抗胰蛋白酶缺乏症",
        "c3肾小球病",
        "pla2r相关膜性肾病",
        "抗mda5阳性皮肌炎",
        "抗lgi1抗体脑炎",
        "抗nmda受体脑炎",
        "抗磷脂酶a2受体阳性膜性肾病",
        "ntrk融合阳性实体瘤",
        "mpl-w515l阳性骨髓增殖性肿瘤",
        "hla-dq2.5相关乳糜泻",
        "anti-mda5阳性皮肌炎",
        "gfap-igg阳性星形胶质细胞病",
        "syngap1相关神经发育障碍",
        "piga相关阵发性睡眠性血红蛋白尿",
        "c9orf72相关额颞叶痴呆",
        "pr3-anca阳性肉芽肿性多血管炎",
        "a20单倍剂量不足综合征",
        "ada2缺乏症",
        "nlrp3相关自身炎症性疾病",
        "pax6相关无虹膜症",
        "lam-tsc2相关肺淋巴管肌瘤病",
        "wt1相关肾病综合征",
        "mog-igg相关皮质脑炎",
        "抗gad65自身免疫性脑炎",
        "lamp2抗体相关坏死性肾小球肾炎",
        "m.3243a>g相关melas综合征",
        "alk融合阳性肺癌",
        "egfr-l858r阳性肺腺癌",
        "ros1融合阳性肺癌",
        "ret融合阳性甲状腺癌",
        "jak2-v617f阳性真性红细胞增多症",
        "calr外显子9突变骨髓增殖性肿瘤",
        "fgfr3融合阳性膀胱癌",
        "idh1-r132h阳性胶质瘤",
        "h3k27m弥漫性中线胶质瘤",
        "npm1突变急性髓系白血病",
        "flt3-itd阳性急性髓系白血病",
        "brca1相关遗传性乳腺癌",
        "lmna相关扩张型心肌病",
        "scn5a相关brugada综合征",
        "tsc1相关结节性硬化症",
        "htt-cag重复扩增亨廷顿病",
        "smn1相关脊髓性肌萎缩症",
        "atp7b相关威尔逊病",
        "pkd1相关常染色体显性多囊肾病",
        "anti-gbm抗体病",
        "aqp4-igg阳性视神经脊髓炎谱系病",
        "nmosd",
        "duchenne型肌营养不良",
        "myh7相关肥厚型心肌病",
        "kcnq1相关长qt综合征",
        "ryr1相关恶性高热易感症",
        "abcd1相关x连锁肾上腺脑白质营养不良",
        "col4a5相关alport综合征",
        "vhl相关肿瘤综合征",
        "men2a型多发性内分泌腺瘤病",
        "apol1相关肾病",
        "braf-v600e阳性黑色素瘤",
        "fbn1相关马凡综合征",
        "gba1相关帕金森病",
        "hla-b51相关behçet病",
    }
)

ILLNESS_ENTITY_ALIASES = {
    "β-地中海贫血": "β地中海贫血",
    "her2+乳腺癌": "her2阳性乳腺癌",
    "bcr:abl1阳性白血病": "bcr::abl1阳性白血病",
}

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
        }
        | {entity for entity in CANONICAL_ILLNESS_ENTITIES if len(entity) >= 3},
        key=lambda value: (-len(value), value),
    )
)

MEDICAL_MORPHOLOGY_RE = re.compile(
    r"(?:病|病症|症|综合征|炎|癌|瘤|淋巴瘤|疹|感染|溃疡|感冒|流感|"
    r"疱疹|烫伤|水泡|伤口|脑梗|梗死|栓塞|偏头痛|疼痛|高血压|"
    r"低血压|哮喘|障碍|闭经|过敏|贫血|呼吸暂停|瘫痪|晕厥|"
    r"脂肪肝|血尿|便秘|失禁|头疼|痛风|甲亢|甲减|房颤|癫痫|"
    r"磨牙|气胸|结石|息肉|出血|结核|卒中|新冠|帕金森(?:病)?|"
    r"红斑狼疮|白癜风|震颤|麻痹|变性|萎缩|失调|扩张症)$",
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
    r"阵发性|系统性|多发性|结节性|减少性|增多性|缺铁性|溶血性|抗磷脂|"
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
    r"硬化|肌无力|萎缩|白血|脑膜|皮肌|心肌|骨髓|免疫球蛋白|"
    r"中枢神经|炎症|脱髓鞘|毛细血管|共济|显微镜下|受体|微球蛋白|"
    r"淀粉样|脊髓|小脑|胆管)",
    re.IGNORECASE,
)

BIOMEDICAL_MODIFIER_RE = re.compile(
    r"(?:(?:抗[A-Z][A-Z0-9]*受体)|"
    r"(?:[A-Z][A-Z0-9]*(?:(?:-|::|:|\+)[A-Z0-9]+)+)|"
    r"(?:[A-Z]+\d+)|IgG\d*|IgA|β\d*|相关性?|阳性|受体|微球蛋白|"
    r"淀粉样|显微镜下)+"
)

# Open-vocabulary disease authorization is deliberately compositional and
# closed over medical tokens. A clinical-looking suffix alone is insufficient:
# every character before the suffix must be explained by a medical modifier or
# body token. This keeps ``遗传算法炎`` and arbitrary-owner prefixes closed while
# permitting well-formed new compounds without an ever-growing sentence regex.
OPEN_ILLNESS_ENTITY_RE = re.compile(
    r"^(?:(?:急性|慢性|复发性|原发性|继发性|遗传性|特发性|重症|阵发性|"
    r"系统性|多发性|结节性|减少性|增多性|血管性|睡眠性|免疫性|"
    r"自身免疫性|代谢性|神经性|缺血性|出血性|阻塞性|感染性|"
    r"药物性|创伤性|活动性|压力性|病毒性|细菌性|真菌性|过敏性|"
    r"进行性|硬化性|肉芽肿性|嗜酸性|粒细胞性|多|"
    r"妊娠|小儿|新生儿|青少年|成人|老年性|职业性|季节性|"
    r"炎症性|脱髓鞘性|出血性|毛细血管|相关性|阳性|显微镜下))*"
    r"(?:(?:脑|颅|心|肺|肝|胆|胆汁|胆管|胰|肾|胃|肠|血|血管|动脉|"
    r"主动脉|多血管|静脉|血小板|血红|红蛋白|骨|骨髓|肌|神经|"
    r"视神经|脊髓|核上性|核上|结节|肉芽肿|粒细胞|多系统|淀粉样|皮肤|关节|脊柱|"
    r"甲状腺|乳腺|子宫|卵巢|前列腺|幽门|螺杆菌|扁桃体|耳石|"
    r"免疫|磷脂|胶质|黑色素|淋巴|呼吸|尿|蛋白|细胞|细菌|病毒|"
    r"真菌|醛固酮|纤维|肉芽|肌无力|萎缩|白血|脑膜|皮肌|心肌|"
    r"免疫球蛋白A?|中枢神经系统|炎症|脱髓鞘|毛细血管|共济|"
    r"显微镜下|受体|微球蛋白|淀粉样|脊髓|小脑|多血管))+"
    r"(?:病|病症|综合征|炎|癌|瘤|淋巴瘤|感染|紫癜|水肿|蛋白尿|"
    r"贫血|纤维化|硬化症|增多症|减少症|失禁|闭经|血尿|"
    r"麻痹|变性|萎缩|失调|扩张症|疾病)$",
)

HEALTH_METRIC_ENTITY_RE = re.compile(
    r"^(?:ALT|AST|CRP|HRV|BMI|血糖|血压|心率|静息心率|呼吸率|"
    r"体重|体脂率|肌肉量|骨量|卡路里|最大摄氧量|血氧|体温|"
    r"尿蛋白|血小板|红蛋白|淋巴细胞|血管|胆汁|心肌细胞|免疫细胞)"
    r"(?:偏高|偏低|升高|降低|异常|障碍|疼痛|震颤)?$",
    re.IGNORECASE,
)

HEALTH_RECORD_DOMAIN_ENTITY_RE = re.compile(
    r"^(?:饮食|餐食|饮水|喝水|体重|腰围|血压|睡眠|心情|情绪|排便|"
    r"运动|锻炼|症状|用药|药物|服药|补剂|营养补充剂|提醒|健康目标|"
    r"体检|体检报告|检查|医学检查|检查报告|化验|化验报告|检验|检验报告|"
    r"报告|病症|疾病|病史|病历)$",
    re.IGNORECASE,
)

BODY_OR_TIME_OWNER_RE = re.compile(
    r"(?:今天|昨天|前天|近期|最近|过去.+|近.+|本周|上周|本月|"
    r"头|头部|颅脑|脑部|胸部|腹部|腰椎|颈椎|肩|左肩|右肩|"
    r"膝|左膝|右膝|膝盖|髋|手|脚|皮肤|口腔|鼻|眼|心脏)$"
)

HEALTH_READ_SCOPE_OWNER_RE = re.compile(
    r"(?:今天|昨日|昨天|前天|近期|最近(?:[0-9一二两三四五六七八九十半]+)?"
    r"(?:个)?(?:小时|天|周|月|年)?|过去.+|近.+|本周|上周|本月|"
    r"今早|晨起|早上|上午|中午|午后|下午|晚上|夜间|运动后|锻炼后|导入|"
    r"服药后|早餐后|午餐后|晚餐后|餐后|睡前|起床后|醒来后)"
    r"(?:测|测量|上传|导入|生成)?$|(?:刚测|刚刚测|刚测量|刚刚测量)$"
)

HEALTH_READ_LEADING_SCOPE_RE = re.compile(
    r"^(?:今早|晨起|早上|上午|中午|午后|下午|晚上|夜间|运动后|锻炼后|"
    r"服药后|早餐后|午餐后|晚餐后|餐后|睡前|起床后|醒来后|"
    r"刚测|刚刚测|刚测量|刚刚测量)"
    r"(?:测|测量)?(?:的)?"
)


def _is_current_user_scope_owner(owner: str) -> bool:
    """Recognize an explicit self owner followed only by a read scope."""
    normalized = str(owner or "").strip()
    self_prefixes = tuple(
        sorted(
            CURRENT_USER_OWNERS | {"我个人", "我本人"},
            key=len,
            reverse=True,
        )
    )
    for prefix in self_prefixes:
        if normalized == prefix:
            return True
        if not normalized.startswith(prefix):
            continue
        remainder = normalized[len(prefix) :].lstrip("的")
        if remainder and HEALTH_READ_SCOPE_OWNER_RE.fullmatch(remainder):
            return True
    return False

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
    r"[vV][sS]|(?<![A-Za-z0-9])\+|\+(?![\u4e00-\u9fff])|"
    r"[、，,；;/／|｜&＆和与及或跟]|"
    r"(?<=[\u4e00-\u9fff])[—–](?=[\u4e00-\u9fff]))"
)

READ_CANCELLATION_RE = re.compile(
    r"(?:"
    r"(?:搁置|搁一搁|作废|作罢|取消|撤销|撤掉|撤回|撤了|叫停|打住|暂缓|停掉|停止|停下|(?<!呼吸)暂停|中止|中断|"
    r"终止|终结|放弃|算了|放一边)[^,.!，。！？?;；、]{0,32}"
    r"(?:查询|查找|查看|搜索|检索|翻查|翻看|调取|调出|调阅|打开|"
    r"展示|发我|发给我|查|搜|看|记录)|"
    r"(?:查询|查找|查看|搜索|检索|翻查|翻看|调取|调出|调阅|打开|"
    r"展示|发我|发给我|查|搜|看|记录)"
    r"[^,.!，。！？?;；、]{0,32}[\s，,]*(?:作废|作罢|取消|撤销|撤回|撤了(?:吧)?|叫停|打住|暂缓|停掉|停止|停下|"
    r"(?<!呼吸)暂停|中止|中断|终止|终结|算了|放一边|到此为止|"
    r"这事先搁一搁|先搁一搁|到这儿|到这(?:里|儿)|别再(?:翻|调|查|看|打开)了)|"
    r"(?:别再|不再)[^,.!，。！？?;；、]{0,12}"
    r"(?:查询|查找|查看|搜索|检索|翻查|翻看|调取|调出|调阅|打开|调|查|看)(?:了)?"
    r")",
    re.IGNORECASE,
)

READ_TRAILING_WITHDRAWAL_RE = re.compile(
    r"(?:先别继续(?:查|看|查询|查看)?了|暂且作罢|先缓一缓|先停一停|"
    r"暂时别继续|先不要继续|到这儿(?:吧)?|先放一放|先搁着|先等等|"
    r"暂时不用|回头再说|晚点再说|稍后再说|不要执行|别执行|不执行|"
    r"改天再说|过(?:两|几)?天再说|等会儿再说|待会儿再说|到时候再说|"
    r"以后再说|晚些时候再说|有空再说|"
    r"打住|叫停|作罢|算了|停止|停下|中止|终止)"
    r"[，,。.!！?？\s]*$",
    re.IGNORECASE,
)
READ_DEFERRED_ACTION_RE = re.compile(
    rf"(?:明天|稍后|晚点|以后|之后|改天|回头|待会儿|等(?:我)?.{{0,12}}后)"
    rf"(?:再)?[^,.!，。！？?;；、]{{0,12}}(?:{READ_VERB_RE.pattern})",
    re.IGNORECASE,
)
READ_NON_AUTHORIZING_RE = re.compile(
    r"(?:"
    r"(?:(?:已经|已|早就|刚)(?:查询|查找|查看|搜索|检索|翻看|调取|打开|查|看)?"
    r"(?:完成|结束|做完|查完|搞定)(?:了)?|"
    r"(?:查询|查找|查看|搜索|检索|翻看|调取|打开|查|看)"
    r"[^,.!，。！？?;；、]{0,64}(?:查完|完成|结束|做完|搞定)(?:了)?$)|"
    r"(?:记录|病史|病历|报告|结果)[^,.!，。！？?;；、]{0,12}"
    r"(?:查完|完成|结束|做完|搞定)(?:了)?$|"
    r"这(?:件事|次查询|次查看)(?:已经|已|早就|刚)?(?:完成|结束|做完|搞定)(?:了)?|"
    r"(?:这)?(?:只是|仅是|不过是|只是为了|仅供|仅用于|仅作|纯属|是|作为)"
    r"(?:一个|一句|个|为了|举个)?(?:示例|例子|举例|演示|测试|测试用例|反例|假设|教程|文档里的命令)|"
    r"仅供参考|"
    r"(?:记录|病史|病历)(?![^,.!，。！？?;；、]{0,20}(?:(?:这些|上述|这项|"
    r"本次|这批)?(?:指标|数值|读数|结果|化验结果|检查结果|检验结果|"
    r"检测结果|数值结果|测量值|检测值|数据)|报告数值))"
    r"[^,.!，。！？?;；、]{0,12}(?:意味着什么|是什么意思|是啥意思|什么意思)$|"
    r"(?:(?:看看|请问|想知道|想问|我想了解|告诉我|说说|请解释|"
    r"解释(?:一下|下)?|帮我解释)"
    r"[^,.!，。！？?;；、]{0,4}"
    r"(?:这句(?:话)?|这段话|这番话|(?:(?:这个|这条|该|此|上述|前述|当前))?"
    r"(?:指令|命令|请求|查询|操作|语句|问题)|"
    r"(?:这次|本次)(?:查询|请求|操作))|"
    r"^(?:这句(?:话)?|这段话|这番话|(?:(?:这个|这条|该|此|上述|前述|当前))?"
    r"(?:指令|命令|请求|操作|语句|问题)|"
    r"(?:这次|本次)(?:查询|请求|操作)|"
    r"查询(?![^,.!，。！？?;；、]{0,30}(?:(?:这些|上述|这项|本次|这批)?"
    r"(?:指标|数值|读数|结果|化验结果|检查结果|检验结果|检测结果|"
    r"数值结果|测量值|检测值|数据)|报告数值))))"
    r"[^,.!，。！？?;；、]{0,20}"
    r"(?:意味|意思|含义|代表|表达|理解|解释|指|说什么|怎么回事|"
    r"干嘛|做什么|作用|用途|怎么用|使用|怎么执行|执行|格式|语法|解读)"
    r"[^,.!，。！？?;；、]{0,6}$|"
    r"(?:请解释|解释(?:一下|下)?|帮我解释)[^,.!，。！？?;；、]{0,4}"
    r"(?:这句(?:话)?|这段话|这番话|(?:(?:这个|这条|该|此|上述))?"
    r"(?:指令|命令|请求|查询|操作|语句|问题))$|"
    r"(?:记录|病史|病历)[^,.!，。！？?;；、]{0,12}会不会成功$|"
    r"(?:这句(?:话)?|这个指令|该指令)(?:来自|出自)|"
    r"(?:查询|查找|搜索|检索|调取|打开|查)"
    r"[^,.!，。！？?;；、]{0,64}(?:的话)?(?:可能)?(?:会|能)"
    r"(?:不会)?(?:发生什么|怎样|怎么样|如何|返回(?:什么|哪些数据)|"
    r"得到什么(?:结果)?|会不会成功|有(?:什么)?(?:结果|影响)?)|"
    r"(?:查询|查找|搜索|检索|调取|打开|查)"
    r"[^,.!，。！？?;；、]{0,64}是否安全"
    r")",
    re.IGNORECASE,
)
READ_AUTHORITY_WITHDRAWAL_RE = re.compile(
    r"(?:"
    r"我(?:没(?:有)?|未|并未|不)(?:明确)?(?:让(?:你)?|授权|同意|允许|批准)|"
    r"(?:没有|未|并未)(?:明确)?授权|"
    r"^(?:不允许|不同意|未同意|没有批准|不授权)$|"
    r"未经(?:我)?(?:明确)?(?:授权|同意|允许|批准)|"
    r"(?:我)?拒绝|"
    r"(?:不用|无需|不必)(?:了|查|查询|查看|执行)?|"
    r"(?:不要|别|不)(?:真的|实际|正式|继续)?(?:查|查询|查看|执行)|"
    r"不代表(?:要|需要|应该)?(?:查|查询|查看|执行)|"
    r"不是(?:要|让你)(?:真的|实际|正式)?(?:查|查询|查看|执行)|"
    r"^(?:不是|并不是|否|no|先不要|不用(?:了)?|不必(?:了)?|没必要|没有这个意思)$"
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
    r"(?:(?:帮我|给我|替我|为我|麻烦你?|请你?|让你|你|再|去|继续)){0,6}"
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
    r"(?:[\n\r，,；;。!！?？、]|(?<!\d)\.(?!\d)|"
    r"但|不过|然而|而是|却|可是|然后|改为)"
)
READ_ACT_LEADING_SCAFFOLD_RE = re.compile(
    r"(?:(?:请(?:你|您)?|麻烦(?:你|您)?|现在|马上|立即|先|再|仅|只|"
    r"还是|接着|真正)\s*)*",
    re.IGNORECASE,
)


def normalize_entity(value: str) -> str:
    """Normalize for comparison without changing the user-visible spelling."""
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip()
    return normalized.translate(str.maketrans("‐‑‒–—−", "------"))


def normalize_health_authorization_text(value: str) -> str:
    """Normalize equivalent biomedical punctuation before policy parsing."""
    normalized = normalize_entity(value)
    return re.sub(r"(?<=[A-Z]):(?=[A-Z])", "::", normalized)


def _illness_lookup_key(value: str) -> str:
    normalized = normalize_entity(value).casefold()
    return ILLNESS_ENTITY_ALIASES.get(normalized, normalized)


def resolve_health_read_act(text: str) -> HealthReadActResolution:
    """Resolve read authority clause by clause, with later clauses winning."""
    normalized = str(text or "").strip()
    if not normalized:
        return HealthReadActResolution("none")

    clause_spans: list[tuple[int, int]] = []
    cursor = 0
    for boundary in _READ_SCOPE_BOUNDARY_RE.finditer(normalized):
        if normalized[cursor : boundary.start()].strip("，,。.!！；;：:?？ "):
            clause_spans.append((cursor, boundary.start()))
        cursor = boundary.end()
    if normalized[cursor:].strip("，,。.!！；;：:?？ "):
        clause_spans.append((cursor, len(normalized)))

    status = "none"
    active_start: int | None = None
    authority_was_reset = False
    saw_read = False
    for clause_start, clause_end in clause_spans:
        clause = normalized[clause_start:clause_end].strip("，,。.!！；;：:?？ ")
        read_match = next(iter(READ_VERB_RE.finditer(clause)), None)
        has_read = read_match is not None and has_positive_health_read_verb(clause)
        saw_read = saw_read or has_read
        cancelled = bool(
            READ_CANCELLATION_RE.search(clause)
            or NEGATED_HEALTH_ACTION_RE.search(clause)
            or READ_TRAILING_WITHDRAWAL_RE.search(clause)
            or READ_AUTHORITY_WITHDRAWAL_RE.search(clause)
            or (
                clause in {"不", "不要", "别"}
                and saw_read
                and status == "active"
            )
        )
        non_authorizing = READ_NON_AUTHORIZING_RE.search(clause) is not None
        deferred = READ_DEFERRED_ACTION_RE.search(clause) is not None

        if has_read:
            if cancelled:
                status = "cancelled"
                active_start = None
                authority_was_reset = True
            elif non_authorizing:
                status = "none"
                active_start = None
                authority_was_reset = True
            elif deferred:
                if status != "cancelled":
                    status = "none"
                active_start = None
                authority_was_reset = True
            else:
                if status != "active":
                    # Preserve leading time/object scope for the first active
                    # read. After a cancellation/completion/deferment, begin at
                    # the later clause that explicitly restarts authority. A
                    # pure discourse prefix ("现在再查") is not part of the
                    # entity scope; object-before-verb text ("把 MRI 发我") is.
                    if authority_was_reset and READ_ACT_LEADING_SCAFFOLD_RE.fullmatch(
                        clause[: read_match.start()]
                    ):
                        active_start = clause_start + read_match.start()
                    else:
                        active_start = clause_start if authority_was_reset else 0
                status = "active"
            continue

        if cancelled:
            status = "cancelled"
            active_start = None
            authority_was_reset = True
        elif non_authorizing or READ_TRAILING_WITHDRAWAL_RE.search(clause):
            status = "none"
            active_start = None
            authority_was_reset = True

    if status == "none" and not saw_read:
        return HealthReadActResolution("none", normalized)
    active_clause = (
        normalized[active_start:].strip("，,。.!！；;：:?？ ")
        if status == "active" and active_start is not None
        else ""
    )
    return HealthReadActResolution(status, active_clause)


def is_clinical_result_interpretation(text: str) -> bool:
    """Return whether a read asks to interpret the returned clinical data."""
    normalized = str(text or "")
    ownership_scope = re.split(
        r"(?:，|,)?看看(?:(?:这些|上述|这项|本次|这批)?(?:指标|数值|读数|"
        r"结果|化验结果|检查结果|检验结果|检测结果|数值结果|测量值|"
        r"检测值|数据)|报告数值)",
        normalized,
        maxsplit=1,
    )[0]
    return bool(
        has_positive_health_read_verb(normalized)
        and not health_read_has_nonself_subject(ownership_scope)
        and not re.search(
            r"(?:上一条|下一条|前一条|后一条|这条|那条|某条|上述那条|前述那条)"
            r"(?:化验|检验|检查|体检|报告|记录|结果)",
            normalized,
        )
        and re.search(r"(?:化验|检验|检查|体检|报告|结果)", normalized)
        and re.search(
            r"(?:(?:这些|上述|这项|本次|这批)?(?:指标|数值|读数|结果|"
            r"化验结果|检查结果|检验结果|检测结果|数值结果|测量值|"
            r"检测值|数据)|报告数值)"
            r"[^,.!，。！？?;；、]{0,20}"
            r"(?:意味|意思|含义|代表|表达|理解|解释|指|说什么|怎么回事|"
            r"干嘛|做什么|作用|用途)",
            normalized,
        )
    )


def has_positive_health_read_verb(text: str) -> bool:
    """Return whether text contains a non-observational read verb."""
    for match in READ_VERB_RE.finditer(str(text or "")):
        if match.group() == "看" and re.match(
            r"(?:似|来|着|上去|起来|不(?:出|到|见|清)|得出)",
            str(text or "")[match.end() :],
        ):
            continue
        return True
    return False


def active_health_read_clause(text: str) -> str:
    """Return the active clause from the structured read-act resolution."""
    return resolve_health_read_act(text).active_clause


def health_read_cancelled(text: str) -> bool:
    """Identify a cancelled read unless a later clause starts a new read."""
    return resolve_health_read_act(text).status == "cancelled"


def has_explicit_health_read_request(text: str) -> bool:
    """Return a positive active read act, excluding observation uses of 看."""
    scoped = active_health_read_clause(text)
    if not scoped:
        return False
    return has_positive_health_read_verb(scoped)


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
        re.search(
            r"(?:(?:上|下|前|后|最后|倒数)(?:一|两|二|三|四|五)?次|"
            r"(?:第|倒数第?)[0-9一二两三四五六七八九十]+条|"
            r"(?:上|下|前|后|最近|最后|倒数)(?:一|两|二|三|四|五)?条)"
            r"(?:化验|检验|检查|体检|报告|记录|结果)",
            normalized,
        )
        or GENERALIZED_INDEXED_HEALTH_REFERENCE_RE.search(normalized)
        or STRUCTURAL_HEALTH_REFERENCE_RE.search(normalized)
        or UNRESOLVED_HEALTH_REFERENCE_RE.fullmatch(scoped)
        or DISCOURSE_HEALTH_REFERENCE_RE.search(normalized)
        or BARE_DEICTIC_REFERENCE_RE.fullmatch(normalized)
    )


def _known_illness(value: str) -> bool:
    return _illness_lookup_key(value) in CANONICAL_ILLNESS_ENTITIES


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
    folded = _illness_lookup_key(candidate)
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
    if OPEN_ILLNESS_ENTITY_RE.fullmatch(candidate):
        return HealthEntityResolution("exact", candidate)
    return HealthEntityResolution("nonhealth")


_ILLNESS_MUTATION_LEADING_SCAFFOLD_RE = re.compile(
    r"^(?:请(?:你|您)?|麻烦(?:你|您)?|小巴|你能|可不可以|能不能|可以|能|"
    r"帮我|给我|替我|把|将|我想|"
    r"更新|修改|更正|修正|调整|删除|删掉|移除|清除|清掉|"
    r"记录一下|记一下|记录|记下|新增|录入|保存|写入|存下来|"
    r"已经痊愈的|已痊愈的|已经康复的|已康复的|"
    r"今天|今日|昨天|昨日|前天|近期|最近|目前|现在|"
    r"以前的|既往|上一次|上次)+"
)
_ILLNESS_MUTATION_SUFFIX_RE = re.compile(
    r"^(?:的)?(?:疾病)?(?:吗|了|记录|条目|病历|病例|状态|ID|编号|#|第|今天|"
    r"昨日|昨天|前天|今早|今晚|目前|现在|近期|最近|上次|上一次|之前|在|于|"
    r"起病|开始|发作|日期|时间|严重|程度|分|级|备注|症状|持续|已经|已|还|仍|"
    r"完全|明显|逐渐|没有|没|未|好|好了|好转|改善|康复|痊愈|"
    r"发作|复发|加重|更新|修改|更正|修正|调整|删除|删掉|移除|"
    r"[0-9（()）=：:，,。.!！；;、\s]).*$",
    re.IGNORECASE,
)


def extract_owned_illness_entity(text: str) -> str | None:
    """Extract the leading current-user disease from a mutation statement.

    Disease recognition is delegated to ``resolve_illness_entity``; this
    function only removes command scaffolding and validates that the remaining
    suffix is state/record syntax rather than an arbitrary concatenated owner.
    """
    candidate = "".join(normalize_entity(text).split()).strip("的了，,。.!！；;：:?？ ")
    previous = None
    while candidate and candidate != previous:
        previous = candidate
        candidate = _ILLNESS_MUTATION_LEADING_SCAFFOLD_RE.sub("", candidate, count=1)
        candidate, _ = _strip_current_user_owner(candidate)
    for end in range(len(candidate), 1, -1):
        entity = candidate[:end].strip("的，,。.!！；;：:?？ ")
        suffix = candidate[end:]
        resolution = resolve_illness_entity(entity)
        if resolution.status != "exact" or not resolution.entity:
            continue
        if not suffix or _ILLNESS_MUTATION_SUFFIX_RE.fullmatch(suffix):
            return resolution.entity
    return None


def illness_entity_has_medical_semantics(value: str) -> bool:
    """Return health meaning backed by the terminology/morphology contract."""
    return resolve_illness_entity(value).status == "exact"


def illness_target_is_unowned_or_referential(value: str) -> bool:
    """Fail closed unless one durable current-user illness entity is exact."""
    return resolve_illness_entity(value).status != "exact"


def _strip_exam_request_scaffolding(value: str) -> str:
    candidate = value.strip("，,。.!！；;：:?？ ")
    prefix_re = re.compile(
        r"^(?:然后|但|不过|而是|方便的话|请问|请您|烦请|劳烦|有劳|劳驾|"
        r"拜托|请|麻烦你?|能不能|可不可以|能否|可否|我想(?:在)?|"
        r"想(?:在)?|能(?=给我|帮我|帮忙|替我|为我|查询|查找|查看|找出|"
        r"翻看|调取|调出|查|看)|给我|帮我|帮忙|替我|为我|把|仅|只|再)"
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
        r"^(?:上一次|最近一次|最后一次|最近那次|最后一回|最近一回|"
        r"上回|上次|末次)(?:的)?",
        "",
        candidate,
    )
    candidate = re.sub(
        r"(?:的)?(?:记录|病史|病历|病例|历史).*$", "", candidate, count=1
    )
    candidate = re.sub(
        r"(?:是什么时候|在什么时候|什么时候|何时|在何时|是哪一天|是哪天|"
        r"是几号|哪天|日期|时间|分别有哪些|有哪些|怎么样|怎样|如何|呢)$",
        "",
        candidate,
    )
    return candidate.strip("的，,。.!！；;：:?？ ")


def health_read_has_nonself_subject(text: str) -> bool:
    """Detect explicit or concatenated non-current-user health subjects."""
    subject_scope = re.sub(
        r"(?:，|,)?看看(?:(?:这些|上述|这项|本次|这批)?(?:指标|数值|读数|"
        r"结果|化验结果|检查结果|检验结果|检测结果|数值结果|测量值|"
        r"检测值|数据)|报告数值)[^,.!，。！？?;；、]{0,32}$",
        "",
        str(text or ""),
    )
    read_act = resolve_health_read_act(subject_scope)
    scoped_text = (
        read_act.active_clause if read_act.status == "active" else subject_scope
    )
    exam = resolve_medical_exam_query(scoped_text)
    if exam.status == "nonself":
        return True
    entity = _health_read_entity_expression(scoped_text)
    if not entity:
        return False
    possessive = re.fullmatch(r"(?P<owner>.+?)的(?P<target>.+)", entity)
    if possessive is not None:
        owner = possessive.group("owner").strip()
        target = possessive.group("target").strip()
        target_without_scope = HEALTH_READ_LEADING_SCOPE_RE.sub("", target, count=1)
        target_resolution = resolve_illness_entity(target_without_scope)
        target_is_health = bool(
            target_resolution.status == "exact"
            or HEALTH_METRIC_ENTITY_RE.fullmatch(target_without_scope)
            or HEALTH_RECORD_DOMAIN_ENTITY_RE.fullmatch(target_without_scope)
            or EXACT_MEDICAL_EXAM_ENTITY_RE.fullmatch(target_without_scope)
        )
        owner_is_scope = bool(
            BODY_OR_TIME_OWNER_RE.fullmatch(owner)
            or HEALTH_READ_SCOPE_OWNER_RE.fullmatch(owner)
        )
        owner_is_current_user_scope = _is_current_user_scope_owner(owner)
        if (
            owner not in CURRENT_USER_OWNERS
            and not owner_is_current_user_scope
            and not owner_is_scope
            and target_is_health
        ):
            return True
        if target_is_health and (owner_is_scope or owner_is_current_user_scope):
            return False
    entity, explicit_self = _strip_current_user_owner(entity)
    entity = re.sub(r"^(?:在|关于|有关)", "", entity)
    entity = _strip_exam_request_scaffolding(entity)
    entity = re.sub(
        r"^(?:(?:上一次|最近一次|最后一次)(?:的)?|最近|近来)",
        "",
        entity,
    )
    if not explicit_self and resolve_illness_entity(entity).status != "exact":
        generic_targets = tuple(
            sorted(
                {
                    "血压",
                    "体重",
                    "睡眠",
                    "用药",
                    "饮水",
                    "运动",
                    "体检",
                    "体检报告",
                    "检查",
                    "检查报告",
                    "化验报告",
                    "检验报告",
                    "报告",
                },
                key=len,
                reverse=True,
            )
        )
        for target in generic_targets:
            if not entity.endswith(target) or len(entity) <= len(target):
                continue
            owner = entity[: -len(target)].strip("的-· ")
            if owner and not (
                BODY_OR_TIME_OWNER_RE.fullmatch(owner)
                or HEALTH_READ_SCOPE_OWNER_RE.fullmatch(owner)
            ) and not re.search(
                r"(?:MRI|核磁|磁共振|CT|X光|B超|胃镜|HRV|头|肩|膝|腰|颈|胸|腹|和|与|及)",
                owner,
                re.IGNORECASE,
            ):
                return True
    parts = HEALTH_ENTITY_CONNECTOR_RE.split(entity)
    return any(
        resolve_illness_entity(part).status == "nonself"
        for part in parts
        if part.strip()
    )


_UNSUPPORTED_CONTRACT_VALUE = object()


def _encode_contract_value(value: object) -> object:
    """Encode content-free grammar constants for deterministic drift evidence."""
    if isinstance(value, re.Pattern):
        return {"pattern": value.pattern, "flags": value.flags}
    if isinstance(value, dict):
        encoded_items: dict[str, object] = {}
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            encoded = _encode_contract_value(item)
            if encoded is _UNSUPPORTED_CONTRACT_VALUE:
                return _UNSUPPORTED_CONTRACT_VALUE
            encoded_items[str(key)] = encoded
        return encoded_items
    if isinstance(value, (set, frozenset)):
        encoded_items = [_encode_contract_value(item) for item in value]
        if any(item is _UNSUPPORTED_CONTRACT_VALUE for item in encoded_items):
            return _UNSUPPORTED_CONTRACT_VALUE
        return sorted(encoded_items, key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, (tuple, list)):
        encoded_items = [_encode_contract_value(item) for item in value]
        if any(item is _UNSUPPORTED_CONTRACT_VALUE for item in encoded_items):
            return _UNSUPPORTED_CONTRACT_VALUE
        return encoded_items
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return _UNSUPPORTED_CONTRACT_VALUE


def authorization_grammar_digest(namespace: dict[str, object]) -> str:
    """Digest every module-level grammar constant, including nested regexes."""
    grammar: dict[str, object] = {}
    for name, value in sorted(namespace.items()):
        if not name.lstrip("_").isupper():
            continue
        encoded = _encode_contract_value(value)
        if encoded is not _UNSUPPORTED_CONTRACT_VALUE:
            grammar[name] = encoded
    payload = json.dumps(
        grammar,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def authorization_behavior_digest(
    namespace: dict[str, object],
    function_names: tuple[str, ...],
) -> str:
    """Fingerprint authorization source without CPython quickening state."""
    behavior: dict[str, object] = {}

    def encode_runtime_value(candidate: object) -> object:
        encoded_candidate = _encode_contract_value(candidate)
        if encoded_candidate is _UNSUPPORTED_CONTRACT_VALUE:
            return f"{type(candidate).__module__}.{type(candidate).__qualname__}"
        return encoded_candidate

    for name in sorted(function_names):
        value = namespace.get(name)
        code = getattr(value, "__code__", None)
        if code is not None:
            try:
                source = inspect.getsource(value)
            except (OSError, TypeError):
                source = ""
            behavior[name] = {
                "module": getattr(value, "__module__", ""),
                "qualname": getattr(value, "__qualname__", ""),
                "source": source,
                "fallback_code": "" if source else code.co_code.hex(),
                "fallback_consts": (
                    None if source else encode_runtime_value(code.co_consts)
                ),
                "defaults": encode_runtime_value(getattr(value, "__defaults__", None)),
                "kwdefaults": encode_runtime_value(
                    getattr(value, "__kwdefaults__", None)
                ),
            }
        else:
            behavior[name] = {
                "module": getattr(value, "__module__", ""),
                "qualname": getattr(value, "__qualname__", ""),
                "type": f"{type(value).__module__}.{type(value).__qualname__}",
                "source": inspect.getsource(value) if inspect.isfunction(value) else "",
            }
    payload = json.dumps(
        behavior,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def authorization_module_behavior_names(
    namespace: dict[str, object],
    module_name: str,
) -> tuple[str, ...]:
    """Return every function defined by one authorization module."""
    return tuple(
        sorted(
            name
            for name, value in namespace.items()
            if inspect.isfunction(value)
            and getattr(value, "__module__", "") == module_name
        )
    )


def authorization_imported_behavior_names(
    namespace: dict[str, object],
    module_name: str,
) -> tuple[str, ...]:
    """Return imported application functions that may affect local decisions."""
    return tuple(
        sorted(
            name
            for name, value in namespace.items()
            if inspect.isfunction(value)
            and getattr(value, "__module__", "") != module_name
            and getattr(value, "__module__", "").startswith("app.")
        )
    )


HEALTH_SEMANTICS_AUTHORIZATION_FUNCTIONS = authorization_module_behavior_names(
    globals(),
    __name__,
)


def health_semantics_contract_payload() -> dict[str, str]:
    """Return versioned static evidence included in the capability digest."""
    content = {
        "authorization_grammar_digest": authorization_grammar_digest(globals()),
        "authorization_behavior_digest": authorization_behavior_digest(
            globals(), HEALTH_SEMANTICS_AUTHORIZATION_FUNCTIONS
        ),
        "illness_entities": sorted(CANONICAL_ILLNESS_ENTITIES),
        "illness_aliases": dict(sorted(ILLNESS_ENTITY_ALIASES.items())),
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
        "authorization_grammar_digest": content["authorization_grammar_digest"],
    }
