"""多租户基因原始数据模型 —— 专用表 + per-tenant 加密密文 + 访问审计 + 删除.

设计要点 (互联网级多租户最敏感表):
- GeneticRawFile.ciphertext 是 **普通 Text**, 不是 EncryptedText —— 加密在 service 层
  (tenant_crypto) 做, 因派生密钥依赖 user_id, TypeDecorator 拿不到 user_id 上下文。
  库里只见 per-tenant Fernet 密文, 绝不明文。
- user_id 是租户键; 生产用 Postgres RLS (policy 用 current_setting('app.user_id'))
  在 DB 层强制隔离, 应用层 WHERE user_id 仍保留作双保险。RLS 见配对迁移。
- 删除(被遗忘权)= delete 端点**硬清 ciphertext**(真删除, 不可逆)+ 置 deleted_at(读路径过滤)。
  注: 软删本身不销毁密钥, 故真删靠硬清密文实现, 不依赖密钥销毁。仅保留审计元数据。
"""
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.database import Base
from app.models.agent_audit_log import JSONColumn

# BIGSERIAL on PG; SQLite 只对 INTEGER PRIMARY KEY 自增, 故 PK 用此 variant
# (生产 64-bit, 测试库 SQLite 也能 autoincrement)。
_BigPK = BigInteger().with_variant(Integer, "sqlite")


class GeneticRawFile(Base):
    """单次基因原始全量上传的 per-tenant 加密密文 (专用最敏感表, RLS 保护)。"""

    __tablename__ = "genetic_raw_files"

    id = Column(_BigPK, primary_key=True)
    # 租户键 —— RLS policy 比对的列。
    user_id = Column(BigInteger, nullable=False, index=True)
    profile_id = Column(
        BigInteger,
        ForeignKey("genetic_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    import_job_id = Column(
        BigInteger,
        ForeignKey("genetic_import_jobs.id"),
        nullable=True,
    )
    raw_sha256 = Column(String(64))
    snp_count = Column(Integer)
    byte_size = Column(Integer)
    key_version = Column(SmallInteger, default=1)
    enc_algo = Column(String(20), default="fernet-hkdf")
    # per-tenant 加密的 {rsid:genotype} JSON 密文 (普通 Text, 加密在 service 层)。
    ciphertext = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # 删除标记: delete 端点硬清 ciphertext(真删除/不可逆)后置此; 非空=已删, 读路径必须过滤。
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "raw_sha256", name="uq_genetic_raw_user_sha"),
        Index("ix_genetic_raw_user_profile", "user_id", "profile_id"),
    )


class GeneticRawAudit(Base):
    """基因原始数据每次访问/变更的审计记录 (lookup/reparse/delete/upload)。"""

    __tablename__ = "genetic_raw_audit"

    id = Column(_BigPK, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    profile_id = Column(BigInteger)
    action = Column(String(20), nullable=False)  # lookup/reparse/delete/upload
    # detail 不得含明文全量基因型, 只放 {rsid}/{gene}/{count} 等元信息。
    detail = Column(JSONColumn)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
