-- Phase 3 P3-2: ConversationMemory 加 status 列, 支持"覆盖而不删"的冲突解决.
-- status='active' (默认) 参与查询; status='superseded' 表示被新记忆替代, 历史可追溯但不展示.

ALTER TABLE conversation_memories
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS superseded_by INTEGER REFERENCES conversation_memories(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMP WITH TIME ZONE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_memory_status'
    ) THEN
        ALTER TABLE conversation_memories
            ADD CONSTRAINT chk_memory_status
            CHECK (status IN ('active', 'superseded', 'deleted'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_memory_active
    ON conversation_memories (user_id, memory_type, status)
    WHERE status = 'active';

COMMENT ON COLUMN conversation_memories.status IS 'P3-2: active=可查 / superseded=被新记忆覆盖 / deleted=用户主动删';
COMMENT ON COLUMN conversation_memories.superseded_by IS '若被覆盖, 指向覆盖它的新记忆 id; 用于审计';
