-- Phase B P3: cross-source reconciliation candidate side-table.
-- Additive scaffolding only — detector writes candidate rows; NO mutation of
-- kb_documents/kb_edges, NO auto-approve. Serving stays reviewed-only.
CREATE TABLE IF NOT EXISTS kb_reconciliation_candidate (
    id BIGSERIAL PRIMARY KEY,
    kind VARCHAR(20) NOT NULL,
    left_doc_id TEXT NOT NULL,
    right_doc_id TEXT NOT NULL,
    entity_type VARCHAR(80),
    entity_id VARCHAR(160),
    relation_tag VARCHAR(20),
    score DOUBLE PRECISION,
    signals JSONB NOT NULL DEFAULT '{}'::jsonb,
    canonical_hint TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    reviewed_by VARCHAR(120),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    decision JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- 有序对 (left,right) 复合唯一 —— detector 写入前恒排序,幂等去重且杜绝字符串键分隔符歧义。
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
