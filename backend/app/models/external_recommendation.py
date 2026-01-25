"""外部健康建议模型 - 存储第三方系统写入的健康建议"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Date, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class ExternalRecommendation(Base):
    """外部健康建议 - 来自第三方系统(如 Browser-LLM-Driven, GPT Health 等)的建议"""
    __tablename__ = "external_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 建议类型
    category = Column(String(50), nullable=False)  # exercise, diet, sleep, supplement, general

    # 内容
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)

    # 来源
    source_name = Column(String(100), nullable=False)  # Browser-LLM-Driven, GPT Health, etc.
    source_api_key_id = Column(Integer, ForeignKey("user_api_keys.id"), nullable=True)

    # 时间
    recommendation_date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    user = relationship("User", backref="external_recommendations")
    source_api_key = relationship("UserApiKey")

    __table_args__ = (
        Index('ix_ext_rec_user_date', 'user_id', 'recommendation_date'),
        Index('ix_ext_rec_user_category', 'user_id', 'category'),
    )
