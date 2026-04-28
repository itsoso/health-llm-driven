-- Health Knowledge Graph — entities + typed relations
-- 配合 memory_facts 形成完整 LLM Wiki v2 数据层:
-- - memory_facts:    "句子" 级事实 (subject 字符串)
-- - health_entities: "节点" 级实体 (canonical_name + aliases)
-- - entity_relations: "边" 级关系 (subject_id → predicate → object_id)

CREATE TABLE IF NOT EXISTS health_entities (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    type VARCHAR(40) NOT NULL,
    canonical_name VARCHAR(200) NOT NULL,
    aliases JSONB DEFAULT '[]'::jsonb,
    attributes JSONB DEFAULT '{}'::jsonb,
    confidence FLOAT NOT NULL DEFAULT 0.7,
    sources JSONB DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT true,
    merged_into_id INTEGER REFERENCES health_entities(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT uq_entity_user_type_name UNIQUE (user_id, type, canonical_name)
);

CREATE INDEX IF NOT EXISTS ix_health_entities_user_id ON health_entities(user_id);
CREATE INDEX IF NOT EXISTS idx_entity_user_type ON health_entities(user_id, type);
CREATE INDEX IF NOT EXISTS idx_entity_user_active ON health_entities(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_gin ON health_entities USING gin(aliases);


CREATE TABLE IF NOT EXISTS entity_relations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL REFERENCES health_entities(id) ON DELETE CASCADE,
    predicate VARCHAR(40) NOT NULL,
    object_id INTEGER NOT NULL REFERENCES health_entities(id) ON DELETE CASCADE,
    confidence FLOAT NOT NULL DEFAULT 0.5,
    evidence_count INTEGER NOT NULL DEFAULT 1,
    sources JSONB DEFAULT '[]'::jsonb,
    started_at TIMESTAMP WITH TIME ZONE,
    ended_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN NOT NULL DEFAULT true,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT uq_relation_triple UNIQUE (user_id, subject_id, predicate, object_id)
);

CREATE INDEX IF NOT EXISTS ix_entity_relations_user_id ON entity_relations(user_id);
CREATE INDEX IF NOT EXISTS ix_entity_relations_subject_id ON entity_relations(subject_id);
CREATE INDEX IF NOT EXISTS ix_entity_relations_object_id ON entity_relations(object_id);
CREATE INDEX IF NOT EXISTS ix_entity_relations_predicate ON entity_relations(predicate);
CREATE INDEX IF NOT EXISTS idx_relation_user_pred ON entity_relations(user_id, predicate);
CREATE INDEX IF NOT EXISTS idx_relation_subject_pred ON entity_relations(subject_id, predicate);
CREATE INDEX IF NOT EXISTS idx_relation_object_pred ON entity_relations(object_id, predicate);
