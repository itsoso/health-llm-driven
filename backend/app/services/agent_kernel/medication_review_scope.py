"""Closed medication-page and symptom-context record reviews; no writes."""

import re

_PROMPT = re.compile(
    r"请基于我的在用药品列表[，,]帮我整理今天的用药执行情况、"
    r"可能需要向医生确认的问题、近期不适该如何描述。"
    r"不要建议我自行停药、换药或改剂量。"
)


def is_medication_review_request(text: str) -> bool:
    return _PROMPT.fullmatch(re.sub(r"[ \t]+", "", str(text or ""))) is not None


def has_medication_review_reference(text: str) -> bool:
    # Restrictive only: altered product actions cannot fall back to broad reads.
    return "在用药品列表" in str(text or "") and "用药执行情况" in str(text or "")


# A closed whole-turn grammar: symptom/drug-duration clauses are background,
# only the explicit records clause grants a bounded read. Unknown text is not
# silently discarded. Neither a drug name nor a symptom grants write authority.
_SYMPTOM = r"(?:肚子疼|肚子痛|胃疼|胃痛|腹痛|胃肠疼痛)"
_COUNT = r"(?:[0-9]{1,2}|[一二两三四五六七八九十]{1,3})"
_SEPARATOR = r"[，,。；;]*"
_RECORD_REVIEW = re.compile(
    rf"(?:(?:我)?{_SYMPTOM}(?:还没好|还没有好|仍未好转)?{_SEPARATOR})?"
    rf"(?:(?:不知道|不知|不是)什么原因(?:导致了?|引起了?){_SYMPTOM}{_SEPARATOR})?"
    rf"(?:(?:我)?(?:吃|服用)了(?P<duration>{_COUNT})天(?P<drug>[^，,。；;]{{1,32}}?)了?{_SEPARATOR})?"
    rf"(?:请)?(?:基于|根据|结合)(?:我(?:的)?)?(?:过去|最近|近)(?P<days>{_COUNT})(?:天|日)的?"
    r"(?P<domains>(?:饮食|补剂|服药|用药)(?:(?:、|和|及|与|，|,)?(?:饮食|补剂|服药|用药))*)记录"
    rf"{_SEPARATOR}(?:帮我)?分析(?:可能的?|的)?原因[。！!]?"
)
_RECORD_DOMAIN = re.compile(r"饮食|补剂|服药|用药")


def symptom_record_review_request(text: str) -> tuple[int, tuple[str, ...]] | None:
    from app.services.agent_longitudinal_read import _number
    from app.services.drug_lexicon import medication_reference_spans

    text = str(text or "")
    if len(text) > 512 or any(ord(c) < 32 for c in text):
        return None
    match = _RECORD_REVIEW.fullmatch(text.replace(" ", "").replace("　", ""))
    if match is None or not 1 <= (days := _number(match['days'])) <= 31:
        return None
    if match['drug'] is not None:
        drug = match['drug']
        if not 1 <= _number(match['duration']) <= 31 or (0, len(drug)) not in medication_reference_spans(drug):
            return None
    mapping = {'饮食': 'diet', '补剂': 'supplements', '服药': 'medication', '用药': 'medication'}
    domains = tuple(mapping[item] for item in _RECORD_DOMAIN.findall(match['domains']))
    if len(domains) != len(set(domains)):
        return None
    return days, domains


def has_symptom_record_review_reference(text: str) -> bool:
    # Restrictive routing only; failed complete parsing cannot grant legacy reads.
    text = str(text or "")
    return bool(re.search(r"(?:基于|根据|结合).*记录.*分析.*原因", text, re.S))


def medication_review_scope_contract_payload():
    from app.services.agent_kernel.health_semantics import (
        authorization_behavior_digest,
        authorization_grammar_digest,
        authorization_module_behavior_names,
    )

    return {
        "version": "medication-review-v1",
        "grammar": authorization_grammar_digest(globals()),
        "behavior": authorization_behavior_digest(
            globals(), authorization_module_behavior_names(globals(), __name__)
        ),
    }
