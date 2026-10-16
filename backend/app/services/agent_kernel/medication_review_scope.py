"""Closed medication-page review action; no medication changes or symptom reads."""

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
