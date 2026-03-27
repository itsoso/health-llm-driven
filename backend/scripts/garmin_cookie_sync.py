#!/usr/bin/env python3
"""
Garmin Cookie 同步 — 绕开 SSO 限流的自动化方案

原理：读取本地 Chrome 浏览器的 Garmin cookies，直接调 Garmin Connect API 拉数据，
然后推送到 Health API。完全不走 SSO 登录，不受 429 限制。

前提：Chrome 浏览器已登录 connect.garmin.com

使用方法：
    cd backend && source venv/bin/activate
    python scripts/garmin_cookie_sync.py              # 同步最近 3 天
    python scripts/garmin_cookie_sync.py --days 7     # 同步最近 7 天

自动化（macOS launchd 每小时执行）：
    python scripts/garmin_cookie_sync.py --install-cron
"""
import argparse
import json
import logging
import os
import sys
from datetime import date, timedelta
from typing import Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

# ── 配置 ──────────────────────────────────────────────
GARMIN_BASE = "https://connect.garmin.com"
HEALTH_API = os.environ.get("HEALTH_API_URL", "https://health-api.executor.life/api/v1")
HEALTH_TOKEN = os.environ.get("HEALTH_API_TOKEN", "")

TYPE_MAP = {
    "running": "running", "trail_running": "running",
    "cycling": "cycling", "swimming": "swimming",
    "strength_training": "strength", "yoga": "yoga",
    "walking": "walking", "hiking": "hiking",
    "cardio": "cardio", "other": "other",
}


def get_garmin_session() -> requests.Session:
    """从 Chrome cookies 创建已认证的 requests session"""
    try:
        import browser_cookie3
        cookies = browser_cookie3.chrome(domain_name=".garmin.com")
    except Exception as e:
        log.error(f"无法读取 Chrome cookies: {e}")
        log.error("确保 Chrome 已登录 connect.garmin.com，并且终端有磁盘访问权限")
        log.error("macOS: 系统设置 → 隐私与安全 → 完全磁盘访问权限 → 添加终端/iTerm")
        sys.exit(1)

    session = requests.Session()
    session.cookies = cookies
    session.headers.update({
        "NK": "NT",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    })

    # 获取 CSRF token
    try:
        r = session.get(f"{GARMIN_BASE}/modern/", allow_redirects=False)
        # 从 HTML meta 标签提取 csrf-token
        import re
        match = re.search(r'csrf-token["\s]+content="([^"]+)"', r.text)
        if match:
            session.headers["connect-csrf-token"] = match.group(1)
            log.info(f"CSRF token 获取成功")
        else:
            log.warning("未找到 CSRF token，某些 API 可能会 403")
    except Exception as e:
        log.warning(f"获取 CSRF token 失败: {e}")

    # 验证 session
    r = session.get(f"{GARMIN_BASE}/gc-api/usersummary-service/usersummary/daily?calendarDate={date.today().isoformat()}")
    if r.status_code != 200:
        log.error(f"Garmin session 无效 (status={r.status_code})，请在 Chrome 中重新登录 connect.garmin.com")
        sys.exit(1)

    log.info("Garmin session 有效")
    return session


def fetch_daily_summaries(session: requests.Session, days: int) -> list:
    """拉取每日汇总数据"""
    results = []
    for i in range(days):
        d = (date.today() - timedelta(days=i)).isoformat()
        try:
            r = session.get(f"{GARMIN_BASE}/gc-api/usersummary-service/usersummary/daily?calendarDate={d}")
            if r.status_code == 200:
                data = r.json()
                summary = {
                    "record_date": d,
                    "steps": data.get("totalSteps"),
                    "resting_heart_rate": data.get("restingHeartRate"),
                    "avg_heart_rate": data.get("averageHeartRate"),
                    "max_heart_rate": data.get("maxHeartRate"),
                    "min_heart_rate": data.get("minHeartRate"),
                    "stress_level": data.get("averageStressLevel"),
                    "body_battery_most_charged": data.get("bodyBatteryHighestValue"),
                    "body_battery_lowest": data.get("bodyBatteryLowestValue"),
                    "calories_burned": data.get("totalKilocalories"),
                    "active_minutes": (data.get("activeSeconds") or 0) // 60,
                }

                # 睡眠数据
                sr = session.get(f"{GARMIN_BASE}/gc-api/sleep-service/sleep/dailySleepData?date={d}")
                if sr.status_code == 200:
                    sleep = sr.json().get("dailySleepDTO", {})
                    scores = sleep.get("sleepScores", {})
                    summary.update({
                        "sleep_score": scores.get("overall", {}).get("value"),
                        "total_sleep_duration": (sleep.get("sleepTimeSeconds") or 0) // 60,
                        "deep_sleep_duration": (sleep.get("deepSleepSeconds") or 0) // 60,
                        "rem_sleep_duration": (sleep.get("remSleepSeconds") or 0) // 60,
                        "light_sleep_duration": (sleep.get("lightSleepSeconds") or 0) // 60,
                        "awake_duration": (sleep.get("awakeSleepSeconds") or 0) // 60,
                    })

                # 去掉 None 值
                summary = {k: v for k, v in summary.items() if v is not None}
                results.append(summary)
                log.info(f"  {d}: steps={summary.get('steps')} sleep={summary.get('sleep_score')}")
            else:
                log.warning(f"  {d}: HTTP {r.status_code}")
        except Exception as e:
            log.warning(f"  {d}: 错误 {e}")

    return results


