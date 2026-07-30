"""Deterministic health-intent compilation for the first golden slice."""

from __future__ import annotations

import re
from typing import Optional

from .contracts import HealthIntentEnvelope, RiskLevel


LOW_BACK_MANDATORY_DISCRIMINATOR_IDS = (
    "low_back.cauda_equina",
    "low_back.progressive_neurologic_deficit",
    "low_back.major_trauma",
    "low_back.systemic_red_flag",
)

_LOW_BACK_TERMS = (
    "腰疼",
    "腰痛",
    "腰部疼",
    "腰部痛",
    "腰部酸痛",
    "腰背疼",
    "腰背痛",
    "腰背酸痛",
    "腰椎疼",
    "腰椎痛",
    "腰骶部疼",
    "腰骶部痛",
    "腰骶疼",
    "腰骶痛",
    "下腰疼",
    "下腰痛",
    "腰酸",
    "下背痛",
    "后腰痛",
    "lowbackpain",
    "lowbackache",
    "lowerbackpain",
    "lowerbackache",
    "low-backpain",
    "lower-backpain",
    "lumbarpain",
    "lumbarbackpain",
)
_BACK_PAIN_TERMS = (
    "背痛",
    "背疼",
    "背部疼痛",
    "脊柱疼",
    "脊柱痛",
    "脊柱疼痛",
    "backpain",
    "backache",
)
_LOW_BACK_EMERGENCY_TERMS = (
    "大小便失禁",
    "尿潴留",
    "尿失禁",
    "漏尿",
    "排不出尿",
    "会阴麻木",
    "鞍区麻木",
    "肛周麻木",
    "生殖器麻木",
    "双腿无力",
    "双下肢无力",
    "双腿越来越没劲",
    "两条腿越来越没劲",
    "双腿越来越软",
    "两条腿越来越软",
    "下肢进行性无力",
    "双下肢进行性无力",
    "进行性下肢无力",
    "尿不出",
    "尿不出来",
    "小便解不出来",
    "小便排不出",
    "无法排尿",
    "不能排尿",
    "瘫痪",
    "urinaryretention",
    "urinaryincontinence",
    "urineleakage",
    "leakurine",
    "leakedurine",
    "leaksurine",
    "leakingurine",
    "cannoturinate",
    "cannotpassurine",
    "difficultypeeing",
    "difficultyurinating",
    "saddlenumbness",
    "saddleanaesthesia",
    "bowelincontinence",
    "bladderincontinence",
    "bilaterallegweakness",
    "progressivelegweakness",
    "worseninglegweakness",
    "legsgettingweaker",
)
_LOW_BACK_HIGH_RISK_TERMS = (
    "发热",
    "发烧",
    "高热",
    "高烧",
    "严重外伤",
    "重大外伤",
    "车祸",
    "高处摔",
    "高处跌",
    "不明原因体重下降",
    "体重下降",
    "癌症史",
    "肿瘤史",
    "严重感染",
    "majortrauma",
    "highfever",
    "unintentionalweightloss",
    "historyofcancer",
    "seriousinfection",
)
_LOW_BACK_EMERGENCY_PATTERNS = (
    re.compile(r"(?:小便|尿).{0,5}(?:解|排)?不出(?:来)?"),
    re.compile(r"(?:大小便|小便|大便).{0,5}(?:控制不住|失控)"),
    re.compile(
        r"(?:会阴|鞍区|肛门周围|肛周|生殖器).{0,5}"
        r"(?:麻木|没感觉|感觉减退)"
    ),
    re.compile(
        r"(?:双腿|两条腿|双下肢|下肢).{0,7}"
        r"(?:越来越|进行性|逐渐|渐渐|明显加重).{0,5}"
        r"(?:无力|没劲|没力气|发软|软)"
    ),
    re.compile(r"(?:cannot|unableto|cant)(?:pee|urinate|passurine)"),
    re.compile(r"(?:cannot|unableto|cant)empty(?:my|the)?bladder"),
    re.compile(r"(?:difficulty|trouble)(?:peeing|urinating)"),
    re.compile(r"(?:difficulty|trouble)(?:with)?starting(?:to)?urination"),
    re.compile(r"(?:saddle|perineal|perianal)numb(?:ness)?"),
    re.compile(
        r"numbness(?:in|around)(?:my|the)?"
        r"(?:saddle|perineal|perianal)area"
    ),
    re.compile(
        r"numbnessaround(?:the)?(?:genitals|genitalarea|buttocks|anus)"
    ),
    re.compile(
        r"(?:weakness|tingling|numbness).{0,20}(?:in)?bothlegs"
    ),
    re.compile(
        r"bothlegs.{0,20}(?:weakness|weak|tingling|numbness|numb)"
    ),
    re.compile(r"(?:progressive|worsening)(?:bilateral)?legweakness"),
    re.compile(r"loss\s*of(?:bladder|bowel)control"),
    re.compile(r"(?:无法|不能).{0,3}控制(?:尿液|小便|排尿|大便)"),
    re.compile(
        r"(?:突然|新出现|最近开始|刚开始|开始).{0,6}"
        r"(?:漏尿|尿失禁)"
    ),
    re.compile(
        r"(?:尿意|便意)(?:(?:和|及|、)(?:尿意|便意))?"
        r".{0,5}(?:消失|感觉不到)"
    ),
    re.compile(
        r"(?:越来越|愈来愈)(?:难尿|难以排尿|排尿困难)"
    ),
    re.compile(
        r"(?:控制不住|失控)(?:小便|排尿|尿液|大便|大小便)"
    ),
)
_LOW_BACK_UNILATERAL_PROGRESSIVE_PATTERNS = (
    re.compile(
        r"(?:左腿|右腿|一条腿|单侧下肢).{0,7}"
        r"(?:越来越|进行性|逐渐|渐渐|明显加重).{0,5}"
        r"(?:无力|没劲|没力气|发软|软)"
    ),
    re.compile(
        r"(?:left|right|one)leg.{0,12}"
        r"(?:getting|becoming|progressively|increasingly).{0,8}"
        r"(?:weak|weaker|numb)"
    ),
)
_LOW_BACK_HIGH_RISK_PATTERNS = (
    *_LOW_BACK_UNILATERAL_PROGRESSIVE_PATTERNS,
    re.compile(r"(?:不明原因|无意).{0,5}(?:体重下降|消瘦|暴瘦)"),
    re.compile(
        r"(?:莫名|没来由|没有原因).{0,8}"
        r"(?:瘦了|消瘦|暴瘦|体重.{0,3}(?:下降|减轻))"
    ),
    re.compile(r"(?:癌症|肿瘤).{0,4}(?:史|病史)"),
    re.compile(
        r"(?:以前|曾经|曾|既往).{0,8}"
        r"(?:得过|患过|有过|诊断过)?(?:癌症|肿瘤)"
    ),
    re.compile(r"(?:严重|近期).{0,4}感染"),
    re.compile(
        r"(?:从)?(?:楼梯|台阶).{0,5}(?:摔|跌)(?:下来|下去)?"
    ),
    re.compile(r"(?:摔|跌)(?:下|落)?(?:楼梯|台阶)"),
)
_AFFIRMED_LOW_BACK_DISCRIMINATOR_TERMS = {
    "low_back.cauda_equina": (
        "排尿困难",
        "大小便失禁",
        "尿潴留",
        "尿失禁",
        "漏尿",
        "排不出尿",
        "会阴麻木",
        "鞍区麻木",
        "肛周麻木",
        "肛门周围麻木",
        "生殖器麻木",
        "感觉不到擦拭肛门",
        "尿不出",
        "尿不出来",
        "小便解不出来",
        "小便排不出",
        "无法排尿",
        "不能排尿",
        "urinaryretention",
        "urinaryincontinence",
        "urineleakage",
        "leakurine",
        "leakedurine",
        "leaksurine",
        "leakingurine",
        "cannoturinate",
        "cannotpassurine",
        "difficultypeeing",
        "difficultyurinating",
        "saddlenumbness",
        "saddleanaesthesia",
        "bowelincontinence",
        "bladderincontinence",
    ),
    "low_back.progressive_neurologic_deficit": (
        "双腿无力",
        "双下肢无力",
        "双腿越来越没劲",
        "两条腿越来越没劲",
        "双腿越来越软",
        "两条腿越来越软",
        "下肢进行性无力",
        "双下肢进行性无力",
        "进行性下肢无力",
        "瘫痪",
        "bilaterallegweakness",
        "progressivelegweakness",
        "worseninglegweakness",
        "legsgettingweaker",
    ),
    "low_back.major_trauma": (
        "严重外伤",
        "重大外伤",
        "车祸",
        "高处摔",
        "高处跌",
        "majortrauma",
    ),
    "low_back.systemic_red_flag": (
        "发热",
        "发烧",
        "高热",
        "高烧",
        "不明原因体重下降",
        "体重下降",
        "癌症史",
        "肿瘤史",
        "严重感染",
        "highfever",
        "unintentionalweightloss",
        "historyofcancer",
        "seriousinfection",
    ),
}
_AFFIRMED_LOW_BACK_DISCRIMINATOR_PATTERNS = {
    "low_back.cauda_equina": (
        re.compile(r"(?:小便|尿).{0,5}(?:解|排)?不出(?:来)?"),
        re.compile(r"(?:大小便|小便|大便).{0,5}(?:控制不住|失控)"),
        re.compile(
            r"(?:会阴|鞍区|肛门周围|肛周|生殖器).{0,12}"
            r"(?:麻木|没感觉|没有感觉|感觉减退|"
            r"感觉.{0,6}(?:迟钝|减退|消失))"
        ),
        re.compile(
            r"(?:排尿|小便|尿).{0,12}(?:困难|费力|不畅)"
        ),
        re.compile(r"(?:排尿|小便|尿).{0,12}(?:解|排)?不出(?:来)?"),
        re.compile(r"(?:感觉不到|没有感觉到).{0,8}(?:擦拭)?肛门"),
        re.compile(r"(?:cannot|unableto|cant)(?:pee|urinate|passurine)"),
        re.compile(r"(?:cannot|unableto|cant)empty(?:my|the)?bladder"),
        re.compile(r"(?:difficulty|trouble)(?:peeing|urinating)"),
        re.compile(
            r"(?:difficulty|trouble)(?:with)?starting(?:to)?urination"
        ),
        re.compile(r"(?:saddle|perineal|perianal)numb(?:ness)?"),
        re.compile(
            r"numbness(?:in|around)(?:my|the)?"
            r"(?:saddle|perineal|perianal)area"
        ),
        re.compile(
            r"numbnessaround(?:the)?(?:genitals|genitalarea|buttocks|anus)"
        ),
        re.compile(r"loss\s*of(?:bladder|bowel)control"),
        re.compile(r"(?:无法|不能).{0,3}控制(?:尿液|小便|排尿|大便)"),
        re.compile(
            r"(?:突然|新出现|最近开始|刚开始|开始).{0,6}"
            r"(?:漏尿|尿失禁)"
        ),
        re.compile(
            r"(?:尿意|便意)(?:(?:和|及|、)(?:尿意|便意))?"
            r".{0,5}(?:消失|感觉不到)"
        ),
        re.compile(
            r"(?:越来越|愈来愈)(?:难尿|难以排尿|排尿困难)"
        ),
        re.compile(
            r"(?:控制不住|失控)(?:小便|排尿|尿液|大便|大小便)"
        ),
    ),
    "low_back.progressive_neurologic_deficit": (
        re.compile(
            r"(?:双腿|两腿|两条腿|双下肢|两侧下肢).{0,8}"
            r"(?:疼|痛|麻木?|刺痛|无力|乏力|没力)"
        ),
        re.compile(
            r"(?:双腿|两条腿|双下肢|下肢).{0,7}"
            r"(?:越来越|进行性|逐渐|渐渐|明显加重).{0,5}"
            r"(?:无力|没劲|没力气|发软|软)"
        ),
        re.compile(
            r"(?:weakness|tingling|numbness).{0,20}(?:in)?bothlegs"
        ),
        re.compile(
            r"bothlegs.{0,20}(?:weakness|weak|tingling|numbness|numb)"
        ),
        re.compile(r"(?:progressive|worsening)(?:bilateral)?legweakness"),
    ),
    "low_back.major_trauma": (
        re.compile(
            r"(?:从)?(?:楼梯|台阶).{0,5}(?:摔|跌)(?:下来|下去)?"
        ),
        re.compile(r"(?:摔|跌)(?:下|落)?(?:楼梯|台阶)"),
    ),
    "low_back.systemic_red_flag": (
        re.compile(r"(?:不明原因|无意).{0,5}(?:体重下降|消瘦|暴瘦)"),
        re.compile(
            r"(?:莫名|没来由|没有原因).{0,8}"
            r"(?:瘦了|消瘦|暴瘦|体重.{0,3}(?:下降|减轻))"
        ),
        re.compile(r"(?:癌症|肿瘤).{0,4}(?:史|病史)"),
        re.compile(
            r"(?:以前|曾经|曾|既往).{0,8}"
            r"(?:得过|患过|有过|诊断过)?(?:癌症|肿瘤)"
        ),
        re.compile(r"(?:严重|近期).{0,4}感染"),
    ),
}
_NEGATED_PREFIXES = (
    "没有",
    "并没有",
    "完全没有",
    "没有任何",
    "并无",
    "并未",
    "未见",
    "未出现",
    "未伴",
    "未",
    "否认",
    "否认有",
    "不伴",
    "不再",
    "不存在",
    "不是",
    "已经停止",
    "已停止",
    "没",
    "无",
    "no",
    "without",
    "denies",
    "donot",
    "dont",
    "doesnot",
    "doesnt",
    "didnot",
    "didnt",
    "hasnt",
    "havent",
    "hadnt",
    "isnt",
    "wasnt",
    "nolonger",
    "never",
    "not",
)
_NEGATION_SCOPE_BOUNDARY_RE = re.compile(
    r"(?:[，,；;。.!！？?]|但是|但|不过|然而|现在|目前|随后|然后|"
    r"but|however|now|currently|then|yet)"
)
_NEGATION_FILLERS = frozenset(
    {
        "出现",
        "发生",
        "任何",
        "任何明显",
        "明显",
        "明显的",
        "不明原因",
        "任何不明原因",
        "新发",
        "新出现",
        "持续",
        "上述",
        "new",
        "any",
        "anynew",
        "have",
        "having",
        "has",
        "had",
        "still",
        "有",
        "伴有",
        "出现",
        "experiencing",
        "继续",
        "continue",
        "continues",
        "continuing",
    }
)
_NEGATION_COORDINATORS = ("或", "和", "及", "、", "/", "or", "and")
_NEGATED_FINDING_IN_MATCH_RE = re.compile(
    r"(?:没有|并没有|完全没有|没有任何|并无|未见|未出现|未伴|"
    r"否认有?|不伴|不存在|并不|不是|没|"
    r"不(?!明原因|出|能|可|受|自主)|无)"
    r".{0,8}"
    r"(?:发麻|麻木|刺痛|无力|乏力|没力|疼痛|疼|痛|困难|费力|"
    r"不畅|感觉减退|感觉迟钝|体重下降|消瘦|暴瘦|癌症|肿瘤|感染)"
)
_STABLE_PREEXISTING_URINARY_DIFFICULTY_PATTERNS = (
    re.compile(
        r"(?:排尿|小便|尿)(?:困难|费力|不畅)"
        r"(?:(?:已|已经)?(?:稳定(?:多年|数年|很久)?|多年|数年|"
        r"很久|一直如此|长期存在)|(?:一直|长期)?"
        r"(?:没有(?:新)?变化|没(?:有)?变化|无变化|未变化))"
    ),
    re.compile(
        r"(?:多年|数年|长期|一直|既往)(?:存在|有)?(?:的)?"
        r"(?:排尿|小便|尿)(?:困难|费力|不畅)"
    ),
    re.compile(
        r"(?:difficulty|trouble)(?:with)?"
        r"(?:peeing|urinating|starting(?:to)?urination)"
        r"(?:(?:has|have)?been)?"
        r"(?:stable(?:foryears)?|unchanged|longterm|longstanding|"
        r"presentforyears)"
    ),
    re.compile(
        r"(?:stable|unchanged|longterm|longstanding|presentforyears)"
        r"(?:historyof|prior|preexisting)?"
        r"(?:difficulty|trouble)(?:with)?"
        r"(?:peeing|urinating|starting(?:to)?urination)"
    ),
)
_INCONTINENCE_FINDING_TERMS = frozenset(
    {
        "尿失禁",
        "漏尿",
        "urinaryincontinence",
        "urineleakage",
        "leakurine",
        "leakedurine",
        "leaksurine",
        "leakingurine",
    }
)
_INCONTINENCE_NEGATED_PREFIX_PATTERNS = (
    re.compile(r"(?:并不|从不|从未|不曾|未曾|不会|不)$"),
)
_INCONTINENCE_HISTORY_PREFIX_MARKERS = (
    "以前",
    "曾经",
    "去年",
    "既往",
    "过去",
    "从前",
    "早先",
    "之前",
    "usedtobe",
    "prior",
    "previous",
    "previously",
    "formerly",
    "historyof",
)
_INCONTINENCE_HISTORY_PREFIX_PATTERNS = (
    re.compile(r"(?:[一二三四五六七八九十百]+|\d+|数|多)年前"),
    re.compile(r"(?:lastyear|yearsago|yearago)"),
)
_INCONTINENCE_POST_MENTION_HISTORY_PATTERNS = (
    re.compile(r"(?:去年|多年前|数年前|以前|之前)"),
    re.compile(r"(?:lastyear|yearsago|previously)"),
)
_INCONTINENCE_RESOLVED_PREFIX_PATTERNS = (
    re.compile(r"(?:has|have|had)stopped$"),
)
_INCONTINENCE_IMMEDIATE_POST_MENTION_RESOLUTION_PATTERNS = (
    re.compile(r"(?:已经|已)?停止"),
    re.compile(r"(?:has|have|had)(?:now)?stopped"),
)
_INCONTINENCE_RESOLUTION_PATTERNS = (
    re.compile(r"(?:已经|已)(?:好了|恢复了?|消失了?)"),
    re.compile(
        r"(?:现在|目前|当前)(?:已经|还是|仍然|还|仍)?"
        r"(?:没有了?|没了|不存在|消失了?)"
    ),
    re.compile(
        r"(?:现在|目前|当前)?(?:已经|已)?"
        r"(?:不再|停止)(?:漏尿|尿失禁|持续)"
    ),
    re.compile(
        r"(?:现在|目前|当前)?(?:没有|没)(?:再)?"
        r"继续(?:漏尿|尿失禁|持续)"
    ),
    re.compile(r"(?:resolved|nolonger|nonenow|(?:is|has)?gone)"),
    re.compile(r"(?:doesnot|doesnt|didnot|didnt)continu(?:e|ing)"),
    re.compile(
        r"(?:(?:has|have|had)stopped)"
        r"(?:leaking(?:urine)?|havingurinaryincontinence)"
    ),
    re.compile(
        r"(?:(?:hasnot|hasnt|didnot|didnt)"
        r"(?:returned|recurred|return|recur)|"
        r"(?:isnot|isnt|wasnot|wasnt)"
        r"(?:ongoing|still(?:leaking|leaks?)(?:urine)?))"
    ),
)
_INCONTINENCE_RECURRENCE_OR_PERSISTENCE_PATTERNS = (
    re.compile(r"(?:再次|重新)(?:出现|发生)"),
    re.compile(r"(?:今天|现在|目前|当前)?又(?:开始)?(?:漏尿|尿失禁)"),
    re.compile(r"(?:复发|再发)"),
    re.compile(
        r"(?:现在|目前|当前)(?:仍然|仍|还)(?:有|存在|持续)"
    ),
    re.compile(r"(?:仍然|仍)(?:有|存在|持续)(?:漏尿|尿失禁)"),
    re.compile(
        r"(?:现在|目前|当前)?(?:仍然|仍|还)在(?:漏尿|尿失禁)"
    ),
    re.compile(r"(?:漏尿|尿失禁)(?:仍然|仍|还)?在持续"),
    re.compile(r"(?:没有|没|未)(?:再)?停止(?:漏尿|尿失禁)"),
    re.compile(r"(?:一直到现在|一直持续到现在|持续至今)"),
    re.compile(r"(?:还没|尚未|未)(?:好|恢复)"),
    re.compile(
        r"continu(?:e(?:s|d)?|ing)(?:to)?"
        r"(?:leak(?:ing)?urine|(?:have|having)urinaryincontinence)"
    ),
    re.compile(
        r"(?:hasnot|hasnt|havent|hadnot|hadnt|didnot|didnt|never)"
        r"stopped"
        r"(?:leaking(?:urine)?|havingurinaryincontinence)"
    ),
    re.compile(
        r"(?:again|returned|recurred|cameback|"
        r"still(?:have|has|do|does|present|ongoing)|"
        r"still(?:leaking|leaks?)(?:urine)?(?:now)?|"
        r"(?:hasnot|hasnt|isnot|isnt|wasnot|wasnt|not)"
        r"(?:yet)?resolved|(?:still)?unresolved|"
        r"persists?|persisting|ongoing)"
    ),
)
_INCONTINENCE_MENTION_LOOKAHEAD = 96
_STABLE_URINARY_OVERRIDE_TERMS = tuple(
    term
    for term in _LOW_BACK_EMERGENCY_TERMS
    if term not in {"difficultypeeing", "difficultyurinating"}
)
_STABLE_URINARY_OVERRIDE_PATTERNS = tuple(
    pattern
    for index, pattern in enumerate(_LOW_BACK_EMERGENCY_PATTERNS)
    if index not in {6, 7}
)
_URINARY_HISTORY_WORSENING_PATTERNS = (
    re.compile(
        r"(?:明显)?(?:加重|恶化|变差|更严重|越来越严重)"
    ),
    re.compile(
        r"(?:muchworse|worsening|gettingworse|"
        r"deteriorat(?:e|ed|ing))"
    ),
)
_URINARY_MENTION_TERMS = (
    "排尿",
    "小便",
    "尿液",
    "膀胱",
    "peeing",
    "urinating",
    "urination",
    "urinary",
    "bladder",
)
_HARD_SENTENCE_BOUNDARY_RE = re.compile(r"[。.!！？?]")
_URINARY_HISTORY_CHANGE_MAX_DISTANCE = 96


