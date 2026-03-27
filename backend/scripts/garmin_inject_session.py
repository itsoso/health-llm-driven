#!/usr/bin/env python3
"""
一次性脚本：本地登录 Garmin → 保存 garth session → 注入到远程服务器 DB

使用方法：
    cd backend && source venv/bin/activate
    python scripts/garmin_inject_session.py

前提：Garmin SSO 429 已解封（停止所有登录尝试 2-6 小时后）
"""
import json
import os
import sys
import tempfile
import subprocess

def main():
    email = input("Garmin email: ").strip()
    password = input("Garmin password: ").strip()

    if not email or not password:
        print("Email and password required")
        sys.exit(1)

    # Step 1: 本地登录 Garmin
    print("\n[1/3] 登录 Garmin SSO...")
    import garth
    try:
        garth.login(email, password)
        print("✅ 登录成功!")
    except Exception as e:
        print(f"❌ 登录失败: {e}")
        print("\n如果仍然 429，请再等几个小时后重试。")
        sys.exit(1)

    # Step 2: 导出 session
    print("[2/3] 导出 garth session...")
    with tempfile.TemporaryDirectory() as tmpdir:
        garth.save(tmpdir)
        session_data = {}
        for filename in ['oauth1_token.json', 'oauth2_token.json']:
            filepath = os.path.join(tmpdir, filename)
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    session_data[filename] = json.load(f)

    if not session_data:
        print("❌ session 数据为空")
        sys.exit(1)

    session_json = json.dumps(session_data)
    print(f"✅ Session 导出成功 ({len(session_json)} bytes)")

    # Step 3: 注入到远程服务器 DB
    print("[3/3] 注入到服务器数据库...")

    # 转义 SQL 中的单引号
    safe_json = session_json.replace("'", "''")

    sql = f"UPDATE garmin_credentials SET garth_session = '{safe_json}', session_expires_at = NOW() + INTERVAL '30 days', login_locked_until = NULL, credentials_valid = true, last_error = NULL WHERE user_id = 3"

    cmd = f'''ssh root@39.98.206.178 "cd /opt/health-app/backend && source venv/bin/activate && python -c \\"
from sqlalchemy import create_engine, text
from app.config import settings
engine = create_engine(settings.database_url)
with engine.connect() as conn:
    conn.execute(text('''{sql}'''))
    conn.commit()
    print('Done')
\\""'''

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        if "Done" in result.stdout:
            print("✅ Session 已注入服务器!")
            print("\n🎉 完成! 现在可以在 App 中同步 Garmin 数据了。")
            print("   garth 会用 OAuth token refresh，不再走 SSO 登录。")
        else:
            print(f"❌ 注入失败: {result.stderr or result.stdout}")
            print(f"\n手动注入: 把以下 JSON 写入 garmin_credentials.garth_session (user_id=3):")
            # 保存到本地文件
            with open('/tmp/garth_session.json', 'w') as f:
                f.write(session_json)
            print(f"   Session 已保存到 /tmp/garth_session.json")
    except Exception as e:
        print(f"❌ SSH 执行失败: {e}")
        with open('/tmp/garth_session.json', 'w') as f:
            f.write(session_json)
        print(f"   Session 已保存到 /tmp/garth_session.json，请手动注入")


if __name__ == "__main__":
    main()
