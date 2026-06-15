"""卧室环境快照 —— 智能卧室睡眠环境闭环的数据底座 (设计文档 §7).

为什么独立成表 (不塞 garmin_data / 通用 environment):
- garmin_data 是**按天聚合**的可穿戴生理指标; 卧室环境是**家居传感器点事件**
  (青萍/Aqara/HA 每 1-5 分钟一条 CO2/PM2.5/温湿度), 语义和上报频率都不同.
- twin 的 outdoor `environment` 分区是**室外天气/AQI**, 进通用 LLM 上下文; 卧室
  居住环境 (CO2/床上状态/占用) 是隐私敏感数据, 按设计文档 §11 **不发通用 LLM**,
  因此**绝不**接入 twin formatter 的 prompt blob (见 tests/test_bedroom_environment.py
  的隐私守门测试).

这是设计文档 §9 点名的「BedroomEnvironmentService 快照」地基; HA Adapter / 场景
下行 / Protocol / UI 是后续 PR.
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.database import Base
from app.models.agent_audit_log import JSONColumn


class BedroomEnvironmentSnapshot(Base):
    """卧室某一时刻的环境快照 (CO2/PM2.5/温湿度/TVOC/照度/占用/床上状态)."""

    __tablename__ = "bedroom_environment_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)

    # 房间标识. 默认 "bedroom"; 多房间未来可扩 (study / nursery 等).
    room_id = Column(String(64), nullable=False, default="bedroom")

    # 采集时刻 (传感器读数时间, 非入库时间). 用于"最近一条"排序与 stale 判定.
    captured_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # 环境指标 —— 全部可空: 不同传感器组合提供的字段不同, 缺则不强填.
    co2_ppm = Column(Float, nullable=True)
    pm25 = Column(Float, nullable=True)
    temperature_c = Column(Float, nullable=True)
    humidity_percent = Column(Float, nullable=True)
    tvoc = Column(Float, nullable=True)
    illuminance_lux = Column(Float, nullable=True)

    # 占用 / 床上状态 (人体传感器 / 床垫). 可空 —— 没有对应传感器时为 None.
    occupancy = Column(Boolean, nullable=True)
    bed_presence = Column(Boolean, nullable=True)

    # 来源映射 {指标: 设备/实体}, 便于排障 (哪条数据来自哪个传感器).
    sources = Column(JSONColumn, nullable=True)

    # 数据置信度 high|medium|low. 红外单向 / 推断值标 low (设计文档 §6.4/§7).
    confidence = Column(String(16), nullable=False, default="medium")

    # 是否过期 (captured_at 距读取时刻超过新鲜窗口). 入库时通常 False;
    # get_current 读取时按时间动态计算并覆盖, 这里仅作落库占位.
    stale = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # 同一房间同一采集时刻幂等 (HA 重复推送不重复入库).
        UniqueConstraint(
            "user_id", "room_id", "captured_at", name="uq_bedroom_env_user_room_ts"
        ),
        Index(
            "ix_bedroom_env_user_room_ts", "user_id", "room_id", "captured_at"
        ),
    )