def classify_health_intent(
    query: str,
    *,
    client: Optional[str] = None,
) -> HealthIntentEnvelope:
    """Compile client-neutral clinical semantics from a user query."""

    del client
    raw_query = str(query or "").strip()
    normalized = re.sub(r"[\s'’_-]+", "", raw_query.lower())
    explicit_low_back = any(term in normalized for term in _LOW_BACK_TERMS)
    back_with_red_flag = (
        any(term in normalized for term in _BACK_PAIN_TERMS)
        and _low_back_risk(normalized)
        in {RiskLevel.EMERGENCY, RiskLevel.HIGH}
    )
    if explicit_low_back or back_with_red_flag:
        return HealthIntentEnvelope(
            query=raw_query,
            intent_id="health_advice.symptom.low_back_pain",
            intent="health_advice",
            domain="low_back_pain",
            risk_level=_low_back_risk(normalized),
            mandatory_discriminator_ids=LOW_BACK_MANDATORY_DISCRIMINATOR_IDS,
            requires_personal_context=True,
            requires_authority=True,
        )
    return HealthIntentEnvelope(
        query=raw_query,
        intent_id="general.chat",
        intent="general",
        domain="general",
        risk_level=RiskLevel.LOW,
    )


def affirmed_low_back_discriminator_ids(query: str) -> frozenset[str]:
    """Return discriminator groups explicitly answered in the affirmative.

    The same scoped-negation parser used for risk classification decides whether
    a matching term is affirmative. This keeps ``没有发热`` from accidentally
    closing the whole systemic-red-flag question.
    """

    normalized = re.sub(r"[\s'’_-]+", "", str(query or "").lower())
    affirmed: set[str] = set()
    for discriminator_id, terms in (
        _AFFIRMED_LOW_BACK_DISCRIMINATOR_TERMS.items()
    ):
        candidate_text = normalized
        if discriminator_id == "low_back.cauda_equina":
            candidate_text = _without_stable_preexisting_urinary_difficulty(
                normalized
            )
        patterns = _AFFIRMED_LOW_BACK_DISCRIMINATOR_PATTERNS[
            discriminator_id
        ]
        if any(
            _has_affirmed_term(candidate_text, term) for term in terms
        ) or any(
            _has_affirmed_pattern(candidate_text, pattern)
            for pattern in patterns
        ):
            affirmed.add(discriminator_id)
    return frozenset(affirmed)


