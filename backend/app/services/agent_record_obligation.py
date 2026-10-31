"""Detect completion obligations without granting health-data authority.

A domain classifier may not recognize a requested record. That must not turn a
clear create request into successful chat. This predicate supplies only a
completion obligation: capability policy and domain validation still own every
read and write permission.
"""
from __future__ import annotations

import re

from app.services.utterance_intent_lexicon import WRITE_COMMAND_ACTIONS
from app.services.write_intent_scope import (
    has_explicit_authorizing_write_request,
    has_non_authorizing_write_context,
    normalize_write_scope_text,
    split_write_clauses,
)

_CREATE_ACTION = "|".join(re.escape(action) for action in sorted(WRITE_COMMAND_ACTIONS, key=len, reverse=True))
_REQUEST_PREFIX = r"(?:(?:请你?|麻烦你?|劳驾|帮我|替我|给我|你帮我))*"
_LEADING_CREATE_ACT = re.compile(
    rf"^{_REQUEST_PREFIX}"
    rf"(?P<action>{_CREATE_ACTION})"
)
_OTHER_OPERATION = re.compile(r"^(?:请你?|麻烦你?|帮我|替我|给我)*(?:删除|删掉|撤销|取消|修改|更新|更正|调整)")
# These are subject/provenance cues, not a list of health activities. They narrow
# obligations only; they are deliberately insufficient to authorize any effect.
_OTHER_SUBJECT = re.compile(
    r"爸爸|妈妈|父亲|母亲|爷爷|奶奶|姥姥|姥爷|外公|外婆|"
    r"儿子|女儿|孩子|丈夫|妻子|老公|老婆|朋友|同事|同学|邻居|"
    r"哥哥|姐姐|弟弟|妹妹|对象|患者|病人|他(?:的)?|她(?:的)?|"
    r"小明|张三|李四|王五"
)
_CAPABILITY_INQUIRY = re.compile(
    r"^(?:请问)?(?:你|系统|小气候|小巴|这个应用|这里)(?:能否|能|可以|支持|会不会|是否)"
)
_TRAILING_RECORD_REVOCATION = re.compile(
    r"(?:^|[，,；;。])(?:算了[，,]?)?(?:都|全部|这次|先)?"
    r"(?:不要|别|不用|不必)(?:再)?(?:记|记录|保存|登记)(?:了)?[。.!！]*$"
)
_FUTURE_OR_CONDITIONAL = re.compile(
    r"明天|后天|下周|下个月|未来|以后|稍后|回头|一会儿|"
    r"假如|假设|假使|如果|等我|等到|待到|一旦"
)


def record_obligation_requested(text: str) -> bool:
    """Return a domain-independent create obligation, never tool authority.

    Retain the shared speech-act and untrusted-context checks. The leading-act
    fallback evaluates only an imperative prefix because the legacy authorizer
    also infers medical subjects from payload words: unknown activities and
    quantity adjuncts must not erase an otherwise explicit request.
    """
    from app.services.agent_kernel.health_semantics import active_health_instruction_text

    active = active_health_instruction_text(str(text or ""))
    normalized = normalize_write_scope_text(active)
    if (
        not normalized
        or _OTHER_OPERATION.match(normalized)
        or _OTHER_SUBJECT.search(normalized)
        or _CAPABILITY_INQUIRY.match(normalized)
        or _FUTURE_OR_CONDITIONAL.search(normalized)
        or _TRAILING_RECORD_REVOCATION.search(normalized)
        or has_non_authorizing_write_context(active)
    ):
        return False
    act = _LEADING_CREATE_ACT.match(normalized)
    if act and normalized[act.end():].startswith(("什么", "哪些", "怎么", "如何", "是否")):
        return False
    if has_explicit_authorizing_write_request(active):
        return True
    if act and has_explicit_authorizing_write_request(act.group(0)):
        return True
    # Full-turn provenance/revocation checks above remain authoritative. A later
    # coordinated clause must not erase an earlier explicit save request.
    return any(has_explicit_authorizing_write_request(clause)
               for clause in split_write_clauses(active))


_BARE_RECORD_ACT = re.compile(
    rf"^{_REQUEST_PREFIX}(?:{_CREATE_ACTION})(?:一下|下来|下|吧|了|即可|就行)*$"
)
_ANALYSIS_ADJUNCT = re.compile(
    rf"^{_REQUEST_PREFIX}(?:计算|估算|分析|评估|解释|比较|总结|解读|核算|统计|查看|查询|说明)"
)
_RECORD_METADATA = re.compile(
    r"^(?:这是|这条是|本条是|本次是|此为)[^，,；;。.!！]*(?:记录|数据)$"
)

_RECORD_PART_BOUNDARY = re.compile(
    rf"[，,；;。.!！]\s*(?:另外|此外|同时|并且|还有|以及|然后|之后)(?:再)?\s*"
    rf"|(?:另外|此外|同时|并且|还有|以及|然后|之后)(?:再)?\s*(?={_REQUEST_PREFIX}(?:{_CREATE_ACTION}))"
    rf"|[，,；;。.!！]\s*再\s*"
    rf"|(?:[，,；;。.!！]\s*|并|再)(?={_REQUEST_PREFIX}(?:{_CREATE_ACTION}))"
)


def record_obligation_parts(text: str) -> tuple[str, ...]:
    """Preserve coordinated create obligations without interpreting their domain.

    This is a coverage check for single-target planners, not an authorization
    parser. Plain commas and noun-list conjunctions remain inside a part so
    quantity/time adjuncts and multi-food meals do not become invented tasks.
    Returned fragments retain their source speech acts; no create verb is added.
    """
    from app.services.agent_kernel.health_semantics import active_health_instruction_text

    active = active_health_instruction_text(str(text or "")).strip()
    if not record_obligation_requested(active):
        return ()
    parts: list[str] = []
    start = 0
    boundaries = tuple(_RECORD_PART_BOUNDARY.finditer(active))
    for index, boundary in enumerate(boundaries):
        part = active[start:boundary.start()].strip(" \t\r\n，,；;。.!！")
        normalized = normalize_write_scope_text(part)
        next_boundary = boundaries[index + 1].start() if index + 1 < len(boundaries) else len(active)
        following = normalize_write_scope_text(active[boundary.end():next_boundary]).strip("，,；;。.!！")
        if (_RECORD_METADATA.fullmatch(normalized)
                or _BARE_RECORD_ACT.fullmatch(following)
                or _ANALYSIS_ADJUNCT.match(following)):
            # Context labels, a postfix request to save the same fact, and an
            # analysis of that fact do not introduce another record target.
            continue
        act = _LEADING_CREATE_ACT.match(normalized)
        body = normalized[act.end():] if act else normalized
        body = body.strip("，,；;。.!！")
        if re.fullmatch(r"(?:(?:我|本人|自己|今天|今日|昨天|昨日|刚才|刚刚|已经|已|的))*", body):
            # A coordinator before the first fact is an adjunct, not a second
            # task: ``记录我同时吃了鸡蛋和牛奶`` still names one meal.
            continue
        parts.append(part)
        start = boundary.end()
    if not parts:
        return (active,)
    remainder = active[start:].strip(" \t\r\n，,；;。.!！")
    if remainder:
        parts.append(remainder)
    return tuple(parts)
