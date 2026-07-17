"""推送服务主类 - 统一管理各渠道推送"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Literal
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.notification import (
    NotificationLog,
    UserNotificationSetting,
    ReminderConfig,
    NotificationType,
    NotificationChannel,
    NotificationStatus
)
from app.services.advice_guard import AdviceCandidate, guard_and_record_advice
from app.services.notification.gatekeeper import gate_proactive_notification
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)

QuietHoursPolicy = Literal["delay", "bypass", "drop"]

MORNING_PUSH_FLOOR = "09:00"
DEFAULT_QUIET_HOURS_START = "22:00"
DEFAULT_QUIET_HOURS_END = "09:00"


# H1-B: severity 排序 (低 → 高). 其他字面量默认 0.
_SEVERITY_ORDER = {
    "info": 0,
    "low": 1,
    "warning": 2,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

_ADVICE_LEDGER_NOTIFICATION_TYPES = {
    NotificationType.HEALTH_ALERT.value,
    NotificationType.AI_ADVICE.value,
    "trend_report",
}

_TELEGRAM_FALLBACK_BLOCKED_TYPES = {
    NotificationType.REMINDER.value,
    "plan_reminder",
}


def _severity_rank(s: Optional[str]) -> int:
    return _SEVERITY_ORDER.get((s or "info").lower(), 0)


def resolve_quiet_hours_policy(
    severity: str,
    quiet_hours_policy: Optional[QuietHoursPolicy],
    respect_quiet_hours: bool,
) -> QuietHoursPolicy:
    """决定静默时段策略.

    基线: 显式 quiet_hours_policy 优先; 否则 respect_quiet_hours=True→delay, False→bypass.

    2026-05-30 (反转 2026-05-11 的"严格不打扰"): critical 健康告警可穿透普通
    quiet-hours. 但 09:00 前的晨间睡眠地板在 send_notification 顶层统一兜住,
    避免 07:00/08:00 影响睡眠.
    """
    policy: QuietHoursPolicy = quiet_hours_policy or (
        "delay" if respect_quiet_hours else "bypass"
    )
    if policy not in {"delay", "bypass", "drop"}:
        raise ValueError(f"invalid quiet_hours_policy: {policy}")
    if _severity_rank(severity) >= _severity_rank("critical"):
        return "bypass"
    return policy


def _allows_telegram_fallback(notification_type: str) -> bool:
    """Global Telegram chat is an operator fallback, not a per-user reminder channel."""

    return notification_type not in _TELEGRAM_FALLBACK_BLOCKED_TYPES


def _hhmm_to_minutes(value: Optional[str], fallback: str) -> int:
    try:
        raw = value or fallback
        h, m = (int(x) for x in raw.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError(raw)
        return h * 60 + m
    except Exception:
        h, m = (int(x) for x in fallback.split(":"))
        return h * 60 + m


def _is_time_in_window(current: int, start: int, end: int) -> bool:
    if start > end:
        return current >= start or current < end
    return start <= current < end


def _next_local_time(now: datetime, minutes: int) -> datetime:
    candidate = now.replace(
        hour=minutes // 60,
        minute=minutes % 60,
        second=0,
        microsecond=0,
    )
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def _not_before_morning_floor(candidate: datetime, floor_minutes: int) -> datetime:
    candidate_min = candidate.hour * 60 + candidate.minute
    if candidate_min >= floor_minutes:
        return candidate
    return candidate.replace(
        hour=floor_minutes // 60,
        minute=floor_minutes % 60,
        second=0,
        microsecond=0,
    )


def _is_before_morning_floor(now: datetime) -> bool:
    floor_min = _hhmm_to_minutes(MORNING_PUSH_FLOOR, "09:00")
    return now.hour * 60 + now.minute < floor_min


def normalize_morning_sleep_floor_time(value: Optional[str]) -> str:
    """Clamp user-visible morning notification times to the 09:00 sleep floor."""
    floor_min = _hhmm_to_minutes(MORNING_PUSH_FLOOR, "09:00")
    minutes = _hhmm_to_minutes(value, MORNING_PUSH_FLOOR)
    if minutes < floor_min:
        minutes = floor_min
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _morning_floor_at(now: datetime) -> datetime:
    floor_min = _hhmm_to_minutes(MORNING_PUSH_FLOOR, "09:00")
    return now.replace(
        hour=floor_min // 60,
        minute=floor_min % 60,
        second=0,
        microsecond=0,
    )


def _advice_candidate_from_push(
    *,
    user_id: int,
    notification_type: str,
    title: str,
    content: str,
    data: Optional[Dict[str, Any]],
    severity: str,
) -> AdviceCandidate | None:
    """Map user-visible advice pushes into the shared advice ledger contract."""

    ntype = notification_type.value if hasattr(notification_type, "value") else str(notification_type)
    if ntype not in _ADVICE_LEDGER_NOTIFICATION_TYPES:
        return None
    if _severity_rank(severity) >= _severity_rank("critical"):
        return None

    text_blob = f"{title}\n{content}".lower()
    is_movement = any(word in text_blob for word in ["运动", "跑步", "训练", "activity", "run", "workout"])
    if not is_movement:
        return None

    if any(word in text_blob for word in ["降低", "暂停跑", "休跑", "恢复", "reduce", "rest"]):
        target_value = "reduce_intensity"
    elif any(word in text_blob for word in ["运动不足", "提高运动", "中等强度", "increase", "low_activity"]):
        target_value = "increase_activity"
    else:
        target_value = (data or {}).get("target_value") or "movement_advice"

    rule_id = (data or {}).get("rule_id")
    metric_key = (data or {}).get("metric_key") or rule_id or "movement"
    source_id = (data or {}).get("advice_source_id") or f"push:{ntype}:{rule_id or title}:{get_china_now().date().isoformat()}"

    return AdviceCandidate(
        user_id=user_id,
        source="push",
        source_id=source_id,
        domain="movement",
        title=title,
        body=content or title,
        metric_key=metric_key,
        target_value=target_value,
        evidence_tier=(data or {}).get("evidence_tier") or "wearable_proxy",
        confidence=(data or {}).get("confidence") or "medium",
        claim_boundary=(data or {}).get("claim_boundary") or "这是健康管理提醒, 不替代医生诊断、处方或治疗。",
        valid_for_date=get_china_now().date(),
    )


class PushService:
    """
    推送服务主类

    统一管理微信、iOS、邮件等多渠道推送
    """

    def __init__(self, db: Session):
        self.db = db
        self._wechat_service = None
        self._ios_service = None
        self._telegram_service = None

    @property
    def wechat(self):
        """延迟加载微信推送服务"""
        if self._wechat_service is None:
            from .wechat_push import WeChatPushService
            self._wechat_service = WeChatPushService()
        return self._wechat_service

    @property
    def ios(self):
        """延迟加载 iOS 推送服务"""
        if self._ios_service is None:
            from .ios_push import IOSPushService
            self._ios_service = IOSPushService()
        return self._ios_service

    @property
    def telegram(self):
        """延迟加载 Telegram 推送服务"""
        if self._telegram_service is None:
            from .telegram_push import TelegramPushService
            self._telegram_service = TelegramPushService()
        return self._telegram_service

    def get_user_settings(self, user_id: int) -> Optional[UserNotificationSetting]:
        """获取用户推送设置"""
        return self.db.query(UserNotificationSetting).filter(
            UserNotificationSetting.user_id == user_id
        ).first()

    def create_or_update_settings(
        self,
        user_id: int,
        settings: Dict[str, Any]
    ) -> UserNotificationSetting:
        """创建或更新用户推送设置"""
        settings = dict(settings)
        for key in ("morning_briefing_time", "quiet_hours_end"):
            if key in settings and settings[key] is not None:
                settings[key] = normalize_morning_sleep_floor_time(settings[key])

        existing = self.get_user_settings(user_id)

        if existing:
            for key, value in settings.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            self.db.commit()
            return existing
        else:
            new_settings = UserNotificationSetting(user_id=user_id, **settings)
            self.db.add(new_settings)
            self.db.commit()
            self.db.refresh(new_settings)
            return new_settings

    def is_quiet_hours(self, user_id: int) -> bool:
        """检查当前是否在免打扰时段。普通 push 09:00 前一律延迟。"""
        settings = self.get_user_settings(user_id)

        now = get_china_now()
        current_min = now.hour * 60 + now.minute
        floor_min = _hhmm_to_minutes(MORNING_PUSH_FLOOR, "09:00")
        if current_min < floor_min:
            return True

        if not settings:
            return False

        start = _hhmm_to_minutes(settings.quiet_hours_start, DEFAULT_QUIET_HOURS_START)
        end = _hhmm_to_minutes(settings.quiet_hours_end, DEFAULT_QUIET_HOURS_END)
        return _is_time_in_window(current_min, start, end)

    def next_quiet_hours_end(self, user_id: int) -> datetime:
        """计算下一次静默时段结束的本地时间.

        例: now=03:14, quiet_hours_end=09:00 → 今天 09:00
        例: now=14:00, quiet_hours_end=09:00, quiet_hours_start=22:00
            → 明天 09:00 (今天 14:00 不在静默, 但若强制延迟到下一次结束就是次日)
        但实际只在 is_quiet_hours()=True 时才调本函数, 所以"今天 end"或"明天 end"都成立.
        """
        settings = self.get_user_settings(user_id)
        now = get_china_now()
        current_min = now.hour * 60 + now.minute
        floor_min = _hhmm_to_minutes(MORNING_PUSH_FLOOR, "09:00")
        candidates: list[datetime] = []

        if current_min < floor_min:
            candidates.append(_next_local_time(now, floor_min))

        end = _hhmm_to_minutes(
            settings.quiet_hours_end if settings else None,
            DEFAULT_QUIET_HOURS_END,
        )
        if settings:
            start = _hhmm_to_minutes(settings.quiet_hours_start, DEFAULT_QUIET_HOURS_START)
            if _is_time_in_window(current_min, start, end):
                candidates.append(
                    _not_before_morning_floor(_next_local_time(now, end), floor_min)
                )

        if candidates:
            return max(candidates)

        # 兼容旧语义: 非静默时段被直接调用时, 返回下一次 quiet_hours_end。
        return _not_before_morning_floor(_next_local_time(now, end), floor_min)

    def can_send_notification(
        self,
        user_id: int,
        notification_type: str,
        respect_quiet_hours: bool = True,
        severity: str = "info",
        rule_id: Optional[str] = None,
    ) -> bool:
        """
        检查是否可以发送通知。

        H1-B 增强 (按影响顺序):
          1. 总开关 / 类型开关
          2. (仅 health_alert) rule_id 在用户的 alert_rule_opt_outs 里 → 不推
          3. (仅 health_alert) severity < alert_severity_threshold → 不推
          4. 免打扰时段 (critical 穿透)
        """
        settings = self.get_user_settings(user_id)

        if not settings or not settings.enabled:
            return False

        # H1-B: health_alert 的 rule 级 opt-out
        if (
            notification_type == NotificationType.HEALTH_ALERT.value
            and rule_id
        ):
            opt_outs = settings.alert_rule_opt_outs or []
            if rule_id in opt_outs:
                logger.info(f"[push] 用户 {user_id} 已 mute rule_id={rule_id}, 跳过")
                return False

        # H1-B: health_alert 的 severity 阈值
        if notification_type == NotificationType.HEALTH_ALERT.value:
            threshold = (settings.alert_severity_threshold or "warning").lower()
            if _severity_rank(severity) < _severity_rank(threshold):
                logger.info(
                    f"[push] 用户 {user_id} severity={severity} < threshold={threshold}, 跳过"
                )
                return False

        # 注: 静默时段不再在 can_send_notification 里检查.
        # is_quiet_hours 不是"拒绝", 而是"延迟"语义 — 由 send_notification 顶层处理:
        # 命中静默时段 → 写 status='delayed' log + scheduled_at, 由 Celery flush 任务后续 fire.
        # 2026-05-30: critical 健康告警穿透普通静默 (resolve_quiet_hours_policy);
        # 09:00 前的晨间睡眠地板仍在 send_notification 顶层统一拦截。

        # 检查具体类型开关
        type_switches = {
            NotificationType.MORNING_BRIEFING.value: settings.morning_briefing_enabled,
            NotificationType.REMINDER.value: settings.reminder_enabled,
            NotificationType.HEALTH_ALERT.value: settings.health_alert_enabled,
            NotificationType.AI_ADVICE.value: settings.ai_advice_enabled,
            NotificationType.WORKOUT_ANALYSIS.value: getattr(settings, "workout_analysis_enabled", True),
        }

        return type_switches.get(notification_type, True)

    async def send_notification(
        self,
        user_id: int,
        notification_type: str,
        title: str,
        content: str,
        data: Optional[Dict[str, Any]] = None,
        channels: Optional[List[str]] = None,
        respect_quiet_hours: bool = True,
        severity: str = "info",
        dedup_window_hours: int = 24,
        quiet_hours_policy: Optional[QuietHoursPolicy] = None,
        log_delivery: bool = True,
    ) -> Dict[str, Any]:
        """
        发送推送通知

        Args:
            user_id: 用户ID
            notification_type: 通知类型
            title: 标题
            content: 内容
            data: 额外数据. data["rule_id"] 若存在 → 参与 rule 级 opt-out 检查, 并成为 dedup key
            channels: 指定渠道，None 表示使用用户设置的渠道
            respect_quiet_hours: 旧参数; False 等价于 quiet_hours_policy="bypass"
            quiet_hours_policy: 静默时段策略: delay=延迟, bypass=立即发, drop=丢弃
            severity: 严重程度 ("info"|"low"|"warning"|"medium"|"high"|"critical")；
                      "critical" 穿透免打扰时段立即推送 (resolve_quiet_hours_policy, 2026-05-30).
                      < 用户 alert_severity_threshold 的 health_alert 也会被过滤 (H1-B).
            dedup_window_hours: 去重窗口（小时）。
                                有 rule_id 时按 (user_id, notification_type, rule_id) 去重;
                                否则按 (user_id, notification_type, title) 去重.
                                传 0 或负数则禁用去重。
            log_delivery: 是否新写 NotificationLog. flush delayed push 时为 False,
                          由原 delayed row 承接 sent/failed 状态, 避免重复展示。

        Returns:
            发送结果 {"success": bool, "channels": {...}}
        """
        rule_id = (data or {}).get("rule_id") if data else None
        # critical 可穿透普通静默 (见 resolve_quiet_hours_policy docstring);
        # 09:00 前的晨间睡眠地板优先级更高。
        effective_quiet_policy: QuietHoursPolicy = resolve_quiet_hours_policy(
            severity, quiet_hours_policy, respect_quiet_hours
        )
        is_non_critical = _severity_rank(severity) < _severity_rank("critical")

        # R4 主动触达统一预算网关(ships-OFF: mode="off" 时零行为)。observe 只算+记决策日志,
        # suppress 恒 False → 投递逐字节不变;enforce 且超预算且非 critical/safety 才真拦。
        # CRITICAL/safety 恒 bypass(硬红线)。fail-open:网关异常绝不吞通知。
        _gate = gate_proactive_notification(self.db, user_id, notification_type, severity)
        if _gate.suppress:
            logger.info(
                "[push] 用户 %s 触达预算超限丢弃 type=%s cat=%s count=%s/%s",
                user_id, notification_type, _gate.category, _gate.count_today, _gate.budget,
            )
            return {"success": False, "reason": "gatekeeper_budget"}

        # 用户明确要求 09:00 前不要 push。这里比普通 quiet-hours 更硬:
        # 即使 critical / 显式 bypass, 也先延迟到 morning floor。
        if (
            effective_quiet_policy == "bypass"
            and _is_before_morning_floor(get_china_now())
        ):
            effective_quiet_policy = "delay"

        # WSCLA 深链注入: data 带 action_card_id → 自动生成 health://card/{id} 深链.
        # 客户端点击通知 → 调 P1-5 click endpoint 回写 push_clicked_at, 然后跳卡片详情页.
        # 已有 deep_link 时不覆盖 (调用方显式优先).
        if data and data.get("action_card_id") and not data.get("deep_link"):
            data = dict(data)  # 不污染调用方的字典
            data["deep_link"] = f"health://card/{data['action_card_id']}"

        # 检查是否可以发送 (用户开关 / threshold / opt-out / 类型开关)
        # 注: can_send 不再检查静默时段, 由下方 quiet_hours 路径独立处理 (延迟而非拒绝).
        if not self.can_send_notification(
            user_id, notification_type, respect_quiet_hours,
            severity=severity, rule_id=rule_id,
        ):
            return {
                "success": False,
                "reason": "通知已禁用/低于阈值/规则已静音",
            }

        # 设置页语义是"安静时段只允许 critical 级告警穿透"。历史调用方传
        # respect_quiet_hours=False / quiet_hours_policy="bypass" 不能覆盖用户睡眠保护。
        if effective_quiet_policy == "bypass" and is_non_critical and self.is_quiet_hours(user_id):
            effective_quiet_policy = "delay"

        advice_candidate = _advice_candidate_from_push(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            content=content,
            data=data,
            severity=severity,
        )
        if advice_candidate is not None:
            decision = guard_and_record_advice(self.db, advice_candidate)
            if not decision.allowed:
                logger.info(
                    "[push] 用户 %s 建议被 AdviceGuard 拦截: reason=%s source=%s",
                    user_id,
                    decision.reason,
                    decision.conflicts_with_source_id,
                )
                return {"success": False, "reason": f"advice_guard_{decision.reason}"}

        # 去重检查必须先于 quiet-hours 延迟队列。
        # 否则夜间同一提醒会被重复写成多条 delayed, 到 09:00 一起 flush 出去。
        if dedup_window_hours and dedup_window_hours > 0:
            existing = self._find_dedup_log(
                user_id=user_id,
                notification_type=notification_type,
                title=title,
                rule_id=rule_id,
                window_start=get_china_now() - timedelta(hours=dedup_window_hours),
                statuses=[
                    NotificationStatus.SENT.value,
                    NotificationStatus.FAILED.value,
                    NotificationStatus.DELAYED.value,
                    NotificationStatus.PENDING.value,
                ],
            )
            if existing:
                key = f"rule_id={rule_id}" if rule_id else f"title={title!r}"
                logger.info(
                    f"用户 {user_id} 相同推送 {notification_type}/{key} "
                    f"在 {dedup_window_hours}h 窗口内已有记录 (log_id={existing.id})，跳过"
                )
                return {"success": False, "reason": "dedup"}

        # 静默时段: critical 可穿透普通 quiet-hours; 但 09:00 前已被上方晨间地板
        # 改回 delay。delay 写 status='delayed' log + scheduled_at, 由 Celery 任务
        # flush_delayed_pushes 在 quiet_hours_end / morning floor 后再 fire.
        if effective_quiet_policy != "bypass" and self.is_quiet_hours(user_id):
            if effective_quiet_policy == "drop":
                logger.info(
                    f"[push] 用户 {user_id} 静默时段命中, policy=drop, severity={severity}, 跳过"
                )
                return {
                    "success": False,
                    "reason": "dropped_for_quiet_hours",
                }
            scheduled_at = self.next_quiet_hours_end(user_id)
            self._log_notification_delayed(
                user_id=user_id,
                notification_type=notification_type,
                title=title,
                content=content,
                data=data,
                severity=severity,
                scheduled_at=scheduled_at,
            )
            logger.info(
                f"[push] 用户 {user_id} 静默时段命中, severity={severity}, "
                f"延迟到 {scheduled_at.isoformat()} 再推"
            )
            return {
                "success": False,
                "reason": "delayed_for_quiet_hours",
                "scheduled_at": scheduled_at.isoformat(),
            }

        settings = self.get_user_settings(user_id)
        results = {"success": False, "channels": {}}

        # 确定要使用的渠道
        if channels is None:
            channels = []
            if settings:
                if settings.wechat_enabled and settings.wechat_openid:
                    channels.append(NotificationChannel.WECHAT.value)
                if settings.ios_push_enabled and settings.ios_device_token:
                    channels.append(NotificationChannel.IOS_APNS.value)
            # Telegram 是全局 fallback chat, 不能承载 per-user reminders;
            # 否则所有用户的睡眠/用药提醒会汇聚到同一个 Telegram 会话。
            if self.telegram.configured and _allows_telegram_fallback(notification_type):
                channels.append("telegram")

        if not channels:
            logger.warning(f"用户 {user_id} 没有可用的推送渠道")
            return {
                "success": False,
                "reason": "没有可用的推送渠道"
            }

        # 逐渠道发送 — 收集各通道结果, 最后写 1 行汇总 log (2026-05-07 重构)
        channels_log: list[dict] = []
        for channel in channels:
            try:
                if channel == NotificationChannel.WECHAT.value:
                    result = await self._send_wechat(
                        user_id, settings, notification_type, title, content, data
                    )
                elif channel == NotificationChannel.IOS_APNS.value:
                    result = await self._send_ios(
                        user_id, settings, notification_type, title, content, data
                    )
                elif channel == "telegram":
                    result = await self._send_telegram(
                        user_id, notification_type, title, content, data
                    )
                else:
                    result = {"success": False, "error": f"不支持的渠道: {channel}"}

                results["channels"][channel] = result

                # 记录到合并 log
                channels_log.append({
                    "name": channel,
                    "status": NotificationStatus.SENT.value if result.get("success") else NotificationStatus.FAILED.value,
                    "error": (result.get("error") or None) if not result.get("success") else None,
                })

                if result.get("success"):
                    results["success"] = True

            except Exception as e:
                logger.error(f"发送推送失败 (user={user_id}, channel={channel}): {e}")
                results["channels"][channel] = {"success": False, "error": str(e)}
                channels_log.append({
                    "name": channel,
                    "status": NotificationStatus.FAILED.value,
                    "error": str(e),
                })

        # 汇总写 1 行 log. 整体 status: 任一通道 sent → sent, 全败 → failed.
        # channel 列用 "multi" 表示这是新结构 log (mobile UI 可识别).
        overall_status = (
            NotificationStatus.SENT.value
            if any(c["status"] == NotificationStatus.SENT.value for c in channels_log)
            else NotificationStatus.FAILED.value
        )
        overall_err = None
        if overall_status == NotificationStatus.FAILED.value:
            # 整体 failed 时把第一个 error 放 error_message 做 quick glance
            overall_err = next((c.get("error") for c in channels_log if c.get("error")), None)
        if log_delivery:
            self._log_notification_multi(
                user_id=user_id,
                notification_type=notification_type,
                title=title,
                content=content,
                data=data,
                status=overall_status,
                channels=channels_log,
                error_message=overall_err,
            )
        else:
            results["_log_status"] = overall_status
            results["_log_error"] = overall_err
            results["_channels_log"] = channels_log

        return results

    def _find_dedup_log(
        self,
        *,
        user_id: int,
        notification_type: str,
        title: str,
        rule_id: Optional[str],
        window_start: datetime,
        statuses: list[str],
        exclude_log_id: int | None = None,
    ) -> NotificationLog | None:
        """查找同一窗口内是否已有同 key 推送记录.

        rule_id 优先; 没有 rule_id 时按 title 退化。生产 PostgreSQL 走 JSONB 提取,
        本机 SQLite 测试用 LIKE 降级。
        """
        dedup_time = func.coalesce(
            NotificationLog.sent_at,
            NotificationLog.scheduled_at,
            NotificationLog.created_at,
        )
        dedup_q = self.db.query(NotificationLog).filter(
            NotificationLog.user_id == user_id,
            NotificationLog.notification_type == notification_type,
            NotificationLog.status.in_(statuses),
            dedup_time >= window_start,
        )
        if exclude_log_id is not None:
            dedup_q = dedup_q.filter(NotificationLog.id != exclude_log_id)

        if rule_id:
            bind = self.db.get_bind()
            dialect_name = bind.dialect.name if bind is not None else ""
            if dialect_name == "postgresql":
                from sqlalchemy import text
                return dedup_q.filter(
                    text("data::jsonb ->> 'rule_id' = :rid").bindparams(rid=rule_id)
                ).first()

            return dedup_q.filter(
                NotificationLog.data.like(f'%"rule_id": "{rule_id}"%')
            ).first()

        return dedup_q.filter(NotificationLog.title == title).first()

    async def _send_wechat(
        self,
        user_id: int,
        settings: UserNotificationSetting,
        notification_type: str,
        title: str,
        content: str,
        data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """发送微信订阅消息"""
        if not settings or not settings.wechat_openid:
            return {"success": False, "error": "未配置微信 OpenID"}

        return await self.wechat.send_subscription_message(
            openid=settings.wechat_openid,
            template_id=self._get_wechat_template(notification_type, settings),
            title=title,
            content=content,
            data=data
        )

    async def _send_ios(
        self,
        user_id: int,
        settings: UserNotificationSetting,
        notification_type: str,
        title: str,
        content: str,
        data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """发送 iOS APNs 推送"""
        if not settings or not settings.ios_device_token:
            return {"success": False, "error": "未配置 iOS Device Token"}

        # 从 data 里抽出 APNs category（如 MEDICATION_REMINDER），其余字段作为 custom data 下发
        category = None
        if data and "category" in data:
            data = {**data}  # shallow copy 避免改外部引用
            category = data.pop("category")

        return await self.ios.send_push(
            device_token=settings.ios_device_token,
            title=title,
            body=content,
            data=data,
            category=category,
            # 用户绑定 token 时上报的 bundle (variant 可能是 .dev / 正式),
            # APNs topic 必须匹配 token 的 bundle, 否则返 DeviceTokenNotForTopic
            bundle_id_override=getattr(settings, "ios_bundle_id", None),
        )

    async def _send_telegram(
        self,
        user_id: int,
        notification_type: str,
        title: str,
        content: str,
        data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """发送 Telegram 推送（Agent Native 告警通道）"""
        severity = (data or {}).get("severity", "info")
        return await self.telegram.send_health_alert(
            title=title,
            message=content,
            severity=severity,
        )

    def _get_wechat_template(
        self,
        notification_type: str,
        settings: UserNotificationSetting
    ) -> Optional[str]:
        """获取微信模板消息 ID"""
        if not settings or not settings.wechat_template_ids:
            return None

        templates = settings.wechat_template_ids
        if isinstance(templates, dict):
            return templates.get(notification_type)
        return None

    def _log_notification(
        self,
        user_id: int,
        notification_type: str,
        channel: str,
        title: str,
        content: str,
        data: Optional[Dict[str, Any]],
        status: str,
        error_message: Optional[str] = None
    ):
        """记录推送日志 (legacy: 单 channel)"""
        log = NotificationLog(
            user_id=user_id,
            notification_type=notification_type,
            channel=channel,
            title=title,
            content=content,
            data=data,
            status=status,
            error_message=error_message,
            sent_at=get_china_now() if status == NotificationStatus.SENT.value else None
        )
        self.db.add(log)
        self.db.commit()

    def _log_notification_multi(
        self,
        user_id: int,
        notification_type: str,
        title: str,
        content: str,
        data: Optional[Dict[str, Any]],
        status: str,
        channels: list[dict],
        error_message: Optional[str] = None,
    ):
        """记录推送日志 (new: 单 row 汇总所有通道).

        channel 列存 'multi', channels JSON 存各通道状态.
        旧查询 / 旧 row 仍兼容 (channel 列还在, 值不同而已).
        """
        log = NotificationLog(
            user_id=user_id,
            notification_type=notification_type,
            channel="multi",
            title=title,
            content=content,
            data=data,
            status=status,
            error_message=error_message,
            channels=channels,
            sent_at=get_china_now() if status == NotificationStatus.SENT.value else None,
        )
        self.db.add(log)
        self.db.commit()

        # WSCLA 生命周期 surface: 若 data 带 action_card_id 且任一通道发送成功,
        # 回写 action_cards.push_sent_at. 旁路, 失败不影响主流程.
        if status == NotificationStatus.SENT.value and data and data.get("action_card_id"):
            try:
                self._stamp_action_card_push_sent(data["action_card_id"], user_id)
            except Exception as e:
                logger.warning(
                    f"[action_card_surface] push_sent_at 回写失败 "
                    f"(user={user_id}, card_id={data.get('action_card_id')}): {e}"
                )

    def _stamp_action_card_push_sent(self, card_id: int, user_id: int) -> None:
        """把 push_sent_at 盖到对应 action_card. 只认 user_id 匹配, 防跨用户串写."""
        from app.models.action_card import ActionCard

        card = (
            self.db.query(ActionCard)
            .filter(ActionCard.id == card_id, ActionCard.user_id == user_id)
            .first()
        )
        if card is None:
            return
        if card.push_sent_at is None:
            card.push_sent_at = get_china_now()
            self.db.commit()

    def _log_notification_delayed(
        self,
        user_id: int,
        notification_type: str,
        title: str,
        content: str,
        data: Optional[Dict[str, Any]],
        severity: str,
        scheduled_at: datetime,
    ) -> None:
        """写一条 status='delayed' 的 NotificationLog, 等 flush_delayed_pushes 后再 fire.

        scheduled_at 是计划发送时间 (静默时段结束后的本地时间).
        sent_at 留空, 等真正 fire 时由 _log_notification_multi 盖.
        action_card.push_sent_at 也等真正 fire 时盖, 这里不 stamp.
        """
        # data 里塞一份 severity, flush 时回放需要
        data_with_meta = dict(data or {})
        data_with_meta.setdefault("severity", severity)

        log = NotificationLog(
            user_id=user_id,
            notification_type=notification_type,
            channel="multi",
            title=title,
            content=content,
            data=data_with_meta,
            status=NotificationStatus.DELAYED.value,
            scheduled_at=scheduled_at,
        )
        self.db.add(log)
        self.db.commit()

    async def flush_delayed_pushes(self, batch_limit: int = 100) -> Dict[str, int]:
        """
        Celery 任务调用: 取所有 status='delayed' 且 scheduled_at <= now 的 log,
        重新走 send_notification (但 respect_quiet_hours=False, 避免再次延迟).

        返回: {"flushed": N, "succeeded": K, "failed": M}
        """
        now = get_china_now()
        if _is_before_morning_floor(now):
            floor_at = _morning_floor_at(now)
            early_logs = (
                self.db.query(NotificationLog)
                .filter(
                    NotificationLog.status == NotificationStatus.DELAYED.value,
                    NotificationLog.scheduled_at <= now,
                )
                .order_by(NotificationLog.scheduled_at.asc())
                .limit(batch_limit)
                .all()
            )
            rescheduled = 0
            for log in early_logs:
                if log.scheduled_at is None or log.scheduled_at < floor_at:
                    log.scheduled_at = floor_at
                    rescheduled += 1
            if rescheduled:
                self.db.commit()
                logger.info(
                    "[flush_delayed_pushes] 09:00 前重排 delayed=%s 到 %s",
                    rescheduled,
                    floor_at.isoformat(),
                )

        delayed_logs = (
            self.db.query(NotificationLog)
            .filter(
                NotificationLog.status == NotificationStatus.DELAYED.value,
                NotificationLog.scheduled_at <= now,
            )
            .order_by(NotificationLog.scheduled_at.asc())
            .limit(batch_limit)
            .all()
        )

        flushed = 0
        succeeded = 0
        failed = 0
        deduped = 0
        for log in delayed_logs:
            flushed += 1
            severity = (log.data or {}).get("severity", "info")
            try:
                existing = self._find_dedup_log(
                    user_id=log.user_id,
                    notification_type=log.notification_type,
                    title=log.title,
                    rule_id=(log.data or {}).get("rule_id"),
                    window_start=now - timedelta(hours=24),
                    statuses=[
                        NotificationStatus.SENT.value,
                        NotificationStatus.FAILED.value,
                    ],
                    exclude_log_id=log.id,
                )
                if existing:
                    log.status = NotificationStatus.FAILED.value
                    log.error_message = "dedup"
                    self.db.commit()
                    deduped += 1
                    continue

                # 标记为 pending 再发, 防止 flush 任务重叠
                log.status = NotificationStatus.PENDING.value
                self.db.commit()

                result = await self.send_notification(
                    user_id=log.user_id,
                    notification_type=log.notification_type,
                    title=log.title,
                    content=log.content,
                    data=log.data,
                    respect_quiet_hours=False,  # flush 时不再二次延迟
                    severity=severity,
                    dedup_window_hours=0,  # flush 跳过 dedup, 因为这些是已经决定要发的
                    log_delivery=False,
                )

                if result.get("success"):
                    log.status = NotificationStatus.SENT.value
                    log.sent_at = now
                    succeeded += 1
                else:
                    log.status = NotificationStatus.FAILED.value
                    log.error_message = result.get("reason", "flush 失败")
                    failed += 1
                log.channels = result.get("_channels_log")
                if result.get("_log_error"):
                    log.error_message = result.get("_log_error")
                self.db.commit()
            except Exception as e:  # noqa: BLE001
                logger.error(
                    f"[flush_delayed_pushes] log_id={log.id} 失败: {e}",
                    exc_info=False,
                )
                log.status = NotificationStatus.FAILED.value
                log.error_message = str(e)[:500]
                self.db.commit()
                failed += 1

        if flushed > 0:
            logger.info(
                f"[flush_delayed_pushes] flushed={flushed} ok={succeeded} "
                f"fail={failed} deduped={deduped}"
            )
        return {"flushed": flushed, "succeeded": succeeded, "failed": failed, "deduped": deduped}

    def get_notification_logs(
        self,
        user_id: int,
        limit: int = 50,
        notification_type: Optional[str] = None
    ) -> List[NotificationLog]:
        """获取推送日志"""
        query = self.db.query(NotificationLog).filter(
            NotificationLog.user_id == user_id
        )

        if notification_type:
            query = query.filter(NotificationLog.notification_type == notification_type)

        return query.order_by(NotificationLog.created_at.desc()).limit(limit).all()

    # ============ 提醒配置管理 ============

    def get_reminders(self, user_id: int) -> List[ReminderConfig]:
        """获取用户的提醒配置"""
        return self.db.query(ReminderConfig).filter(
            ReminderConfig.user_id == user_id,
            ReminderConfig.enabled.is_(True)
        ).all()

    def create_reminder(
        self,
        user_id: int,
        reminder_type: str,
        name: str,
        reminder_times: List[str],
        days_of_week: List[int] = None,
        message: Optional[str] = None
    ) -> ReminderConfig:
        """创建提醒配置"""
        reminder = ReminderConfig(
            user_id=user_id,
            reminder_type=reminder_type,
            name=name,
            reminder_times=reminder_times,
            days_of_week=days_of_week or [1, 2, 3, 4, 5, 6, 7],
            message=message
        )
        self.db.add(reminder)
        self.db.commit()
        self.db.refresh(reminder)
        return reminder

    def update_reminder(
        self,
        reminder_id: int,
        user_id: int,
        updates: Dict[str, Any]
    ) -> Optional[ReminderConfig]:
        """更新提醒配置"""
        reminder = self.db.query(ReminderConfig).filter(
            ReminderConfig.id == reminder_id,
            ReminderConfig.user_id == user_id
        ).first()

        if not reminder:
            return None

        for key, value in updates.items():
            if hasattr(reminder, key):
                setattr(reminder, key, value)

        self.db.commit()
        return reminder

    def delete_reminder(self, reminder_id: int, user_id: int) -> bool:
        """删除提醒配置"""
        reminder = self.db.query(ReminderConfig).filter(
            ReminderConfig.id == reminder_id,
            ReminderConfig.user_id == user_id
        ).first()

        if reminder:
            self.db.delete(reminder)
            self.db.commit()
            return True
        return False

    def get_due_reminders(self) -> List[Dict[str, Any]]:
        """
        获取当前时间应该发送的提醒

        返回格式: [{"user_id": int, "reminder": ReminderConfig}, ...]
        """
        now = get_china_now()
        current_time = now.strftime("%H:%M")
        current_day = now.isoweekday()  # 1=周一, 7=周日

        # 获取所有启用的提醒
        all_reminders = self.db.query(ReminderConfig).filter(
            ReminderConfig.enabled.is_(True)
        ).all()

        due_reminders = []
        for reminder in all_reminders:
            # 检查星期
            if current_day not in (reminder.days_of_week or [1, 2, 3, 4, 5, 6, 7]):
                continue

            # 检查时间（允许1分钟误差）
            for reminder_time in (reminder.reminder_times or []):
                if self._time_matches(current_time, reminder_time):
                    due_reminders.append({
                        "user_id": reminder.user_id,
                        "reminder": reminder
                    })
                    break

        return due_reminders

    def _time_matches(self, current: str, target: str, tolerance_minutes: int = 1) -> bool:
        """检查时间是否匹配（允许一定误差）"""
        try:
            current_parts = [int(x) for x in current.split(":")]
            target_parts = [int(x) for x in target.split(":")]

            current_minutes = current_parts[0] * 60 + current_parts[1]
            target_minutes = target_parts[0] * 60 + target_parts[1]

            return abs(current_minutes - target_minutes) <= tolerance_minutes
        except Exception:
            return False


# ============ 预定义提醒类型 ============

PREDEFINED_REMINDERS = {
    "nasal_wash": {
        "name": "洗鼻提醒",
        "default_times": ["07:30", "19:00"],
        "message": "🌊 该用生理盐水洗鼻了！保持鼻腔清洁，预防鼻炎。"
    },
    "drink_water": {
        "name": "喝水提醒",
        "default_times": ["08:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00"],
        "message": "💧 记得喝水！保持每日饮水量 2000ml 以上。"
    },
    "exercise": {
        "name": "运动提醒",
        "default_times": ["18:00"],
        "message": "🏃 该运动了！今天的运动目标还没完成哦。"
    },
    "sleep": {
        "name": "睡眠提醒",
        "default_times": ["22:00"],
        "message": "😴 该准备睡觉了！保证 7-8 小时的优质睡眠。"
    },
    "medicine": {
        "name": "服药提醒",
        "default_times": ["08:00", "20:00"],
        "message": "💊 记得按时服药！"
    },
    "supplement": {
        "name": "补剂提醒",
        "default_times": ["08:00"],
        "message": "🍀 记得吃今天的补剂！"
    },
    "posture": {
        "name": "姿势提醒",
        "default_times": ["10:00", "14:00", "16:00"],
        "message": "🧘 注意坐姿！站起来活动一下，做几个深蹲或拉伸。"
    },
    "eye_rest": {
        "name": "护眼提醒",
        "default_times": ["10:00", "12:00", "14:00", "16:00", "18:00"],
        "message": "👀 让眼睛休息一下！远眺 20 秒，做做眼保健操。"
    }
}
