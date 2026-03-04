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

    async def send_alerts(self, user_id: int, alerts: List[AnomalyAlert]):
        """发送预警推送通知"""
        if not alerts:
            return

        from app.services.notification.push_service import PushService
        from app.models.notification import NotificationType

        push_service = PushService(self.db)

        for alert in alerts:
            if alert.notification_sent:
                continue

            # critical 级别绕过静默时段
            respect_quiet = alert.severity != "critical"

            try:
                result = await push_service.send_notification(
                    user_id=user_id,
                    notification_type=NotificationType.HEALTH_ALERT.value,
                    title=f"健康预警：{alert.metric_name}",
                    content=alert.message,
                    data={"alert_id": alert.id, "severity": alert.severity, "type": alert.alert_type},
                    respect_quiet_hours=respect_quiet,
                )
                if result.get("success"):
                    alert.notification_sent = True
            except Exception as e:
                logger.warning(f"发送预警通知失败 alert={alert.id}: {e}")

        self.db.commit()
