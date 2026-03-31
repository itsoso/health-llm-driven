"""
Monkey-patch garth 的 HTTP client 使用 curl_cffi (Chrome TLS 指纹)

解决 Garmin SSO 被 Cloudflare 检测 Python requests TLS 指纹为 bot 的问题。
在应用启动时调用 patch_garth_with_cffi() 即可。
"""
import logging

logger = logging.getLogger(__name__)

_patched = False


def patch_garth_with_cffi():
    """
    替换 garth 全局 client 的 requests.Session 为 curl_cffi.Session(impersonate="chrome")。

    这样 garth 的所有 HTTP 请求（SSO 登录、token refresh、API 调用）
    都会使用 Chrome 的 TLS 指纹，绕过 Cloudflare bot 检测。
    """
    global _patched
    if _patched:
        return

    try:
        from curl_cffi.requests import Session as CffiSession
    except ImportError:
        logger.warning("curl_cffi 未安装，garth 将使用默认 requests.Session（可能被 Cloudflare 429）")
        return

    try:
        import garth

        # 创建 Chrome TLS 指纹的 session
        cffi_sess = CffiSession(impersonate="chrome")

        # 保留 garth 原有的 headers
        original_headers = dict(garth.client.sess.headers)
        cffi_sess.headers.update(original_headers)

        # 替换
        garth.client.sess = cffi_sess

        _patched = True
        logger.info("garth HTTP client 已 patch 为 curl_cffi (Chrome TLS)")
    except Exception as e:
        logger.warning(f"garth patch 失败: {e}")
