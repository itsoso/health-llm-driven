"""Shared fail-closed checks for user-authored write language."""
from __future__ import annotations

import re
import unicodedata


_EXPLICIT_WRITE_CANCELLATION_RE = re.compile(
    r"(?:先不要|暂不|不需要|不要|不用|无需|先别|别|不)"
    r"(?:再|先|想|要|帮我|给我|把|将|这|该|本|这次|本次|"
    r"早餐|午餐|晚餐|加餐|饮食|一餐|这餐|条|份|个|次|"
    r"[\s，,。.!！；;：:])*"
    r"(?:记录|记一下|记下|记|保存|录入|写入|写回|添加|加到饮食)"
)


def is_explicit_write_cancellation(text: str) -> bool:
    """Match cancellation of a write action without matching food modifiers."""
    normalized = str(text or "").strip()
    return bool(
        _EXPLICIT_WRITE_CANCELLATION_RE.search(normalized)
        or re.search(
            r"(?:取消|撤销)(?:这次|本次|该次)?(?:记录|保存|录入|写入)",
            normalized,
        )
        or re.search(
            r"(?:记录|保存|录入|写入)(?:这次|本次|该次)?(?:取消|撤销|算了)",
            normalized,
        )
    )


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
