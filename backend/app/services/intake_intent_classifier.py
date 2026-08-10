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


def classify_intake_intent(query: Any) -> IntakeIntent:
    raw = _flatten_text(query)
    normalized = _normalize(raw)
    if not normalized:
        return IntakeIntent("unknown", 0.0, "empty")

    # 顶层提问守卫:在 diet/medication/supplement/water 分支之前。
    # 提问(如「午餐我吃了啥？」)绝不落记录草稿。管理类(删除/恢复)不受此门——
    # 那些是显式命令而非提问,且不产出 intake 写草稿。
    if not _has_any(normalized, DIET_MANAGEMENT_MARKERS) and _is_intake_question(normalized):
        return IntakeIntent("unknown", 0.3, "intake_question", raw)

    # 否定/吐槽守卫(2026-07-14 founder 截图: "下次不吃那个牛肋骨面了…我吃完
    # 晚上就睡不着觉了" 被误判成 diet 草稿, 整句塞进 food_items)。反思("下次不
    # 吃X了")/决心("再也不喝")/以食物为病因的症状吐槽("吃完就睡不着/拉肚子")
    # 都不是记一餐/一次摄入 —— 与提问守卫同层, 绝不落 intake 写草稿。
    if not _has_any(normalized, DIET_MANAGEMENT_MARKERS) and _is_intake_negation_or_complaint(normalized):
        return IntakeIntent("unknown", 0.3, "intake_reflection", raw)

    if _has_any(normalized, DIET_MANAGEMENT_MARKERS):
        return IntakeIntent("diet_management", 0.95, "diet_management", raw)

    if _looks_like_health_metric(normalized):
        return IntakeIntent("health_metric", 0.88, "health_metric", raw)

    water_amount = _extract_water_amount(normalized)
    if _looks_like_water(normalized):
        slots: dict[str, Any] = {}
        if water_amount is not None:
            slots["amount_ml"] = water_amount
        return IntakeIntent("water", 0.9, "water", raw, slots)

    if _looks_like_medication(raw, normalized):
        item = _extract_item_text(raw)
        if _is_pure_question_item(item):
            return IntakeIntent("unknown", 0.3, "intake_question", raw)
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
        if _is_pure_question_item(item):
            return IntakeIntent("unknown", 0.3, "intake_question", raw)
        return IntakeIntent("supplement", 0.82, "supplement_marker", item)

    if _looks_like_diet(raw, normalized):
        item = _extract_food_text(raw) or _extract_item_text(raw)
        if not item or _is_vague_item(item) or _is_pure_question_item(item):
            return IntakeIntent("unknown", 0.35, "ambiguous", raw)
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


def _looks_like_diet(raw: str, normalized: str) -> bool:
    if _is_vague_item(raw):
        return False
    has_food_action = bool(re.search(r"吃了|刚吃|吃的是|点了|喝了|刚喝", raw))
    has_meal = any(marker in raw for markers in _MEAL_LABELS.values() for marker in markers)
    has_nutrition = bool(re.search(r"\d+(?:\.\d+)?\s*(?:kcal|千卡|大卡|卡路里|g|克)", raw, re.I))
    has_food_word = bool(re.search(r"餐食|食物|牛肉面|能量碗|米饭|面|粥|蛋|肉|菜|茶|咖啡|奶|水果", raw))
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
