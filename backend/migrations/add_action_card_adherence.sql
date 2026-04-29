-- ActionCard Adherence 信号
-- 没有依从度的评分是噪声. final_score = accuracy × adherence_confidence.
-- 兼容: adherence_confidence IS NULL 视为 100 (不降分, 老卡不受影响).

ALTER TABLE action_cards
    ADD COLUMN IF NOT EXISTS adherence_kind VARCHAR(30),
    ADD COLUMN IF NOT EXISTS adherence_confidence INTEGER;

-- 约束: confidence 合理范围 (Postgres 不支持 ADD CONSTRAINT IF NOT EXISTS, 用 DO block)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_adherence_confidence'
    ) THEN
        ALTER TABLE action_cards
            ADD CONSTRAINT chk_adherence_confidence
            CHECK (adherence_confidence IS NULL OR (adherence_confidence >= 0 AND adherence_confidence <= 100));
    END IF;
END $$;

-- 查询索引: 未来 hit-rate 过滤低依从度卡需要
CREATE INDEX IF NOT EXISTS idx_action_card_adherence
    ON action_cards (adherence_kind, adherence_confidence)
    WHERE adherence_kind IS NOT NULL;
