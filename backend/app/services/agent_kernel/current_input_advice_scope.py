"""Prove a narrow starter asks for advice using only its stated symptoms.

This is an answer-scope proof, never personal-data read or write authority.
Match the complete original utterance; do not recover a match by discarding
quoted material, unknown annotations, other people, or additional clauses.
"""

from __future__ import annotations

import re


CURRENT_INPUT_RECOVERY_ADVICE_INSTRUCTIONS = """
本轮只依据用户当前输入中明确描述的病症，结合可靠的通用健康知识，回答今天如何休息和恢复。
这段描述不授权查询个人记录；不读取病史、用药、睡眠、设备数据或其他个人资料，也不调用会读取这些资料的综合分析或恢复评估工具。
不得将历史汇总、缓存、背景档案或模型推测冒充本轮查询结果。说明本轮未查询个人记录，建议仅基于当前描述；信息不足时说明限制并询问必要症状。
可检索通用医学知识，但不能以检索或工具参数扩大个人数据权限。不要宣称已核实诊断、指标或用药。只提供非药物的休息和恢复建议，保留适用的就医警示。
不要给出任何药物或补剂的执行建议，包括开始、继续原方案、按时服用、剂量、频次、服药时点或疗程；用药只提示向医生或药师核对。
""".strip()

_REQUEST_RE = re.compile(
    r"我有(?P<conditions>[^，,\r\n]+)[，,]今天该怎么休息和恢复[？?]"
)
_UNSPECIFIED_RE = re.compile(r"我身体不太舒服[，,]今天该怎么休息和恢复[？?]")
# Stage annotations are literal clinical data, not discarded arbitrary text.
# Matching brackets and one annotation per entity are intentional boundaries.
_STAGE = r"(?:[AHS][12]期|(?:I{1,3}|IV|[ⅠⅡⅢⅣ一二三四1-4])期|急性期|慢性期|活动期|恢复期|缓解期)"
_CONDITION_RE = re.compile(
    rf"(?P<name>[\u4e00-\u9fff]{{1,40}})(?:\({_STAGE}\)|（{_STAGE}）)?"
)
_CLINICAL_TERM_RE = re.compile(
    r"(?:急性|慢性|复发性|过敏性|非过敏性|萎缩性|非萎缩性|感染性|病毒性|细菌性){0,3}"
    r"(?:鼻|鼻窦|咽|喉|扁桃体|支气管|肺|胃|胃窦|十二指肠|肠|皮肤|关节){1,2}"
    r"(?:炎|溃疡)(?:伴(?:糜烂|溃疡))?"
)
_SYMPTOMS = frozenset({
    "感冒", "发热", "发烧", "咳嗽", "过敏", "乏力", "鼻塞", "流涕", "流鼻涕",
    "头痛", "头疼", "头晕", "胃痛", "胃疼", "腹痛", "腹泻", "恶心", "呕吐",
    "咽痛", "肌肉酸痛", "关节痛",
})


def _is_bounded_condition(value: str) -> bool:
    for suffix in ("急性发作", "发作", "症状"):
        if value.endswith(suffix):
            value = value[:-len(suffix)]
            break
    match = _CONDITION_RE.fullmatch(value)
    if match is None:
        return False
    name = match["name"]
    if name in _SYMPTOMS or _CLINICAL_TERM_RE.fullmatch(name) is not None:
        return True
    # Reuse the existing exact terminology contract for other known illnesses;
    # a clinical-looking suffix alone never proves an otherwise unknown term.
    from app.services.agent_kernel.health_semantics import illness_entity_has_medical_semantics

    return illness_entity_has_medical_semantics(name)


def is_current_input_recovery_advice(text: str) -> bool:
    """Recognize complete generated recovery advice without granting reads."""
    if not isinstance(text, str) or len(text) > 512 or any(ch in text for ch in "\r\n\t"):
        return False
    # Horizontal spacing is common around clinical annotations and '+'. Other
    # whitespace/control characters remain visible and cannot conceal clauses.
    candidate = text.replace(" ", "").replace("\u3000", "")
    if _UNSPECIFIED_RE.fullmatch(candidate):
        return True
    match = _REQUEST_RE.fullmatch(candidate)
    if match is None:
        return False
    conditions = match["conditions"]
    if not conditions.endswith(("症状", "发作")):
        return False
    parts = re.split(r"[、+]", conditions)
    return 1 <= len(parts) <= 6 and all(_is_bounded_condition(part) for part in parts)


def current_input_advice_scope_contract_payload() -> dict[str, str]:
    """Fingerprint the complete proof grammar, prompt and implementation."""
    from app.services.agent_kernel.health_semantics import (
        authorization_behavior_digest,
        authorization_grammar_digest,
        authorization_module_behavior_names,
    )

    return {
        "version": "current-input-advice-scope-v1",
        "grammar": authorization_grammar_digest(globals()),
        "behavior": authorization_behavior_digest(
            globals(), authorization_module_behavior_names(globals(), __name__)),
    }
