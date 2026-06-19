"""事件前提醒去重记账(P1-B)。

每条 (user_id, item_key, remind_date) 至多提醒一次 —— 防 1 分钟扫描在边界
重复推、防 beat 重试/补偿造成的二次推送。`item_key` 即排程项/日历事件的稳定标识
(如 `med:123` / `cal:<event_id>`),`remind_date` 为北京日历日。

不存 PII(无标题/无内容);仅作幂等账。UniqueConstraint 兜底,应用层先 INSERT
命中冲突即视为"已提醒过"。
"""
from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.database import Base


class SentEventReminder(Base):
    """事件前提醒去重记录(至多一次/天/项)。"""

    __tablename__ = "sent_event_reminders"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "item_key", "remind_date",
            name="uq_sent_event_reminder_user_item_date",
        ),
        Index("ix_sent_event_reminder_user_date", "user_id", "remind_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # 排程项 / 日历事件稳定标识: "med:123" / "supplement:45" / "meal:lunch" /
    # "workout:today" / "cal:<event_id>"。绝不含 PII。
    item_key = Column(String(120), nullable=False)
    remind_date = Column(Date, nullable=False)  # 北京日历日
    kind = Column(String(40))  # meeting/medication/supplement/movement (可观测用,非键)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