def _without_stable_preexisting_urinary_difficulty(text: str) -> str:
    """Remove only explicitly stable historical urinary-difficulty findings.

    Stable prior urinary symptoms are not evidence of a *new* cauda-equina
    change. Any separate current retention, incontinence, saddle sensory change,
    or bilateral neurologic finding remains in the text and still escalates.
    """

    stable_history_matches = tuple(
        match
        for pattern in _STABLE_PREEXISTING_URINARY_DIFFICULTY_PATTERNS
        for match in pattern.finditer(text)
    )
    if not stable_history_matches:
        return text
    if _has_current_or_worsening_cauda_change(
        text,
        stable_history_matches,
    ):
        return text

    remaining = text
    for pattern in _STABLE_PREEXISTING_URINARY_DIFFICULTY_PATTERNS:
        remaining = pattern.sub("", remaining)
    return remaining


def _has_current_or_worsening_cauda_change(
    text: str,
    stable_history_matches: tuple[re.Match[str], ...],
) -> bool:
    """Let any affirmative current/new/worse CES finding override history."""

    if any(
        _has_affirmed_term(text, term)
        for term in _STABLE_URINARY_OVERRIDE_TERMS
    ):
        return True
    if any(
        _has_affirmed_pattern(text, pattern)
        for pattern in _STABLE_URINARY_OVERRIDE_PATTERNS
    ):
        return True
    return _has_affirmed_worsening_of_stable_urinary_history(
        text,
        stable_history_matches,
    )


