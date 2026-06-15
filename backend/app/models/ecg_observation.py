"""Apple Watch ECG 观测记录 —— 单次心电图分类事件.

为什么独立建表 (不塞 garmin_data):
- garmin_data 是**按天聚合**的连续生理指标, upsert 键是 (user_id, record_date,
  data_source). ECG 是**点事件** (某时刻按一下表录一段心电图, 给一个分类),
  同一天可能多次、也可能连续多天, 塞进日聚合会互相覆盖, 丢失"房颤出现过几次".
- afib_event_count 是某次上送**窗口内**的房颤分类计数, 不是日生理量, 不属于
  garmin_data 的语义.
- ECG 是 Apple Watch 独有的房颤筛查信号 (Garmin/RingConn 给不了), 单独成表
  便于 Safety/Twin 直接查"最近一次分类 / 最近是否有房颤", 不污染连续 vitals.

注意 —— 这是**筛查信号, 非诊断**. classification 原样存 HealthKit 字符串
(SinusRhythm / AtrialFibrillation / InconclusiveLowHeartRate / ...), 下游只对
明确的 "AtrialFibrillation" 做安全告警, 未知分类不误报.
"""

from sqlalchemy import Column, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base
from app.models.agent_audit_log import JSONColumn


class EcgObservation(Base):
    """单次 Apple Watch ECG 分类事件 (点事件, 非日聚合)."""

    __tablename__ = "ecg_observations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)

    # HealthKit 原样分类字符串. 不枚举 —— Apple 可能新增分类, 未知值原样存, 下游容错.
    classification = Column(String(64), nullable=False)

    # 该次 ECG 记录时间 (HealthKit sample 的 startDate). 用于"最近一次"排序.
    recorded_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # 本次上送窗口内被分类为 AtrialFibrillation 的 ECG 次数 (mobile 端聚合给出).
    # 默认 0 —— 缺失/未知时不当作有房颤.
    afib_event_count = Column(Integer, nullable=False, default=0)

    # 来源标签 (apple-watch 等), 与 garmin_data.data_source 对齐.
    data_source = Column(String(32), nullable=False, default="apple-watch")

    # 完整原始 HealthKit ECG 样本, 审计/回溯用.
    raw_data = Column(JSONColumn, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # (user_id, recorded_at) 唯一: 同一次 ECG 重复上送幂等 (按时间定位, upsert).
        # recorded_at 为 NULL 的记录不参与唯一约束 (SQL NULL != NULL), 退化为追加.
        UniqueConstraint("user_id", "recorded_at", name="uq_ecg_user_recorded"),
        Index("ix_ecg_user_recorded", "user_id", "recorded_at"),
    )
