"""PII 脱敏 — LLM prompt 入参前一道防线 (review #3, 2026-05-12).

目的: 用户对话/记录里偶尔会写自己的手机号 / 身份证 / 邮箱, 不想被发到 LLM
provider 训练池. 健康数据 (HRV/化验值/SNP genotype) 是 LLM 推理必需, **不**
脱敏 — 那是另一个层 (provider 信任 + 数据合作协议) 解决.

scrub 命中类型:
- 中国手机号  (11 位 1[3-9]xxxxxxxxx)
- 身份证号    (18 位 数字+末位 X)
- 邮箱        (常规 RFC5322 子集)
- 银行卡号    (16-19 位连续数字, 弱启发避免误中长 ID)

被脱敏后用占位符替换, 例:
  "我手机 13800138000 出问题"  → "我手机 [PHONE] 出问题"

返回 (scrubbed_text, hits_dict). hits_dict 用于 audit log, 不打印原值.
"""

import re
from typing import Dict, Tuple


# ── 正则 (使用 lookahead/lookbehind 减少误匹配) ──

_RE_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_RE_IDCARD = re.compile(r"(?<!\d)\d{17}[\dXx](?!\w)")
_RE_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
# 银行卡: 16-19 位连续数字, 排除前后是字母数字, 用空格/标点边界
_RE_BANKCARD = re.compile(r"(?<![\d\w])\d{16,19}(?![\d\w])")


def scrub_pii(text: str) -> Tuple[str, Dict[str, int]]:
    """脱敏 + 返回命中统计.

    Returns:
        (scrubbed_text, {"phone": N, "idcard": N, "email": N, "bankcard": N})
        命中数为 0 的不出现在 dict 里.
    """
    if not text or not isinstance(text, str):
        return text, {}

    hits: Dict[str, int] = {}

    def _sub(pat: re.Pattern, placeholder: str, kind: str, t: str) -> str:
        c = 0
        def _r(_m):
            nonlocal c
            c += 1
            return placeholder
        new = pat.sub(_r, t)
        if c > 0:
            hits[kind] = c
        return new

    # 顺序敏感: idcard (17+1) 先于 bankcard (16-19), 否则身份证会被当银行卡命中
    text = _sub(_RE_IDCARD, "[IDCARD]", "idcard", text)
    text = _sub(_RE_BANKCARD, "[BANKCARD]", "bankcard", text)
    text = _sub(_RE_PHONE, "[PHONE]", "phone", text)
    text = _sub(_RE_EMAIL, "[EMAIL]", "email", text)
    return text, hits


def scrub_messages(messages):
    """对 chat messages list (OpenAI shape) 逐条 scrub content. 返回 (new_msgs, total_hits).

    支持 content 是 str 或 list (multi-modal).
    """
    if not messages:
        return messages, {}
    total: Dict[str, int] = {}
    out = []
    for m in messages:
        if not isinstance(m, dict):
            out.append(m)
            continue
        c = m.get("content")
        if isinstance(c, str):
            scrubbed, hits = scrub_pii(c)
            for k, v in hits.items():
                total[k] = total.get(k, 0) + v
            out.append({**m, "content": scrubbed})
        elif isinstance(c, list):
            new_parts = []
            for part in c:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    scrubbed, hits = scrub_pii(part["text"])
                    for k, v in hits.items():
                        total[k] = total.get(k, 0) + v
                    new_parts.append({**part, "text": scrubbed})
                else:
                    new_parts.append(part)
            out.append({**m, "content": new_parts})
        else:
            out.append(m)
    return out, total


# ── Provider 包装 (factory 链式调用) ──


import logging

_pii_logger = logging.getLogger(__name__)


def wrap_provider_pii_scrub(provider):
    """所有 chat / chat_with_vision 调用前对 messages 跑 scrub_pii.

    放在 usage_tracker 外面 — 这样 tracker 记录的也是脱敏后文本.
    幂等: 重复包装无效 (检测 _pii_wrapped flag).
    """
    if getattr(provider, "_pii_wrapped", False):
        return provider

    original_chat = getattr(provider, "chat", None)
    original_vision = getattr(provider, "chat_with_vision", None)
    original_chat_stream = getattr(provider, "chat_stream", None)

    if original_chat is not None:
        async def chat_scrubbed(messages, **kwargs):
            scrubbed, hits = scrub_messages(messages)
            if hits:
                _pii_logger.warning(
                    "[pii_scrub] redacted before LLM call: %s",
                    " ".join(f"{k}={v}" for k, v in hits.items()),
                )
            return await original_chat(scrubbed, **kwargs)
        provider.chat = chat_scrubbed

    if original_vision is not None:
        async def vision_scrubbed(messages, image_url, **kwargs):
            scrubbed, hits = scrub_messages(messages)
            if hits:
                _pii_logger.warning(
                    "[pii_scrub] redacted before vision LLM call: %s",
                    " ".join(f"{k}={v}" for k, v in hits.items()),
                )
            return await original_vision(scrubbed, image_url, **kwargs)
        provider.chat_with_vision = vision_scrubbed

    if original_chat_stream is not None:
        # chat_stream 是 async generator — 不能 await 整体, 必须 scrub 后逐事件透传。
        # 这是硬安全边界: 流式路径也必须脱敏, 不能绕过。
        def chat_stream_scrubbed(messages, **kwargs):
            scrubbed, hits = scrub_messages(messages)
            if hits:
                _pii_logger.warning(
                    "[pii_scrub] redacted before streaming LLM call: %s",
                    " ".join(f"{k}={v}" for k, v in hits.items()),
                )
            return original_chat_stream(scrubbed, **kwargs)
        provider.chat_stream = chat_stream_scrubbed

    provider._pii_wrapped = True
    return provider