def _has_affirmed_worsening_of_stable_urinary_history(
    text: str,
    stable_history_matches: tuple[re.Match[str], ...],
) -> bool:
    """Bind an elliptical worsening phrase to its urinary antecedent.

    A phrase such as ``这两天更严重了`` can inherit the preceding urinary
    subject. A new explicit low-back subject breaks that inheritance, and the
    normal scoped-negation parser still owns ``没有/并未/not worse``.
    """

    for pattern in _URINARY_HISTORY_WORSENING_PATTERNS:
        for change_match in pattern.finditer(text):
            if not _is_affirmed_pattern_match(text, change_match):
                continue
            for history_match in stable_history_matches:
                if history_match.end() > change_match.start():
                    continue
                intervening = text[
                    history_match.end():change_match.start()
                ]
                if (
                    len(intervening)
                    > _URINARY_HISTORY_CHANGE_MAX_DISTANCE
                    or _HARD_SENTENCE_BOUNDARY_RE.search(intervening)
                ):
                    continue
                urinary_subject_repeated = any(
                    term in intervening for term in _URINARY_MENTION_TERMS
                )
                low_back_subject_started = any(
                    term in intervening
                    for term in (*_LOW_BACK_TERMS, *_BACK_PAIN_TERMS)
                )
                if low_back_subject_started and not urinary_subject_repeated:
                    continue
                return True
    return False


