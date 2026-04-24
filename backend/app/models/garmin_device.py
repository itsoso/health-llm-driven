"""Garmin 设备信息（电量、最后同步、佩戴时长）。

来源：garminconnect.get_devices()
用途：
- 区分"HRV=0 是真低"还是"没戴表"
- SafetyGuardian 的"设备 48h 未同步"低优先级提醒
- 前端设置页展示设备卡片
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.agent_audit_log import JSONColumn


class GarminDevice(Base):
    __tablename__ = "garmin_devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    device_id = Column(String, nullable=False)
    unit_id = Column(String)
    product_number = Column(String)
    model = Column(String)
    display_name = Column(String)
    image_url = Column(String)

    last_sync_time = Column(DateTime(timezone=True))
    last_used_time = Column(DateTime(timezone=True))
    battery_level = Column(Integer)
    battery_status = Column(String)  # Low/Medium/High/OK/New
    firmware_version = Column(String)

    is_primary = Column(Boolean, default=False)
    raw_payload = Column(JSONColumn)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="garmin_devices")

    __table_args__ = (
        Index('idx_garmin_devices_user', 'user_id'),
    )
