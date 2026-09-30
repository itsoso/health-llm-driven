"""Shared deterministic intake intent classifier.

This layer routes ambiguous "吃了" text before any write-like card/tool path.
It is intentionally conservative: medication/dose-like phrases must fail away
from diet, while vague intake text stays unknown.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.services.drug_lexicon import contains_drug_name, contains_supplement_name


@dataclass(frozen=True)
class IntakeIntent:
    kind: str
    confidence: float
    reason: str
    text: str = ""
    slots: dict[str, Any] = field(default_factory=dict)


DIET_MANAGEMENT_MARKERS = (
    "删除",
    "删掉",
    "删了",
    "删去",
    "移除",
    "撤销",
    "取消记录",
    "取消这一餐",
    "取消这餐",
    "误删",
    "不小心删",
    "恢复",
    "找回",
    "没有保存成功",
    "没保存成功",
    "保存失败",
    "保存成",
    "是否保存",
    "有没有保存",
    "查询全天饮食",
    "全天饮食和热量",
    "今日饮食和热量",
    "今天总热量",
    "全天热量",
)

MEDICATION_MARKERS = (
    "沃克",
    "伏诺拉生",
    "替普瑞酮",
    "施维舒",
    "奥美拉唑",
    "雷贝拉唑",
    "泮托拉唑",
    "埃索美拉唑",
    "阿莫西林",
    "布洛芬",
    "氯雷他定",
    "西替利嗪",
    "孟鲁司特",
    "二甲双胍",
    "美沙拉嗪",
)

FOOD_UI_TEXT_MARKERS = (
    "营养卡",
    "保存并确认",
    "确认记录",
    "今日饮食",
    "待确认",
    "完成修正",
    "去饮食页修正",
    "看下一餐建议",
)

SUPPLEMENT_MARKERS = (
    "鱼油",
    "维生素",
    "维d",
    "d3",
    "d2",
    "b族",
    "益生菌",
    "nac",
    "辅酶q10",
    "镁",
    "magnesium",
)

_MEDICATION_ACTION_RE = re.compile(r"服药|吃药|用药|药物|药品|处方药|非处方药|抗生素|止痛药|胃药")
_MEDICATION_FORM_RE = re.compile(r"(?:胶囊|缓释片|肠溶片|分散片|口服液|滴剂|喷雾|吸入剂|颗粒)")
_MEDICATION_DOSE_RE = re.compile(r"\d+(?:\.\d+)?(?:mg|毫克|μg|ug|iu|单位)", re.I)
_MEDICATION_SUFFIX_RE = re.compile(r"(?:拉唑|瑞酮|霉素|沙星|洛芬|司特|他汀|地平|沙坦|普利|格列|替丁)")
_HEALTH_METRIC_RE = re.compile(
    r"(?:跑步|晨跑|夜跑|快走|步数|运动|训练|健身|游泳|骑行)\d*(?:分钟|分|步|公里|km|千米)?"
    r"|(?:体重|腰围|臀围|体脂|bmi)\d+(?:\.\d+)?(?:kg|公斤|斤|cm|厘米|%)?"
    r"|(?:睡了|睡眠|入睡|起床|醒来|午睡|小睡)\d+(?:\.\d+)?(?:小时|h|分钟|分)?"
    r"|(?:血压|收缩压|舒张压)\d{2,3}/\d{2,3}"
    r"|(?:血糖|空腹血糖|餐后血糖)\d+(?:\.\d+)?"
    r"|(?:心率|静息心率|rhr)\d{2,3}",
    re.I,
)

_MEAL_LABELS = {
    "breakfast": ("早餐", "早饭", "早上"),
    "lunch": ("午餐", "中饭", "中午"),
    "dinner": ("晚餐", "晚饭", "晚上"),
    "snack": ("加餐", "零食", "夜宵", "下午茶"),
}

# ──── 提问守卫(R4 边界 · founder 「午餐我吃了啥？」实锤) ────
# 查询回合绝不产出 intake 写草稿。摄入动词 + 疑问词/疑问语气共现 → 判为提问,
# 而非记录。所有 *_draft builder 都门控在 classify_intake_intent 上,故守卫放这里,
# 三个 draft builder 一并继承。刻意 PRECISE:裸 "?" 不足以否决,必须与摄入动词共现。
_INTAKE_VERB = r"(?:吃了|喝了|服了|用了|补了|吃|喝|服|用|补)"
# 摄入动词 + (可选 的/了/过) + 疑问词:「吃了啥」「喝了多少」「补了几片」「午餐吃什么」
_INTAKE_QUESTION_WORD_RE = re.compile(
    _INTAKE_VERB + r"(?:的|了|过|点|些)?\s*(?:啥|什么|多少|几|哪些|哪)"
)
# 摄入动词 + 尾部问号:「…吃的啥？」「…喝了吗？」——问号锚定疑问语气
_INTAKE_QUESTION_MARK_RE = re.compile(_INTAKE_VERB + r"[^?？]{0,12}[?？]")
# 摄入动词 + 尾部是非语气词 吗/呢:「我吃了吗」「喝了呢」
_INTAKE_YESNO_PARTICLE_RE = re.compile(_INTAKE_VERB + r"(?:了|过|的)?\s*(?:吗|呢)\s*[?？]?$")

# 纯疑问 token(去空白后整串就是疑问词)——item 级第二层拒绝,即使漏过顶层守卫,
# 抽出的 item 若只是疑问词也绝不成草稿。
_PURE_QUESTION_TOKEN_RE = re.compile(r"^(?:啥|什么|多少|几|哪|哪些|吗|呢)$")


def _is_intake_question(normalized: str) -> bool:
    """摄入动词 + 疑问共现 → 提问(非记录)。PRECISE:三种独立信号任一命中。"""
    if _INTAKE_QUESTION_WORD_RE.search(normalized):
        return True
    if _INTAKE_QUESTION_MARK_RE.search(normalized):
        return True
    if _INTAKE_YESNO_PARTICLE_RE.search(normalized):
        return True
    return False


def _is_pure_question_item(item: str) -> bool:
    """抽出的 item 去掉尾部问号/标点后若只剩疑问词 → 拒绝(item 级第二层)。"""
    stripped = _normalize(item).strip("?？ ")
    return bool(_PURE_QUESTION_TOKEN_RE.match(stripped))


# 非摄入言语行为(提问 / 否定·漏服·计划·提醒)的 reason。命中即 kind=unknown,
# 任何调用方都不得再用别的解析兜底把它写成记录(quick_record 旧正则即一例)。
NON_INTAKE_REASONS = frozenset({"intake_question", "intake_reflection"})


def classify_intake_intent(query: Any) -> IntakeIntent:
    """Classify text as an intake *record*; non-intake speech acts are unknown."""
    return _classify(_flatten_text(query), speech_act_guards=True)


def classify_intake_subject(query: Any) -> IntakeIntent:
    """Classify what the text is about, even when it is not an intake record.

    Blocking callers (diet write validators, vision sanitizing, domain routing)
    use this: "没吃维生素D" is not an intake, but it is still a supplement and
    must never become a diet record.
    """
    return _classify(_flatten_text(query), speech_act_guards=False)


def _classify(raw: str, *, speech_act_guards: bool) -> IntakeIntent:
    normalized = _normalize(raw)
    if not normalized:
        return IntakeIntent("unknown", 0.0, "empty")

    is_management = _has_any(normalized, DIET_MANAGEMENT_MARKERS)
    if speech_act_guards and not is_management:
        # 顶层提问守卫:在 diet/medication/supplement/water 分支之前。
        # 提问(如「午餐我吃了啥？」)绝不落记录草稿。管理类(删除/恢复)不受此门——
        # 那些是显式命令而非提问,且不产出 intake 写草稿。
        if _is_intake_question(normalized):
            return IntakeIntent("unknown", 0.3, "intake_question", raw)

        # 否定/吐槽守卫(2026-07-14 founder 截图: "下次不吃那个牛肋骨面了…我吃完
        # 晚上就睡不着觉了" 被误判成 diet 草稿, 整句塞进 food_items)。反思("下次不
        # 吃X了")/决心("再也不喝")/以食物为病因的症状吐槽("吃完就睡不着/拉肚子")
        # 都不是记一餐/一次摄入 —— 与提问守卫同层, 绝不落 intake 写草稿。
        if _is_intake_negation_or_complaint(normalized):
            return IntakeIntent("unknown", 0.3, "intake_reflection", raw)

    if is_management:
        return IntakeIntent("diet_management", 0.95, "diet_management", raw)

    if _looks_like_health_metric(normalized):
        return IntakeIntent("health_metric", 0.88, "health_metric", raw)

    # 漏服/否定/计划/提醒/句末提问(2026-09-30 supplement-taken-contract follow-up):
    # 「没吃维生素D」「今天不吃镁」「准备吃鱼油」「吃了维生素D吗」曾落成摄入草稿,
    # 虚高补剂依从进 Twin 在服集与 DSI/DDI 推理。放在指标之后:空腹测量常注明
    # 「没吃早饭」,指标本身仍要记录。
    if speech_act_guards:
        not_taken = _not_taken_reason(normalized)
        if not_taken:
            return IntakeIntent("unknown", 0.3, not_taken, raw)

    water_amount = _extract_water_amount(normalized)
    if _looks_like_water(normalized):
        slots: dict[str, Any] = {}
        if water_amount is not None:
            slots["amount_ml"] = water_amount
        return IntakeIntent("water", 0.9, "water", raw, slots)

    if _looks_like_medication(raw, normalized):
        item = _extract_item_text(raw)
        if speech_act_guards:
            rejected = "intake_question" if _is_pure_question_item(item) else _non_intake_item_reason(item, named=True)
            if rejected:
                return IntakeIntent("unknown", 0.3, rejected, raw)
        slots = _extract_medication_slots(item)
        return IntakeIntent(
            "medication",
            0.9,
            "medication_marker",
            _strip_medication_slot_tokens(item, slots),
            slots,
        )

    if _looks_like_supplement(raw, normalized):
        item = _extract_item_text(raw)
        if speech_act_guards:
            rejected = "intake_question" if _is_pure_question_item(item) else _non_intake_item_reason(item, named=True)
            if rejected:
                return IntakeIntent("unknown", 0.3, rejected, raw)
        return IntakeIntent("supplement", 0.82, "supplement_marker", item)

    if _looks_like_diet(raw, normalized):
        item = _extract_food_text(raw) or _extract_item_text(raw)
        if not item or _is_vague_item(item) or (speech_act_guards and _is_pure_question_item(item)):
            return IntakeIntent("unknown", 0.35, "ambiguous", raw)
        if speech_act_guards:
            rejected = _non_intake_item_reason(item, named=False)
            if rejected:
                return IntakeIntent("unknown", 0.3, rejected, raw)
        return IntakeIntent(
            "diet",
            0.82,
            "diet_marker",
            item,
            {"meal_type": _infer_meal_type(raw)},
        )

    return IntakeIntent("unknown", 0.35, "ambiguous", raw)


def looks_like_food_ui_text(value: Any) -> bool:
    """Reject OCR/card chrome before it reaches any authoritative diet write."""
    normalized = _normalize(_flatten_text(value))
    if not normalized:
        return False
    if re.fullmatch(r"(?:和)?(?:早餐|午餐|晚餐|加餐|餐食)?(?:食品?)?营养卡", normalized):
        return True
    return any(marker in normalized for marker in FOOD_UI_TEXT_MARKERS)


def is_reusable_food_description(value: str) -> bool:
    """Exclude symptom and non-intake narratives from one-tap reuse, not from history.

    A meal plus a symptom may be a valid historical observation, but must not
    repeat that symptom as today's food. Legacy parsers also stored non-intake
    text ("没吃", "牛肉面吗"); replaying it would create a false intake. Unknown
    food names remain eligible; this is deliberately not a food vocabulary
    allowlist or a write validator.
    Keep the mobile stale-cache guard and its positive/negative cases aligned.
    """
    normalized = _normalize(value)
    return bool(normalized) and not any(p.search(normalized) for p in _REUSE_EXCLUSION_RES)


_FOOD_REUSE_SYMPTOM_RE = re.compile(
    r"(?:肚子|腹部|胃).{0,4}(?:痛|疼|胀)|腹痛|腹胀|腹泻|拉肚子|"
    r"胃痛|胃疼|反酸|烧心|恶心|想吐|呕吐|头晕|心悸|"
    r"不舒服|睡不着|失眠|睡不好"
)


def _flatten_text(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_text(item) for item in value if item is not None).strip()
    if value is None:
        return ""
    return str(value).strip()


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value or "").lower()


def _has_any(normalized: str, markers: Iterable[str]) -> bool:
    return any(marker.lower() in normalized for marker in markers)


def _looks_like_water(normalized: str) -> bool:
    return bool(
        re.search(r"(喝水|饮水|温水|白水|矿泉水|纯净水)", normalized)
        or re.search(r"喝了?\d+(?:\.\d+)?(?:ml|毫升).{0,4}水", normalized, re.I)
    )


def _looks_like_health_metric(normalized: str) -> bool:
    return bool(_HEALTH_METRIC_RE.search(normalized))


def _extract_water_amount(normalized: str) -> int | None:
    match = re.search(r"(\d+(?:\.\d+)?)(?:ml|毫升)", normalized, re.I)
    if not match:
        return None
    try:
        return int(round(float(match.group(1))))
    except ValueError:
        return None


_ADJACENT_NAMED_INTAKE_DOSE_RE = re.compile(
    r"(?<=[a-z])(?=\d+(?:\.\d+)?\s*(?:mg|mcg|μg|ug|iu|ml|g|毫克|毫升|克|片|粒|颗|袋|包|滴|支|瓶))",
    re.IGNORECASE,
)


def _boundary_preserving_intake_text(raw: str) -> str:
    """Separate only an ASCII name followed immediately by a recognized dose."""
    return _ADJACENT_NAMED_INTAKE_DOSE_RE.sub(" ", raw or "")


def _looks_like_medication(raw: str, normalized: str) -> bool:
    named_intake_text = _boundary_preserving_intake_text(raw)
    if _has_any(normalized, MEDICATION_MARKERS) or contains_drug_name(named_intake_text):
        return True
    return bool(
        _MEDICATION_ACTION_RE.search(normalized)
        or _MEDICATION_FORM_RE.search(normalized)
        or _MEDICATION_DOSE_RE.search(normalized)
        or _MEDICATION_SUFFIX_RE.search(normalized)
    )


def _looks_like_supplement(raw: str, normalized: str) -> bool:
    if re.search(r"维\s*c\s*(?:茶|饮|饮料|果汁|柠檬|柠)", raw, re.I):
        return False
    if re.search(
        r"(?:红景天|rhodiola)\s*(?:"
        r"茶|饮(?:品|料)?|果汁|鸡?汤|粥|糕|饼|面包|软糖|果冻|炖|煮|烤"
        r")",
        raw,
        re.I,
    ):
        return False
    if contains_supplement_name(raw):
        return True
    for marker in SUPPLEMENT_MARKERS:
        lowered = marker.lower()
        if lowered.isascii():
            if re.search(rf"(?<![a-z0-9]){re.escape(lowered)}(?![a-z0-9])", normalized, re.I):
                return True
            continue
        if lowered in normalized:
            return True
    return False


# 摄入否定:反思/决心不再吃喝(未来时否定),不是当次记录。
_INTAKE_NEGATION_RE = re.compile(
    r"(?:下次|以后|再也|从此|今后)(?:都)?不(?:吃|喝|碰)"
    r"|(?:下次|以后|再也|从此|今后)?(?:都)?别(?:吃|喝|碰)"
    r"|不(?:应该|想|该|能|要|会|再)(?:吃|喝|碰)"
    r"|不(?:吃|喝|碰)\S{0,10}了"
)
# 以食物为病因的症状吐槽词(含用户对食物质量的怀疑)。
_INTAKE_SYMPTOM_RE = re.compile(
    r"睡不着|失眠|睡不好|拉肚子|腹泻|胃疼|胃痛|反酸|烧心|恶心|想吐|呕吐|"
    r"过敏|难受|不舒服|头晕|心悸|上头|兴奋剂|罂粟"
)
# 明确「记一餐/一次摄入」的记录结构 —— 有它就是真记录, 症状吐槽守卫放行。
_INTAKE_LOG_VERB_RE = re.compile(r"记录|打卡|打个卡|吃了|点了|吃的是|服用了|喝了(?!.{0,3}就)")


def _is_intake_negation_or_complaint(normalized: str) -> bool:
    if _INTAKE_NEGATION_RE.search(normalized):
        return True
    # 症状吐槽:有症状/病因词且是摄入语境,但没有明确记录结构 → 判反馈而非记录。
    # (保护真记录:"晚饭吃了牛肉面, 吃完有点反酸" 有 "吃了" → 不误杀。)
    if _INTAKE_SYMPTOM_RE.search(normalized) and re.search(r"吃|喝", normalized):
        if not _INTAKE_LOG_VERB_RE.search(normalized):
            return True
    return False


# ──── 非摄入言语行为守卫(2026-09-30 supplement-taken-contract follow-up) ────
# PRECISE:标记必须紧贴摄入动词(或在句末),「吃了维生素D」「服用镁」「补剂鱼油」
# 「午餐吃了没放盐的鸡胸肉」「吃了别嘌醇」照常记录。
# mobile/utils/dietIntakeGuard.ts::isReusableDietFoodDescription 镜像这些正则。
_NOT_TAKEN_VERB = r"(?:吃|喝|服|补|補|用药|用藥)"
# 漏服 / 过去否定 / 当下否定 / 停用
_INTAKE_NOT_TAKEN_RE = re.compile(
    # 没吃 / 还没吃 / 没有服用 / 未服 / 没按时吃 / 维生素D还没吃
    r"(?:没|沒|未)有?(?:按时|按時|及时|及時|准时|準時|来得及|來得及|能|法|再|怎么|怎麼)?" + _NOT_TAKEN_VERB
    # 漏服 / 漏吃 / 漏了吃
    + r"|漏(?:了|掉了?)?" + _NOT_TAKEN_VERB
    # 忘了吃 / 忘记服 / 忘吃 / 忘了带
    + r"|忘(?:了|记了?|記了?|掉了?)?(?:吃|喝|服|补|補|用药|用藥|带|帶)"
    # 句末「鱼油忘了」;「差点忘了」是没忘
    + r"|(?<!差点)(?<!差點)(?<!险些)(?<!險些)(?<!差一点)(?<!差一點)忘(?:了|记了?|記了?|掉了?)[。.!！~～…]*$"
    # 今天不吃镁 / 不再服 / 不想喝 / 不用补
    + r"|不(?:应该|應該|应|應|想|该|該|能|要|会|會|再|用|必|需要|需|打算|准备|準備|敢)?(?:吃|喝|碰|服|补|補)"
    # 停用 / 暂停
    + r"|停(?:掉|用|服|药|藥|吃|喝|补|補)|暂停|暫停"
)
# 提醒 / 计划 / 将来时间(未带 了/过/完/的 完成体)
_INTAKE_NOT_YET_RE = re.compile(
    # 别忘了吃 / 别再吃(排除 特别/分别/个别… 里的「别」)
    r"(?<![特分个個区區差性类類级級识識辨告鉴鑑])[别別](?:再|忘)"
    # 记得吃 / 提醒我吃(「我记得吃了」是回忆,放行)
    r"|[记記]得(?:要|再|按时|按時)?(?:吃|喝|服|补|補)(?![了过過完])"
    r"|提醒我?(?:要|按时|按時|记得|記得)?(?:吃|喝|服|补|補)"
    # 准备吃 / 打算服 / 想喝 / 该吃了 / 得吃药 / 要吃(排除 主要/记得/觉得/难得…)
    r"|(?:准备|準備|打算|计划|計劃|想|[将將]|[该該]|(?<![记記觉覺晓曉懂舍捨值难難])得|(?<!主)要)"
    r"(?:再|去|先|开始|開始|按时|按時)?(?:吃|喝|服|补|補)"
    # 待会吃 / 明天吃 / 今晚喝;「今晚吃了」「马上吃完」是已发生
    r"|(?:待会|待會|等会|等會|等下|等一下|一会|一會|过会|過會|稍后|稍後|晚点|晚點|回头|回頭"
    r"|马上|馬上|立刻|今晚|明天|明早|明晚|后天|後天)儿?(?:再|就|要|会|會|去|得)?"
    r"(?:吃|喝|服|补|補)(?![了过過完的])"
)
# 句末是非问:「吃了维生素D吗」「今天吃鱼油了吗」「晚饭吃了牛肉面吗」
_INTAKE_TRAILING_QUESTION_RE = re.compile(
    _INTAKE_VERB + r".{0,24}(?:吗|嗎|么|麼|呢)[?？!！。.~～…]*$"
)
# 正反问 / 是否问 / 方式问:「吃没吃」「有没有吃」「要不要吃」「鱼油吃了没」「鱼油怎么吃」
_INTAKE_ALT_QUESTION_RE = re.compile(
    r"(吃|喝|服|补|補|用)(?:没|沒|不)\1"
    r"|(?:有没有|有沒有|是不是|是否|要不要|该不该|該不該|能不能|可不可以|用不用|需不需要)"
    r"(?:已经|已經|按时|按時|再)?(?:吃|喝|服|补|補|用)"
    r"|(?:吃|喝|服|补|補|用)(?:了|过|過).{0,20}(?:没有?|沒有?)[?？!！。.~～…]*$"
    r"|(?:怎么|怎麼|怎样|怎樣|如何|为什么|為什麼|为啥|為啥|咋|何时|何時|什么时候|什麼時候)"
    r"(?:才能|能|要|该|該)?(?:吃|喝|服|补|補|用)"
)
# item 级第二层:无摄入动词的提问/否定会整句落进 item(「维生素D吗」「我停了鱼油」)。
_ITEM_QUESTION_RE = re.compile(r"[?？]|(?:吗|嗎|么|麼|呢)$")
# 疑问词只看具名 item 的首个分句:「记一下吃了鱼油，看看对基因有什么影响」是先记录后查询。
_ITEM_QUESTION_WORD_RE = re.compile(r"什么|什麼|啥|多少|哪|怎么|怎麼|如何|为什么|為什麼")
# 补剂/药名里不会出现这些字(已核对 drug_lexicon 全部别名);食物描述里会(「没放盐」),故只用于具名 item。
_NAME_NOT_TAKEN_RE = re.compile(r"没|沒|未|漏|停")
_CLAUSE_BREAK_RE = re.compile(r"(?<=[^\x00-\x7f])\s+|\s+(?=[^\x00-\x7f])")


def _not_taken_reason(normalized: str) -> str | None:
    if _INTAKE_TRAILING_QUESTION_RE.search(normalized) or _INTAKE_ALT_QUESTION_RE.search(normalized):
        return "intake_question"
    if _INTAKE_NOT_TAKEN_RE.search(normalized) or _INTAKE_NOT_YET_RE.search(normalized):
        return "intake_reflection"
    return None


def non_intake_reason(text: str, *, named: bool = False) -> str | None:
    """Speech-act verdict alone, without domain or health_metric precedence.

    For parsers that fall back to their own regexes after the classifier
    ("午餐没吃，血糖5.6" classifies as health_metric, yet is no meal record).
    """
    normalized = _normalize(text)
    if _is_intake_question(normalized):
        return "intake_question"
    if _is_intake_negation_or_complaint(normalized):
        return "intake_reflection"
    return _not_taken_reason(normalized) or _non_intake_item_reason(text, named=named)


def _non_intake_item_reason(item: str, *, named: bool) -> str | None:
    if _ITEM_QUESTION_RE.search(_normalize(item)):
        return "intake_question"
    if not named:
        return None
    if _NAME_NOT_TAKEN_RE.search(_normalize(item)):
        return "intake_reflection"
    # 分句边界(标点或 item 抽取换成的空格);只在贴着中文的空格处切,不切开 "fish oil"。
    first_clause = _CLAUSE_BREAK_RE.split(re.sub(r"[，,;；。]", " ", item).strip(), maxsplit=1)[0]
    if _ITEM_QUESTION_RE.search(_normalize(first_clause)) or _ITEM_QUESTION_WORD_RE.search(_normalize(first_clause)):
        return "intake_question"
    return None


# 一键复用排除集:症状吐槽 + 全部非摄入言语行为。mobile 过期缓存守卫编译同一组
# 源串(test_reuse_exclusions_mirror_mobile_guard 逐条比对)。
_REUSE_EXCLUSION_RES = (
    _FOOD_REUSE_SYMPTOM_RE,
    _INTAKE_QUESTION_WORD_RE,
    _INTAKE_QUESTION_MARK_RE,
    _INTAKE_YESNO_PARTICLE_RE,
    _INTAKE_NEGATION_RE,
    _INTAKE_TRAILING_QUESTION_RE,
    _INTAKE_ALT_QUESTION_RE,
    _INTAKE_NOT_TAKEN_RE,
    _INTAKE_NOT_YET_RE,
    _ITEM_QUESTION_RE,
    _ITEM_QUESTION_WORD_RE,
)


def _looks_like_diet(raw: str, normalized: str) -> bool:
    if _is_vague_item(raw):
        return False
    has_food_action = bool(re.search(r"吃了|刚吃|吃的是|点了|喝了|刚喝", raw))
    has_meal = any(marker in raw for markers in _MEAL_LABELS.values() for marker in markers)
    has_nutrition = bool(re.search(r"\d+(?:\.\d+)?\s*(?:kcal|千卡|大卡|卡路里|g|克)", raw, re.I))
    has_food_word = bool(re.search(
        r"餐食|食物|牛肉面|能量碗|米饭|面|粥|汤|糕|饼|软糖|果冻|"
        r"蛋|肉|菜|茶|咖啡|奶|水果",
        raw,
    ))
    return (has_food_action and (has_meal or has_nutrition or has_food_word)) or (has_meal and has_food_word)


def _infer_meal_type(raw: str) -> str:
    for meal_type, labels in _MEAL_LABELS.items():
        if any(label in raw for label in labels):
            return meal_type
    return "snack"


def _strip_nutrition_tokens(raw: str) -> str:
    cleaned = re.sub(r"(?:热量|约|大约|总共)?\s*\d+(?:\.\d+)?\s*(?:kcal|千卡|大卡|卡路里)", " ", raw, flags=re.I)
    cleaned = re.sub(r"(?:蛋白质?|protein)\s*\d+(?:\.\d+)?\s*(?:g|克)?", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"(?:碳水|carbs?|碳水化合物)\s*\d+(?:\.\d+)?\s*(?:g|克)?", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"(?:脂肪|fat)\s*\d+(?:\.\d+)?\s*(?:g|克)?", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"(?:纤维|fiber|膳食纤维)\s*\d+(?:\.\d+)?\s*(?:g|克)?", " ", cleaned, flags=re.I)
    return cleaned


def _extract_food_text(raw: str) -> str:
    cleaned = _strip_nutrition_tokens(raw)
    cleaned = re.sub(r"[，,;；。]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    patterns = [
        r"(?:记录|打卡)?\s*(?:早餐|早饭|午餐|中饭|晚餐|晚饭|加餐|夜宵|零食)?\s*(?:吃了|吃的是|吃|点了|喝了|刚喝)\s*(.+)",
        r"(?:早餐|早饭|午餐|中饭|晚餐|晚饭|加餐|夜宵|零食)\s*[:：]?\s*(.+)",
        # 裸意图动词 + 冒号/空格 + 条目("打卡:替普瑞酮胶囊"/"记录 维生素D")——
        # 无服用动词时前两个模式都不命中,兜底路径又不会洗掉"打卡"前缀,
        # 曾把 medication_name 整成"打卡:替普瑞酮胶囊"(mac 卡片实锤)。
        r"(?:记录|打卡|打个卡)\s*[:：]?\s*(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if not match:
            continue
        value = _clean_item_text(match.group(1))
        if value:
            return value[:160]
    return ""


def _extract_item_text(raw: str) -> str:
    cleaned = _strip_nutrition_tokens(raw)
    cleaned = re.sub(r"[，,;；。]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    patterns = [
        r"(?:记录|打卡)?\s*(?:我)?\s*(?:刚才|刚|今天)?\s*(?:吃了|服用了|服用|吃|用了|用药|补了|喝了)\s*(.+)",
        r"(?:早餐|早饭|午餐|中饭|晚餐|晚饭|加餐|夜宵|零食)\s*[:：]?\s*(.+)",
        # 裸意图动词 + 冒号/空格 + 条目("打卡:替普瑞酮胶囊"/"记录 维生素D")——
        # 无服用动词时前两个模式都不命中,兜底路径又不会洗掉"打卡"前缀,
        # 曾把 medication_name 整成"打卡:替普瑞酮胶囊"(mac 卡片实锤)。
        r"(?:记录|打卡|打个卡)\s*[:：]?\s*(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if not match:
            continue
        value = _clean_item_text(match.group(1))
        if value:
            return value[:160]
    return _clean_item_text(cleaned)[:160]


def _clean_item_text(value: str) -> str:
    cleaned = value.strip(" ：:，,;；。")
    cleaned = re.sub(r"^(?:一份|一个|一碗|一杯|了)\s*", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_medication_slots(item: str) -> dict[str, Any]:
    slots: dict[str, Any] = {}
    dose = _MEDICATION_DOSE_RE.search(item)
    if dose:
        slots["dose"] = dose.group(0)
    return slots


def _strip_medication_slot_tokens(item: str, slots: dict[str, Any]) -> str:
    cleaned = item
    dose = slots.get("dose")
    if isinstance(dose, str) and dose:
        cleaned = cleaned.replace(dose, " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ：:，,;；。")
    return cleaned or item


def _is_vague_item(value: str) -> bool:
    normalized = _normalize(value)
    return bool(re.search(r"(一个东西|一点东西|吃了东西|随便吃|不知道吃了啥|这个东西)$", normalized))