def infer_low_back_population(query: str) -> str | None:
    """Infer only an explicit turn-scoped age band; never guess from context."""

    normalized = re.sub(r"[\s'’_-]+", "", str(query or "").lower())
    if any(
        marker in normalized
        for marker in (
            "未满16岁",
            "不到16岁",
            "16岁以下",
            "under16",
            "youngerthan16",
        )
    ):
        return "under_16"
    age_matches = (
        re.findall(r"(?<!\d)(\d{1,3})岁", normalized)
        + re.findall(r"(?<!\d)(\d{1,3})years?old", normalized)
    )
    for raw_age in age_matches:
        age = int(raw_age)
        if 0 <= age <= 120:
            return "adults_16_plus" if age >= 16 else "under_16"
    if any(
        marker in normalized
        for marker in (
            "已满16岁",
            "16岁及以上",
            "我是成年人",
            "本人是成年人",
            "iamanadult",
        )
    ):
        return "adults_16_plus"
    return None


def has_unilateral_progressive_neurologic_red_flag(query: str) -> bool:
    """Detect unilateral progression without upgrading it to emergency."""

    normalized = re.sub(r"[\s'’_-]+", "", str(query or "").lower())
    return any(
        _has_affirmed_pattern(normalized, pattern)
        for pattern in _LOW_BACK_UNILATERAL_PROGRESSIVE_PATTERNS
    )


