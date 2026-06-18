"""基因数据模型 — 基因检测报告 + 基因变异位点"""
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey, JSON, Index
from sqlalchemy.sql import func
from app.database import Base
from app.models._encrypted import EncryptedString, EncryptedText


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
    rsid = Column(String(30), index=True)
    category = Column(String(50), nullable=False, index=True)  # nutrition/exercise/drug_sensitivity/disease_risk/sleep
    gene_name = Column(String(50), nullable=False)
    variant_name = Column(String(100))
    # 2026-05-13 C 优化: genotype 是用户最敏感"独一无二"字段, 列加密
    # (Fernet 输出 ~140 char, 旧明文行 decrypt fallback 共存)
    genotype = Column(EncryptedString(200))
    raw_genotype = Column(EncryptedString(200))
    result_label = Column(String(100))
    risk_level = Column(String(20), default="info")  # low/medium/high/info
    variant_nature = Column(String(20), default="neutral")  # protective/risk/neutral — 区分优势基因vs风险基因
    mapping_source = Column(String(50), default="known_snp")
    evidence_level = Column(String(50), default="screening")
    description = Column(Text)
    health_implications = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_genetic_variants_user_category", "user_id", "category"),
        Index("ix_genetic_variants_user_gene", "user_id", "gene_name"),
        Index("ix_genetic_variants_profile_rsid", "profile_id", "rsid"),
    )


class GeneticImportJob(Base):
    """Structured provenance for every genetic import attempt."""
    __tablename__ = "genetic_import_jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    profile_id = Column(Integer, ForeignKey("genetic_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(20), nullable=False)  # txt/pdf/manual
    provider = Column(String(100))
    status = Column(String(20), default="queued", index=True)  # queued/processing/done/failed
    parser_version = Column(String(50), nullable=False, default="genetic-import-v2")
    raw_file_hash = Column(String(64))
    raw_record_count = Column(Integer, default=0)
    known_total = Column(Integer, default=0)
    matched_count = Column(Integer, default=0)
    duplicate_count = Column(Integer, default=0)
    unknown_count = Column(Integer, default=0)
    unmapped_count = Column(Integer, default=0)
    missing_count = Column(Integer, default=0)
    coverage_summary = Column(JSON)
    # DEPRECATED (2026-06-17): 原始全量基因型已迁移到专用多租户表 GeneticRawFile
    # (per-tenant 加密 + Postgres RLS + 软删/被遗忘权)。本列保留只为不动已 ship 的迁移,
    # 新写入一律走 GeneticRawFile, 不再写本列。读路径也已切到 GeneticRawFile。
    raw_genotypes = Column(EncryptedText)
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_genetic_import_jobs_user_profile", "user_id", "profile_id"),
    )
