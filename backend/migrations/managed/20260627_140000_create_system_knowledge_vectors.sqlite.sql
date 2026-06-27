CREATE TABLE IF NOT EXISTS kb_document_vectors (
    doc_id TEXT PRIMARY KEY REFERENCES kb_documents(doc_id) ON DELETE CASCADE,
    embedding_model VARCHAR(80) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    vector JSON NOT NULL DEFAULT '{}',
    magnitude FLOAT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_kb_document_vectors_embedding_model
    ON kb_document_vectors(embedding_model);
CREATE INDEX IF NOT EXISTS ix_kb_document_vectors_content_hash
    ON kb_document_vectors(content_hash);