def _low_back_risk(normalized_query: str) -> RiskLevel:
    discriminator_ids = affirmed_low_back_discriminator_ids(normalized_query)
    if discriminator_ids.intersection(
        {
            "low_back.cauda_equina",
            "low_back.progressive_neurologic_deficit",
        }
    ):
        return RiskLevel.EMERGENCY
    if discriminator_ids.intersection(
        {"low_back.major_trauma", "low_back.systemic_red_flag"}
    ):
        return RiskLevel.HIGH
    acute_query = _without_stable_preexisting_urinary_difficulty(
        normalized_query
    )
    if (
        any(
            _has_affirmed_term(acute_query, term)
            for term in _LOW_BACK_EMERGENCY_TERMS
        )
        or any(
            _has_affirmed_pattern(acute_query, pattern)
            for pattern in _LOW_BACK_EMERGENCY_PATTERNS
        )
    ):
        return RiskLevel.EMERGENCY
    if (
        any(
            _has_affirmed_term(normalized_query, term)
            for term in _LOW_BACK_HIGH_RISK_TERMS
        )
        or any(
            _has_affirmed_pattern(normalized_query, pattern)
            for pattern in _LOW_BACK_HIGH_RISK_PATTERNS
        )
    ):
        return RiskLevel.HIGH
    return RiskLevel.MEDIUM


