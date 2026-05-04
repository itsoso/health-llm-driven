"""
Memory reference detector — heuristic to check if LLM output references
previously-injected user memory.

WHY: orchestrator._inject_memory injects up to 4 stages (conversation memory /
case timeline / directives / hybrid retrieval) into user_prompt. Audit log
records what was *injected* but not what was *referenced* in LLM output —
so we couldn't tell if the LLM actually used memory or just generated based
on Twin data.

Phase 0.3 (2026-05-04): add this lightweight regex-based detector. Not
perfect (LLM might paraphrase memory without using marker phrases), but
captures the explicit cases. Result feeds into agent_audit_log.result_detail
so observability dashboard can compute reference-rate over time.

Detection markers — Chinese, anchored on phrases that *only* make sense
when LLM is recalling something from memory (not just describing current
Twin state):

- 时间锚定: "之前/此前/上次/上回/上周/前天/几天前"
- 历史锚定: "记得你/根据你的/根据您之前/历史上/曾经/过去"
- 持续性锚定: "一直/向来/惯常/平时"
- 对话回指: "你提到/你说过/你之前提到"
"""
from __future__ import annotations

import re

# 编译一次, 避免每次调用 re.compile.
# Markers 设计原则:
# - 必须是只在 "回忆" 语境出现的短语. 单字"前/上"匹配范围太广 (例: "睡前刷牙"), 不用.
# - 用 (?:...) 非捕获组, search 比 match 更宽松 (LLM 输出任意位置).
_MEMORY_REF_PATTERN = re.compile(
    r"(?:"
    # 时间锚定 (相对过去)
    r"之前(?:提到|说过|讲过|遇到)?"
    r"|此前"
    r"|上[次回周]"
    r"|前几天|几天前|前几次"
    r"|过往|过去"
    # 历史/记忆锚定
    r"|记得[你您]"
    r"|根据[你您](?:之前|的历史|历史上|的偏好|的习惯|的记录)"
    r"|按[你您]之前"
    r"|历史上"
    r"|曾经"
    # 持续性 (暗示来自历史)
    r"|[你您]一直"
    r"|[你您]向来"
    r"|[你您]惯常"
    r"|平时[你您]"
    # 对话回指
    r"|[你您]提到(?:过)?"
    r"|[你您]说过"
    r"|[你您]之前(?:提到|说过|讲过|提及)"
    r")"
)


def detect_memory_reference(text: str) -> bool:
    """
    Best-effort heuristic: True iff text contains an explicit memory-recall marker.

    False negatives expected: LLM paraphrases memory without using a marker phrase.
    False positives rare: marker phrases are anchored to recall semantics.

    Empty / None text → False.
    """
    if not text:
        return False
    return bool(_MEMORY_REF_PATTERN.search(text))


def find_memory_references(text: str) -> list[str]:
    """
    Same detection but returns matched marker phrases for debugging / dashboard
    inspection ("which phrase tipped us off?").
    """
    if not text:
        return []
    return _MEMORY_REF_PATTERN.findall(text)
