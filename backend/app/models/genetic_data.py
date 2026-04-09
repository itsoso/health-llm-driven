"""基因数据模型 — 基因检测报告 + 基因变异位点"""
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey, JSON, Index
from sqlalchemy.sql import func
from app.database import Base


class GeneticProfile(Base):
    """基因检测报告档案"""
    __tablename__ = "genetic_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    test_provider = Column(String(100), nullable=False)  # 华大基因/微基因
    test_date = Column(Date, nullable=False)
    report_id = Column(String(100))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class GeneticVariant(Base):
    """基因变异位点"""
    __tablename__ = "genetic_variants"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    profile_id = Column(Integer, ForeignKey("genetic_profiles.id", ondelete="CASCADE"), nullable=False)
    category = Column(String(50), nullable=False, index=True)  # nutrition/exercise/drug_sensitivity/disease_risk/sleep
    gene_name = Column(String(50), nullable=False)
    variant_name = Column(String(100))
    genotype = Column(String(50))
    result_label = Column(String(100))
    risk_level = Column(String(20), default="info")  # low/medium/high/info
    variant_nature = Column(String(20), default="neutral")  # protective/risk/neutral — 区分优势基因vs风险基因
    description = Column(Text)
    health_implications = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_genetic_variants_user_category", "user_id", "category"),
        Index("ix_genetic_variants_user_gene", "user_id", "gene_name"),
    )
