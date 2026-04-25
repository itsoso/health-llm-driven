"""血压追踪模型"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, Text, Time, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class BloodPressureRecord(Base):
    """血压记录"""
    __tablename__ = "blood_pressure_records"
    __table_args__ = (
        Index("idx_blood_pressure_records_user_date", "user_id", "record_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    record_date = Column(Date, nullable=False, index=True)
    measured_at = Column(DateTime(timezone=True))  # 测量时间（数据库实际字段）

    systolic = Column(Integer, nullable=False)  # 收缩压 (mmHg)
    diastolic = Column(Integer, nullable=False)  # 舒张压 (mmHg)
    pulse = Column(Integer)  # 脉搏 (次/分)

    notes = Column(Text)  # 备注

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="blood_pressure_records")

    # 为了兼容前端API，添加属性别名
    @property
    def record_time(self):
        """从 measured_at 提取时间部分"""
        if self.measured_at:
            return self.measured_at.time()
        return None

    @property
    def measurement_position(self):
        """测量姿势（旧数据库没有此字段，返回默认值）"""
        return "坐"

    @property
    def arm(self):
        """测量手臂（旧数据库没有此字段，返回默认值）"""
        return "左"

    @property
    def category(self):
        """血压分类"""
        if self.systolic < 120 and self.diastolic < 80:
            return "正常"
        elif 120 <= self.systolic < 130 and self.diastolic < 80:
            return "正常偏高"
        elif (130 <= self.systolic < 140) or (80 <= self.diastolic < 90):
            return "高血压前期"
        elif self.systolic >= 140 or self.diastolic >= 90:
            return "高血压"
        else:
            return "未知"
