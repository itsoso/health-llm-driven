#!/usr/bin/env python3
"""
Playwright 自动化 Garmin 数据同步

使用真实浏览器绕过 Cloudflare 防护，从 Garmin Connect 拉取数据，
注入 OAuth session 到服务器 DB，实现完全自动化。

第一次运行会打开浏览器让你登录 Garmin，之后复用 session 不再需要手动操作。

用法：
    cd backend && source venv/bin/activate
    python scripts/garmin_playwright_sync.py                  # 拉数据 + 注入 session
    python scripts/garmin_playwright_sync.py --days 7         # 同步最近 7 天
    python scripts/garmin_playwright_sync.py --headless       # 无头模式（已有 session 时）
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

SERVER = "root@39.98.206.178"
USER_ID = 3
GARMIN_BASE = "https://connect.garmin.com"
HEALTH_API = os.environ.get("HEALTH_API_URL", "https://health-api.executor.life/api/v1")
HEALTH_TOKEN = os.environ.get("HEALTH_API_TOKEN", "")

# Playwright session 持久化目录
SESSION_DIR = Path.home() / ".garmin-playwright-session"


def run(days=3, headless=False):
    from playwright.sync_api import sync_playwright

    SESSION_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        # 使用持久化上下文（保留登录状态）
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=headless,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )

        page = browser.pages[0] if browser.pages else browser.new_page()

        # 拦截 API 响应
        captured = {}

        def handle_response(response):
            url = response.url
            if response.status == 200 and any(k in url for k in [
                "usersummary", "sleepData", "dailySleepData",
                "heartrate", "wellness", "bodyBattery",
                "oauth", "token",
            ]):
                try:
                    body = response.json()
                    if body and body != {}:
                        key = url.split("garmin.com")[-1].split("?")[0]
                        captured[key] = body
                        print(f"  捕获: {key}")
                except Exception:
                    pass

        page.on("response", handle_response)

        # 导航到 Garmin Connect
        print("[1/4] 打开 Garmin Connect...")
        page.goto(f"{GARMIN_BASE}/modern/", wait_until="domcontentloaded", timeout=30000)

        # 检查是否需要登录
        page.wait_for_timeout(3000)
        if "sso.garmin.com" in page.url or "signin" in page.url:
            print("  需要登录 — 请在弹出的浏览器中完成登录...")
            # 等待用户手动登录（最多 5 分钟）
            try:
                page.wait_for_url(f"{GARMIN_BASE}/**", timeout=300000)
                print("  登录成功!")
                page.wait_for_timeout(3000)
            except Exception:
                print("  登录超时，请重试")
                browser.close()
                return
        else:
            print("  已登录（复用 session）")

        # 拉取数据
        print(f"[2/4] 拉取最近 {days} 天数据...")
        all_data = {}

        for i in range(days):
            d = (date.today() - timedelta(days=i)).isoformat()
            print(f"  {d}...")
            captured.clear()

            # 导航到对应日期的仪表盘
            page.goto(
                f"{GARMIN_BASE}/modern/daily-summary/{d}",
                wait_until="domcontentloaded",
                timeout=20000,
            )
            page.wait_for_timeout(4000)  # 等待 API 请求完成

            # 如果拦截没抓到，手动用页面上下文请求
            if not captured:
                try:
                    summary = page.evaluate(f"""
                        async () => {{
                            const r = await fetch('/gc-api/usersummary-service/usersummary/daily?calendarDate={d}',
                                {{headers: {{"NK": "NT", "Accept": "application/json"}}}});
                            return r.ok ? await r.json() : null;
                        }}
                    """)
                    if summary:
                        captured[f"/usersummary/{d}"] = summary
                        print(f"    手动获取 summary 成功")
                except Exception as e:
                    print(f"    手动获取失败: {e}")

            # 睡眠数据
            try:
                sleep = page.evaluate(f"""
                    async () => {{
                        const r = await fetch('/gc-api/wellness-service/wellness/dailySleepData/{d}',
                            {{headers: {{"NK": "NT", "Accept": "application/json"}}}});
                        return r.ok ? await r.json() : null;
                    }}
                """)
                if sleep:
                    captured[f"/sleep/{d}"] = sleep
            except Exception:
                pass

            all_data[d] = dict(captured)

        # 获取活动列表
        print("  拉取活动列表...")
        try:
            activities = page.evaluate("""
                async () => {
                    const r = await fetch('/gc-api/activitylist-service/activities/search/activities?limit=20&start=0',
                        {headers: {"NK": "NT", "Accept": "application/json"}});
                    return r.ok ? await r.json() : [];
                }
            """)
            all_data["activities"] = activities
            print(f"    获取到 {len(activities) if isinstance(activities, list) else 0} 条活动")
        except Exception:
            pass

        # 尝试获取 OAuth token（用于注入服务器）
        print("[3/4] 尝试获取 OAuth token...")
        oauth_token = None
        try:
            # 从浏览器存储中提取 token
            cookies = browser.cookies()
            jwt_web = next((c["value"] for c in cookies if c["name"] == "JWT_WEB"), None)
            if jwt_web:
                print(f"  JWT_WEB 获取成功 (len={len(jwt_web)})")
                oauth_token = {"jwt_web": jwt_web}

            # 尝试 OAuth exchange
            exchange = page.evaluate("""
                async () => {
                    try {
                        const r = await fetch('/modern/di-oauth/exchange',
                            {method: 'POST', headers: {"Accept": "application/json"}});
                        return r.ok ? await r.json() : null;
                    } catch(e) { return null; }
                }
            """)
            if exchange and exchange.get("access_token"):
                print(f"  OAuth exchange 成功! refresh_token={'YES' if exchange.get('refresh_token') else 'NO'}")
                oauth_token = exchange
        except Exception as e:
            print(f"  OAuth 获取失败: {e}")

        browser.close()

        # 推送数据
        print("[4/4] 推送数据到 Health API...")
        push_data_to_health_api(all_data, days)

        # 注入 OAuth session
        if oauth_token and oauth_token.get("access_token"):
            inject_oauth_session(oauth_token)

        print("\n✅ 完成!")


def push_data_to_health_api(all_data, days):
    """推送数据到 Health API"""
    import requests

    if not HEALTH_TOKEN:
        print("  未配置 HEALTH_API_TOKEN，跳过推送")
        print(f"  设置: export HEALTH_API_TOKEN=your_jwt_token")
        # 保存到本地文件
        out = Path("/tmp/garmin_sync_data.json")
        out.write_text(json.dumps(all_data, ensure_ascii=False, indent=2))
        print(f"  数据已保存到 {out}")
        return

    headers = {"Authorization": f"Bearer {HEALTH_TOKEN}", "Content-Type": "application/json"}

    for d, day_data in all_data.items():
        if d == "activities":
            continue
        # 找 summary 数据
        summary = None
        for key, val in day_data.items():
            if "usersummary" in key or "summary" in key:
                summary = val
                break
        if summary:
            try:
                record = {
                    "record_date": d,
                    "steps": summary.get("totalSteps"),
                    "resting_heart_rate": summary.get("restingHeartRate"),
                    "avg_heart_rate": summary.get("averageHeartRate"),
                    "stress_level": summary.get("averageStressLevel"),
                    "body_battery_most_charged": summary.get("bodyBatteryHighestValue"),
                    "body_battery_lowest": summary.get("bodyBatteryLowestValue"),
                    "calories_burned": summary.get("totalKilocalories"),
                    "active_minutes": (summary.get("activeSeconds") or 0) // 60,
                }
                r = requests.post(f"{HEALTH_API}/daily-health/garmin/me", json=record, headers=headers)
                print(f"  {d}: pushed (status={r.status_code})")
            except Exception as e:
                print(f"  {d}: push failed ({e})")


def inject_oauth_session(oauth_token):
    """将 OAuth token 注入服务器 DB"""
    if not oauth_token.get("refresh_token"):
        print("  无 refresh_token，跳过注入")
        return

    print("  注入 OAuth session 到服务器...")
    session_data = {
        "oauth2_token.json": {
            "scope": oauth_token.get("scope", ""),
            "jti": oauth_token.get("jti", ""),
            "token_type": oauth_token.get("token_type", "Bearer"),
            "access_token": oauth_token.get("access_token", ""),
            "refresh_token": oauth_token.get("refresh_token", ""),
            "expires_in": oauth_token.get("expires_in", 3600),
            "expires_at": oauth_token.get("expires_at", 0),
            "refresh_token_expires_in": oauth_token.get("refresh_token_expires_in", 7776000),
            "refresh_token_expires_at": oauth_token.get("refresh_token_expires_at", 0),
        }
    }

    session_json = json.dumps(session_data)
    local_tmp = "/tmp/garth_playwright_session.json"
    Path(local_tmp).write_text(session_json)

    r = subprocess.run(
        ["scp", local_tmp, f"{SERVER}:/tmp/garth_playwright_session.json"],
        capture_output=True, text=True, timeout=15,
    )
    if r.returncode != 0:
        print(f"  scp 失败: {r.stderr}")
        return

    inject = f"""
