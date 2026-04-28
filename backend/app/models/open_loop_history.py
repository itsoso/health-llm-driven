"""
Open-Loop 推送历史 — 去重 + 用户反馈学习.

每条 APNs 推送写一行, 用户点击/反馈后更新.
用于:
  1. dedup: 同 user × kind × signal_key 在 N 天内不重发
  2. learning: user feedback 反向降权
  3. analytics: 哪类 signal 用户最常 dismiss
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from sqlalchemy.sql import func
from app.database import Base


class OpenLoopHistory(Base):
    __tablename__ = "open_loop_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)

    # 去重三元组: (user_id, kind, signal_key) 在 N 天内只发一次
    kind = Column(String(40), nullable=False, index=True)  # lab_overdue / action_card_due / ...
    signal_key = Column(String(100), nullable=False)
    # 例: lab_overdue: 'LDL' / action_card_due: 'card_id=123' / sync_stale: '<empty>'

    score = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    deeplink = Column(String(200))

    # 推送状态
    sent_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    delivery_ok = Column(Integer, nullable=False, default=1)  # 0/1
    delivery_error = Column(Text)

    # 用户反馈 (异步更新)
    user_action = Column(String(20))  # opened / dismissed / not_interested / snooze_7d / done
    action_at = Column(DateTime(timezone=True))
    snoozed_until = Column(DateTime(timezone=True))  # snooze_7d 时设置

    __table_args__ = (
        Index('idx_open_loop_user_kind_signal', 'user_id', 'kind', 'signal_key'),
        Index('idx_open_loop_user_sent', 'user_id', 'sent_at'),
    )
