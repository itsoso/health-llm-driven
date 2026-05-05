"""健康异常检测服务"""
import logging
from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.models.anomaly_alert import AnomalyAlert
from app.models.daily_health import GarminData
from app.utils.timezone import get_china_today

logger = logging.getLogger(__name__)

# 异常检测阈值
THRESHOLDS = {
    "rhr_spike_pct": 15,        # 静息心率高于7天均值15%
    "hrv_drop_pct": 20,         # HRV低于7天均值20%
    "sleep_critical": 50,       # 睡眠评分低于50为critical
    "sleep_warning_threshold": 60,  # 连续3天低于60为warning
    "sleep_warning_days": 3,
    "stress_high": 75,          # 压力水平高于75
    "stress_high_days": 2,      # 连续2天以上
    "spo2_critical": 95,        # 血氧低于95%
    "battery_low": 30,          # Body Battery晨起低于30
    # 趋势检测阈值
    "rhr_trend_days": 3,        # 连续3天RHR逐日上升
    "rhr_trend_step": 2,        # 每天比前一天高≥2 bpm
    "hrv_trend_days": 3,        # 连续3天HRV逐日下降
    "hrv_trend_step": 5,        # 每天比前一天低≥5 ms
    "multi_metric_min_hits": 2, # 多指标恶化：3项中命中≥2项
}


