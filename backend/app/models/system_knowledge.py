"""System-level LLM Wiki v2 knowledge base models."""

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
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
    tsv = Column(Text)
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
