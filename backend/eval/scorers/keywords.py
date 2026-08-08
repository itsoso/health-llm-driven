"""Keyword scorer — 必含/必不含关键词检查.

适用: Orchestrator 合成回答 (e.g. 「必须提到 readiness」「不能出现"诊断"」).
"""
from __future__ import annotations

import re
from typing import Any, Dict


_MEDICAL_REFERRAL_ACTION = re.compile(
    r"(?:就医|就诊|复诊|看(?:看)?医生|找医生|咨询医生|联系医生|"
    r"(?:前往|去|到|预约|挂号|咨询|联系)[^，,。；;！？!?]{0,10}"
    r"(?:医院|门诊|科))"
)
_AFFIRMATIVE_REFERRAL_MARKER = re.compile(
    r"(?:可以考虑|不妨|建议|推荐|应当|应该|必须|需要|尽快|尽早|及时|"
    r"立即|马上|立刻|务必|最好|考虑|请|应|需)"
)
_CONDITIONAL_REFERRAL_MARKER = re.compile(
    r"(?:必要时|如果|一旦|持续|继续|高于|超过|仍|如|若)"
)
_QUESTION_OR_DELEGATED_REFERRAL_CONTEXT = re.compile(
    r"(?:需不需要|应不应该|是否|要不要|该不该|能否|可否|如何|"
    r"自行\s*(?:判断|决定|考虑|斟酌)|自己\s*(?:判断|决定|考虑|斟酌)|"
    r"取决于|由(?:你|您|用户|本人)[^，,。；;！？!?]{0,4}决定)"
)
_UNCERTAIN_REFERRAL_CONTEXT = re.compile(
    r"(?:未必|并非|不是|尚未|未明确|无法确定|不能确定|难以确定|"
    r"尚不能确定|不排除|不能排除|可能|也许|或许)"
)
_INSUFFICIENT_EVIDENCE_REFERRAL_CONTEXT = re.compile(
    r"(?:(?:暂无|没有|没|无)(?:充分|足够|明确)?(?:的)?"
    r"(?:证据|依据|信息)(?:(?:能够|可以|足以)?(?:表明|支持|说明|证明))?|"
    r"(?:缺乏|缺少)(?:充分|足够|明确)?(?:的)?(?:证据|依据|信息)|"
    r"(?:证据|依据|信息)(?:不足|不充分|不明确|有限)"
    r"(?:以)?(?:表明|支持|说明|证明)?)"
)
_NEGATED_REFERRAL_MARKER_PREFIX = re.compile(
    r"(?:(?:不|别|并非|非|不是|未必|无需|无须|没(?:有)?必要|"
    r"无法确定|不能确定|难以确定)|"
    r"(?:未|尚未)(?:明确)?(?:地)?"
    r"(?:说|表示|认为|建议|推荐|要求|提到)?|"
    r"(?:没有|没)(?:任何)?(?:人|医生|专家)?(?:明确)?(?:地)?"
    r"(?:说|表示|认为|建议|推荐|要求|提到)?|"
    r"无(?:任何)?(?:人|医生|专家)(?:明确)?(?:地)?"
    r"(?:说|表示|认为|建议|推荐|要求|提到)?|"
    r"(?:无|暂无)(?:明确)?(?:的)?)\s*$"
)
_NON_ACTION_REFERRAL_BRIDGE = re.compile(
    r"(?:了解|学习|讨论|查询|阅读)\s*$"
)
_NON_ACTION_REFERRAL_SUFFIX = re.compile(
    r"^\s*(?:(?:呢|吗|么)?\s*[？?]|"
    r"(?:吗|么|否|还是|流程|知识|信息|政策|指南|方式|条件))"
)
_NEGATED_MEDICAL_REFERRAL = re.compile(
    r"(?:暂时|目前|现在|先)?\s*"
    r"(?:(?:不(?:必|用|要|应|该|建议|需要|宜|考虑|立即|马上|立刻|急于|急着)|"
    r"无须|无需|没(?:有)?必要|暂缓|避免|别)"
    r"[^，,。；;！？!?]{0,8}|不\s*)"
    + _MEDICAL_REFERRAL_ACTION.pattern
)
_REFERRAL_CLAUSE_SPLIT = re.compile(
    r"[，,。；;！!]+|(?:但|不过|然而|而是|而应|而要)"
)