def _has_affirmed_term(text: str, term: str) -> bool:
    start = 0
    while (index := text.find(term, start)) >= 0:
        prefix = text[max(0, index - 64):index]
        scoped_prefix = _NEGATION_SCOPE_BOUNDARY_RE.split(prefix)[-1]
        affirmed = not _negates_following_term(scoped_prefix)
        if affirmed and term in _INCONTINENCE_FINDING_TERMS:
            affirmed = not any(
                pattern.search(scoped_prefix)
                for pattern in _INCONTINENCE_NEGATED_PREFIX_PATTERNS
            ) and _incontinence_mention_is_current(
                text,
                start=index,
                end=index + len(term),
                scoped_prefix=scoped_prefix,
            )
        if affirmed:
            return True
        start = index + len(term)
    return False


def _incontinence_mention_is_current(
    text: str,
    *,
    start: int,
    end: int,
    scoped_prefix: str,
) -> bool:
    """Classify one incontinence mention without suppressing later recurrence."""

    hard_boundary = _HARD_SENTENCE_BOUNDARY_RE.search(text, end)
    scope_end = min(
        len(text),
        end + _INCONTINENCE_MENTION_LOOKAHEAD,
        hard_boundary.start() if hard_boundary else len(text),
    )
    if _has_affirmed_pattern_in_window(
        text,
        _INCONTINENCE_RECURRENCE_OR_PERSISTENCE_PATTERNS,
        start=end,
        end=scope_end,
    ):
        return True

    explicit_history = any(
        marker in scoped_prefix
        for marker in _INCONTINENCE_HISTORY_PREFIX_MARKERS
    ) or any(
        pattern.search(scoped_prefix)
        for pattern in _INCONTINENCE_HISTORY_PREFIX_PATTERNS
    ) or any(
        pattern.search(text, end, scope_end)
        for pattern in _INCONTINENCE_POST_MENTION_HISTORY_PATTERNS
    )
    explicitly_resolved = _has_affirmed_pattern_in_window(
        text,
        _INCONTINENCE_RESOLUTION_PATTERNS,
        start=end,
        end=scope_end,
    ) or any(
        pattern.search(scoped_prefix)
        for pattern in _INCONTINENCE_RESOLVED_PREFIX_PATTERNS
    ) or any(
        pattern.match(text, end, scope_end)
        for pattern in (
            _INCONTINENCE_IMMEDIATE_POST_MENTION_RESOLUTION_PATTERNS
        )
    )
    return not (explicit_history or explicitly_resolved)