def fetch_activities(session: requests.Session, days: int) -> list:
    """拉取运动记录"""
    results = []
    try:
        r = session.get(f"{GARMIN_BASE}/gc-api/activitylist-service/activities/search/activities?limit=50&start=0")
        if r.status_code != 200:
            log.warning(f"活动列表获取失败: HTTP {r.status_code}")
            return results

        cutoff = date.today() - timedelta(days=days)
        for a in r.json():
            start = a.get("startTimeLocal", "")
            if start and start[:10] < cutoff.isoformat():
                continue

            type_key = a.get("activityType", {}).get("typeKey", "other")
            avg_speed = a.get("averageSpeed", 0) or 0
            max_speed = a.get("maxSpeed", 0) or 0

            activity = {
                "garmin_activity_id": str(a.get("activityId")),
                "workout_date": start[:10] if start else date.today().isoformat(),
                "start_time": start or None,
                "workout_type": TYPE_MAP.get(type_key, "other"),
                "workout_name": a.get("activityName"),
                "duration_seconds": int(a.get("duration", 0) or 0),
                "moving_duration_seconds": int(a.get("movingDuration", 0) or 0),
                "distance_meters": round(a.get("distance", 0) or 0, 2),
                "avg_speed_kmh": round(avg_speed * 3.6, 2),
                "max_speed_kmh": round(max_speed * 3.6, 2),
                "avg_heart_rate": a.get("averageHR"),
                "max_heart_rate": a.get("maxHR"),
                "calories": int(a.get("calories", 0) or 0),
                "steps": a.get("steps"),
                "elevation_gain_meters": round(a.get("elevationGain", 0) or 0, 1),
            }
            activity = {k: v for k, v in activity.items() if v is not None}
            results.append(activity)

        log.info(f"  获取到 {len(results)} 条活动记录")
    except Exception as e:
        log.warning(f"活动记录获取失败: {e}")

    return results


def push_to_health_api(dailies: list, activities: list):
    """推送到 Health API"""
    if not HEALTH_TOKEN:
        log.error("未配置 HEALTH_API_TOKEN，无法推送")
        log.error("设置: export HEALTH_API_TOKEN=your_jwt_token")
        return False

    payload = {"dailies": dailies, "activities": activities}

    try:
        r = requests.post(
            f"{HEALTH_API}/garmin-import/bulk",
            json=payload,
            headers={"Authorization": f"Bearer {HEALTH_TOKEN}"},
            timeout=30,
        )
        if r.status_code == 200:
            result = r.json()
            log.info(f"推送成功: daily={result['daily_imported']}新/{result['daily_updated']}更新, "
                     f"activity={result['activity_imported']}新/{result['activity_skipped']}跳过")
            return True
        else:
            log.error(f"推送失败: HTTP {r.status_code} {r.text[:200]}")
            return False
    except Exception as e:
        log.error(f"推送失败: {e}")
        return False


def install_cron():
    """安装 macOS launchd 定时任务（每小时执行）"""
    script_path = os.path.abspath(__file__)
    venv_python = os.path.join(os.path.dirname(script_path), "..", "venv", "bin", "python")
    venv_python = os.path.abspath(venv_python)

    plist_name = "com.health.garmin-sync"
    plist_path = os.path.expanduser(f"~/Library/LaunchAgents/{plist_name}.plist")

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{plist_name}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{venv_python}</string>
        <string>{script_path}</string>
        <string>--days</string>
        <string>2</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HEALTH_API_TOKEN</key>
        <string>{HEALTH_TOKEN}</string>
        <key>HEALTH_API_URL</key>
        <string>{HEALTH_API}</string>
    </dict>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>StandardOutPath</key>
    <string>/tmp/garmin-sync.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/garmin-sync-error.log</string>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>"""

    with open(plist_path, "w") as f:
        f.write(plist_content)

    os.system(f"launchctl unload {plist_path} 2>/dev/null")
    os.system(f"launchctl load {plist_path}")

    print(f"✅ 定时任务已安装: 每小时自动同步最近 2 天数据")
    print(f"   配置文件: {plist_path}")
    print(f"   日志: /tmp/garmin-sync.log")
    print(f"   停用: launchctl unload {plist_path}")


def main():
    parser = argparse.ArgumentParser(description="Garmin Cookie 同步")
    parser.add_argument("--days", type=int, default=3, help="同步天数 (默认3)")
    parser.add_argument("--install-cron", action="store_true", help="安装每小时自动同步")
    args = parser.parse_args()

    if args.install_cron:
        if not HEALTH_TOKEN:
            print("请先设置 HEALTH_API_TOKEN:")
            print("  export HEALTH_API_TOKEN=your_jwt_token")
            sys.exit(1)
        install_cron()
        return

    log.info(f"=== Garmin Cookie 同步 (最近 {args.days} 天) ===")

    # 1. 获取 Garmin session
    session = get_garmin_session()

    # 2. 拉取数据
    log.info("拉取每日汇总...")
    dailies = fetch_daily_summaries(session, args.days)

    log.info("拉取运动记录...")
    activities = fetch_activities(session, args.days)

    if not dailies and not activities:
        log.warning("没有获取到任何数据")
        return

    # 3. 推送到 Health API
    log.info("推送到 Health API...")
    push_to_health_api(dailies, activities)

    log.info("=== 同步完成 ===")


if __name__ == "__main__":
    main()