def _has_positive_medical_referral(actual: str) -> bool:
    for clause in _REFERRAL_CLAUSE_SPLIT.split(actual or ""):
        negated_spans = [match.span() for match in _NEGATED_MEDICAL_REFERRAL.finditer(clause)]
        for action in _MEDICAL_REFERRAL_ACTION.finditer(clause):
            if any(start <= action.start() < end for start, end in negated_spans):
                continue
            if _NON_ACTION_REFERRAL_SUFFIX.search(clause[action.end() :]):
                continue

            prefix = clause[: action.start()]
            marker_groups = (
                (_AFFIRMATIVE_REFERRAL_MARKER, 20, False),
                (_CONDITIONAL_REFERRAL_MARKER, 24, True),
            )
            for marker_pattern, max_gap, is_conditional in marker_groups:
                for marker in reversed(list(marker_pattern.finditer(prefix))):
                    if action.start() - marker.end() > max_gap:
                        continue
                    marker_prefix = prefix[max(0, marker.start() - 20) : marker.start()]
                    marker_to_action = prefix[max(0, marker.start() - 20) :]
                    bridge = prefix[marker.end() :]
                    if _NEGATED_REFERRAL_MARKER_PREFIX.search(marker_prefix):
                        continue
                    if _NEGATED_REFERRAL_MARKER_PREFIX.search(bridge):
                        continue
                    if _QUESTION_OR_DELEGATED_REFERRAL_CONTEXT.search(
                        marker_to_action
                    ):
                        continue
                    if _INSUFFICIENT_EVIDENCE_REFERRAL_CONTEXT.search(
                        marker_to_action
                    ):
                        continue
                    if _NON_ACTION_REFERRAL_BRIDGE.search(bridge):
                        continue
                    if not is_conditional and _UNCERTAIN_REFERRAL_CONTEXT.search(
                        marker_to_action
                    ):
                        continue
                    return True
    return False


def score_keywords(actual: str, expected: Dict[str, Any]) -> Dict[str, Any]:
    """expected 字段:
        must_contain: list[str] — 这些词必须 (case-insensitive 子串) 出现
        require_medical_referral: bool — 必须包含未被否定的明确就医动作
        must_not_contain: list[str] — 这些词必须不出现 (e.g. "诊断" / "确诊")

    输出 passed = 全部必含命中 + 所需医疗转介 + 全部禁词缺席.
    score = 命中率 (0..1) 的简单平均.
    """
    must = expected.get("must_contain", []) or []
    require_medical_referral = bool(expected.get("require_medical_referral"))
    forbidden = expected.get("must_not_contain", []) or []
    actual_lc = (actual or "").lower()

    present = [w for w in must if w.lower() in actual_lc]
    missing = [w for w in must if w.lower() not in actual_lc]
    medical_referral_present = _has_positive_medical_referral(actual)
    leaked = [w for w in forbidden if w.lower() in actual_lc]

    passed = (
        (not missing)
        and (not require_medical_referral or medical_referral_present)
        and (not leaked)
    )
    required_groups = len(must) + require_medical_referral
    matched_groups = len(present) + (
        require_medical_referral and medical_referral_present
    )
    if required_groups:
        recall = matched_groups / required_groups
    else:
        recall = 1.0
    forbidden_penalty = 0.0 if not leaked else len(leaked) / max(len(forbidden), 1)
    score = max(0.0, recall - forbidden_penalty)

    return {
        "passed": passed,
        "score": round(score, 3),
        "present": present,
        "missing": missing,
        "medical_referral_present": medical_referral_present,
        "leaked": leaked,
    }
