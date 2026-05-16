CREATE TABLE IF NOT EXISTS kb_documents (
    doc_id TEXT PRIMARY KEY,
    doc_type VARCHAR(40) NOT NULL,
    entity_type VARCHAR(80),
    entity_id VARCHAR(160),
    title TEXT,
    summary TEXT,
    body TEXT,
    content_hash VARCHAR(64),
    confidence DOUBLE PRECISION,
    evidence_level CHAR(1),
    applies_when JSONB DEFAULT '[]'::jsonb,
    recommends_lookup JSONB DEFAULT '[]'::jsonb,
    sources JSONB DEFAULT '[]'::jsonb,
    tsv TSVECTOR,
    last_confirmed TIMESTAMP WITH TIME ZONE,
    decay_rate VARCHAR(20) DEFAULT 'normal',
    is_archived BOOLEAN NOT NULL DEFAULT false,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_kb_documents_doc_type ON kb_documents(doc_type);
CREATE INDEX IF NOT EXISTS ix_kb_documents_entity ON kb_documents(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_kb_documents_tsv ON kb_documents USING GIN(tsv);
CREATE INDEX IF NOT EXISTS ix_kb_documents_applies_when ON kb_documents USING GIN(applies_when);
CREATE INDEX IF NOT EXISTS ix_kb_documents_sources ON kb_documents USING GIN(sources);

CREATE TABLE IF NOT EXISTS kb_edges (
    edge_id SERIAL PRIMARY KEY,
    src_doc_id TEXT NOT NULL REFERENCES kb_documents(doc_id) ON DELETE CASCADE,
    dst_doc_id TEXT NOT NULL REFERENCES kb_documents(doc_id) ON DELETE CASCADE,
    relation VARCHAR(80) NOT NULL,
    confidence DOUBLE PRECISION,
    source_claim_id TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_kb_edges_src_relation ON kb_edges(src_doc_id, relation);
CREATE INDEX IF NOT EXISTS ix_kb_edges_dst_relation ON kb_edges(dst_doc_id, relation);
CREATE INDEX IF NOT EXISTS ix_kb_edges_source_claim ON kb_edges(source_claim_id);

CREATE TABLE IF NOT EXISTS kb_audit (
    id SERIAL PRIMARY KEY,
    doc_id TEXT,
    op VARCHAR(40) NOT NULL,
    actor VARCHAR(120),
    diff JSONB DEFAULT '{}'::jsonb,
    ts TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_kb_audit_doc_id ON kb_audit(doc_id);
CREATE INDEX IF NOT EXISTS ix_kb_audit_op ON kb_audit(op);
CREATE INDEX IF NOT EXISTS ix_kb_audit_ts ON kb_audit(ts);
