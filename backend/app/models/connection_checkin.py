"""社会连接 check-in —— L4 长期韧性层的主观问询(非监控)。

盘点缺口:系统有代谢/睡眠/慢病维度,但缺"社会连接"——而关系质量是长期健康最强
单一预测因子(哈佛 Grant Study 85 年)。这里用**季度主观问询**(UCLA-3 孤独量表 +
2 个连接问题)采集,完全用户主动填,绝不读对话内容/通讯录,避开隐私雷区。
"""
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Text

from app.database import Base


class ConnectionCheckin(Base):
    __tablename__ = "connection_checkins"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    checkin_date = Column(Date, nullable=False, default=date.today)

    # UCLA-3 孤独量表:3 题各 1-3 分(1=几乎没有 3=经常),总分 3-9。≥6 提示孤独风险。
    ucla_score = Column(Integer)            # 3-9
    # 连接结构问题(主观勾选)
    has_confidant = Column(Boolean)         # 是否有至少一位可吐露脆弱的人
    in_stable_group = Column(Boolean)       # 是否参与至少一个稳定群体
    notes = Column(Text)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
