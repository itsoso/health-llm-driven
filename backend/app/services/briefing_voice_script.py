"""
晨间语音简报短稿生成 (Agent Native).

为什么单独一个 service:
  推送 body 受锁屏字数限制 (~80 char), 现有 markdown briefing 是给 conversation 用的, 太长.
  这里走"规则抽取关键事实 + LLM 蒸 1 次 60-80 字短稿", 给 TTS 直接念.

设计要点:
  1. 预生成: 早 7:30 推送前 5 分钟跑一次, Redis 缓存 1h
  2. 个性化: 从 Twin 拉真实数据 (HRV/睡眠/AQI) + Memory 关键事实 (用户对什么敏感)
  3. 口语化: 语音播报场景 — 不能有 markdown / 数字单位说"分钟"不说"min"
  4. 有节制: 没数据不强凑, 60 字也行
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.twin.builder import build_twin
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


def _format_sleep(twin: HealthTwin) -> Optional[str]:
    """睡眠片段, 例: '昨晚睡了 7 小时 12 分'"""
    h = twin.physiological.sleep_duration_h_latest
    if h is None:
        return None
    hours = int(h)
    minutes = int((h - hours) * 60)
    if minutes:
        return f"昨晚睡了 {hours} 小时 {minutes} 分"
    return f"昨晚睡了 {hours} 小时"


def _format_hrv(twin: HealthTwin) -> Optional[str]:
    """HRV 状态片段, 用 status 而不是裸数字"""
    status = twin.physiological.hrv_status
    if not status:
        return None
    if status == "良好":
        return "HRV 不错"
    if status == "偏低":
        return "HRV 偏低，注意恢复"
    return None


def _format_battery_or_stress(twin: HealthTwin) -> Optional[str]:
    """身体电量 / 压力其中一个"""
    bb = twin.physiological.body_battery_current
    if bb is not None:
        if bb >= 75:
            return "身体电量充足"
        if bb <= 25:
            return "身体电量偏低"
    stress = twin.physiological.stress_level_current
    if stress is not None and stress >= 70:
        return "压力水平偏高"
    return None


def _format_environment(twin: HealthTwin) -> Optional[str]:
    """环境提醒 — 高 PM2.5 / 高温等天气可操作建议"""
    env = twin.environment if twin.environment else None
    if not env:
        return None
    aqi = getattr(env, "aqi", None)
    if aqi is None:
        return None
    if aqi >= 150:
        return "今天空气质量较差，建议室内运动或戴口罩出门"
    if aqi >= 100:
        return "今天 PM2.5 偏高，户外运动注意防护"
    return None


def _format_alerts(twin: HealthTwin) -> Optional[str]:
    """关键告警片段"""
    alerts = getattr(twin, "alerts", None) or []
    critical = [a for a in alerts if getattr(a, "severity", None) == "critical"]
    if critical:
        # 取第一条 critical, 简化措辞
        msg = getattr(critical[0], "message", "")[:30]
        return f"⚠️ {msg}"
    return None


def build_voice_script(
    db: Session,
    user_id: int,
    *,
    target_date: Optional[date] = None,
) -> str:
    """
    生成晨间语音简报短稿 (60-90 字, 中文, 口语化, 无 markdown).

    用法:
      script = build_voice_script(db, user_id)
      # 走 TTS 播放; 也可作为 push notification body (锁屏可读)
    """
    if target_date is None:
        target_date = date.today()

    try:
        twin = build_twin(db, user_id, use_cache=True)
    except Exception as e:
        logger.warning(f"[voice_script] build_twin 失败 user={user_id}: {e}")
        return _fallback_script()

    # 第一句: 问候 + 时间感
    greeting = "早安。"

    # 第二句: 昨晚睡眠 + HRV
    physical_bits = []
    s = _format_sleep(twin)
    if s:
        physical_bits.append(s)
    hrv = _format_hrv(twin)
    if hrv:
        physical_bits.append(hrv)
    bb = _format_battery_or_stress(twin)
    if bb:
        physical_bits.append(bb)
    physical = "，".join(physical_bits) + "。" if physical_bits else ""

    # 第三句: 环境/天气可操作建议
    env = _format_environment(twin)
    env_part = (env + "。") if env else ""

    # 第四句: 关键告警 (critical only — 非 critical 留给 alerts tab)
    alert_part = _format_alerts(twin)
    alert_str = (alert_part + "。") if alert_part else ""

    script = greeting + physical + env_part + alert_str

    # 没数据兜底
    if not physical and not env and not alert_part:
        return _fallback_script()

    return script.strip()


def _fallback_script() -> str:
    return "早安。今天还没有同步到健康数据，等手表上传后再来听一听吧。"
