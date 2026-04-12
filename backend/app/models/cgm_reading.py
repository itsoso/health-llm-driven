"""
CGM (Continuous Glucose Monitor) 读数模型。

支持多个厂商：
- Libre / LibreLinkUp (FreeStyle Libre 3, Libre 2+)
- Dexcom (G6, G7)
- Stelo (Dexcom Stelo)
- 其他符合 mg/dL 单位的设备

数据频率：通常每 5 分钟一次（G7/Libre 3）或 1 分钟（Stelo），
历史查询按时段聚合，实时读数仅保留最近 24 小时明细。
"""

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class CgmReading(Base):
    """单次 CGM 读数。"""

    __tablename__ = "cgm_readings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 时间与数值
    measured_at = Column(DateTime(timezone=True), nullable=False, index=True)
    glucose_mg_dl = Column(Float, nullable=False)
    trend_arrow = Column(String(20))  # double_up / up / flat / down / double_down
    trend_rate = Column(Float)         # mg/dL per minute

    # 来源
    source = Column(String(30), nullable=False, default="manual")  # libre / dexcom / stelo / manual
    device_serial = Column(String(80))
    raw_id = Column(String(120), index=True)  # 源系统 ID，用于幂等写入

    # 上下文（可选）
    notes = Column(String(500))

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="cgm_readings")

    __table_args__ = (
        Index("ix_cgm_user_time", "user_id", "measured_at"),
        Index("ix_cgm_user_raw", "user_id", "raw_id", unique=True),
    )

    @property
    def glucose_mmol_l(self) -> float:
        """mg/dL → mmol/L 换算。"""
        return round(self.glucose_mg_dl / 18.0, 2) if self.glucose_mg_dl else None