class AnomalyDetectionService:
    """健康指标异常检测服务"""

    def __init__(self, db: Session):
        self.db = db

    def detect_anomalies(self, user_id: int, check_date: Optional[date] = None) -> List[AnomalyAlert]:
        """检测用户健康异常，返回新发现的预警列表"""
        if check_date is None:
            check_date = get_china_today()

        alerts = []

        checkers = [
            self._check_rhr_spike,
            self._check_hrv_drop,
            self._check_sleep_low,
            self._check_stress_high,
            self._check_spo2_low,
            self._check_battery_low,
            # 趋势检测器（Agent Native Phase 1）
            self._check_rhr_trend,
            self._check_hrv_trend,
            self._check_multi_metric_deterioration,
        ]

        for checker in checkers:
            try:
                alert = checker(user_id, check_date)
                if alert and not self._is_duplicate(user_id, alert.alert_type, check_date):
                    self.db.add(alert)
                    alerts.append(alert)
            except Exception as e:
                logger.warning(f"异常检测失败 [{checker.__name__}] user={user_id}: {e}")

        if alerts:
            self.db.commit()
            for alert in alerts:
                self.db.refresh(alert)

        return alerts

    def _get_recent_garmin_data(self, user_id: int, check_date: date, days: int = 7) -> List[GarminData]:
        """获取最近N天的Garmin数据（不含当天）"""
        start_date = check_date - timedelta(days=days)
        return self.db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start_date,
            GarminData.record_date < check_date,
        ).order_by(GarminData.record_date.desc()).all()

    def _get_today_garmin(self, user_id: int, check_date: date) -> Optional[GarminData]:
        """获取当天Garmin数据"""
        return self.db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == check_date,
        ).first()

    def _is_duplicate(self, user_id: int, alert_type: str, detection_date: date) -> bool:
        """检查同一天同类型是否已有预警"""
        existing = self.db.query(AnomalyAlert).filter(
            AnomalyAlert.user_id == user_id,
            AnomalyAlert.alert_type == alert_type,
            AnomalyAlert.detection_date == detection_date,
        ).first()
        return existing is not None

    def _check_rhr_spike(self, user_id: int, check_date: date) -> Optional[AnomalyAlert]:
        """检测静息心率异常飙升"""
        today = self._get_today_garmin(user_id, check_date)
        if not today or not today.resting_heart_rate:
            return None

        recent = self._get_recent_garmin_data(user_id, check_date, days=7)
        rhr_values = [r.resting_heart_rate for r in recent if r.resting_heart_rate]
        if len(rhr_values) < 3:
            return None

        avg_rhr = sum(rhr_values) / len(rhr_values)
        current_rhr = today.resting_heart_rate
        threshold_pct = THRESHOLDS["rhr_spike_pct"]

        if avg_rhr > 0:
            deviation_pct = ((current_rhr - avg_rhr) / avg_rhr) * 100
        else:
            return None

        if deviation_pct > threshold_pct:
            return AnomalyAlert(
                user_id=user_id,
                alert_type="rhr_spike",
                severity="warning",
                metric_name="resting_heart_rate",
                current_value=current_rhr,
                baseline_value=round(avg_rhr, 1),
                threshold_value=round(avg_rhr * (1 + threshold_pct / 100), 1),
                deviation_pct=round(deviation_pct, 1),
                detection_date=check_date,
                message=f"静息心率异常偏高：当前 {current_rhr} bpm，7天均值 {avg_rhr:.0f} bpm，偏高 {deviation_pct:.0f}%",
            )
        return None

    def _check_hrv_drop(self, user_id: int, check_date: date) -> Optional[AnomalyAlert]:
        """检测HRV骤降"""
        today = self._get_today_garmin(user_id, check_date)
        if not today:
            return None

        # 方式1：HRV status 为 low
        if today.hrv_status and today.hrv_status.lower() == "low":
            return AnomalyAlert(
                user_id=user_id,
                alert_type="hrv_drop",
                severity="warning",
                metric_name="hrv",
                current_value=today.hrv,
                baseline_value=today.hrv_7day_avg,
                detection_date=check_date,
                message=f"HRV 状态偏低：当前 {today.hrv or '未知'} ms，状态为 low",
            )

        # 方式2：HRV数值低于7天均值20%
        if not today.hrv:
            return None

        recent = self._get_recent_garmin_data(user_id, check_date, days=7)
        hrv_values = [r.hrv for r in recent if r.hrv]
        if len(hrv_values) < 3:
            return None

        avg_hrv = sum(hrv_values) / len(hrv_values)
        if avg_hrv <= 0:
            return None

        deviation_pct = ((avg_hrv - today.hrv) / avg_hrv) * 100
        threshold_pct = THRESHOLDS["hrv_drop_pct"]

        if deviation_pct > threshold_pct:
            return AnomalyAlert(
                user_id=user_id,
                alert_type="hrv_drop",
                severity="warning",
                metric_name="hrv",
                current_value=today.hrv,
                baseline_value=round(avg_hrv, 1),
                threshold_value=round(avg_hrv * (1 - threshold_pct / 100), 1),
                deviation_pct=round(deviation_pct, 1),
                detection_date=check_date,
                message=f"HRV 异常偏低：当前 {today.hrv:.0f} ms，7天均值 {avg_hrv:.0f} ms，偏低 {deviation_pct:.0f}%",
            )
        return None

    def _check_sleep_low(self, user_id: int, check_date: date) -> Optional[AnomalyAlert]:
        """检测睡眠评分异常"""
        today = self._get_today_garmin(user_id, check_date)
        if not today or today.sleep_score is None:
            return None

        critical_threshold = THRESHOLDS["sleep_critical"]
        warning_threshold = THRESHOLDS["sleep_warning_threshold"]
        warning_days = THRESHOLDS["sleep_warning_days"]

        # Critical: 单日低于50
        if today.sleep_score < critical_threshold:
            return AnomalyAlert(
                user_id=user_id,
                alert_type="sleep_low",
                severity="critical",
                metric_name="sleep_score",
                current_value=today.sleep_score,
                threshold_value=critical_threshold,
                detection_date=check_date,
                message=f"睡眠评分极低：{today.sleep_score} 分（阈值 {critical_threshold}），请关注睡眠质量",
            )

        # Warning: 连续N天低于60
        recent = self._get_recent_garmin_data(user_id, check_date, days=warning_days)
        if len(recent) < warning_days - 1:
            return None

        # 包含今天的评分
        all_scores = [today.sleep_score] + [r.sleep_score for r in recent if r.sleep_score is not None]
        recent_scores = all_scores[:warning_days]

        if len(recent_scores) >= warning_days and all(s < warning_threshold for s in recent_scores):
            avg = sum(recent_scores) / len(recent_scores)
            return AnomalyAlert(
                user_id=user_id,
                alert_type="sleep_low",
                severity="warning",
                metric_name="sleep_score",
                current_value=today.sleep_score,
                baseline_value=round(avg, 1),
                threshold_value=warning_threshold,
                detection_date=check_date,
                message=f"连续 {warning_days} 天睡眠评分低于 {warning_threshold}，最近均值 {avg:.0f} 分",
            )
        return None

    def _check_stress_high(self, user_id: int, check_date: date) -> Optional[AnomalyAlert]:
        """检测连续高压力"""
        today = self._get_today_garmin(user_id, check_date)
        if not today or today.stress_level is None:
            return None

        high_threshold = THRESHOLDS["stress_high"]
        required_days = THRESHOLDS["stress_high_days"]

        if today.stress_level < high_threshold:
            return None

        # 检查连续天数
        recent = self._get_recent_garmin_data(user_id, check_date, days=required_days)
        high_stress_days = 1  # 今天已经是高压力
        for r in recent:
            if r.stress_level is not None and r.stress_level >= high_threshold:
                high_stress_days += 1
            else:
                break

        if high_stress_days >= required_days:
            return AnomalyAlert(
                user_id=user_id,
                alert_type="stress_high",
                severity="warning",
                metric_name="stress_level",
                current_value=today.stress_level,
                threshold_value=high_threshold,
                detection_date=check_date,
                message=f"连续 {high_stress_days} 天压力偏高（>{high_threshold}），当前 {today.stress_level}，建议放松",
            )
        return None

    def _check_spo2_low(self, user_id: int, check_date: date) -> Optional[AnomalyAlert]:
        """检测血氧饱和度异常"""
        today = self._get_today_garmin(user_id, check_date)
        if not today or today.spo2_avg is None:
            return None

        critical_threshold = THRESHOLDS["spo2_critical"]

        if today.spo2_avg < critical_threshold:
            return AnomalyAlert(
                user_id=user_id,
                alert_type="spo2_low",
                severity="critical",
                metric_name="spo2_avg",
                current_value=today.spo2_avg,
                threshold_value=critical_threshold,
                detection_date=check_date,
                message=f"血氧饱和度偏低：{today.spo2_avg:.1f}%（阈值 {critical_threshold}%），请注意",
            )
        return None

    def _check_battery_low(self, user_id: int, check_date: date) -> Optional[AnomalyAlert]:
        """检测Body Battery晨起偏低"""
        today = self._get_today_garmin(user_id, check_date)
        if not today or today.body_battery_most_charged is None:
            return None

        low_threshold = THRESHOLDS["battery_low"]

        if today.body_battery_most_charged < low_threshold:
            return AnomalyAlert(
                user_id=user_id,
                alert_type="battery_low",
                severity="info",
                metric_name="body_battery",
                current_value=today.body_battery_most_charged,
                threshold_value=low_threshold,
                detection_date=check_date,
                message=f"身体电量偏低：最高充电仅 {today.body_battery_most_charged}（阈值 {low_threshold}），注意休息",
            )
        return None

    # ─────────────── 趋势检测器（Agent Native Phase 1）────────────────

    def _get_recent_garmin_sorted(self, user_id: int, check_date: date, days: int = 5) -> List[GarminData]:
        """获取最近N天数据（含当天），按日期正序排列"""
        start_date = check_date - timedelta(days=days - 1)
        return self.db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start_date,
            GarminData.record_date <= check_date,
        ).order_by(GarminData.record_date.asc()).all()

    def _check_rhr_trend(self, user_id: int, check_date: date) -> Optional[AnomalyAlert]:
        """检测连续N天静息心率逐日上升（趋势恶化）"""
        required_days = THRESHOLDS["rhr_trend_days"]
        step = THRESHOLDS["rhr_trend_step"]

        data = self._get_recent_garmin_sorted(user_id, check_date, days=required_days + 1)
        rhr_series = [(d.record_date, d.resting_heart_rate) for d in data if d.resting_heart_rate]
        if len(rhr_series) < required_days + 1:
            return None

        # 取最近 required_days+1 天，检查连续上升
        recent = rhr_series[-(required_days + 1):]
        rising_days = 0
        for i in range(1, len(recent)):
            if recent[i][1] - recent[i - 1][1] >= step:
                rising_days += 1
            else:
                rising_days = 0  # 中断则重置

        if rising_days >= required_days:
            first_val = recent[-(required_days + 1)][1]
            last_val = recent[-1][1]
            return AnomalyAlert(
                user_id=user_id,
                alert_type="rhr_rising_trend",
                severity="warning",
                metric_name="resting_heart_rate",
                current_value=last_val,
                baseline_value=first_val,
                deviation_pct=round((last_val - first_val) / first_val * 100, 1) if first_val else None,
                detection_date=check_date,
                message=f"静息心率连续 {required_days} 天上升：{first_val}→{last_val} bpm，可能提示过度训练或身体不适",
            )
        return None

    def _check_hrv_trend(self, user_id: int, check_date: date) -> Optional[AnomalyAlert]:
        """检测连续N天HRV逐日下降（趋势恶化）"""
        required_days = THRESHOLDS["hrv_trend_days"]
        step = THRESHOLDS["hrv_trend_step"]

        data = self._get_recent_garmin_sorted(user_id, check_date, days=required_days + 1)
        hrv_series = [(d.record_date, d.hrv) for d in data if d.hrv]
        if len(hrv_series) < required_days + 1:
            return None

        recent = hrv_series[-(required_days + 1):]
        declining_days = 0
        for i in range(1, len(recent)):
            if recent[i - 1][1] - recent[i][1] >= step:
                declining_days += 1
            else:
                declining_days = 0

        if declining_days >= required_days:
            first_val = recent[-(required_days + 1)][1]
            last_val = recent[-1][1]
            return AnomalyAlert(
                user_id=user_id,
                alert_type="hrv_declining_trend",
                severity="warning",
                metric_name="hrv",
                current_value=last_val,
                baseline_value=first_val,
                deviation_pct=round((first_val - last_val) / first_val * 100, 1) if first_val else None,
                detection_date=check_date,
                message=f"HRV 连续 {required_days} 天下降：{first_val}→{last_val} ms，自主神经调节能力可能在减弱",
            )
        return None

    def _check_multi_metric_deterioration(self, user_id: int, check_date: date) -> Optional[AnomalyAlert]:
        """检测多指标同时恶化（综合预警）

        检查 3 个指标近 3 天 vs 前 4 天均值：
        - sleep_score 下降 >10%
        - stress_level 上升 >15%
        - HRV 下降 >15%
        命中 ≥2 项 → 触发综合恶化预警
        """
        data = self._get_recent_garmin_sorted(user_id, check_date, days=7)
        if len(data) < 5:
            return None

        # 分成两段：前半段（baseline）和后半段（recent）
        mid = len(data) - 3
        baseline = data[:mid]
        recent = data[mid:]

        hits = []
        details = []

        def _avg(items, attr):
            vals = [getattr(d, attr) for d in items if getattr(d, attr) is not None]
            return sum(vals) / len(vals) if vals else None

        # Sleep score
        base_sleep = _avg(baseline, 'sleep_score')
        recent_sleep = _avg(recent, 'sleep_score')
        if base_sleep and recent_sleep and base_sleep > 0:
            change = (base_sleep - recent_sleep) / base_sleep * 100
            if change > 10:
                hits.append('sleep')
                details.append(f"睡眠评分下降{change:.0f}%({base_sleep:.0f}→{recent_sleep:.0f})")

        # Stress level
        base_stress = _avg(baseline, 'stress_level')
        recent_stress = _avg(recent, 'stress_level')
        if base_stress and recent_stress and base_stress > 0:
            change = (recent_stress - base_stress) / base_stress * 100
            if change > 15:
                hits.append('stress')
                details.append(f"压力上升{change:.0f}%({base_stress:.0f}→{recent_stress:.0f})")

        # HRV
        base_hrv = _avg(baseline, 'hrv')
        recent_hrv = _avg(recent, 'hrv')
        if base_hrv and recent_hrv and base_hrv > 0:
            change = (base_hrv - recent_hrv) / base_hrv * 100
            if change > 15:
                hits.append('hrv')
                details.append(f"HRV下降{change:.0f}%({base_hrv:.0f}→{recent_hrv:.0f})")

        min_hits = THRESHOLDS["multi_metric_min_hits"]
        if len(hits) >= min_hits:
            return AnomalyAlert(
                user_id=user_id,
                alert_type="multi_metric_deterioration",
                severity="warning",
                metric_name=",".join(hits),
                current_value=len(hits),
                threshold_value=min_hits,
                detection_date=check_date,
                message=f"多指标同步恶化（{len(hits)}/{3}）：{'；'.join(details)}。建议减少训练强度、优先睡眠恢复",
            )
        return None

    async def send_alerts(self, user_id: int, alerts: List[AnomalyAlert]):
        """发送预警推送通知.

        降噪策略 (P3 告警风暴修复):
          1. info 级别不推 APNs (battery_low 等运营性告警)
          2. 连续 3 天同类告警 → 标 is_suppressed, 不推 (避免告警疲劳)
             新告警仍写 DB, 用户主动进 App 能看
          3. critical 级别不受疲劳规则影响, 一定推

        P4 信任循环接入: 每条非 info 告警自动产一张 ActionCard (可 grade 的 metric),
        check_back_date = 3 天 (critical) / 7 天 (warning), 让 outcome_grader 有活干.
        """
        if not alerts:
            return

        from app.services.notification.push_service import PushService
        from app.models.notification import NotificationType

        push_service = PushService(self.db)

        for alert in alerts:
            if alert.notification_sent:
                continue

            severity = (alert.severity or "").lower()

            # 规则 1: info 级别不推 APNs
            if severity == "info":
                alert.notification_sent = True
                alert.is_suppressed = True
                logger.info(
                    f"[anomaly] suppress info alert type={alert.alert_type} user={user_id}"
                )
                continue

            # 规则 2: 连续 N 天同类疲劳 (critical 除外)
            is_fatigued = (severity != "critical"
                           and self._is_fatigued(user_id, alert.alert_type, alert.detection_date))
            if is_fatigued:
                alert.notification_sent = True
                alert.is_suppressed = True
                logger.info(
                    f"[anomaly] suppress fatigued alert type={alert.alert_type} user={user_id} "
                    f"(连续 3+ 天同类告警)"
                )
                # 疲劳时不创建新 ActionCard (已有同 metric 的 active card 在跑)
                continue

            # critical 级别绕过静默时段
            respect_quiet = severity != "critical"

            # L9 (Karpathy partial autonomy): 用户的告警反应档位
            # silent   → 只写 alerts tab, 不推送 (alert 已写库, 直接 mark sent 跳过)
            # notify   → 推送 + deep_link 跳 trace 详情 (不开口)
            # converse → 推送 + deep_link 跳 voice-chat 主动开口 (默认, 现状)
            settings = push_service.get_user_settings(user_id)
            mode = (
                getattr(settings, "alert_clarify_mode", None) if settings else None
            ) or "converse"

            # critical 级别强制至少 notify (生命安全, 不让用户彻底静默危险告警)
            if mode == "silent" and severity != "critical":
                alert.notification_sent = True
                logger.info(
                    f"[anomaly] user={user_id} mode=silent, alert={alert.id} "
                    f"type={alert.alert_type} 只写库不推送"
                )
                continue

            # Agent Native 闭环: 该 alert_type 有 clarify 模板 + mode=converse → deep_link 跳 voice-chat
            #                    其它情况 → 退回 trace 详情页
            from app.services.alert_clarification import get_clarification_opener
            has_clarification = get_clarification_opener(alert) is not None
            if has_clarification and mode == "converse":
                deep_link = f"/voice-chat?intent=clarify&alert_id={alert.id}"
            else:
                deep_link = f"/trace/anomaly_{alert.id}"

            try:
                result = await push_service.send_notification(
                    user_id=user_id,
                    notification_type=NotificationType.HEALTH_ALERT.value,
                    title=f"健康预警：{alert.metric_name}",
                    content=alert.message,
                    data={
                        "alert_id": alert.id,
                        "severity": alert.severity,
                        "type": alert.alert_type,
                        "deep_link": deep_link,
                        "rule_id": f"anomaly.{alert.alert_type}",  # H1-B opt-out 用
                    },
                    respect_quiet_hours=respect_quiet,
                )
                if result.get("success"):
                    alert.notification_sent = True
            except Exception as e:
                logger.warning(f"发送预警通知失败 alert={alert.id}: {e}")

            # P4 信任循环: 自动创建 ActionCard (旁路, 失败不影响推送)
            try:
                self._create_action_card_from_alert(user_id, alert)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[anomaly] 自动创建 ActionCard 失败 (旁路) alert={alert.id}: {e}")

        self.db.commit()

    # metric_name → outcome_grader 能接受的 metric_key 映射
    _METRIC_KEY_MAP = {
        "resting_heart_rate": "rhr",
        "hrv": "hrv",
        "sleep_score": "sleep_score",
        "spo2_avg": "spo2_odi",
        # 以下不能 grade 的 metric 不自动产 card
        # "stress_level": None, "body_battery": None,
    }

    def _create_action_card_from_alert(self, user_id: int, alert: AnomalyAlert) -> Optional[int]:
        """AnomalyAlert → ActionCard. 返回 card id 或 None.

        - 仅对可 grade 的 metric 创建 (避免 stress_level 等产无法评分的 card)
        - 同 metric 最近 7 天已有 active card 则跳过 (防止刷屏)
        - check_back_date: critical 3 天 / warning 7 天
        """
        metric_key = self._METRIC_KEY_MAP.get(alert.metric_name)
        if not metric_key:
            return None

        from app.models.action_card import ActionCard
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td

        # Dedup: 7 天内同 metric active card 跳过
        existing = (
            self.db.query(ActionCard)
            .filter(
                ActionCard.user_id == user_id,
                ActionCard.metric_key == metric_key,
                ActionCard.status == "active",
                ActionCard.creator_specialist == "anomaly_detector",
                ActionCard.created_at > _dt.now(_tz.utc) - _td(days=7),
            )
            .first()
        )
        if existing:
            return None

        severity = (alert.severity or "").lower()
        check_back_days = 3 if severity == "critical" else 7
        title = f"[{alert.metric_name}] {alert.message[:40]}"
        content_lines = [f"**触发原因**: {alert.message}"]
        if alert.deviation_pct is not None:
            content_lines.append(
                f"**基线**: {alert.baseline_value} · **当前**: {alert.current_value} "
                f"({alert.deviation_pct:+.1f}% 偏离)"
            )
        else:
            content_lines.append(
                f"**基线**: {alert.baseline_value} · **当前**: {alert.current_value}"
            )
        content_lines.append(
            f"**建议**: 关注 {check_back_days} 天, 记录作息 / 运动 / 压力, "
            f"{check_back_days} 天后看指标是否回归."
        )
        content = "\n\n".join(content_lines)

        card = ActionCard(
            user_id=user_id,
            title=title[:200],
            content=content,
            card_type="recommendation",
            source_type="anomaly_alert",
            source_id=str(alert.id),
            status="active",
            priority=10 if severity == "critical" else 5,
            metric_key=metric_key,
            baseline_value=str(alert.baseline_value) if alert.baseline_value is not None else None,
            target_value=f"回归到基线 ±10%",
            verification_days=check_back_days,
            creator_specialist="anomaly_detector",
            check_back_date=_dt.now(_tz.utc) + _td(days=check_back_days),
        )
        self.db.add(card)
        self.db.flush()
        logger.info(
            f"[anomaly] 创建 ActionCard #{card.id} user={user_id} metric={metric_key} "
            f"check_back={check_back_days}d"
        )
        return card.id

    def _is_fatigued(self, user_id: int, alert_type: str, check_date: date) -> bool:
        """最近 3 天 (不含今天) 每天都有同类告警推送过 → 疲劳, 今天静默.

        评估: 2 天冷却期推送, 第 3 天开始冷却; 直到同类告警连续中断 1 天才重新允许推送.
        """
        recent_sent = (
            self.db.query(AnomalyAlert)
            .filter(
                AnomalyAlert.user_id == user_id,
                AnomalyAlert.alert_type == alert_type,
                AnomalyAlert.detection_date >= check_date - timedelta(days=3),
                AnomalyAlert.detection_date < check_date,
                AnomalyAlert.notification_sent.is_(True),
                AnomalyAlert.is_suppressed.is_(False),  # 只数真推过的
            )
            .count()
        )
        return recent_sent >= 2
