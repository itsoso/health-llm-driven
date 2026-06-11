"""原研药推荐状态 —— 记录系统对某用户某药的原研药推荐及其采纳情况。

用途:对话中基于用户在用药给出原研药建议;用户采纳/忽略后置 status,后续对话
**不再重复推荐**(除非用户主动要求,届时把该药 status 重置回 suggested)。
"""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String

from app.database import Base


class OriginatorRecommendation(Base):
    __tablename__ = "originator_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 规范化通用名(originator_drugs._normalize 的结果),作为每用户唯一键。
    generic_name = Column(String(100), nullable=False)
    brand = Column(String(120))         # 原研药品牌(推荐时快照)
    manufacturer = Column(String(160))  # 原研厂家(快照)

    # suggested(已建议未处理) / adopted(已采纳=系统推荐) / dismissed(用户不需要)
    status = Column(String(20), nullable=False, default="suggested")
    source = Column(String(20), default="chat")  # chat / scan / manual

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        # 每用户每药一条状态(upsert 定位)
        Index("idx_orig_rec_user_generic", "user_id", "generic_name", unique=True),
    )
