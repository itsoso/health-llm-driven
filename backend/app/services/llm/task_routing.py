# -*- coding: utf-8 -*-
"""任务分级 → 模型路由(成本/延迟,Next Horizon Tier 4 / RFC 方向十)。

高风险裁决(safety/longevity/clinical)用强模型;日常/闲聊用快且便宜的模型。
复用 model_registry 已有的 speed_tier(fast/balanced/reasoning),不重复定义模型。

安全切入:flag 门控(settings.task_tiered_routing,默认关)+ create_provider_for_user
加可选 task_tier(默认 None)。flag 关 或 不传 tier → **零行为变更**。
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from app.services.drug_lexicon import (
    drug_name_free_text_terms,
    supplement_name_free_text_terms,
)
from app.services.llm.model_registry import list_models
from app.services.utterance_intent_classifier import classify_agent_utterance
from app.services.workday_microbreak_safety import contains_acute_symptom_language

# 任务档 → 期望 speed_tier
_TASK_TIER_TO_SPEED = {
    "high_stakes": "reasoning",   # safety / 抗衰裁决 / 临床
    "balanced": "balanced",       # 综合分析
    "casual": "fast",             # 闲聊 / 轻量
    # 内部工具决策轮 (agent tool-decision round): 只产出结构化 function call,
    # 无任何面向用户的医疗正文。这是**唯一**被显式授权降到 fast 的档 (见下方白名单)。
    # 合成/答案轮不走这个档 —— 它们无 tools, 由质量模型生成医疗结论。
    "tool_routing": "fast",
}

# ── 安全不变量(fail-closed):哪些任务档允许真的落到 fast(弱)模型 ──
# 只有**明确无医疗内容生成**的档才准降到 fast:简单查数 / 记录写入的意图分类 /
# 内部辅助任务。任何面向用户的医疗内容生成(健康建议 / 安全评估 / orchestrator
# 合成 / 专科叙事)绝不允许降到 fast —— 弱模型编造/漏说医疗结论是不可接受的风险。
#
# 强制点在 pick_model_id_by_tier:tier 不在此白名单时,即便目标/回退档命中 fast 模型
# 也会被地板到 non-fast(balanced)。将来若真有"记录写入意图分类"这类纯内部快任务,
# 显式往这里加档名并配对抗测试,别偷偷放宽。
#
# 2026-07-06:加入 "tool_routing" —— agent 工具决策轮 (tool-decision round)。
# 该档**只**代表"模型输出一个结构化 function call"这一步 (agent_executor 的带 tools 轮),
# 绝无面向用户的医疗正文:安全评估是确定性 SafetyGuardian、写入受 R4 draft/confirm 门控,
# 都与这一步用哪个模型无关。合成/答案轮 (无 tools) 恒不走此档,仍由质量模型生成医疗结论。
# 说明:此白名单只声明"该内部档**允许**降到 fast";落到具体模型时,tool 轮必须是
# reliable_tool_calling=True 的 fast 模型 (由 agent_executor 经 pick_reliable_tool_model_id
# 选,而非本文件的 pick_model_id_by_tier —— 后者不保证工具可靠性)。见 test_task_routing*。
_FAST_ELIGIBLE_TIERS: frozenset[str] = frozenset({"tool_routing"})

# 目标 speed_tier 无可用模型时的回退顺序 —— 对注册表裁剪鲁棒(如套餐收敛后不再有 fast 档,
# casual 自动落到 balanced,而不是返回 None 让任务路由整个失效)。
_SPEED_FALLBACK = {
    "fast": ("fast", "balanced", "reasoning"),
    "balanced": ("balanced", "reasoning", "fast"),
    "reasoning": ("reasoning", "balanced", "fast"),
}

_HIGH_STAKES_MARKERS = (
    "用药", "药", "药物", "吃药", "服药", "停药", "换药", "剂量", "疗程", "处方",
    "补剂", "补充剂", "维生素", "矿物质", "钙片",
    "吸入剂", "吸入器", "气雾剂", "鼻喷", "喷雾剂", "哮喘喷雾",
    "化验", "体检报告", "检查报告", "肝功能", "肾功能", "血常规", "血脂", "血糖",
    "病理报告", "病理", "报告", "化验单", "检查单",
    "基因", "位点", "影像", "胃镜", "核磁", "mri", "ct", "血氧", "spo2",
    "胃溃疡", "高血压", "糖尿病", "冠心病", "诊断", "术后", "过敏",
    "头痛", "胃痛", "腹痛", "膝盖痛", "腰痛", "疼痛", "酸痛", "痛", "疼", "不适", "发烧", "发热",
    "头晕", "恶心", "呕吐", "腹泻",
    "胸痛", "呼吸困难", "晕厥", "昏厥", "呕血", "黑便", "大出血", "急诊",
    "自杀", "伤害自己", "怀孕", "孕期", "孕妇", "备孕", "哺乳期", "喂奶", "母乳喂养", "产后",
    "保健品",
)
_HIGH_STAKES_DOMAINS = frozenset(
    {"medication", "supplement", "symptom", "clinical_context"}
)
_ACUTE_QUERY_SAFETY_MARKERS = (
    "胸闷", "心悸", "心慌", "气短", "气促", "喘不上气", "喘不过气",
    "呼吸费力", "憋气", "意识模糊", "单侧无力", "言语不清", "口唇发绀",
)
_ANALYSIS_MARKERS = (
    "分析", "解读", "评估", "建议", "为什么", "怎么", "如何", "适合", "判断",
    "方案", "风险", "趋势", "复盘", "综合", "结合",
)
_KNOWN_BALANCED_DOMAIN_MARKERS = (
    "睡眠", "睡得", "hrv", "恢复", "锻炼", "运动", "训练", "步数",
    "饮食", "早餐", "午餐", "晚餐", "热量", "蛋白质", "饮水", "体重",
)

_CONTEXTUAL_MEDICATION_REFERENCES = (
    "这个", "那个", "它", "这颗", "那颗", "那一颗", "那一粒", "这个量", "按这个量",
    "照旧", "继续", "那今晚", "今晚还", "还吃",
)
_CONTEXTUAL_MEDICATION_ACTIONS = (
    "吃", "服", "吞", "咽", "嚼", "含", "用", "吸入", "注射", "打针", "喷", "滴", "涂", "贴",
    "剂量", "用量", "加倍", "减半", "停",
)
_DIET_WRITE_MARKERS = ("记录", "记下", "记一下", "录入", "打卡")
_DIET_INGESTION_MARKERS = (
    "吃了", "喝了", "食用", "摄入", "早餐吃", "午餐吃", "晚餐吃", "加餐吃",
)
_DIET_MEAL_MARKERS = (
    "早餐", "早饭", "午餐", "午饭", "晚餐", "晚饭", "加餐", "夜宵", "这餐",
)
_EXPLICIT_FOOD_MARKERS = (
    "苹果", "橙子", "香蕉", "水果", "蔬菜", "沙拉", "面包", "麦片", "米饭",
    "白米饭", "粥", "面条", "鸡汤", "水", "咖啡", "茶", "饮料", "果汁", "酸奶", "牛奶", "豆奶",
    "坚果", "豆腐", "鸡蛋", "鱼肉", "牛肉", "猪肉", "鸡肉", "火锅",
)
_NUTRITION_DESCRIPTION_MARKERS = (
    "富含", "含量高", "维生素饮料", "高血糖指数", "矿物质", "药膳",
)
_SUPPLEMENT_SAFETY_MARKERS = (
    "补剂", "补充剂", "保健品", "维生素", "矿物质", "钙片",
)
_INHALED_MEDICATION_MARKERS = (
    "吸入剂", "吸入器", "气雾剂", "鼻喷", "喷雾剂", "哮喘喷雾",
)
_EXPLICIT_NON_MEDICAL_CONTEXT_MARKERS = (
    "训练", "运动", "健身", "动作", "器械", "设备", "工具", "软件", "计划",
    "贴纸", "喷壶", "面膜",
)
_EXPLICIT_MEDICATION_MARKERS = (
    "药", "用药", "药物", "吃药", "服药", "停药", "药片", "剂量", "疗程",
    "处方", "补剂", "保健品", "吸入剂", "气雾剂", "鼻喷剂",
)
_IMPLICIT_DOSE_RE = re.compile(
    r"(?:半|[0-9]+(?:\.[0-9]+)?|[一二两三四五六七八九十]+)\s*"
    r"(?:颗|粒|片|丸|袋|支|针|揿|喷|滴|泵|贴|毫克|mg|单位|iu|u|毫升|ml)"
)
_FOOD_BINDING_GAP_RE = re.compile(
    r"(?:(?:约|全麦|吐司|烤|熟|生|温|冰|矿泉|纯净|脱脂|低脂|无糖|原味|去皮|切片|小|大)){0,2}"
)
_FORWARD_FOOD_BINDING_PREFIXES = (
    *_DIET_INGESTION_MARKERS,
    "和", "与", "跟", "配", "搭配", "加", "以及", "还有", "并且",
    "，", ",", "、", "；", ";", "。",
)


def _normalized_text(message: Optional[str]) -> str:
    return unicodedata.normalize("NFKC", str(message or "")).strip().lower()


def _contains_named_drug(text: str) -> bool:
    """Use the canonical lexicon without building its large regex on hot path."""
    return any(term in text for term in drug_name_free_text_terms())


def _contains_named_supplement(text: str) -> bool:
    return any(term in text for term in supplement_name_free_text_terms())


def _looks_like_contextual_medication_followup(text: str) -> bool:
    """Fail closed for short dose/combination follow-ups that omit a drug name."""
    return any(marker in text for marker in _CONTEXTUAL_MEDICATION_REFERENCES) and any(
        marker in text for marker in _CONTEXTUAL_MEDICATION_ACTIONS
    )


def _looks_like_implicit_medication_dose(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "吃", "服", "吞", "咽", "嚼", "含", "用", "吸", "吸入", "打", "注射", "喷", "滴", "涂", "贴",
        )
    ) and bool(
        _IMPLICIT_DOSE_RE.search(text)
    )


def _has_explicit_food_item_language(text: str) -> bool:
    return any(marker in text for marker in _EXPLICIT_FOOD_MARKERS)


def _dose_mentions_are_explicit_food_portions(text: str) -> bool:
    """Return true only when every tablet-shaped count binds to adjacent food.

    A meal can contain both food and a supplement, so clause-level food evidence
    is insufficient.  Adjacency keeps ordinary portions such as ``两片面包`` or
    ``鸡肉一片`` fast while ``一粒维C配苹果`` fails closed without enumerating
    every connector or supplement alias. Unknown modifiers deliberately fail
    closed to the quality model.
    """
    matches = tuple(_IMPLICIT_DOSE_RE.finditer(text))
    if not matches:
        return False
    for dose in matches:
        locally_bound = False
        for food in _EXPLICIT_FOOD_MARKERS:
            cursor = 0
            while (food_start := text.find(food, cursor)) >= 0:
                food_end = food_start + len(food)
                if food_end <= dose.start():
                    gap = text[food_end:dose.start()].replace(" ", "")
                    has_safe_prefix = True
                elif food_start >= dose.end():
                    gap = text[dose.end():food_start].replace(" ", "")
                    prefix = text[:dose.start()].rstrip()
                    has_safe_prefix = not prefix or prefix.endswith(
                        _FORWARD_FOOD_BINDING_PREFIXES
                    )
                else:
                    gap = ""
                    has_safe_prefix = True
                if has_safe_prefix and _FOOD_BINDING_GAP_RE.fullmatch(gap):
                    locally_bound = True
                    break
                cursor = food_start + 1
            if locally_bound:
                break
        if not locally_bound:
            return False
    return True


def is_explicit_medication_safety_language(text: str) -> bool:
    """Detect explicit inhaled medicines or supplement-shaped doses.

    Food anchors must not hide a separate supplement clause.  Conversely,
    nutrition descriptions without a tablet/capsule dose remain diet language.
    """
    normalized = _normalized_text(text)
    if any(marker in normalized for marker in _INHALED_MEDICATION_MARKERS):
        return True
    if any(
        marker in normalized for marker in _EXPLICIT_NON_MEDICAL_CONTEXT_MARKERS
    ):
        return False
    has_dose = bool(_IMPLICIT_DOSE_RE.search(normalized))
    return has_dose and (
        any(marker in normalized for marker in _SUPPLEMENT_SAFETY_MARKERS)
        or not _dose_mentions_are_explicit_food_portions(normalized)
    )


def is_low_risk_diet_record_language(
    text: str,
    *,
    named_supplement: Optional[bool] = None,
) -> bool:
    """Keep food records fast when nutrition words merely describe the food.

    A meal anchor or an explicit food item is mandatory, so terse multi-turn
    medication records such as ``记录吃了这个`` cannot enter this exception.
    ``药膳`` and vitamins used as food descriptors are allowed; named drugs,
    dose language, and analysis are rejected by surrounding safety floors.
    """
    normalized = _normalized_text(text)
    if not (
        any(marker in normalized for marker in _DIET_MEAL_MARKERS)
        or _has_explicit_food_item_language(normalized)
        or any(marker in normalized for marker in _NUTRITION_DESCRIPTION_MARKERS)
    ):
        return False
    has_ingestion = any(marker in normalized for marker in _DIET_INGESTION_MARKERS)
    has_descriptive_write = (
        any(marker in normalized for marker in _DIET_WRITE_MARKERS)
        and any(marker in normalized for marker in _NUTRITION_DESCRIPTION_MARKERS)
    )
    if not (has_ingestion or has_descriptive_write):
        return False
    if any(marker in normalized for marker in _ANALYSIS_MARKERS):
        return False
    # Nutrition adjectives alone are not enough to prove food when the same
    # clause carries a tablet/capsule-like dose.  Keep real meals such as
    # "早餐吃了两片面包" fast, but fail closed for "矿物质一粒".
    has_strong_food_anchor = (
        any(marker in normalized for marker in _DIET_MEAL_MARKERS)
        or _has_explicit_food_item_language(normalized)
    )
    has_dose = bool(_IMPLICIT_DOSE_RE.search(normalized))
    if has_dose and (
        not has_strong_food_anchor
        or not _dose_mentions_are_explicit_food_portions(normalized)
    ):
        return False
    medication_boundary_text = normalized.replace("药膳", "")
    if any(
        marker in medication_boundary_text for marker in _EXPLICIT_MEDICATION_MARKERS
    ):
        return False
    if named_supplement is None:
        named_supplement = _contains_named_supplement(normalized)
    return not named_supplement


def is_contextual_medication_safety_language(text: str) -> bool:
    """Referential medication guard shared by routing and phase-one copy."""
    normalized = _normalized_text(text)
    if (
        _has_explicit_food_item_language(normalized)
        or any(marker in normalized for marker in _EXPLICIT_NON_MEDICAL_CONTEXT_MARKERS)
    ) and not _IMPLICIT_DOSE_RE.search(normalized):
        return False
    return _looks_like_contextual_medication_followup(normalized)


def is_implicit_medication_dose_language(text: str) -> bool:
    """Dose-without-entity guard, evaluated after explicit meal evidence."""
    return _looks_like_implicit_medication_dose(_normalized_text(text))


def classify_answer_task_tier(
    message: Optional[str],
    *,
    has_attachments: bool,
) -> str:
    """Classify user-facing answer difficulty with a safety-first floor.

    Only explicit, single-domain read/write turns are casual. Health advice is
    at least balanced; medication, labs, red flags and medical attachments are
    high-stakes. Unknowns never fall to a fast user-facing answer model.
    """
    text = _normalized_text(message)
    # Run deterministic safety floors before the broader intent classifier.
    # Besides being fail-closed, this avoids paying its medication parser setup
    # cost for named-drug and acute-symptom turns that are unconditionally high.
    acute_symptom = contains_acute_symptom_language(text)
    if acute_symptom or _contains_named_drug(text):
        return "high_stakes"
    if is_explicit_medication_safety_language(text):
        return "high_stakes"
    named_supplement = _contains_named_supplement(text)
    low_risk_diet_record = (
        not has_attachments
        and is_low_risk_diet_record_language(
            text,
            named_supplement=named_supplement,
        )
    )
    if is_contextual_medication_safety_language(text):
        return "high_stakes"
    if low_risk_diet_record:
        return "casual"
    if named_supplement or _looks_like_implicit_medication_dose(text):
        return "high_stakes"
    high_stakes = (
        any(marker in text for marker in _HIGH_STAKES_MARKERS)
        or any(marker in text for marker in _ACUTE_QUERY_SAFETY_MARKERS)
    )
    if high_stakes:
        return "high_stakes"
    if (
        any(marker in text for marker in _KNOWN_BALANCED_DOMAIN_MARKERS)
        and any(marker in text for marker in _ANALYSIS_MARKERS)
    ):
        return "balanced"
    if (
        any(marker in text for marker in _EXPLICIT_NON_MEDICAL_CONTEXT_MARKERS)
        and any(marker in text for marker in _ANALYSIS_MARKERS)
    ):
        return "balanced"
    intent = classify_agent_utterance(text)
    if intent.domain in _HIGH_STAKES_DOMAINS:
        return "high_stakes"
    if has_attachments:
        # Opaque attachments may be medical reports even when the caption is
        # only "帮我看看这个".  Keep only explicit low-risk meal recording or
        # media creation on balanced; everything else gets the reasoning floor
        # before vision runs.
        if (intent.domain == "diet" and intent.is_write) or intent.domain == "aigc_media":
            return "balanced"
        return "high_stakes"
    if (
        intent.primary in {"read", "write"}
        and intent.domain != "unknown"
        and not intent.requires_reliable_tool_model
        and not any(marker in text for marker in _ANALYSIS_MARKERS)
    ):
        return "casual"
    if (
        intent.primary == "advice"
        and intent.domain == "unknown"
        and not any(marker in text for marker in _KNOWN_BALANCED_DOMAIN_MARKERS)
    ):
        return "high_stakes"
    return "balanced"


def pick_model_id_by_tier(task_tier: Optional[str], only_available: bool = True) -> Optional[str]:
    """按任务档选一个对应 speed_tier 的可用模型 id;目标档无模型时按 _SPEED_FALLBACK 降级;
    全无 → None(调用方回退默认)。

    安全不变量(fail-closed):tier 不在 _FAST_ELIGIBLE_TIERS 时,绝不返回 fast 档模型 ——
    fast 目标 / fast 回退项一律被跳过并地板到 non-fast。未知 tier → None(默认模型)。
    """
    tier_key = (task_tier or "").lower()
    speed = _TASK_TIER_TO_SPEED.get(tier_key)
    if speed is None:
        return None
    fast_allowed = tier_key in _FAST_ELIGIBLE_TIERS
    models = list_models(only_available=only_available)
    for target in _SPEED_FALLBACK.get(speed, (speed,)):
        if target == "fast" and not fast_allowed:
            # fail-closed:非白名单档不许落到弱模型,跳过 fast 继续找 balanced/reasoning。
            continue
        for m in models:
            if getattr(m, "speed_tier", None) == target:
                return m.id
    return None
