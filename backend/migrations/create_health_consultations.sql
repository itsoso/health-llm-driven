-- 健康咨询系统 (Health Consultation)
--
-- 一等公民级别的"多层级症状咨询追踪"表:
-- 每次咨询 = 一份决策文档 + 多个 items (假设/行动/预测/警戒)
-- items 分 4 类, 共用同一张表, 用 item_type 区分, meta JSONB 存类型特有字段
--
-- 与 supplement_audits 的区别:
-- - audits: 补剂方案决策, 五段式 (keep/add/upgrade/remove/monitor)
-- - consultations: 症状咨询, 四类条目 (hypothesis/action/prediction/red_flag)
-- - predictions 是 consultations 独有的: 带 baseline/target/check_at/data_source 可自动回测

CREATE TABLE IF NOT EXISTS health_consultations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,                       -- 同 user 下自增版本号
    parent_consultation_id INTEGER REFERENCES health_consultations(id) ON DELETE SET NULL,

    -- 基本信息
    title VARCHAR(200) NOT NULL,
    topic VARCHAR(100),                             -- "口腔溃疡+自主神经失衡"
    consultation_type VARCHAR(30) NOT NULL DEFAULT 'symptom_advisory',
                                                    -- symptom_advisory | lifestyle_advice | preventive_review | urgent | followup
    triggered_by VARCHAR(30) NOT NULL DEFAULT 'manual',
                                                    -- manual | new_symptom | scheduled | linked_event | followup

    chief_complaint TEXT,                            -- 主诉
    input_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,  -- 咨询时的健康数据快照
    rationale_markdown TEXT NOT NULL,                -- 完整对话 markdown
    summary VARCHAR(500),

    -- 生命周期
    status VARCHAR(20) NOT NULL DEFAULT 'active',    -- active | superseded | verified | archived
    verification_scheduled_at DATE,                  -- 下次自动复盘时间
    verified_at TIMESTAMP WITH TIME ZONE,            -- 最后一次验证时间

    -- 来源
    generated_by VARCHAR(50) DEFAULT 'manual',       -- manual | claude-code | llm-auto
    llm_model VARCHAR(50),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (user_id, version)
);

CREATE INDEX IF NOT EXISTS idx_consultation_user_status
    ON health_consultations(user_id, status);
CREATE INDEX IF NOT EXISTS idx_consultation_user_version
    ON health_consultations(user_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_consultation_verification
    ON health_consultations(verification_scheduled_at)
    WHERE status = 'active';


CREATE TABLE IF NOT EXISTS consultation_items (
    id SERIAL PRIMARY KEY,
    consultation_id INTEGER NOT NULL REFERENCES health_consultations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- 核心分类
    item_type VARCHAR(20) NOT NULL,                 -- hypothesis | action | prediction | red_flag | note
    item_code VARCHAR(20),                           -- H1/A1/P1/R1 (内部编号,便于 LLM 引用)
    priority INTEGER NOT NULL DEFAULT 3,             -- 1=最高, 5=最低

    -- 内容
    title VARCHAR(300) NOT NULL,
    content_markdown TEXT,

    -- 多态元数据 (不同 item_type 塞不同结构)
    -- hypothesis: {confidence, verify_method, evidence_for[], evidence_against[]}
    -- action:     {action_category, frequency, start_date, trigger_condition}
    -- prediction: {metric_name, metric_display, baseline, target, data_source, check_after_days, verify_method}
    -- red_flag:   {severity, trigger_condition}
    meta JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- 状态机 (不同类型使用不同子集的状态)
    -- hypothesis: pending | confirmed | refuted | inconclusive
    -- action:     pending | in_progress | completed | skipped | deferred
    -- prediction: pending | met | not_met | partial | inconclusive
    -- red_flag:   watching | triggered | resolved
    status VARCHAR(20) NOT NULL DEFAULT 'pending',

    due_date DATE,                                   -- 行动项截止 / 预测检查日
    user_note TEXT,
    outcome TEXT,                                    -- 验证结果描述(例如"深睡从 80 涨到 93")
    actual_value VARCHAR(200),                       -- prediction 的实际值(结构化)

    verified_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_consultation_item_consult
    ON consultation_items(consultation_id, item_type, priority);
CREATE INDEX IF NOT EXISTS idx_consultation_item_user_status
    ON consultation_items(user_id, item_type, status);
CREATE INDEX IF NOT EXISTS idx_consultation_item_due
    ON consultation_items(user_id, due_date)
    WHERE status IN ('pending', 'in_progress', 'watching');
