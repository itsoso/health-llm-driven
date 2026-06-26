"""Write 自治层每用户每日执行计数 —— 每日上限的**硬保证**(cap-TOCTOU 封口)。

背景:`write_autonomy.auto_execute_pending` 原先 `budget = CAP - _auto_executed_today()`
只读一次,两个并发 GET /write-intents 可各算出 budget=4 各执行 4 → 至多 2×CAP。把"今日
已自治执行数"落到本表一行(user_id, day),用单条原子
`UPDATE count=count+1 WHERE count<CAP` 的 rowcount 门把"检查 + 自增"做成一次原子操作
(行锁串行化并发预留)→ 跨并发请求绝不超过 CAP。这是 allowlist 扩容(更多 eligible pending)
前必须就位的硬封口,见 write_autonomy.py 的 `_reserve_autonomy_slot`。

注:`day` 用北京日历日(get_china_today),与依从/测量子系统口径一致。
"""
from sqlalchemy import Column, Date, DateTime, Integer
from sqlalchemy.sql import func

from app.database import Base


class AutonomyDailyCounter(Base):
    """(user_id, day) → 今日自治执行计数。复合主键即每用户每日唯一,天然防重复行。"""

    __tablename__ = "autonomy_daily_counters"

    user_id = Column(Integer, primary_key=True, nullable=False)
    day = Column(Date, primary_key=True, nullable=False)
    count = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
