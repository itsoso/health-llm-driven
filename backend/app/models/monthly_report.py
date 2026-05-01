"""MonthlyReport — 月度自动复盘报告.

每个用户每月一份 (user_id, year, month)：
- 趋势 (metric_trends)
- AI 命中率 (ai_scorecard)
- 关键干预 (key_interventions)
- 简短叙事 (narrative)
- 下月重点 (next_focus)

生成策略：
- Celery 每月 1 日 08:10 批量生成上月报告
- API 查询时若缺失则 lazy-generate 兜底
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from app.database import Base


class MonthlyReport(Base):
    __tablename__ = "monthly_reports"
    __table_args__ = (
        UniqueConstraint("user_id", "year", "month", name="uq_monthly_report_user_ym"),
        Index("ix_monthly_report_user_ym", "user_id", "year", "month"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)  # 1..12

    # 完整报告 payload (JSONB on PG, JSON on SQLite fallback)
    report_data = Column(JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict)

    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    version = Column(String(16), default="v1", nullable=False)
