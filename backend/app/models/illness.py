"""当前病症追踪模型 - 用于记录急性/周期性小病的发作和进展"""
from sqlalchemy import Column, Integer, String, Date, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import DateTime
from app.database import Base


class IllnessEpisode(Base):
    """病症发作记录 - 记录一次病症的完整周期"""
    __tablename__ = "illness_episodes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    name = Column(String(100), nullable=False)          # 自由命名，如"口腔溃疡"、"嘴唇起泡"
    start_date = Column(Date, nullable=False)            # 发作日期
    end_date = Column(Date, nullable=True)              # 痊愈日期，null 表示仍在发作
    status = Column(String(20), nullable=False, default="active")  # active/improving/resolved
    severity = Column(Integer, nullable=True)             # 当前严重程度 1-10；未知为 null
    notes = Column(Text, nullable=True)                 # 备注

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 关联
    user = relationship("User", backref="illness_episodes")
    updates = relationship(
        "IllnessUpdate",
        back_populates="episode",
        cascade="all, delete-orphan",
        order_by="IllnessUpdate.update_date",
    )

    __table_args__ = (
        Index("idx_illness_episode_user_status", "user_id", "status"),
    )


class IllnessUpdate(Base):
    """病症进展更新 - 记录病症的每日变化"""
    __tablename__ = "illness_updates"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(Integer, ForeignKey("illness_episodes.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    update_date = Column(Date, nullable=False)
    severity = Column(Integer, nullable=True)            # 当日严重程度 1-10
    status = Column(String(20), nullable=True)           # 状态变化
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    episode = relationship("IllnessEpisode", back_populates="updates")

    __table_args__ = (
        Index("idx_illness_update_episode_date", "episode_id", "update_date"),
    )
