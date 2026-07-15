"""Per-category capability-URL TTL(2026-07-15 修 mac 图片 broken)。

病灶:签名图片 URL 只活 5 分钟,但 mac 把整段会话(含签名 URL)缓存进 UserDefaults
并从缓存重渲染 transcript —— 5 分钟后 URL 过期 → WebView 401 → 图片显示成 broken
"attached image"。修法:会话图片附件(chat/diet)给 7 天 TTL 覆盖客户端缓存回放缝;
敏感的 medical 扫描 + 未知 other 保持 5 分钟纵深防御。chat/diet 只给 7 天(不是更长):
chat 可含 L3 医疗影像、公开分享撤销后已提取 URL 仍可用一个 TTL。expiry 进 HMAC 签名
→ 客户端无法伪造更长有效期。
"""
import time
from urllib.parse import parse_qs, urlsplit

from app.services.private_uploads import (
    PRIVATE_UPLOAD_URL_TTL_SECONDS,
    build_signed_private_upload_url,
    verify_signed_private_upload_url,
)

_LONG = 7 * 24 * 60 * 60
_SHORT = PRIVATE_UPLOAD_URL_TTL_SECONDS  # 5 * 60


def _expires_delta(url: str) -> int:
    q = parse_qs(urlsplit(url).query)
    return int(q["expires"][0]) - int(time.time())


def test_chat_and_diet_get_long_ttl():
    for category in ("chat", "diet"):
        delta = _expires_delta(build_signed_private_upload_url(category, 3, "meal.jpg"))
        # 允许几秒执行漂移
        assert _LONG - 60 < delta <= _LONG, f"{category} TTL 应 ~30 天,实得 {delta}s"


def test_medical_and_other_keep_short_ttl():
    for category in ("medical", "other"):
        delta = _expires_delta(build_signed_private_upload_url(category, 3, "scan.jpg"))
        assert 0 < delta <= _SHORT, f"{category} 敏感/未知类别必须保持短 TTL,实得 {delta}s"


def test_long_ttl_url_verifies_ok():
    # verify 无独立 max-TTL 上限:信任签名里的 expiry(不在过去 + 签名对),
    # 所以长 TTL 的 chat URL 必须能通过校验(否则图片仍打不开)。
    filename = "meal.jpg"
    url = build_signed_private_upload_url("chat", 3, filename)
    q = parse_qs(urlsplit(url).query)
    assert verify_signed_private_upload_url(
        "chat", 3, filename, int(q["expires"][0]), q["signature"][0]
    ) is True


def test_forged_longer_expiry_is_rejected():
    # 客户端不能靠改 query 里的 expires 延长有效期 —— expiry 进 HMAC,改了签名就不对。
    filename = "meal.jpg"
    url = build_signed_private_upload_url("medical", 3, filename)
    q = parse_qs(urlsplit(url).query)
    forged_expires = int(time.time()) + _LONG  # 试图把 5 分钟撑成 30 天
    assert verify_signed_private_upload_url(
        "medical", 3, filename, forged_expires, q["signature"][0]
    ) is False
