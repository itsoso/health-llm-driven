"""Narrow, secret-free projection of the authenticated credential-status read.

This endpoint has no job correlation. A last successful sync is historical
evidence, never an acknowledgement that the user's latest task completed.
"""
from datetime import datetime
from typing import Any


def project_garmin_status(payload: Any) -> dict:
    if not isinstance(payload, dict) or type(payload.get('bound')) is not bool:
        return {'lookup_status': 'failed', 'current_task_status': 'unknown'}
    result = {'lookup_status': 'available', 'current_task_status': 'unknown',
              'bound': payload['bound']}
    if not payload['bound']:
        return result
    for key in ('sync_enabled', 'credentials_valid', 'requires_mfa'):
        if type(payload.get(key)) is not bool:
            return {'lookup_status': 'failed', 'current_task_status': 'unknown'}
        result[key] = payload[key]
    count = payload.get('error_count')
    if type(count) is not int or count < 0:
        return {'lookup_status': 'failed', 'current_task_status': 'unknown'}
    result['error_count'] = count
    last = payload.get('last_sync_at')
    if last is not None:
        try:
            datetime.fromisoformat(last)
        except (TypeError, ValueError):
            return {'lookup_status': 'failed', 'current_task_status': 'unknown'}
    result['last_sync_at'] = last
    return result


def garmin_status_text(payload: Any) -> str:
    status = project_garmin_status(payload)
    if not isinstance(payload, dict) or payload.get('lookup_status') != 'available' or status['lookup_status'] != 'available':
        return '佳明同步状态：本轮状态查询未成功，无法确认刚才的任务是否完成。'
    if not status['bound']:
        return '佳明同步状态：当前账号尚未绑定佳明，请先到「设置 → 设备」绑定。'
    if status['requires_mfa']:
        detail = '账号需要两步验证，请到「设置 → 设备」完成验证。'
    elif not status['credentials_valid']:
        detail = '登录状态已失效，请到「设置 → 设备」重新连接。'
    elif not status['sync_enabled']:
        detail = '自动同步已关闭，可到「设置 → 设备」开启。'
    elif status['error_count']:
        detail = '账号存在同步错误，可到「设置 → 设备」检查连接。'
    else:
        detail = '账号已连接，同步开关已开启。'
    # Keep the stored offset visible; never interpret a timezone-less historical
    # timestamp as the user's local time or as a correlated task receipt.
    if status.get('last_sync_at'):
        detail += f"最近一次成功同步时间：{status['last_sync_at']}。"
    else:
        detail += '尚无成功同步时间记录。'
    return f'佳明同步状态：{detail}仍无法确认刚才的任务是否完成；已有睡眠记录不代表本次同步已完成。'
