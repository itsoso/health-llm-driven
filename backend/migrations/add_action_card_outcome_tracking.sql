-- ActionCard outcome tracking — Specialist 信任循环
-- 给 action_cards 加 5 个字段, 用于 30 天 hit-rate 计算
-- 兼容: 老卡片所有新字段为 NULL, 不参与评分.

ALTER TABLE action_cards
    ADD COLUMN IF NOT EXISTS creator_specialist VARCHAR(64),
    ADD COLUMN IF NOT EXISTS check_back_date TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS actual_value VARCHAR(100),
    ADD COLUMN IF NOT EXISTS accuracy_score INTEGER,
    ADD COLUMN IF NOT EXISTS graded_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS grading_notes TEXT;

CREATE INDEX IF NOT EXISTS idx_action_card_creator_specialist
    ON action_cards (creator_specialist);

CREATE INDEX IF NOT EXISTS idx_action_card_check_back_date
    ON action_cards (check_back_date)
    WHERE graded_at IS NULL AND check_back_date IS NOT NULL;
