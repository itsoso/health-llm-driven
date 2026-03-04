"""健康异常预警模型"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, Boolean, Text, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class AnomalyAlert(Base):
    """健康指标异常预警记录"""
    __tablename__ = "anomaly_alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 预警类型
    alert_type = Column(String(50), nullable=False)  # rhr_spike, hrv_drop, sleep_low, stress_high, spo2_low, battery_low

    # 严重度
    severity = Column(String(20), nullable=False, default="warning")  # info, warning, critical

    # 指标详情
    metric_name = Column(String(50), nullable=False)  # resting_heart_rate, hrv, sleep_score, stress_level, spo2_avg, body_battery
    current_value = Column(Float, nullable=True)
    baseline_value = Column(Float, nullable=True)  # 7天均值基线
    threshold_value = Column(Float, nullable=True)  # 触发阈值
    deviation_pct = Column(Float, nullable=True)  # 偏离百分比

    # 检测日期
    detection_date = Column(Date, nullable=False, index=True)

    # 预警消息
    message = Column(Text, nullable=False)

    # 状态
    notification_sent = Column(Boolean, default=False)
    is_suppressed = Column(Boolean, default=False)  # 用户主动忽略
    acknowledged = Column(Boolean, default=False)  # 用户已查看

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", backref="anomaly_alerts")

    __table_args__ = (
        Index('idx_anomaly_user_type_date', 'user_id', 'alert_type', 'detection_date', unique=True),
    )

    def __repr__(self):
        return f"<AnomalyAlert {self.alert_type} severity={self.severity} user={self.user_id} date={self.detection_date}>"
