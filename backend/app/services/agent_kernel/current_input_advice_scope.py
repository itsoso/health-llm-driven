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
    rf"我准备睡觉了[，,]{_HEALTH_ADVICE}[。？?]?"
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


_WEARABLE_PLACEMENT_QUESTION = re.compile(
    r"(?:佳明(?:手表)?|Garmin(?:手表)?|智能手表|手表)"
    r"(?:戴|佩戴)在(?:脚踝|脚腕|手腕)(?:上)?[，,]"
    r"(?:睡眠(?:和|与|、)血氧|血氧(?:和|与|、)睡眠|睡眠|血氧)"
    r"(?:的)?(?:读数|测量|监测)(?:会受影响吗|有影响吗|会不会受影响)[？?]?",
    re.IGNORECASE,
)
_WEARABLE_PLACEMENT_INSTRUCTIONS = (
    "本轮是佩戴位置对可穿戴设备测量原理的通用解释，不是个人数据查询。"
    "仅解释传感器接触、佩戴位置和算法适用性的可能影响；"
    "不能推断这位用户实际佩戴方式、某次读数是否准确或任何诊断。"
    "未提供具体型号和官方支持信息时，不声称脚踝佩戴受到厂商支持；可查询通用知识。"
    "说明本轮未读取个人记录，不要求为一般原理解释提供查询日期。"
)


def is_wearable_placement_question(text: str) -> bool:
    return bool(isinstance(text, str) and _WEARABLE_PLACEMENT_QUESTION.fullmatch(text.strip()))


def is_current_input_advice(text: str) -> bool:
    """Prove an entire current-input answer goal; unknown residue stays strict."""
    if is_current_input_recovery_advice(text) or is_wearable_placement_question(text):
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

    return "睡眠" in text and is_general_advice_only_request(text)


def current_input_advice_instructions(text: str) -> str:
    if is_wearable_placement_question(text):
        return _WEARABLE_PLACEMENT_INSTRUCTIONS
    if is_current_input_recovery_advice(text):
        return CURRENT_INPUT_RECOVERY_ADVICE_INSTRUCTIONS
    return CURRENT_INPUT_CONVERSATIONAL_ADVICE_INSTRUCTIONS if is_current_input_advice(text) else ""


# Server-owned prose, not a model-output keyword denylist. No title, history,
# context or model text is interpolated into these answers. Sources are public
# editorial provenance, not evidence of an individual's state or appointment.
_SLEEP_ADVICE = (
    "如果你已经困了、接近平时就寝时间，可以开始准备休息；这不是对你当前身体状况的安全判断。"
    "先放下屏幕，让卧室安静、昏暗，做些轻松的睡前活动；没有睡意时不必强迫入睡。\n\n"
    "本轮未查询个人记录，因此不能判断你是否缺觉，也不能仅凭这句话确认现在入睡是否适合你。"
    "如果有明显或突然加重的不适，先寻求医疗帮助，不要把睡觉当作处理不适的方法。"
    "你现在是困了，还是有不舒服、担心睡不着？\n\n"
    "通用参考：[NHS 睡眠习惯建议](https://www.nhs.uk/every-mind-matters/mental-wellbeing-tips/how-to-fall-asleep-faster-and-sleep-better/)"
)
_FOLLOW_UP_ADVICE = (
    "这条行动是在提示复查，但标题本身不能证明今天就是医生确定的检查日期。\n\n"
    "为什么做：复查通常用于和医生重新评估病情及后续安排；为什么安排在今天，需要核对原来的医嘱或预约通知，不能仅从标题推断。\n\n"
    "怎么准备：先确认具体检查项目、预约时间和准备要求；整理之前的报告、近期症状变化和想问的问题，带给接诊医生。"
    "是否需要空腹，以及药物相关注意事项，应向检查机构、医生或药师核对。\n\n"
    "什么情况下不适合直接照做：检查项目或准备要求不清楚，或身体出现新的、明显加重的不适时，先联系医疗人员确认，"
    "不要自行决定停药、改方案或推迟必要的就医。具体禁忌取决于检查项目和个人情况。\n\n"
    "本轮未查询个人记录，也没有执行或更改这条行动。你可以提供具体检查名称或原医嘱，我再帮你解释文字含义。\n\n"
    "通用参考：[NHS 就诊提问清单](https://www.nhs.uk/nhs-services/gps/what-to-ask-your-doctor/)"
)
CURRENT_INPUT_UNVERIFIED_ANSWER_NOTICE = (
    "本轮未查询个人记录，无法核实生成内容中的个人数据或医嘱依据，已停止提供这部分结论。"
    "请补充你想解释的具体信息；一般建议不需要先查询历史记录。"
)


def local_advice_response(message: str) -> tuple[str, str] | None:
    """Return a proven goal kind and its reviewed exact answer, without reads.

    Existing symptom-recovery remains on its existing model/medical pipeline.
    A bare general-health request is not silently changed into sleep advice.
    """
    if (is_current_input_recovery_advice(message) or is_wearable_placement_question(message)
            or not is_current_input_advice(message)):
        return None
    candidate = message.replace(" ", "").replace("\u3000", "")
    if _ACTION_EXPLANATION_RE.fullmatch(candidate):
        return "follow_up_explanation", _FOLLOW_UP_ADVICE
    if "睡" in candidate:
        return "bedtime_advice", _SLEEP_ADVICE
    return None


def guard_current_input_answer(message: str, answer: str) -> tuple[str, bool]:
    expected = local_advice_response(message)
    if expected is not None and answer != expected[1]:
        return CURRENT_INPUT_UNVERIFIED_ANSWER_NOTICE, False
    return answer, True


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
