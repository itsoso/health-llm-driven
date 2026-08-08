"""Shared fail-closed checks for user-authored write language."""
from __future__ import annotations

import re
import unicodedata

from app.services.write_intent_scope import (
    has_negated_write_scope,
    is_historical_write_reference,
    is_write_capability_question,
)


def is_explicit_write_cancellation(text: str) -> bool:
    """Match cancellation of a write action without matching food modifiers."""
    return has_negated_write_scope(text)


def is_non_authorizing_write_reference(text: str) -> bool:
    """Fail closed on questions/history that mention a write action."""
    return is_write_capability_question(text) or is_historical_write_reference(text)


_AIGC_PROVIDER_TERMS_RE = re.compile(r"百炼|万相|wan", re.IGNORECASE)
_AIGC_PROVIDER_VETO_RE = re.compile(
    r"取消|撤销|拒绝|停止|放弃|暂停|谢绝|撤回|终止|反悔|作罢|算了|"
    r"不要|别|勿|禁止|严禁|不可|不得|不能|不应|不传|不发",
    re.IGNORECASE,
)
_AIGC_LOCAL_SCOPE = (
    r"(?:手机本地|当前设备|设备本身|手机自身|本地|离线|断网|本机|"
    r"设备内|设备端|手机内|手机内部|手机上|手机端|终端侧|端侧|端上|"
    r"端内|本端)"
)
_AIGC_LOCAL_ONLY_RE = re.compile(
    rf"(?:仅限|只限|仅在|只在|只许|必须|务必|只能|仅能|只可|仅可|限定在|只用|仅用)"
    rf".{{0,10}}{_AIGC_LOCAL_SCOPE}|"
    r"(?:只用|仅用).{0,4}(?:手机|设备|终端)(?:处理|完成|运行|做|模型)|"
    rf"(?:留在|保留在|保存在|限定在).{{0,8}}{_AIGC_LOCAL_SCOPE}|"
    rf"{_AIGC_LOCAL_SCOPE}.{{0,8}}(?:处理|完成|生成|运行|制作|创作|渲染|留存|保存|做)|"
    r"(?:不让|不要让|不能|不许|不准|不得|禁止|严禁|不).{0,12}"
    r"(?:离开|移出|带出).{0,6}(?:手机|本机|设备|终端)|"
    r"(?:不要|别|请勿|勿|禁止|严禁|不可|不得|不能|不应|不允许|不准|不许|无需|无须)"
    r".{0,24}(?:上传|发送|发给|发出去|传给|交给|交由|传到|外传|外发|传出去|"
    r"出网|联网|接入外网|调用(?:云接口|外部服务)|连接外部服务|"
    r"使用(?:云服务|云端服务|外部服务|第三方服务)|远程处理|送往|送到|同步|上云)",
    re.IGNORECASE | re.DOTALL,
)
_AIGC_ENGLISH_PRIVACY_RE = re.compile(
    r"\b(?:local\s+only|offline\s+only|on[- ]device\s+only|"
    r"do\s+not\s+upload|don['’]t\s+upload|keep\s+it\s+on\s+my\s+(?:phone|device)|"
    r"no\s+cloud\s+(?:processing|upload))\b",
    re.IGNORECASE,
)


def is_explicit_aigc_media_provider_veto(text: str) -> bool:
    """Deny explicit provider revocation/privacy limits before AIGC dispatch.

    The check is deliberately independent from the broad intent classifier:
    even a model-selected draft on the general toolset cannot override a
    current-turn cancellation or local-only requirement.
    """
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKC", str(text or ""))
        if unicodedata.category(character) != "Cf"
    ).strip()
    if not normalized:
        return False
    return bool(
        _AIGC_LOCAL_ONLY_RE.search(normalized)
        or _AIGC_ENGLISH_PRIVACY_RE.search(normalized)
        or (
            _AIGC_PROVIDER_TERMS_RE.search(normalized)
            and _AIGC_PROVIDER_VETO_RE.search(normalized)
        )
    )
