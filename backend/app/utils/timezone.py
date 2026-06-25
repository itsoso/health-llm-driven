"""时区工具模块 - 默认使用中国时区"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# 中国时区 (UTC+8)
CHINA_TIMEZONE = timezone(timedelta(hours=8))

# 生效时区的最终兜底(IANA 名)。本产品以中国为锚。
DEFAULT_TIMEZONE_NAME = "Asia/Shanghai"


def is_valid_timezone(name: Optional[str]) -> bool:
    """是否合法 IANA 时区名(能被 ZoneInfo 解析)。空/None/未知 → False。"""
    if not name:
        return False
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def resolve_timezone_name(
    manual_tz: Optional[str] = None,
    detected_tz: Optional[str] = None,
    legacy_tz: Optional[str] = None,
) -> Tuple[str, str]:
    """派生用户生效时区名 + 来源。纯函数,无 DB。

    优先级:手动锁定(manual)→ 设备/位置检测(detected)→ 旧 profile.timezone 列
    (legacy)→ 默认中国(default)。非法/空值跳过。返回 (iana_name, source)。

    与 location_resolver.resolve_effective_location 同构:manual 覆盖 auto,auto 自动跟随。
    """
    for name, source in ((manual_tz, "manual"), (detected_tz, "detected"), (legacy_tz, "profile")):
        if is_valid_timezone(name):
            return name, source  # type: ignore[return-value]
    return DEFAULT_TIMEZONE_NAME, "default"


def get_china_today() -> date:
    """获取中国时区的今天日期"""
    return datetime.now(CHINA_TIMEZONE).date()


def get_china_now() -> datetime:
    """获取中国时区的当前时间"""
    return datetime.now(CHINA_TIMEZONE)


def get_china_yesterday() -> date:
    """获取中国时区的昨天日期"""
    return get_china_today() - timedelta(days=1)


def to_china_date(dt: datetime) -> date:
    """把任意 datetime 归一到中国时区后的日历日期。

    naive datetime 一律按 UTC 解读(本仓库 event_time 等列存的是 UTC 墙钟,
    naive)。aware datetime 按其自带时区换算。返回中国时区(UTC+8)下的 .date()。

    动机:在上海午夜边界,16:30Z = 上海次日 00:30 —— 直接 `dt.date()`(UTC 基准)
    会把完成事件解析到错误的「中国日」,导致 due 协议匹配错日 / 当日协议关不上。
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CHINA_TIMEZONE).date()


def get_user_timezone(db, user_id: int):
    """获取用户本地时区。

    生效时区按 resolve_timezone_name 的优先级派生:用户手动锁定(manual_timezone)→
    设备/位置自动检测(detected_timezone)→ 旧 timezone 列 → 默认中国。

    回退用 CHINA_TIMEZONE 而非服务器 OS 时区:本产品以中国为锚,服务器/CI runner
    的 OS 时区不代表用户所在地(历史教训:回退到 runner OS TZ 会在 UTC CI 上引发
    午夜边界 date flake)。
    """
    name = DEFAULT_TIMEZONE_NAME
    try:
        from app.models.user_profile import UserProfile

        row = (
            db.query(
                UserProfile.manual_timezone,
                UserProfile.detected_timezone,
                UserProfile.timezone,
            )
            .filter(UserProfile.user_id == user_id)
            .first()
        )
        if row is not None:
            name, _ = resolve_timezone_name(row[0], row[1], row[2])
    except Exception:
        # 列尚未迁移 / 查询失败 → 安全降级到中国时区,绝不抛
        name = DEFAULT_TIMEZONE_NAME

    if name != DEFAULT_TIMEZONE_NAME:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            pass

    # 默认中国用固定偏移(不依赖系统 tzdata,保持历史行为)
    return CHINA_TIMEZONE


def get_user_now(db, user_id: int) -> datetime:
    """获取用户本地当前时间。"""
    return datetime.now(get_user_timezone(db, user_id))


def get_user_today(db, user_id: int) -> date:
    """获取用户本地今天日期。"""
    return get_user_now(db, user_id).date()
