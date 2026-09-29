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

# Complete questions only: these describe an answer goal, never read authority.
_HEALTH_ADVICE = r"(?:请)?(?:给|给出|提供)(?:我)?(?:一些|一点|些|点)?(?:健康|通用健康)(?:的)?建议"
_BEDTIME = r"(?:我)?(?:现在|今晚|今天晚上)(?:是不是|是否)?(?:可以|能|该|应该)(?:去)?睡觉(?:了)?(?:吗)?"
_BEDTIME_RE = re.compile(
    rf"(?:{_HEALTH_ADVICE}[，,。])?{_BEDTIME}[？?。]?|"
    rf"我准备睡觉了[，,]{_HEALTH_ADVICE}[。？?]?|{_HEALTH_ADVICE}[。？?]?"
)
_ACTION_EXPLANATION_RE = re.compile(
    r"请解释今天这条行动：[“\"](?P<title>[^“”\"\r\n]{1,120})[”\"]。"
    r"告诉我为什么现在做、怎么做，以及什么情况下不适合做。"
)
_CLINICAL_NOTE = rf"(?:{_STAGE}|[Hh][Pp](?:阳性|阴性)|(?:胃|胃窦|胃体|十二指肠)(?:前壁|后壁|侧壁|大弯|小弯))"
_FOLLOW_UP_TITLE_RE = re.compile(
    rf"(?:复查|检查)[:：](?P<condition>[\u4e00-\u9fff]{{1,40}})"
    rf"(?:\({_CLINICAL_NOTE}(?:[，,、]{_CLINICAL_NOTE}){{0,3}}\)|"
    rf"（{_CLINICAL_NOTE}(?:[，,、]{_CLINICAL_NOTE}){{0,3}}）)?"
)

CURRENT_INPUT_CONVERSATIONAL_ADVICE_INSTRUCTIONS = """
本轮只依据用户当前输入，回答其通用健康建议、睡前问题或所提供行动标题的解释；不要假设用户描述了病症。
这不是个人记录查询，不读取病史、用药、睡眠、设备数据或其他个人资料；不调用综合分析或恢复评估工具。可检索通用知识。
不得将历史、缓存、背景档案、标题或模型推测冒充已核实个人事实。明确本轮未查询个人记录；信息不足时说明限制并问必要问题，不要求用户为普通建议补查询日期。
睡前问题先回应如何判断是否适合休息，给有条件的非药物建议；不能断言其健康状态、安全性、睡眠债或个人作息已经核实。不要凭钟点保证可以入睡或忽略急性不适。
行动解释分清一般目的、如何准备和何时应暂停或咨询专业人员。仅凭标题不能确定为什么安排在今天、具体检查项目、禁忌或医嘱，须明确这些未知，不编造个体化方案或宣称执行了行动。
保留适用的就医警示。不要给药物或补剂的开始、停用、继续、剂量、频次、时点或疗程指令，用药问题只提示向医生或药师核对。
""".strip()


def is_current_input_advice(text: str) -> bool:
    """Prove an entire current-input answer goal; unknown residue stays strict."""
    if is_current_input_recovery_advice(text):
        return True
    if not isinstance(text, str) or len(text) > 512 or any(ch in text for ch in "\r\n\t"):
        return False
    candidate = text.replace(" ", "").replace("\u3000", "")
    if _BEDTIME_RE.fullmatch(candidate):
        return True
    match = _ACTION_EXPLANATION_RE.fullmatch(candidate)
    if match:
        title = _FOLLOW_UP_TITLE_RE.fullmatch(match["title"])
        return bool(title and _is_bounded_condition(title["condition"]))
    from app.services.agent_policy_retry import is_general_advice_only_request

    return is_general_advice_only_request(text)


def current_input_advice_instructions(text: str) -> str:
    if is_current_input_recovery_advice(text):
        return CURRENT_INPUT_RECOVERY_ADVICE_INSTRUCTIONS
    return CURRENT_INPUT_CONVERSATIONAL_ADVICE_INSTRUCTIONS if is_current_input_advice(text) else ""


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
