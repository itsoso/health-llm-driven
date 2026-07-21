"""
可复用的 curl_cffi Garmin 登录模块

从 scripts/garmin_cffi_login.py 提取的核心逻辑，
可被 Celery 任务和脚本共同调用。

curl_cffi 用于绕过 Garmin SSO 的 Cloudflare 反爬，
在 garth 常规 refresh 失败时作为最后手段。
"""
import json
import logging
import os
import re
import tempfile

logger = logging.getLogger(__name__)

CURL_CFFI_AVAILABLE = False
try:
    from curl_cffi.requests import Session as CffiSession
    CURL_CFFI_AVAILABLE = True
except ImportError:
    pass


def cffi_login_and_get_session(email: str, password: str, is_cn: bool = False) -> dict:
    """
    使用 curl_cffi (Chrome TLS fingerprint) 登录 Garmin SSO，
    返回 garth session dict（可直接存入 GarminCredential.garth_session）。

    Args:
        email: Garmin 邮箱
        password: Garmin 密码
        is_cn: 是否使用中国服务器 (garmin.cn)

    Returns:
        dict: garth session 数据，包含 oauth1_token.json 和 oauth2_token.json

    Raises:
        ImportError: curl_cffi 未安装
        RuntimeError: 登录失败（CSRF 获取失败、密码错误、MFA、账号锁定等）
    """
    if not CURL_CFFI_AVAILABLE:
        raise ImportError(
            "curl_cffi 未安装，无法使用 Chrome TLS 登录。"
            "请运行: pip install curl_cffi"
        )

    try:
        import garth
        from garth.sso import get_oauth1_token, exchange
    except ImportError:
        raise ImportError("garth 未安装，请运行: pip install garth")

    if is_cn:
        SSO = "https://sso.garmin.cn/sso"
    else:
        SSO = "https://sso.garmin.com/sso"

    SSO_EMBED = f"{SSO}/embed"
    SIGNIN_PARAMS = {
        "id": "gauth-widget",
        "embedWidget": "true",
        "gauthHost": SSO_EMBED,
        "service": SSO_EMBED,
        "source": SSO_EMBED,
        "redirectAfterAccountLoginUrl": SSO_EMBED,
        "redirectAfterAccountCreationUrl": SSO_EMBED,
    }

    s = CffiSession(impersonate="chrome")

    # Step 1: GET signin page
    logger.info(f"[cffi_login] GET signin page (embed mode) for {email[:3]}***")
    s.get(f"{SSO}/embed", params={"id": "gauth-widget", "embedWidget": "true", "gauthHost": SSO})
    r1 = s.get(f"{SSO}/signin", params=SIGNIN_PARAMS)

    csrf_match = re.search(r'name="_csrf"\s+value="([^"]+)"', r1.text)
    if not csrf_match:
        is_challenge = "challenge" in r1.text.lower()
        raise RuntimeError(
            f"CSRF token 获取失败 (status={r1.status_code}, cloudflare_challenge={is_challenge})"
        )

    # Step 2: POST login
    logger.info("[cffi_login] POST login...")
    r2 = s.post(
        f"{SSO}/signin",
        params=SIGNIN_PARAMS,
        data={
            "username": email,
            "password": password,
            "embed": "true",
            "_csrf": csrf_match.group(1),
        },
        headers={"Referer": r1.url, "Origin": SSO.rsplit("/sso", 1)[0]},
    )

    title_match = re.search(r"<title>([^<]+)</title>", r2.text)
    title = title_match.group(1).strip() if title_match else "?"

    ticket_match = (
        re.search(r"ticket=([A-Za-z0-9_\-]+)", r2.text)
        or re.search(r"ticket=([A-Za-z0-9_\-]+)", str(r2.url))
    )

    if not ticket_match:
        errors = re.findall(r'class="[^"]*error[^"]*"[^>]*>([^<]+)', r2.text)
        error_msgs = [e.strip() for e in errors if e.strip()]

        if "MFA" in title or "verification" in title.lower():
            raise RuntimeError("需要 MFA 两步验证，cffi_login 不支持")
        if r2.status_code == 429:
            raise RuntimeError("Garmin SSO 限流 (429)，请稍后再试")

        raise RuntimeError(
            f"登录失败: title={title}, errors={error_msgs}, status={r2.status_code}"
        )

    ticket = ticket_match.group(1)
    logger.info("[cffi_login] 已取得一次性 SSO ticket")

    # Step 3: Exchange ticket for OAuth tokens via garth
    client = garth.Client()
    if is_cn:
        client.configure(domain="garmin.cn")

    for cookie in s.cookies.jar:
        client.sess.cookies.set(
            cookie.name, cookie.value, domain=cookie.domain, path=cookie.path
        )

    oauth1 = get_oauth1_token(ticket, client)
    oauth2 = exchange(oauth1, client)
    client.oauth1_token = oauth1
    client.oauth2_token = oauth2

    logger.info(
        f"[cffi_login] OAuth 交换成功! refresh_token={'YES' if oauth2.refresh_token else 'NO'}"
    )

    # Step 4: Export session to dict
    with tempfile.TemporaryDirectory() as d:
        client.dump(d)
        session_data = {}
        for fname in ["oauth1_token.json", "oauth2_token.json"]:
            fpath = os.path.join(d, fname)
            if os.path.exists(fpath):
                with open(fpath) as f:
                    session_data[fname] = json.load(f)

    if not session_data:
        raise RuntimeError("session 导出为空")

    return session_data
