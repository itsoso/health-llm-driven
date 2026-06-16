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
