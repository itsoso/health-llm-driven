"""Owner-scoped signed URLs for privacy-sensitive uploaded files."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from urllib.parse import urlencode, urlsplit

from app.config import settings


PRIVATE_UPLOAD_URL_TTL_SECONDS = 5 * 60
PRIVATE_UPLOAD_CATEGORIES = frozenset({"chat", "diet", "medical", "other", "aigc"})

# Per-category capability-URL TTL(2026-07-15).
# 病灶:签名 URL 只活 5 分钟,但 mac 把整个会话(含签名 URL)缓存进 UserDefaults 并从
# 缓存重渲染 transcript —— 5 分钟后 URL 过期 → WebView 拿 401 → 图片显示成 broken
# "attached image"(founder 实测:小米粥+蔬菜饼那餐)。web/mobile 同样缓存渲染会中招。
# 修法:给会话图片附件一个能覆盖"客户端缓存回放缝"的 TTL(每次从后端加载会话历史
# refresh_chat_image_url_value 都会重签,静态窗口只需覆盖两次服务端同步之间的间隔)。
#
# ⚠️ 敏感度取舍(勿照抄"低敏感"前提放宽):chat 是**万能通道**,用户在对话里可能发
# 化验单/皮肤病灶/处方/药盒(= §5 的 L3 机密医疗影像),diet 的 category 也是用户可控
# 标签、可被夹带医疗图。故 chat/diet 只给 7 天(不是 30 天)—— 平衡缓存回放体验与:
#   ① 泄露 bearer URL 的有效窗口;② 公开分享页(shared_conversation)撤销后已提取的
#      capability URL 仍可用最长一个 TTL(verify 只查签名+expiry、不查分享状态)。
# medical(化验/体检扫描)+ other(未知)保持 5 分钟纵深防御不变。
# 伪造防护:expiry 进 HMAC 签名,客户端改 query 里的 expires 会致签名不符 → 拒。
_PRIVATE_UPLOAD_CATEGORY_TTL_SECONDS: dict[str, int] = {
    "chat": 7 * 24 * 60 * 60,
    "diet": 7 * 24 * 60 * 60,
}


def _ttl_for_category(category: str) -> int:
    return _PRIVATE_UPLOAD_CATEGORY_TTL_SECONDS.get(category, PRIVATE_UPLOAD_URL_TTL_SECONDS)


def _normalized_category(category: str) -> str:
    normalized = str(category or "").strip().lower()
    if normalized not in PRIVATE_UPLOAD_CATEGORIES:
        raise ValueError("unsupported_private_upload_category")
    return normalized


def _private_upload_signature(
    category: str,
    owner_id: int,
    filename: str,
    expires: int,
    legacy: bool,
) -> str:
    namespace = "legacy" if legacy else "private"
    payload = (
        f"{namespace}:{_normalized_category(category)}:{int(owner_id)}:"
        f"{os.path.basename(filename)}:{int(expires)}"
    ).encode()
    return hmac.new(settings.secret_key.encode(), payload, hashlib.sha256).hexdigest()


def build_signed_private_upload_url(
    category: str,
    owner_id: int,
    filename: str,
    *,
    expires: int | None = None,
    legacy: bool = False,
) -> str:
    normalized_category = _normalized_category(category)
    safe_filename = os.path.basename(filename)
    expiry = int(expires or (time.time() + _ttl_for_category(normalized_category)))
    signature = _private_upload_signature(
        normalized_category,
        owner_id,
        safe_filename,
        expiry,
        legacy,
    )
    if legacy:
        path = f"/api/v1/upload/files/{normalized_category}/{safe_filename}"
        query = {
            "owner_id": int(owner_id),
            "expires": expiry,
            "signature": signature,
        }
    else:
        path = (
            f"/api/v1/upload/files/{normalized_category}/"
            f"{int(owner_id)}/{safe_filename}"
        )
        query = {"expires": expiry, "signature": signature}
    return f"{path}?{urlencode(query)}"


def verify_signed_private_upload_url(
    category: str,
    owner_id: int,
    filename: str,
    expires: int | None,
    signature: str | None,
    *,
    legacy: bool = False,
) -> bool:
    if not expires or not signature or int(expires) < int(time.time()):
        return False
    try:
        expected = _private_upload_signature(
            category,
            owner_id,
            filename,
            int(expires),
            legacy,
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(expected, str(signature))


def refresh_private_upload_url(
    raw_url: str | None,
    category: str,
    owner_id: int,
) -> str | None:
    """Return a fresh capability URL for canonical or legacy private paths."""
    if not raw_url:
        return raw_url
    normalized_category = _normalized_category(category)
    path = urlsplit(str(raw_url)).path
    private_match = re.search(
        rf"/api/v\d+/upload/files/{re.escape(normalized_category)}/(\d+)/([^/]+)$",
        path,
    )
    legacy_match = re.search(
        rf"/api/v\d+/upload/files/{re.escape(normalized_category)}/([^/]+)$",
        path,
    )
    if private_match and int(private_match.group(1)) == int(owner_id):
        return build_signed_private_upload_url(
            normalized_category,
            owner_id,
            private_match.group(2),
        )
    if legacy_match:
        return build_signed_private_upload_url(
            normalized_category,
            owner_id,
            legacy_match.group(1),
            legacy=True,
        )
    return str(raw_url)