def _has_affirmed_pattern_in_window(
    text: str,
    patterns: tuple[re.Pattern[str], ...],
    *,
    start: int,
    end: int,
) -> bool:
    return any(
        _is_affirmed_pattern_match(text, match)
        for pattern in patterns
        for match in pattern.finditer(text, start, end)
    )


def _has_affirmed_pattern(text: str, pattern: re.Pattern[str]) -> bool:
    for match in pattern.finditer(text):
        if _is_affirmed_pattern_match(text, match):
            return True
    return False


def _is_affirmed_pattern_match(
    text: str,
    match: re.Match[str],
) -> bool:
    prefix = text[max(0, match.start() - 64):match.start()]
    scoped_prefix = _NEGATION_SCOPE_BOUNDARY_RE.split(prefix)[-1]
    return (
        not _negates_following_term(scoped_prefix)
        and not _NEGATED_FINDING_IN_MATCH_RE.search(match.group(0))
    )


def _negates_following_term(scoped_prefix: str) -> bool:
    """Return true only when a negator actually scopes the following term."""

    for negator in sorted(_NEGATED_PREFIXES, key=len, reverse=True):
        index = scoped_prefix.rfind(negator)
        if index < 0:
            continue
        tail = scoped_prefix[index + len(negator):]
        if not tail or tail in _NEGATION_FILLERS:
            return True
        if (
            len(tail) <= 32
            and tail.endswith(_NEGATION_COORDINATORS)
        ):
            return True
    return False
