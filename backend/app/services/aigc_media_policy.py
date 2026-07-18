"""Deterministic safety boundary for Xiaoba's external Wan media work.

This is deliberately not the conversational intent classifier.  The LLM may
help propose a draft, but provider dispatch is rejected unless it is assigned
to a bounded wellness-communication purpose and it does not ask the generated
asset to diagnose, prescribe, dose, or promise treatment.  The small, explicit
red-line vocabulary is a fail-closed safety control, not a keyword shortcut for
deciding what a user meant in general conversation.
"""
from __future__ import annotations

import re
import unicodedata

from app.services.drug_lexicon import (
    contains_drug_name,
    contains_medication_reference,
    sensitive_name_free_text_terms,
)


ALLOWED_PURPOSES = frozenset(
    {
        "meal_visual",
        "movement_routine",
        "hydration_reminder",
        "sleep_routine",
        "wellness_story",
    }
)

_MEDICAL_RED_LINES = (
    "诊断", "确诊", "处方", "开药", "药方", "药量", "剂量", "用药方案", "治疗方案",
    "治愈", "疗效保证", "替代医生", "停药", "加药", "减药", "化验单解读", "检验报告解读",
    "diagnose", "diagnosis", "prescribe", "prescription", "dosage", "medication plan",
    "treatment plan", "cure", "replace a doctor",
)

# This is a provider-dispatch authorization check, not a general-language
# intent router. The bounded terms cover medical entities that must never be
# transformed into an instructional or persuasive external asset. The agent
# still uses semantic context to decide whether to offer an AIGC draft at all.
_MEDICAL_ENTITY_TERMS = (
    "糖尿病", "高血压", "低血压", "高血脂", "冠心病", "心脏病", "心衰", "肾病", "肝病",
    "甲状腺", "癌", "肿瘤", "化疗", "放疗", "感染", "哮喘", "抑郁", "焦虑", "癫痫",
    "中风", "脑卒中", "术后", "手术", "妊娠", "孕期", "diagnosis", "diabetes",
    "hypertension", "heart disease", "heart failure", "kidney disease", "liver disease",
    "thyroid", "cancer", "tumor", "chemotherapy", "radiotherapy", "infection", "asthma",
    "depression", "anxiety", "epilepsy", "stroke", "postoperative", "pregnan",
    "透析", "dialysis",
)
_MEDICATION_CLASS_TERMS = (
    "胰岛素", "激素", "类固醇", "抗生素", "抗凝", "降压药", "抗抑郁",
    "insulin", "steroid", "corticosteroid", "antibiotic", "anticoagulant",
    "antihypertensive", "antidepressant",
    "heparin", "testosterone", "hormone", "antiretroviral", "inhaler",
)
_CLINICAL_TREATMENT_TERMS = (
    "医疗", "临床", "患者", "病人", "医嘱", "疗程", "治疗", "疗法", "干预方案",
    "treat", "treating", "treatment", "therapy", "therapeutic", "regimen",
    "patient", "clinical", "medical", "disease",
    "hiv", "copd",
)
_MEDICATION_ACTION_TERMS = (
    "注射", "服用", "口服", "吃药", "用药", "停药", "加药", "减药", "滴注",
    "inject", "injection", "take", "oral", "medicate", "medication", "drug",
    "administer", "infuse", "infusion",
)
_DOSE_SIGNAL = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:mg|g|ug|μg|mcg|iu|ml|unit|units)\b|"
    r"\d+(?:[.,]\d+)?\s*(?:单位|片|粒|滴|毫克|微克|毫升)",
    re.IGNORECASE,
)


class AIGCMediaPolicyError(ValueError):
    """A draft falls outside the permitted external-media product boundary."""


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    # Invisible format characters are a common way to bypass text boundaries
    # (for example, a zero-width joiner inside a drug name). Keep normal word
    # separators intact, but remove only the non-rendering format category.
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Cf")
    return " ".join(normalized.split())


def validate_aigc_media_policy(*, purpose: str, prompt: str) -> str:
    """Return a normalized purpose or fail before any provider interaction."""
    normalized_purpose = _normalize(purpose)
    if normalized_purpose not in ALLOWED_PURPOSES:
        raise AIGCMediaPolicyError("AIGC 仅支持健康行动沟通类视觉内容")
    normalized_prompt = _normalize(prompt)
    has_medical_entity = any(term in normalized_prompt for term in _MEDICAL_ENTITY_TERMS)
    has_medication_class = any(term in normalized_prompt for term in _MEDICATION_CLASS_TERMS)
    has_clinical_treatment = any(term in normalized_prompt for term in _CLINICAL_TREATMENT_TERMS)
    has_medication_reference = contains_medication_reference(normalized_prompt)
    has_named_sensitive_substance = any(
        term in normalized_prompt
        for term in sensitive_name_free_text_terms()
        if len(term) > 2
    )
    has_medication_action = any(term in normalized_prompt for term in _MEDICATION_ACTION_TERMS)
    has_dose_signal = _DOSE_SIGNAL.search(normalized_prompt) is not None

    if (
        any(term in normalized_prompt for term in _MEDICAL_RED_LINES)
        or has_medical_entity
        or has_medication_class
        or has_clinical_treatment
        or contains_drug_name(normalized_prompt)
        or has_medication_reference
        or has_named_sensitive_substance
        or (has_dose_signal and has_medication_action)
    ):
        raise AIGCMediaPolicyError("AIGC 不能生成诊断、处方、用药或治疗决策内容")
    return normalized_purpose
