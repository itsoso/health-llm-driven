"""Exact proof for a self-authored symptom status observation, never a diagnosis.

This deliberately small grammar authorizes one new SymptomEntry containing the
entire utterance. It does not authorize illness updates, severity inference,
reminders, medication changes, or a second action. Unknown text fails closed.
"""
from __future__ import annotations

import re
import unicodedata


# These are the user's labels, not diagnoses assigned by this parser.
_SYMPTOM = r"(?:头痛|头疼|眼睛发痒|眼睛痒|鼻塞|流鼻涕|咳嗽|喉咙痛|嗓子痛|感冒)"
_SEP = r"[，,。；;]"
_SNEEZE_COUNT = r"(?:[1-9][0-9]?|一|二|两|三|四|五|六|七|八|九|十|一两|一二|两三|二三|三四|四五|五六|六七|七八|八九|九十)"
_RESIDUAL = rf"(?:偶尔)?(?:(?:还有|有)(?:一点|有点|轻微|点)?{_SYMPTOM}|打{_SNEEZE_COUNT}(?:次|个)喷嚏)"
_STATUS = re.compile(
    rf"(?:请记录|记录下来|记录一下|帮我记录一下|帮我记录){_SEP}?"
    rf"我的{_SYMPTOM}(?:状况|症状)?(?:已经|已)?(?:消失了|消失|恢复正常了|恢复正常|好了|缓解了)"
    rf"(?:{_SEP}(?:目前|现在)?一切正常)?"
    rf"(?:{_SEP}(?:(?:但|但是){_RESIDUAL}|除了{_RESIDUAL}(?:之外|以外)))?"
    r"[。.]?"
)


def parse_symptom_status_observation(message: object) -> dict[str, str] | None:
    """Return an exact write payload only for the entire explicit self request.

    Keep negative/resolved and residual facts together, without assigning an
    anatomical location or severity. Reject oversized text instead of clipping
    its authorization or description. No context or model data supplies proof.
    """
    if not isinstance(message, str) or not message or len(message) > 500:
        return None
    if any(unicodedata.category(char).startswith("C") for char in message):
        return None
    normalized = message.replace(" ", "").replace("\u3000", "")
    if _STATUS.fullmatch(normalized) is None:
        return None
    return {"body_part": "general", "description": message}
