-- ActionCard outcome tracking — Specialist 信任循环
-- 给 action_cards 加结构化干预 + 评分字段.
-- 注意: 历史漂移 — 之前 model 有 metric_key/baseline/target/verification_days
-- 但 prod DB 没建过, 这里一起补.
-- 兼容: 老卡片所有新字段为 NULL, 不参与评分.

ALTER TABLE action_cards
    -- 结构化干预 (legacy, 历史从未在 prod 建过)
    ADD COLUMN IF NOT EXISTS metric_key VARCHAR(50),
    ADD COLUMN IF NOT EXISTS baseline_value VARCHAR(100),
    ADD COLUMN IF NOT EXISTS target_value VARCHAR(100),
    ADD COLUMN IF NOT EXISTS verification_days INTEGER,
    -- 信任循环新增
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
