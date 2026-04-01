"""
Monkey-patch garth 的 HTTP client 使用 curl_cffi (Chrome TLS 指纹)

解决 Garmin SSO 被 Cloudflare 检测 Python requests TLS 指纹为 bot 的问题。
在应用启动时调用 patch_garth_with_cffi() 即可。
"""
import logging

logger = logging.getLogger(__name__)

_patched = False


def make_cffi_session_compatible(cffi_sess):
    """给 curl_cffi.Session 补上 requests.Session 的兼容属性"""
    from requests.adapters import HTTPAdapter
    defaults = {
        'adapters': {'https://': HTTPAdapter(), 'http://': HTTPAdapter()},
        'auth': None,
        'hooks': {'response': []},
        'params': {},
        'proxies': {},
        'stream': False,
        'verify': True,
        'cert': None,
        'max_redirects': 30,
        'trust_env': True,
    }
    for attr, default in defaults.items():
        if not hasattr(cffi_sess, attr):
            setattr(cffi_sess, attr, default)

    # 补充 requests.Session 的方法（garminconnect 可能调用）
    if not hasattr(cffi_sess, 'mount'):
        cffi_sess.mount = lambda prefix, adapter: cffi_sess.adapters.update({prefix: adapter})
    if not hasattr(cffi_sess, 'prepare_request'):
        from requests import Request
        cffi_sess.prepare_request = lambda req: req.prepare()
    if not hasattr(cffi_sess, 'merge_environment_settings'):
        cffi_sess.merge_environment_settings = lambda url, proxies, stream, verify, cert: {
            'proxies': proxies or {}, 'stream': stream, 'verify': verify, 'cert': cert
        }

    return cffi_sess


def patch_garth_with_cffi():
    """
    替换 garth 全局 client 的 requests.Session 为 curl_cffi.Session(impersonate="chrome")。
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

        cffi_sess = CffiSession(impersonate="chrome")
        original_headers = dict(garth.client.sess.headers)
        cffi_sess.headers.update(original_headers)
        make_cffi_session_compatible(cffi_sess)
        garth.client.sess = cffi_sess

        _patched = True
        logger.info("garth HTTP client 已 patch 为 curl_cffi (Chrome TLS)")
    except Exception as e:
        logger.warning(f"garth patch 失败: {e}")
