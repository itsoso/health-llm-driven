"""Closed body-measurement product review; never authorizes writes or diagnosis.

Full consumption separates trend evidence from today's lifestyle evidence and
future recording advice. Unknown owners, filters and appended clauses fail shut.
"""
import re

_REVIEW = re.compile(
    r'(?:请)?(?:基于|根据|结合)(?:我(?:自己|本人|个人)?|本人)的体重和腰围记录，'
    r'复盘趋势和代谢风险，结合今天饮食和运动给出调整建议。'
    r'请说明我接下来还应该记录哪些数据。?'
)


def is_body_measurement_review_request(text: str) -> bool:
    if not isinstance(text, str):
        return False
    normalized = re.sub(r'[ \t]+', '', text.strip()).replace(',', '，')
    return _REVIEW.fullmatch(normalized) is not None


def has_body_measurement_review_reference(text: str) -> bool:
    """Restrictive marker only: unsupported variants cannot fall into legacy reads."""
    return bool(re.search(r'体重.*腰围|腰围.*体重', str(text or ''), re.S)
                and re.search(r'复盘|趋势|代谢风险', str(text or '')))


def body_measurement_review_scope_contract_payload():
    from app.services.agent_kernel.health_semantics import (
        authorization_behavior_digest, authorization_grammar_digest,
        authorization_module_behavior_names,
    )
    return {
        'version': 'body-measurement-review-v1',
        'grammar': authorization_grammar_digest(globals()),
        'behavior': authorization_behavior_digest(
            globals(), authorization_module_behavior_names(globals(), __name__)),
    }
