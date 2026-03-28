#!/usr/bin/env python3
"""
本地登录 Garmin → 保存 garth session → 注入到远程服务器 DB

用于绕过服务器 IP 被 Garmin SSO 429 限流的问题。
本地网络 IP 不同，通常不受限流影响。

使用方法：
    cd backend && source venv/bin/activate
    python scripts/garmin_inject_session.py                    # 默认 user_id=3
    python scripts/garmin_inject_session.py --user-id 15       # 指定用户
    python scripts/garmin_inject_session.py --is-cn            # 佳明中国 (garmin.cn)
"""
import argparse
import json
import os
import sys
import tempfile
import subprocess


SERVER = "root@39.98.206.178"


def main():
    parser = argparse.ArgumentParser(description="注入 Garmin OAuth session 到生产服务器")
    parser.add_argument("--user-id", type=int, default=3, help="目标用户 ID (默认: 3)")
    parser.add_argument("--is-cn", action="store_true", help="使用佳明中国 (garmin.cn)")
    parser.add_argument("--email", type=str, default=None, help="Garmin 邮箱 (不指定则交互输入)")
    parser.add_argument("--password", type=str, default=None, help="Garmin 密码 (不指定则交互输入)")
    args = parser.parse_args()

    user_id = args.user_id
    email = args.email or input("Garmin email: ").strip()
    password = args.password or input("Garmin password: ").strip()

    if not email or not password:
        print("Email and password required")
        sys.exit(1)

    # Step 0: 先探测 SSO 是否 429
    print(f"\n[0/4] 探测 Garmin SSO 状态...")
    import requests as req
    try:
        probe = req.get("https://sso.garmin.com/sso/signin", timeout=10, allow_redirects=False)
        if probe.status_code == 429:
            print(f"  当前 IP 被 Garmin SSO 限流 (429)!")
            print(f"  解决方案:")
            print(f"    1. 连手机热点，换一个 IP 后重新运行本脚本")
            print(f"    2. 等 2-6 小时让限流自然解除")
            print(f"    3. 在 Chrome 已登录 Garmin 的情况下运行:")
            print(f"       python scripts/garmin_cookie_sync.py --days 3")
            print()
            answer = input("  是否仍然尝试登录？(y/N): ").strip().lower()
            if answer != "y":
                sys.exit(1)
        else:
            print(f"  SSO 可用 (HTTP {probe.status_code})")
    except Exception as e:
        print(f"  SSO 探测失败: {e}，仍尝试登录...")

    # Step 1: 本地登录 Garmin
    print(f"[1/4] 登录 Garmin SSO (user_id={user_id}, {'CN' if args.is_cn else 'Global'})...")
    import garth

    if args.is_cn:
        garth.configure(domain="garmin.cn")

    try:
        garth.login(email, password)
        print("  登录成功!")
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg:
            print(f"  429 限流: {e}")
            print("  请连手机热点换 IP 后重试。")
        else:
            print(f"  登录失败: {e}")
        sys.exit(1)

    # Step 2: 导出 session
    print("[2/4] 导出 garth session...")
    with tempfile.TemporaryDirectory() as tmpdir:
        garth.save(tmpdir)
        session_data = {}
        for filename in ["oauth1_token.json", "oauth2_token.json"]:
            filepath = os.path.join(tmpdir, filename)
            if os.path.exists(filepath):
                with open(filepath, "r") as f:
                    session_data[filename] = json.load(f)

    if not session_data:
        print("  session 数据为空")
        sys.exit(1)

    session_json = json.dumps(session_data)
    print(f"  Session 导出成功 ({len(session_json)} bytes)")

    # Step 3: scp 到服务器
    print("[3/4] 上传到服务器...")
    local_tmp = "/tmp/garth_session_inject.json"
    remote_tmp = "/tmp/garth_session_inject.json"
    with open(local_tmp, "w") as f:
        f.write(session_json)

    r = subprocess.run(
        ["scp", local_tmp, f"{SERVER}:{remote_tmp}"],
        capture_output=True, text=True, timeout=15,
    )
    if r.returncode != 0:
        print(f"  scp 失败: {r.stderr}")
        print(f"  Session 已保存到 {local_tmp}，请手动注入")
        sys.exit(1)
    print("  上传成功")

    # Step 4: 远程注入 DB
    print("[4/4] 注入到数据库...")

    # 使用 effective_database_url 而非 database_url
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
    # 验证
    row = conn.execute(text(
        "SELECT garth_session IS NOT NULL as ok, session_expires_at "
        "FROM garmin_credentials WHERE user_id = {user_id}"
    )).fetchone()
    if row and row[0]:
        print(f'INJECT_OK expires={{row[1]}}')
    else:
        print('INJECT_FAIL')
"""

    r = subprocess.run(
        ["ssh", SERVER, f"cd /opt/health-app/backend && source venv/bin/activate && python3 -c {repr(inject_script)}"],
        capture_output=True, text=True, timeout=30,
    )

    if "INJECT_OK" in r.stdout:
        expires = r.stdout.split("expires=")[1].strip() if "expires=" in r.stdout else "?"
        print(f"  Session 已注入! (有效期至 {expires})")
        print(f"\n  完成! 现在可以在 App 中同步 Garmin 数据了。")
        print(f"  OAuth token 会自动刷新，不再走 SSO 登录。")
    else:
        print(f"  远程注入失败:")
        if r.stderr:
            print(f"  {r.stderr[:500]}")
        if r.stdout:
            print(f"  {r.stdout[:500]}")
        print(f"\n  Session 已保存到 {local_tmp}")
        print(f"  手动注入 SQL:")
        print(f"    UPDATE garmin_credentials SET garth_session = '<content>', login_locked_until = NULL, error_count = 0 WHERE user_id = {user_id};")


if __name__ == "__main__":
    main()
