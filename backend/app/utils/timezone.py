"""时区工具模块 - 默认使用中国时区"""
from datetime import date, datetime, timedelta, timezone

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