import json
from sqlalchemy import create_engine, text
from app.config import settings
engine = create_engine(settings.effective_database_url)
session = open('/tmp/garth_playwright_session.json').read()
with engine.connect() as conn:
    conn.execute(text(
        "UPDATE garmin_credentials "
        "SET garth_session = :s, "
        "    session_expires_at = NOW() + INTERVAL '23 hours', "
        "    login_locked_until = NULL, "
        "    credentials_valid = true, "
        "    last_error = NULL, "
        "    error_count = 0 "
        "WHERE user_id = {USER_ID}"
    ), {{'s': session}})
    conn.commit()
    print('INJECT_OK')
"""
    r = subprocess.run(
        ["ssh", SERVER, f"cd /opt/health-app/backend && source venv/bin/activate && python3 -c {repr(inject)}"],
        capture_output=True, text=True, timeout=30,
    )
    if "INJECT_OK" in r.stdout:
        print("  ✅ Session 已注入服务器!")
    else:
        print(f"  ❌ 注入失败: {r.stderr or r.stdout}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Playwright 自动化 Garmin 同步")
    parser.add_argument("--days", type=int, default=3, help="同步天数 (默认 3)")
    parser.add_argument("--headless", action="store_true", help="无头模式")
    parser.add_argument("--user-id", type=int, default=3, help="目标用户 ID")
    args = parser.parse_args()
    USER_ID = args.user_id
    run(days=args.days, headless=args.headless)
