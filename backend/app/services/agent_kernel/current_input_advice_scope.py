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
_CONDITION_NOTE = rf"(?:{_STAGE}|用户自述)"
_CONDITION_RE = re.compile(
    rf"(?P<name>[\u4e00-\u9fff]{{1,40}})(?:\({_CONDITION_NOTE}\)|（{_CONDITION_NOTE}）)?"
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

# Closed symptom clauses, including bare follow-up answers to a symptom
# question. Full consumption is essential: a symptom keyword cannot erase an
# additional read/write, medication, third-party or quoted request.
_GI_PAIN = r"(?:(?:胃|腹|肚子|上腹|下腹)(?:疼|痛)|疼|痛)"
_GI_SYMPTOM = rf"(?:嗳气|打嗝|反酸|烧心|胃胀|腹胀|恶心|呕吐|腹泻|便秘|呕血|黑便|便血|{_GI_PAIN})"
_GI_INTERVAL = r"(?:半|[一二两三四五六七八九十\d]{1,3})(?:个)?(?:小时|分钟)"
_GI_AFTER_MEAL = rf"(?:(?:吃(?:完)?饭|进食){_GI_INTERVAL}后|(?:饭后|餐后)(?:{_GI_INTERVAL})?)"
_GI_SYMPTOM_CLAUSE = rf"(?:我)?(?:{_GI_AFTER_MEAL})?(?:开始|有点|有|感觉)?{_GI_SYMPTOM}(?:的感觉)?"
_GI_STOOL_CLAUSE = r"(?:我)?(?:大便|排便)(?:正常|不正常|黑色|带血)"
_GI_DESCRIPTION_RE = re.compile(
    rf"(?:{_GI_SYMPTOM_CLAUSE}|{_GI_STOOL_CLAUSE})"
    rf"(?:[，,。；;、]?(?:{_GI_SYMPTOM_CLAUSE}|{_GI_STOOL_CLAUSE})){{0,7}}"
    r"(?:[，,。]?(?:怎么办|怎么回事|需要就医吗))?[。？?]?"
)

_GI_ADVICE_INSTRUCTIONS = """
本轮只依据用户当前输入的症状描述或症状补充，回应不适和必要的下一步，不把它解释成数据查询，也不要求查询日期。
明确本轮未查询个人记录；不查询、不保存健康记录，不使用历史、缓存或背景档案补齐病史和用药。可检索通用医学知识。
先回应当前描述；疼痛部位不明确时先问哪里疼，不凭饭后时间或嗳气直接诊断胃炎或溃疡，大便正常不能排除需要就医的原因。
询问疼痛部位、程度、持续时间和是否加重，以及是否有呕血、黑便或便血等伴随表现。不能将未提及的症状说成没有。
若用户已描述突然或剧烈腹痛、呕血、黑便或便血、胸痛、呼吸困难或晕倒，应优先提示立即寻求急救；未描述时给条件式警示，不能断言没有危险。
疼痛持续、反复或明显加重应及时就医。只给有条件的非药物建议，不给药物或补剂开始、停用、继续、剂量、频次、时点或疗程指令；用药问题向医生或药师核对。
""".strip()


def is_current_input_gastrointestinal_advice(text: str) -> bool:
    """Prove a bounded symptom-only turn, without personal tool authority."""
    if not isinstance(text, str) or len(text) > 256 or any(ch in text for ch in "\r\n\t"):
        return False
    candidate = text.replace(" ", "").replace("\u3000", "")
    if not (_GI_DESCRIPTION_RE.fullmatch(candidate)
            and (re.search(_GI_SYMPTOM, candidate)
                 or re.search(r"(?:大便|排便)(?:黑色|带血)", candidate))):
        return False
    # Existing explicit/self-observation write contracts take precedence.
    # This proof must not mask a record goal or block its authorized tools.
    from app.services.utterance_intent_classifier import classify_agent_utterance

    return not classify_agent_utterance(text).is_write

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
本轮只依据用户当前输入，回答其通用健康建议、启发或思路、睡前问题或所提供行动标题的解释；不要假设用户描述了病症。
这不是个人记录查询，不读取病史、用药、睡眠、设备数据或其他个人资料；不调用综合分析或恢复评估工具。可检索通用知识。
不得将历史、缓存、背景档案、标题或模型推测冒充已核实个人事实。明确本轮未查询个人记录；信息不足时说明限制并问必要问题，不要求用户为普通建议补查询日期。
请求启发或思路时，直接提供可选择的通用方向和一个轻量起步方法；不把上一轮未完成的个人数据查询自动带入本轮，也不声称已制定或保存个体化计划。
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


_DAILY_DOMAINS = r"(?:饮食|运动|睡眠)(?:(?:和|与|及|、|以及)?(?:饮食|运动|睡眠)){1,2}"
_DAILY_HORIZON = r"(?:今天|明天|本周|这周|下周)"
_DAILY_PLAN_RE = re.compile(
    r"(?:请你?|麻烦你?)?(?:(?:帮|为|给)我)?(?:规划|安排|制定)(?:一下)?"
    rf"(?:我(?:的)?)?{_DAILY_HORIZON}的?{_DAILY_DOMAINS}"
    r"(?:的)?(?:计划|安排|方案|草稿)?[。？?！!]?"
)
# A plan's time horizon is not a historical read window. Consume the complete
# question in either word order; do not strip basis clauses or unknown residue.
_DAILY_QUESTION_RE = re.compile(
    rf"(?:请问|请你?|麻烦你?)?(?:我)?{_DAILY_HORIZON}(?:我)?"
    rf"(?:(?:应该|该|应|要)?(?:如何|怎么|怎样)(?:安排|规划|制定)?{_DAILY_DOMAINS}"
    rf"(?:的)?(?:计划|安排|方案|草稿)?|"
    rf"的?{_DAILY_DOMAINS}(?:应该|该|应|要)?(?:如何|怎么|怎样)(?:安排|规划|制定))"
    r"[。？?！!]?"
)


def is_daily_planning_advice(text: str) -> bool:
    """A fully consumed draft request grants no personal read or write."""
    if not isinstance(text, str) or len(text) > 128:
        return False
    candidate = text.replace(' ', '').replace('\u3000', '')
    return bool(_DAILY_PLAN_RE.fullmatch(candidate) or _DAILY_QUESTION_RE.fullmatch(candidate))


def is_current_input_advice(text: str) -> bool:
    """Prove an entire current-input answer goal; unknown residue stays strict."""
    if (is_current_input_recovery_advice(text) or is_wearable_placement_question(text)
            or is_daily_planning_advice(text) or is_current_input_gastrointestinal_advice(text)):
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
    from app.services.agent_policy_retry import (
        is_general_advice_only_request, is_general_inspiration_request,
    )

    return is_general_inspiration_request(text) or (
        "睡眠" in text and is_general_advice_only_request(text)
    )


def current_input_advice_instructions(text: str) -> str:
    if is_current_input_gastrointestinal_advice(text):
        return _GI_ADVICE_INSTRUCTIONS
    if is_daily_planning_advice(text):
        return (CURRENT_INPUT_CONVERSATIONAL_ADVICE_INSTRUCTIONS
                + '\n本轮任务是饮食、运动和睡眠的通用安排草稿。直接按用户指定的领域和期限给出有条件、可选择的安排，'
                '而不是睡前问答；不查询个人记录，不要求查询日期。明确未核验个人数据、未保存计划。'
                '不使用历史上下文推断当前健康状况，不保证运动安全或给出用药补剂指令。'
                '\n先说明本轮未查询个人记录、未保存计划，再分别给所问领域的简短选项。'
                '用户没有提供目标、体能、禁忌或营养需求时，不默认减重或建议主食减半、制造热量缺口；'
                '不指定训练强度或要求完成固定运动量。运动选项须以无明显不适、符合已有医嘱和自身能力为前提。'
                '不能仅凭当前钟点断言适合入睡、保证睡眠时长或指定必须就寝时间；参考平时作息、困意和次日起床安排。'
                '若已到晚上，只安排余下时间，不补做白天任务。结尾可询问用户目标或需要考虑的限制。')
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


_GI_ADVICE = (
    "仅凭当前描述还不能确定原因；饭后出现不适或大便正常，都不足以确定病因或排除需要就医的情况。\n\n"
    "请补充：疼痛部位在哪里、程度如何、持续多久、有没有加重？是否伴有呕吐、黑便或便血？\n\n"
    "如果疼痛突然发生或很剧烈，或有呕血、黑便或便血、胸痛、呼吸困难、晕倒，请立即寻求急救，不要等待聊天回复。"
    "疼痛持续、反复或加重时，请及时就医。\n\n"
    "本轮未查询个人记录，也未保存症状记录。用药问题应向医生或药师核对。\n\n"
    "通用参考：[NHS 腹痛就医提示](https://www.nhs.uk/symptoms/stomach-ache/)"
)
_GI_URGENT_ADVICE = (
    "你描述中提到了可能需要紧急处理的表现，请立即寻求急救或前往急诊，不要等待线上判断。"
    "如无法安全前往，请联系当地急救服务。\n\n"
    "这不是病因诊断；大便的其他表现或饭后时间不能排除风险。就诊时告诉医护人员疼痛部位、程度、"
    "开始时间，以及呕吐和排便变化。\n\n"
    "本轮未查询个人记录，也未保存症状记录。用药问题应向接诊医生或药师核对。\n\n"
    "通用参考：[NHS 腹痛就医提示](https://www.nhs.uk/symptoms/stomach-ache/)"
)
_GI_URGENT_RE = re.compile(r"呕血|黑便|便血|(?:大便|排便)(?:黑色|带血)")


_DAILY_GUIDANCE = {
    "运动": "没有明显不适，且符合已有医嘱和自身能力时，可选一种熟悉的轻松活动，如散步或舒缓拉伸；感觉疲劳时可以休息，不必为完成安排额外加量。出现胸痛、明显呼吸困难或突然加重的不适时，停止活动并及时就医。",
    "饮食": "结合饥饿感和原有进餐节奏安排日常饮食，选择自己能耐受的食物，并遵守已知过敏限制和医生的饮食要求。已经吃过的餐次不用补吃；这里没有设定减重目标或调整摄入量。",
    "睡眠": "结合困意、平时作息和次日起床安排准备休息；可以先减少干扰，做熟悉的放松活动。有明显不适时先处理不适或寻求医疗帮助，不用强迫自己在某个钟点入睡。",
}


def _daily_planning_response(message: str) -> str:
    """Render only reviewed prose and closed domain/horizon tokens; no context."""
    if not is_daily_planning_advice(message):
        raise ValueError("Daily planning response requires a complete advice goal")
    candidate = message.replace(" ", "").replace("\u3000", "")
    horizon = re.search(_DAILY_HORIZON, candidate).group()
    domains = dict.fromkeys(re.findall(r"饮食|运动|睡眠", candidate))
    lines = [f"{horizon}的通用安排", "本轮未查询个人记录、未保存计划。以下选项需要结合你的实际状态选择，不能据此确认运动或饮食方案适合你。"]
    lines.extend(f"**{domain}**：{_DAILY_GUIDANCE[domain]}" for domain in domains)
    lines.extend(["按所问时段里还没过去的时间安排即可，不必补做已经错过的事项。",
                  "你更希望关注恢复、规律作息，还是建立活动习惯？也可以告诉我需要考虑的限制。"])
    return "\n\n".join(lines)


def local_advice_response(message: str) -> tuple[str, str] | None:
    """Return a proven goal kind and its reviewed exact answer, without reads.

    Existing symptom-recovery remains on its existing model/medical pipeline.
    A bare general-health request is not silently changed into sleep advice.
    """
    if is_daily_planning_advice(message):
        return "daily_planning_advice", _daily_planning_response(message)
    if is_current_input_gastrointestinal_advice(message):
        # Only fully parsed, non-negated current symptoms reach this branch.
        # Never interpolate model/history/client context into reviewed prose.
        candidate = message.replace(" ", "").replace("\u3000", "")
        return "gastrointestinal_symptom_advice", (
            _GI_URGENT_ADVICE if _GI_URGENT_RE.search(candidate) else _GI_ADVICE)
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
    name = match["name"].removesuffix("样不适")
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


def build_current_input_recovery_advice(illness_phrase: str) -> str:
    """Only emit starters the answer-scope parser can consume in full.

    Preserve accepted qualifiers verbatim. Unsupported labels use the existing
    general discomfort question instead of emitting an unexecutable read goal.
    Submitted text is still revalidated; this builder confers no authority.
    """
    suffix = "" if illness_phrase.endswith(("发作", "症状")) else "症状"
    candidate = f"我有{illness_phrase}{suffix}，今天该怎么休息和恢复？"
    if illness_phrase and is_current_input_recovery_advice(candidate):
        return candidate
    return "我身体不太舒服，今天该怎么休息和恢复？"


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
