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
    "未见",
    "未出现",
    "未伴",
    "否认",
    "否认有",
    "不伴",
    "不存在",
    "不是",
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
        "有",
        "伴有",
        "出现",
        "experiencing",
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
        patterns = _AFFIRMED_LOW_BACK_DISCRIMINATOR_PATTERNS[
            discriminator_id
        ]
        if any(_has_affirmed_term(normalized, term) for term in terms) or any(
            _has_affirmed_pattern(normalized, pattern)
            for pattern in patterns
        ):
            affirmed.add(discriminator_id)
    return frozenset(affirmed)


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
    if (
        any(
            _has_affirmed_term(normalized_query, term)
            for term in _LOW_BACK_EMERGENCY_TERMS
        )
        or any(
            _has_affirmed_pattern(normalized_query, pattern)
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
        if not _negates_following_term(scoped_prefix):
            return True
        start = index + len(term)
    return False


def _has_affirmed_pattern(text: str, pattern: re.Pattern[str]) -> bool:
    for match in pattern.finditer(text):
        prefix = text[max(0, match.start() - 64):match.start()]
        scoped_prefix = _NEGATION_SCOPE_BOUNDARY_RE.split(prefix)[-1]
        if (
            not _negates_following_term(scoped_prefix)
            and not _NEGATED_FINDING_IN_MATCH_RE.search(match.group(0))
        ):
            return True
    return False


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
