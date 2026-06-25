"""时区:用户本地时区优先,缺省确定性回退中国时区(而非服务器/CI runner 的 OS 时区)。

锁 design:follow-up 到期、用药时长/过期等「日历日」判定按 UserProfile.timezone 走;
无 profile 时回退中国时区,不随 runner OS 时区漂移(否则 UTC runner 午夜边界 date flake)。
"""
from datetime import timedelta
from zoneinfo import ZoneInfo

from app.models.user_profile import UserProfile
from app.utils.timezone import (
    CHINA_TIMEZONE,
    get_china_today,
    get_user_now,
    get_user_timezone,
    get_user_today,
    is_valid_timezone,
    resolve_timezone_name,
)
from tests.conftest import create_authenticated_user


def test_no_profile_falls_back_to_china_not_runner_os(db):
    """无 UserProfile → 回退中国时区,与 get_china_today 一致(不依赖 runner OS TZ)。"""
    user, _ = create_authenticated_user(db)
    assert get_user_today(db, user.id) == get_china_today()
    assert get_user_now(db, user.id).utcoffset() == timedelta(hours=8)


def test_user_profile_timezone_is_honored(db):
    """设了 UserProfile.timezone → 按用户本地时区,而非中国时区。"""
    user, _ = create_authenticated_user(db)
    db.add(UserProfile(user_id=user.id, timezone="America/Los_Angeles"))
    db.commit()
    assert get_user_timezone(db, user.id) == ZoneInfo("America/Los_Angeles")
    # LA 偏移是 -08:00 / -07:00(夏令时),绝不会是 +08:00
    assert get_user_now(db, user.id).utcoffset() != timedelta(hours=8)


def test_invalid_timezone_falls_back_to_china(db):
    """无效时区字符串 → 同样确定性回退中国时区,不抛、不漂移到 runner OS。"""
    user, _ = create_authenticated_user(db)
    db.add(UserProfile(user_id=user.id, timezone="Not/AZone"))
    db.commit()
    assert get_user_timezone(db, user.id) == CHINA_TIMEZONE
    assert get_user_today(db, user.id) == get_china_today()


# ── resolver 纯函数:优先级 manual → detected → legacy → 默认中国 ──────────
def test_resolver_precedence():
    assert resolve_timezone_name("America/New_York", "Asia/Tokyo", "Asia/Shanghai") == ("America/New_York", "manual")
    assert resolve_timezone_name(None, "Asia/Tokyo", "Asia/Shanghai") == ("Asia/Tokyo", "detected")
    assert resolve_timezone_name(None, None, "Europe/Paris") == ("Europe/Paris", "profile")
    assert resolve_timezone_name(None, None, None) == ("Asia/Shanghai", "default")
    # 非法值被跳过,继续往下找
    assert resolve_timezone_name("Bogus/Zone", "Asia/Tokyo", None) == ("Asia/Tokyo", "detected")
    assert resolve_timezone_name("", "  ", "also bad") == ("Asia/Shanghai", "default")


def test_is_valid_timezone():
    assert is_valid_timezone("Asia/Shanghai")
    assert is_valid_timezone("America/Los_Angeles")
    assert not is_valid_timezone("Not/AZone")
    assert not is_valid_timezone("")
    assert not is_valid_timezone(None)


# ── 自动跟随 detected;manual 覆盖;旅行(detected 变)生效时区跟随 ──────────
def test_detected_timezone_auto_follows(db):
    """无手动锁定 → 生效时区 = detected(自动跟随设备/位置)。"""
    user, _ = create_authenticated_user(db)
    db.add(UserProfile(user_id=user.id, detected_timezone="America/Los_Angeles"))
    db.commit()
    assert get_user_timezone(db, user.id) == ZoneInfo("America/Los_Angeles")
    assert get_user_now(db, user.id).utcoffset() != timedelta(hours=8)


def test_manual_overrides_detected(db):
    """手动锁定优先于设备检测(旅行时不被 detected 带跑)。"""
    user, _ = create_authenticated_user(db)
    db.add(UserProfile(
        user_id=user.id,
        manual_timezone="Asia/Shanghai",
        detected_timezone="America/Los_Angeles",
    ))
    db.commit()
    # 生效 = 上海(UTC+8);默认/上海路径返回固定偏移 CHINA_TIMEZONE,断言看偏移而非对象
    assert get_user_now(db, user.id).utcoffset() == timedelta(hours=8)
    assert get_user_today(db, user.id) == get_china_today()


# ── 端点:device 上报(auto)/ manual 锁定+解锁 / 非法 400 ──────────────────
def test_device_timezone_endpoint_auto_follow(client, db):
    user, token = create_authenticated_user(db)
    h = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/v1/profile/me/device-timezone", headers=h, json={"timezone": "America/Los_Angeles"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["timezone"] == "America/Los_Angeles" and body["source"] == "detected"
    assert body["detected_timezone"] == "America/Los_Angeles" and body["manual_timezone"] is None
    # 非法时区 → 400
    bad = client.post("/api/v1/profile/me/device-timezone", headers=h, json={"timezone": "Not/AZone"})
    assert bad.status_code == 400


def test_manual_timezone_lock_then_unlock(client, db):
    user, token = create_authenticated_user(db)
    h = {"Authorization": f"Bearer {token}"}
    # 设备在洛杉矶
    client.post("/api/v1/profile/me/device-timezone", headers=h, json={"timezone": "America/Los_Angeles"})
    # 手动锁定上海 → 覆盖 detected
    lock = client.put("/api/v1/profile/me/manual-timezone", headers=h, json={"timezone": "Asia/Shanghai"})
    assert lock.status_code == 200, lock.text
    assert lock.json()["timezone"] == "Asia/Shanghai" and lock.json()["source"] == "manual"
    # 解锁(传 null)→ 恢复自动跟随设备(洛杉矶)
    unlock = client.put("/api/v1/profile/me/manual-timezone", headers=h, json={"timezone": None})
    assert unlock.status_code == 200, unlock.text
    assert unlock.json()["timezone"] == "America/Los_Angeles" and unlock.json()["source"] == "detected"
    # 手动锁定非法 → 400
    bad = client.put("/api/v1/profile/me/manual-timezone", headers=h, json={"timezone": "Not/AZone"})
    assert bad.status_code == 400


def test_effective_timezone_endpoint_default(client, db):
    user, token = create_authenticated_user(db)
    h = {"Authorization": f"Bearer {token}"}
    r = client.get("/api/v1/profile/me/effective-timezone", headers=h)
    assert r.status_code == 200, r.text
    # 全新用户:无 detected/manual,旧 timezone 列默认 Asia/Shanghai
    assert r.json()["timezone"] == "Asia/Shanghai"
    # 未认证拒绝
    assert client.get("/api/v1/profile/me/effective-timezone").status_code in (401, 403)
