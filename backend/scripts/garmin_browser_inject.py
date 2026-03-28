#!/usr/bin/env python3
"""
从浏览器 cookies 提取 Garmin OAuth token → 注入远程服务器 DB

完全不走 SSO 登录，不受 429 限流影响。
前提：Chrome/Edge 浏览器已登录 connect.garmin.com 或 connect.garmin.cn

使用方法：
    cd backend && source venv/bin/activate
    python scripts/garmin_browser_inject.py                     # 默认 user_id=3
    python scripts/garmin_browser_inject.py --user-id 15        # 指定用户
    python scripts/garmin_browser_inject.py --cn                # 佳明中国
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import date

import requests

SERVER = "root@39.98.206.178"


def extract_garmin_session_from_browser(is_cn=False):
    """从 Chrome cookies 中提取 Garmin 会话，然后用 garth 换取 OAuth token"""
    domain = "garmin.cn" if is_cn else "garmin.com"
    base = f"https://connect.{domain}"

    # 1. 读取 Chrome cookies
    print(f"[1/3] 读取浏览器 cookies ({domain})...")
    try:
        import browser_cookie3
        cookies = browser_cookie3.chrome(domain_name=f".{domain}")
    except PermissionError:
        print("  需要完全磁盘访问权限:")
        print("  macOS: 系统设置 → 隐私与安全 → 完全磁盘访问权限 → 添加终端/iTerm")
        sys.exit(1)
    except Exception as e:
        print(f"  读取 cookies 失败: {e}")
        print(f"  请确保 Chrome 已登录 {base}")
        sys.exit(1)

    # 2. 验证 cookies 有效
    print("[2/3] 验证浏览器 session...")
    session = requests.Session()
    session.cookies = cookies
    session.headers.update({
        "NK": "NT",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    })

    test_url = f"{base}/gc-api/usersummary-service/usersummary/daily?calendarDate={date.today().isoformat()}"
    r = session.get(test_url)
    if r.status_code != 200:
        print(f"  浏览器 session 无效 (HTTP {r.status_code})")
        print(f"  请在 Chrome 中登录 {base} 后重试")
        sys.exit(1)

    print(f"  浏览器 session 有效!")

    # 3. 使用 garth 从 cookies 获取 OAuth token
    print("[3/3] 通过 cookies 获取 OAuth token...")
    import garth

    if is_cn:
        garth.configure(domain="garmin.cn")

    # 从 cookie jar 提取关键 cookies 给 garth
    cookie_dict = {}
    for cookie in cookies:
        if domain in cookie.domain:
            cookie_dict[cookie.name] = cookie.value

    # garth 需要 oauth1 和 oauth2 token。浏览器 cookies 里有 session，
    # 我们用 cookies 调 Garmin 的 OAuth exchange endpoint 来获取 token
    try:
        # 方法: 用 cookies 直接调 garth 的 exchange 端点
        oauth_url = f"https://connect.{domain}/modern/di-oauth/exchange"
        r = session.post(oauth_url, headers={"Accept": "application/json"})
        if r.status_code == 200:
            token_data = r.json()
            print(f"  OAuth exchange 成功!")

            # 构造 garth 兼容的 session 格式
            session_data = {
                "oauth1_token.json": {
                    "oauth": cookie_dict.get("GARMIN-SSO-GUID", ""),
                    "oauth_token": "",
                    "oauth_token_secret": "",
                },
                "oauth2_token.json": {
                    "scope": token_data.get("scope", ""),
                    "jti": token_data.get("jti", ""),
                    "token_type": token_data.get("token_type", "Bearer"),
                    "access_token": token_data.get("access_token", ""),
                    "refresh_token": token_data.get("refresh_token", ""),
                    "expires_in": token_data.get("expires_in", 3600),
                    "expires_at": token_data.get("expires_at", 0),
                    "refresh_token_expires_in": token_data.get("refresh_token_expires_in", 7776000),
                    "refresh_token_expires_at": token_data.get("refresh_token_expires_at", 0),
                },
            }

            # 验证 token
            if not session_data["oauth2_token.json"]["access_token"]:
                print("  OAuth exchange 返回空 token")
                return None
            return session_data
        else:
            print(f"  OAuth exchange 失败 (HTTP {r.status_code}): {r.text[:200]}")
    except Exception as e:
        print(f"  OAuth exchange 异常: {e}")

    # 回退方案: 不使用 garth，直接用 cookies 同步数据
    print("  OAuth token 获取失败，回退到直接 cookie 同步模式")
    return None


def inject_to_server(user_id, session_json):
    """注入 session 到远程服务器 DB"""
    print(f"\n注入到服务器 (user_id={user_id})...")

    local_tmp = "/tmp/garth_session_browser.json"
    remote_tmp = "/tmp/garth_session_browser.json"
    with open(local_tmp, "w") as f:
        f.write(session_json)

    r = subprocess.run(
        ["scp", local_tmp, f"{SERVER}:{remote_tmp}"],
        capture_output=True, text=True, timeout=15,
    )
    if r.returncode != 0:
        print(f"  scp 失败: {r.stderr}")
        return False

    inject_script = f"""
import json
from sqlalchemy import create_engine, text
from app.config import settings
engine = create_engine(settings.effective_database_url)
session = open('{remote_tmp}').read()
with engine.connect() as conn:
    conn.execute(text(
        "UPDATE garmin_credentials "
        "SET garth_session = :s, "
        "    session_expires_at = NOW() + INTERVAL '23 hours', "
        "    login_locked_until = NULL, "
        "    credentials_valid = true, "
        "    last_error = NULL, "
        "    error_count = 0 "
        "WHERE user_id = {user_id}"
    ), {{'s': session}})
    conn.commit()
    print('INJECT_OK')
"""

    r = subprocess.run(
        ["ssh", SERVER, f"cd /opt/health-app/backend && source venv/bin/activate && python3 -c {repr(inject_script)}"],
        capture_output=True, text=True, timeout=30,
    )
    return "INJECT_OK" in r.stdout


def fallback_cookie_sync(is_cn=False, days=3):
    """回退方案: 直接用 cookies 同步数据到 Health API"""
    print(f"\n使用 cookie 直接同步最近 {days} 天数据...")
    cmd = [sys.executable, "scripts/garmin_cookie_sync.py", "--days", str(days)]
    if is_cn:
        cmd.append("--cn")
    os.execv(sys.executable, cmd)


def main():
    parser = argparse.ArgumentParser(description="从浏览器 cookies 注入 Garmin session")
    parser.add_argument("--user-id", type=int, default=3, help="目标用户 ID")
    parser.add_argument("--cn", action="store_true", help="佳明中国 (garmin.cn)")
    parser.add_argument("--days", type=int, default=3, help="回退同步天数")
    args = parser.parse_args()

    session_data = extract_garmin_session_from_browser(is_cn=args.cn)

    if session_data:
        session_json = json.dumps(session_data)
        if inject_to_server(args.user_id, session_json):
            print(f"\n  完成! Session 已注入，服务器可自动刷新 OAuth token。")
        else:
            print(f"\n  注入失败，回退到直接同步模式...")
            fallback_cookie_sync(is_cn=args.cn, days=args.days)
    else:
        print("\n  无法获取 OAuth token，使用直接 cookie 同步...")
        fallback_cookie_sync(is_cn=args.cn, days=args.days)


if __name__ == "__main__":
    main()
