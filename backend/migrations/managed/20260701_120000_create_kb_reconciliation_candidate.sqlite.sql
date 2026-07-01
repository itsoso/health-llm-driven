-- Phase B P3: cross-source reconciliation candidate side-table (sqlite mirror).
CREATE TABLE IF NOT EXISTS kb_reconciliation_candidate (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind VARCHAR(20) NOT NULL,
    left_doc_id TEXT NOT NULL,
    right_doc_id TEXT NOT NULL,
    entity_type VARCHAR(80),
    entity_id VARCHAR(160),
    relation_tag VARCHAR(20),
    score FLOAT,
    signals JSON NOT NULL DEFAULT '{}',
    canonical_hint TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_by VARCHAR(120),
    reviewed_at TIMESTAMP,
    decision JSON NOT NULL DEFAULT '{}'
);

-- 有序对 (left,right) 复合唯一 —— 与 postgresql 版对等。
CREATE UNIQUE INDEX IF NOT EXISTS ux_kb_recon_candidate_pair
    ON kb_reconciliation_candidate(left_doc_id, right_doc_id);
CREATE INDEX IF NOT EXISTS ix_kb_recon_candidate_kind
    ON kb_reconciliation_candidate(kind);
CREATE INDEX IF NOT EXISTS ix_kb_recon_candidate_status
    ON kb_reconciliation_candidate(status);
CREATE INDEX IF NOT EXISTS ix_kb_recon_candidate_entity_type
    ON kb_reconciliation_candidate(entity_type);
CREATE INDEX IF NOT EXISTS ix_kb_recon_candidate_left
    ON kb_reconciliation_candidate(left_doc_id);
CREATE INDEX IF NOT EXISTS ix_kb_recon_candidate_right
    ON kb_reconciliation_candidate(right_doc_id);
CREATE INDEX IF NOT EXISTS ix_kb_recon_candidate_relation_tag
    ON kb_reconciliation_candidate(relation_tag);
CREATE INDEX IF NOT EXISTS ix_kb_recon_candidate_detected_at
    ON kb_reconciliation_candidate(detected_at);
