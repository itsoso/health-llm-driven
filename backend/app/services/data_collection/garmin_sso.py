"""Garmin SSO 探测器.

从 garmin_connect.py 抽出. 这是一个完全独立的工具函数, 用于在调度器中
轻量级探测 Garmin SSO 是否可用 (避免触发限流的尝试登录).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def probe_sso_availability(is_cn: bool = False, timeout: int = 10) -> bool:
    """轻量级探测 Garmin SSO 是否可用 (GET 请求, 不会触发登录).

    用于在调度器中, 当 DB 锁定到期后, 先探测 SSO 是否还在限流,
    避免直接尝试登录导致再次触发 429 并延长锁定.

    Args:
        is_cn: 是否探测中国版 SSO
        timeout: 请求超时秒数

    Returns:
        True 表示 SSO 可用 (返回 200), False 表示仍在限流或不可达
    """
    import requests

    sso_url = "https://sso.garmin.cn/sso/signin" if is_cn else "https://sso.garmin.com/sso/signin"

    try:
        resp = requests.get(sso_url, timeout=timeout, allow_redirects=True)
        if resp.status_code == 429:
            logger.info(f"🔍 SSO 探测: {sso_url} 返回 429, 仍在限流中")
            return False
        logger.info(f"🔍 SSO 探测: {sso_url} 返回 {resp.status_code}, SSO 可用")
        return True
    except Exception as e:
        logger.warning(f"🔍 SSO 探测失败 ({sso_url}): {e}")
        return False
