"""Shared deterministic intake intent classifier.

This layer routes ambiguous "吃了" text before any write-like card/tool path.
It is intentionally conservative: medication/dose-like phrases must fail away
from diet, while vague intake text stays unknown.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable


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
)

MEDICATION_MARKERS = (
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

_MEAL_LABELS = {
    "breakfast": ("早餐", "早饭", "早上"),
    "lunch": ("午餐", "中饭", "中午"),
    "dinner": ("晚餐", "晚饭", "晚上"),
    "snack": ("加餐", "零食", "夜宵", "下午茶"),
}


def classify_intake_intent(query: Any) -> IntakeIntent:
    raw = _flatten_text(query)
    normalized = _normalize(raw)
    if not normalized:
        return IntakeIntent("unknown", 0.0, "empty")

    if _has_any(normalized, DIET_MANAGEMENT_MARKERS):
        return IntakeIntent("diet_management", 0.95, "diet_management", raw)

    water_amount = _extract_water_amount(normalized)
    if _looks_like_water(normalized):
        slots: dict[str, Any] = {}
        if water_amount is not None:
            slots["amount_ml"] = water_amount
        return IntakeIntent("water", 0.9, "water", raw, slots)

    if _looks_like_medication(normalized):
        item = _extract_item_text(raw)
        slots = _extract_medication_slots(item)
        return IntakeIntent(
            "medication",
            0.9,
            "medication_marker",
            _strip_medication_slot_tokens(item, slots),
            slots,
        )

    if _looks_like_supplement(raw, normalized):
        return IntakeIntent("supplement", 0.82, "supplement_marker", _extract_item_text(raw))

    if _looks_like_diet(raw, normalized):
        item = _extract_food_text(raw) or _extract_item_text(raw)
        if not item or _is_vague_item(item):
            return IntakeIntent("unknown", 0.35, "ambiguous", raw)
        return IntakeIntent(
            "diet",
            0.82,
            "diet_marker",
            item,
            {"meal_type": _infer_meal_type(raw)},
        )

    return IntakeIntent("unknown", 0.35, "ambiguous", raw)


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


def _extract_water_amount(normalized: str) -> int | None:
    match = re.search(r"(\d+(?:\.\d+)?)(?:ml|毫升)", normalized, re.I)
    if not match:
        return None
    try:
        return int(round(float(match.group(1))))
    except ValueError:
        return None


def _looks_like_medication(normalized: str) -> bool:
    if _has_any(normalized, MEDICATION_MARKERS):
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
    for marker in SUPPLEMENT_MARKERS:
        lowered = marker.lower()
        if lowered.isascii():
            if re.search(rf"(?<![a-z0-9]){re.escape(lowered)}(?![a-z0-9])", normalized, re.I):
                return True
            continue
        if lowered in normalized:
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
