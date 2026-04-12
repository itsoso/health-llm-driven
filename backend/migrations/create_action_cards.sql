-- ActionCard: 对话产出固化到首页的行动卡片
CREATE TABLE IF NOT EXISTS action_cards (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    card_type VARCHAR(30) DEFAULT 'note',
    color VARCHAR(20),
    source_type VARCHAR(30) DEFAULT 'manual',
    source_id VARCHAR(120),
    status VARCHAR(20) DEFAULT 'active',
    priority INTEGER DEFAULT 0,
    is_visible BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_action_cards_user_id ON action_cards(user_id);
CREATE INDEX IF NOT EXISTS ix_action_cards_status ON action_cards(status);
CREATE INDEX IF NOT EXISTS ix_action_cards_user_status ON action_cards(user_id, status);

COMMENT ON TABLE action_cards IS '对话产出固化到首页的行动卡片（训练计划/饮食方案/复查提醒等）';
