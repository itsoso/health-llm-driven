CREATE TABLE IF NOT EXISTS kb_documents (
    doc_id TEXT PRIMARY KEY,
    doc_type VARCHAR(40) NOT NULL,
    entity_type VARCHAR(80),
    entity_id VARCHAR(160),
    title TEXT,
    summary TEXT,
    body TEXT,
    content_hash VARCHAR(64),
    confidence FLOAT,
    evidence_level VARCHAR(1),
    applies_when JSON DEFAULT '[]',
    recommends_lookup JSON DEFAULT '[]',
    sources JSON DEFAULT '[]',
    tsv TEXT,
    last_confirmed TIMESTAMP,
    decay_rate VARCHAR(20) DEFAULT 'normal',
    is_archived BOOLEAN NOT NULL DEFAULT 0,
    metadata JSON DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_kb_documents_doc_type ON kb_documents(doc_type);
CREATE INDEX IF NOT EXISTS ix_kb_documents_entity ON kb_documents(entity_type, entity_id);

CREATE TABLE IF NOT EXISTS kb_edges (
    edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    src_doc_id TEXT NOT NULL REFERENCES kb_documents(doc_id) ON DELETE CASCADE,
    dst_doc_id TEXT NOT NULL REFERENCES kb_documents(doc_id) ON DELETE CASCADE,
    relation VARCHAR(80) NOT NULL,
    confidence FLOAT,
    source_claim_id TEXT,
    metadata JSON DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_kb_edges_src_relation ON kb_edges(src_doc_id, relation);
CREATE INDEX IF NOT EXISTS ix_kb_edges_dst_relation ON kb_edges(dst_doc_id, relation);
CREATE INDEX IF NOT EXISTS ix_kb_edges_source_claim ON kb_edges(source_claim_id);

CREATE TABLE IF NOT EXISTS kb_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT,
    op VARCHAR(40) NOT NULL,
    actor VARCHAR(120),
    diff JSON DEFAULT '{}',
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_kb_audit_doc_id ON kb_audit(doc_id);
CREATE INDEX IF NOT EXISTS ix_kb_audit_op ON kb_audit(op);
CREATE INDEX IF NOT EXISTS ix_kb_audit_ts ON kb_audit(ts);
