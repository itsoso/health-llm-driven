"""System-level LLM Wiki v2 knowledge base models."""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.sql import func

from app.database import Base


class KBDocument(Base):
    """Metadata and compiled text for system wiki entities, claims, and articles."""

    __tablename__ = "kb_documents"

    doc_id = Column(Text, primary_key=True)
    doc_type = Column(String(40), nullable=False, index=True)
    entity_type = Column(String(80), index=True)
    entity_id = Column(String(160), index=True)
    title = Column(Text)
    summary = Column(Text)
    body = Column(Text)
    content_hash = Column(String(64))
    confidence = Column(Float)
    evidence_level = Column(String(1))
    applies_when = Column(JSONB, default=list)
    recommends_lookup = Column(JSONB, default=list)
    sources = Column(JSONB, default=list)
    tsv = Column(Text().with_variant(TSVECTOR(), "postgresql"))
    last_confirmed = Column(DateTime(timezone=True))
    decay_rate = Column(String(20), default="normal")
    is_archived = Column(Boolean, default=False, nullable=False)
    metadata_json = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class KBEdge(Base):
    """Typed relationship between system knowledge documents."""

    __tablename__ = "kb_edges"

    edge_id = Column(Integer, primary_key=True, autoincrement=True)
    src_doc_id = Column(Text, ForeignKey("kb_documents.doc_id"), nullable=False, index=True)
    dst_doc_id = Column(Text, ForeignKey("kb_documents.doc_id"), nullable=False, index=True)
    relation = Column(String(80), nullable=False, index=True)
    confidence = Column(Float)
    source_claim_id = Column(Text)
    metadata_json = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class KBDocumentVector(Base):
    """Sparse vector index for reviewed-system-knowledge retrieval."""

    __tablename__ = "kb_document_vectors"

    doc_id = Column(
        Text,
        ForeignKey("kb_documents.doc_id", ondelete="CASCADE"),
        primary_key=True,
    )
    embedding_model = Column(String(80), nullable=False, index=True)
    content_hash = Column(String(64), nullable=False, index=True)
    vector_json = Column("vector", JSONB, nullable=False, default=dict)
    magnitude = Column(Float, nullable=False, default=0.0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class KBAudit(Base):
    """Audit trail for system knowledge operations."""

    __tablename__ = "kb_audit"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(Text, index=True)
    op = Column(String(40), nullable=False, index=True)
    actor = Column(String(120))
    diff = Column(JSONB, default=dict)
    ts = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class KBReconciliationCandidate(Base):
    """跨源对账候选(Phase B 旁路表)—— detector/judge 只往这写「合并前可审状态」。

    **治理边界**:本表是 authoring/审核面对象,**绝不进健康运行时**(lookup_for_twin /
    knowledge_librarian / search_knowledge 只读 kb_documents 且套 reviewed 门,永不读本表)。
    P3 只有确定性 detector 写候选 + 只读队列;**零 kb_documents/kb_edges mutation、零 auto-approve**。
    relation_tag/score 的语义判定与自动合并留到 P5(过逐 entity_type 零误合 eval 才开)。
    """

    __tablename__ = "kb_reconciliation_candidate"
    # 无序对去重 = **有序对复合唯一** (left_doc_id, right_doc_id),写入前 left/right 恒排序(lo,hi)。
    # 复合唯一直接以真 doc_id 为键 → 重扫幂等且**不复活已 rejected 候选**,并杜绝
    # 字符串 pair_key 的分隔符歧义(doc_id 是外部 authoring 面的自由 TEXT,可含任意分隔符)。
    __table_args__ = (
        UniqueConstraint("left_doc_id", "right_doc_id", name="ux_kb_recon_candidate_pair"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    kind = Column(String(20), nullable=False, index=True)  # entity_align | claim_overlap
    left_doc_id = Column(Text, nullable=False, index=True)   # 恒为 min(doc_id_a, doc_id_b)
    right_doc_id = Column(Text, nullable=False, index=True)  # 恒为 max(doc_id_a, doc_id_b)
    entity_type = Column(String(80), index=True)
    entity_id = Column(String(160))
    # P3 确定性 detector 只在 content_hash 完全相同(同内容)时敢填 'duplicate';
    # 其余弱信号留 NULL 待 P5 judge 语义判(agree|conflict|complementary|duplicate)。
    relation_tag = Column(String(20), index=True)
    score = Column(Float)
    # 迁移里 signals/decision 是 NOT NULL DEFAULT '{}';model 同步 nullable=False + default=dict,
    # 防「ORM/conftest 过、真迁移表挂」的 null 漂移。
    signals = Column(JSONB, nullable=False, default=dict)  # 哪些 detector 触发 + 逐信号强度 + detected_by
    # resolve_canonical 纯函数输出(D1);None = 无 reviewed down-dedao 锚 → 只能走人。仅提示,零 mutation。
    canonical_hint = Column(Text)
    status = Column(String(20), nullable=False, default="open", index=True)  # open|approved|rejected|deferred
    detected_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    reviewed_by = Column(String(120))
    reviewed_at = Column(DateTime(timezone=True))
    decision = Column(JSONB, nullable=False, default=dict)
