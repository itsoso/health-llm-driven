CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kb_document_embeddings (
    doc_id TEXT PRIMARY KEY REFERENCES kb_documents(doc_id) ON DELETE CASCADE,
    embedding_model VARCHAR(120) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    embedding vector(1024) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_kb_document_embeddings_model_doc
    ON kb_document_embeddings(embedding_model, doc_id);

CREATE INDEX IF NOT EXISTS ix_kb_document_embeddings_embedding_cosine
    ON kb_document_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
