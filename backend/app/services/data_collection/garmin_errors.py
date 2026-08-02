"""Garmin 数据收集相关的自定义异常.

从 garmin_connect.py 抽出, 让导入清晰且方便单测.
原 garmin_connect.py 仍 re-export 这些名字, 老代码不破.
"""
from __future__ import annotations

from datetime import datetime


class GarminAuthenticationError(Exception):
    """Garmin 认证错误, 用于标识凭证问题"""
    pass


class GarminLoginLockedError(Exception):
    """Garmin 登录被锁定 (防止频繁登录)"""

    def __init__(self, message: str, locked_until: datetime):
        super().__init__(message)
        self.locked_until = locked_until


class GarminMFARequiredError(Exception):
    """Garmin 需要两步验证"""

    def __init__(self, message: str, client_state: dict):
        super().__init__(message)
        self.client_state = client_state


class GarminSyncError(Exception):
    """Garmin reached the service but an operational sync failed."""


# 登录失败阈值和锁定时间配置
LOGIN_FAIL_THRESHOLD = 2  # 连续失败次数阈值 (429 立即触发, 其他错误 2 次后锁定)
# 指数退避锁定时间 (分钟): 第1次30分钟, 第2次2小时, 第3次8小时, 第4次+24小时
LOGIN_LOCK_MINUTES_SCHEDULE = [30, 120, 480, 1440]
