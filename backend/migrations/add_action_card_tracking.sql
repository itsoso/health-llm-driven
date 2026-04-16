-- Agent Native Phase 2: ActionCard 干预效果追踪字段
ALTER TABLE action_cards ADD COLUMN IF NOT EXISTS checklist JSONB DEFAULT '[]';
ALTER TABLE action_cards ADD COLUMN IF NOT EXISTS last_assessed_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE action_cards ADD COLUMN IF NOT EXISTS assessment_count INTEGER DEFAULT 0;
ALTER TABLE action_cards ADD COLUMN IF NOT EXISTS latest_assessment JSONB;
