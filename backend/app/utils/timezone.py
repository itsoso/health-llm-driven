"""时区工具模块 - 默认使用中国时区"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# 中国时区 (UTC+8)
CHINA_TIMEZONE = timezone(timedelta(hours=8))


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
    """获取用户本地时区;缺失或无效时回退到服务运行环境本地时区。"""
    tz_name = None
    try:
        from app.models.user_profile import UserProfile

        tz_name = (
            db.query(UserProfile.timezone)
            .filter(UserProfile.user_id == user_id)
            .scalar()
        )
    except Exception:
        tz_name = None

    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            pass

    return datetime.now().astimezone().tzinfo or CHINA_TIMEZONE


def get_user_now(db, user_id: int) -> datetime:
    """获取用户本地当前时间。"""
    return datetime.now(get_user_timezone(db, user_id))


def get_user_today(db, user_id: int) -> date:
    """获取用户本地今天日期。"""
    return get_user_now(db, user_id).date()
