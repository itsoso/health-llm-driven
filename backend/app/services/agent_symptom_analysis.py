"""Closed symptom clarifications; data for an existing analysis, never consent."""

import re


_PAIN = r"(?:腹痛|肚子(?:疼|痛)|胃痛|胃疼|头痛|头疼|腰痛|腰疼)"
_LOCATION = r"(?:肚脐(?:周边|周围)|上腹(?:部)?|下腹(?:部)?|右下腹|左下腹|右上腹|左上腹|腹部正中)"
_OBSERVATION = re.compile(
    r"(?:我|本人)?(?:今天|今日|下午|现在)?(?:还是|仍然|还|有点|隐约|隐隐约约|隐隐|稍微)*"
    + _PAIN + r"(?:还没好|没好|减轻了?|加重了?|没有缓解|好一些了?)?"
    r"|(?:我|本人)?(?:疼痛|痛|疼)(?:在|位于)" + _LOCATION
    + r"(?:[、，,\s]+" + _LOCATION + r")*"
    r"|(?:我|本人)?(?:疼痛感|疼痛|痛|疼)(?:大概|约)?(?:是)?(?:10|[0-9])(?:分|/10)"
    r"|(?:[一二两三四五六七八九十]|[1-9])天前开始(?:疼|痛)"
    r"|(?:我|本人)?(?:有嗳气(?:的感觉)?|大便正常|没有腹泻|没有呕吐|没有发热)"
    r"|(?:我|本人)?吃饭(?:[一二两三四五六七八九十]|[1-9])个?小时后开始(?:疼|痛)"
    r"|(?:我|本人)?(?:吃|服用)了?(?:[一二两三四五六七八九十]|[1-9])天[\u4e00-\u9fffA-Za-z]{1,12}了?"
    r"|(?:最近|近)(?:[一二两三四五六七八九十]|[1-9])天(?:间或|偶尔)(?:吃|服用)[\u4e00-\u9fffA-Za-z]{1,12}"
    r"|[0-9]+(?:\.[0-9]+)?(?:毫克|mg)"
)
_UNSAFE_CONTEXT = re.compile(r"查|读取|记录|数据|删除|保存|同步|修改|更新|授权|之前|之后|以前|以后|仅|只|朋友|同事|别人|爸爸|妈妈|妻子|丈夫|孩子|父亲|母亲|他的|她的")
_CAUSE_QUESTION = re.compile(
    r"(?:(?:不知|不知道)(?:是)?什么原因|不是什么原因|为什么|为啥)"
    r"(?:我)?(?:又)?(?:开始)?(?:导致了?)?(?:胃肠疼痛|" + _PAIN + r")"
)


def is_symptom_analysis_followup(text: str) -> bool:
    """Every clause must be a self observation, with no read/write instruction."""
    if _UNSAFE_CONTEXT.search(text):
        return False
    normalized = text.strip(" 。!！")
    if _OBSERVATION.fullmatch(normalized):
        return True
    clauses = [part.strip() for part in re.split(r"[。，,；;\s]+", normalized) if part.strip()]
    return bool(clauses) and all(_OBSERVATION.fullmatch(clause) for clause in clauses)


def is_symptom_analysis_context(text: str) -> bool:
    """Consume oral clinical background without treating it as read scope."""
    clauses = [part.strip() for part in re.split(r"[。，,；;！？!?\s]+", text) if part.strip()]
    return bool(clauses) and all(
        is_symptom_analysis_followup(clause) or _CAUSE_QUESTION.fullmatch(clause)
        for clause in clauses
    )
