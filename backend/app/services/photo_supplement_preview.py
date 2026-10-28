"""Pure photo candidate presentation; this module never authorizes writes.

A result is an untrusted, unsaved preview. Callers must bind it to the authenticated
owner and source image/message, durably present it, and obtain confirmation before
using a separate write-intent handler. Recognition fields cannot supply identity,
quantity, record date, endpoint, or any authorization metadata.
"""
from __future__ import annotations

import re
from typing import Any

_REQUEST = re.compile(
    r"记录\s*(?P<total>[2-8二两三四五六七八])\s*种补剂\s*"
    r"NAC\s*(?P<nac>[1-9])\s*粒\s*[，,、]?\s*"
    r"其他各\s*(?P<other>[1-9])\s*粒[。.]?",
    re.IGNORECASE,
)
_COUNTS = dict(zip("二两三四五六七八", (2, 2, 3, 4, 5, 6, 7, 8)))
_NAC_NAME = re.compile(r"^NAC(?:$|[\s（(])", re.IGNORECASE)
_NAME = re.compile(r"[\w\s+()（）.,·%μ/-]{1,80}")
_PHOTO_REFERENCE = re.compile(
    r"(?:请|帮我|请帮我)?记录(?:一下)?"
    r"(?:以上|上面|上一张|这张|刚才那张)(?:的)?(?:图片|照片)"
    r"(?:里|中)?(?:的)?补剂[。.]?"
)


def is_incomplete_photo_supplement_reference(message: Any) -> bool:
    """A photo reference can request clarification, never recover write authority.

    No historical image, product identity, recipient or intake fact is resolved
    here. Explicit amounts, dates and other subjects stay on their own paths.
    """
    if not isinstance(message, str):
        return False
    from app.services.agent_kernel.health_semantics import active_health_read_authority_text

    return (
        active_health_read_authority_text(message) == message.strip()
        and _PHOTO_REFERENCE.fullmatch(message.strip()) is not None
    )


def match_photo_supplement_request(message: Any) -> re.Match[str] | None:
    """Inspect original material before whitespace normalization can erase code."""
    if not isinstance(message, str):
        return None
    from app.services.agent_kernel.health_semantics import active_health_read_authority_text

    if active_health_read_authority_text(message) != message.strip():
        return None
    return _REQUEST.fullmatch(message.strip())


def build_photo_supplement_preview(message: Any, candidates: Any) -> dict[str, Any] | None:
    """Bind only the supported explicit count phrase; unresolved forms stay unresolved.

    Label strengths are display text, never converted into intake quantities.
    This does not assess medical suitability or recommend a dose.
    """
    if not isinstance(message, str) or not isinstance(candidates, list):
        return None
    match = match_photo_supplement_request(message)
    if match is None:
        return None
    total_text = match['total']
    total = _COUNTS.get(total_text) if not total_text.isascii() else int(total_text)
    if len(candidates) != total:
        return None
    names: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get('name'), str):
            return None
        name = candidate['name'].strip()
        if not _NAME.fullmatch(name) or any(ord(c) < 32 for c in name):
            return None
        if any(term in name for term in ('未知', '不明', '疑似', '无法', '指令', '记录')):
            return None
        names.append(name)
    if len({re.sub(r'\s+', '', name).casefold() for name in names}) != len(names):
        return None
    nac_indexes = [i for i, name in enumerate(names) if _NAC_NAME.match(name)]
    if len(nac_indexes) != 1:
        return None
    return {
        'requires_confirmation': True,
        'items': [
            {'name': name, 'actual_dosage': f"{match['nac'] if i == nac_indexes[0] else match['other']}粒"}
            for i, name in enumerate(names)
        ],
    }


def needs_photo_supplement_details(message: Any) -> bool:
    """Incomplete current-turn photo captions request clarification, never intake.

    A product label (including Kids) cannot establish who took it, the amount,
    or whether the user wants an inventory entry instead of an intake record.
    """
    if not isinstance(message, str):
        return False
    from app.services.agent_kernel.health_semantics import active_health_read_authority_text

    if active_health_read_authority_text(message) != message.strip():
        return False
    return bool(
        re.fullmatch(r"记录(?:这个|这瓶|益生菌)?补剂[。.]?", message.strip())
        or is_incomplete_photo_supplement_reference(message)
    )
