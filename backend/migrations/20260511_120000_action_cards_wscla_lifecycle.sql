-- action_cards: WSCLA 生命周期字段
-- Phase 0 · W1 定基线: 让 action_cards 能同时承载
--   (1) 建议/计划 (既有)
--   (2) safety alerts (severity + user_decision='false_positive' 反馈 FP)
--   (3) 通知生命周期 (seen / push_sent / push_delivered / push_clicked)
--   (4) outcome 分类 (improved/unchanged/worsened/inconclusive)
--
-- 不建新表 agent_action_log: action_cards 已覆盖 80% (metric_key / baseline_value /
-- target_value / verification_days / check_back_date / actual_value / accuracy_score /
-- graded_at / adherence_kind / adherence_confidence / checklist / latest_assessment)
-- 缺的只是用户决策语义 + 通知埋点 + outcome 分类.
--
-- 兼容: 全部字段 nullable, 老卡不受影响, 未显式评过的卡在 WSCLA 聚合里自然不计入.

ALTER TABLE action_cards
    -- 通知生命周期 (Push CTR / 送达率基础)
    ADD COLUMN IF NOT EXISTS seen_at              TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS push_sent_at         TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS push_delivered_at    TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS push_clicked_at      TIMESTAMP WITH TIME ZONE,
    -- 用户决策语义 (status 是系统视角, user_decision 是用户意图, 正交)
    ADD COLUMN IF NOT EXISTS user_decision        VARCHAR(20),
    ADD COLUMN IF NOT EXISTS decided_at           TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS decision_reason      TEXT,
    -- safety alert 分级 (普通建议 NULL)
    ADD COLUMN IF NOT EXISTS severity             VARCHAR(20),
    -- outcome 分类 (accuracy_score 数字之外的语义标签)
    ADD COLUMN IF NOT EXISTS outcome              VARCHAR(20),
    ADD COLUMN IF NOT EXISTS effect_size          DOUBLE PRECISION;

-- 约束: Postgres 不支持 ADD CONSTRAINT IF NOT EXISTS, 用 DO block
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_action_card_user_decision'
    ) THEN
        ALTER TABLE action_cards
            ADD CONSTRAINT chk_action_card_user_decision
            CHECK (user_decision IS NULL OR user_decision IN
                   ('accepted','adjusted','declined','dismissed','false_positive'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_action_card_severity'
    ) THEN
        ALTER TABLE action_cards
            ADD CONSTRAINT chk_action_card_severity
            CHECK (severity IS NULL OR severity IN
                   ('critical','high','medium','low','info'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_action_card_outcome'
    ) THEN
        ALTER TABLE action_cards
            ADD CONSTRAINT chk_action_card_outcome
            CHECK (outcome IS NULL OR outcome IN
                   ('improved','unchanged','worsened','inconclusive'));
    END IF;
END $$;

-- 索引: WSCLA 聚合 / Push CTR 查询 / severity 过滤
CREATE INDEX IF NOT EXISTS idx_action_card_user_decision
    ON action_cards (user_id, user_decision)
    WHERE user_decision IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_action_card_push_clicked
    ON action_cards (user_id, push_clicked_at)
    WHERE push_clicked_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_action_card_severity
    ON action_cards (user_id, severity, created_at DESC)
    WHERE severity IS NOT NULL;

COMMENT ON COLUMN action_cards.seen_at           IS 'WSCLA: 用户首次打开/展开这张卡的时间';
COMMENT ON COLUMN action_cards.push_sent_at      IS 'WSCLA: 通知发出时间 (APNs 调用返回后)';
COMMENT ON COLUMN action_cards.push_delivered_at IS 'WSCLA: APNs 回执送达时间';
COMMENT ON COLUMN action_cards.push_clicked_at   IS 'WSCLA: 通知被点击, 深链触发回写';
COMMENT ON COLUMN action_cards.user_decision     IS 'WSCLA: accepted=执行意愿 / declined=明拒 / dismissed=划走 / false_positive=safety误报 / adjusted=修改后接受';
COMMENT ON COLUMN action_cards.decided_at        IS 'WSCLA: user_decision 第一次设置的时间';
COMMENT ON COLUMN action_cards.severity          IS 'safety alert 分级: critical / high / medium / low / info; 普通建议 NULL';
COMMENT ON COLUMN action_cards.outcome           IS 'WSCLA: 验证窗口结束时的语义分类, 与 accuracy_score 数字配合';
COMMENT ON COLUMN action_cards.effect_size       IS 'WSCLA: (实测值 - baseline) / baseline_sd, 标准化效应值; 可空';
