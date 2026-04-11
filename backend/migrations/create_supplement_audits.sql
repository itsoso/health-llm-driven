-- 补剂审计系统 (Supplement Audit)
-- 审计是一份"决策文档"：证据链 + 五段式建议（keep/add/upgrade/remove/monitor）
-- 区别于日度推荐 (ai_insights) 和周报 (health_reports type=weekly)，
-- 审计的生命周期是 3-12 个月，按事件触发或用户手动生成。

CREATE TABLE IF NOT EXISTS supplement_audits (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,                       -- v1, v2, v3...（同 user 下自增）
    triggered_by VARCHAR(30) NOT NULL,              -- manual | new_exam | new_gene | scheduled | changed_conditions | migration
    parent_audit_id INTEGER REFERENCES supplement_audits(id) ON DELETE SET NULL,  -- 上一版
    data_period_start DATE,                         -- 审计依据数据的起始
    data_period_end DATE,                           -- 审计依据数据的结束
    title VARCHAR(200) NOT NULL,
    input_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,   -- profile+labs+gene+garmin+meds 快照
    rationale_markdown TEXT NOT NULL,               -- 完整 markdown 推理
    summary VARCHAR(500),                           -- 一句话摘要
    status VARCHAR(20) NOT NULL DEFAULT 'active',   -- active | superseded | archived
    next_review_at DATE,                            -- 建议下次复查时间
    generated_by VARCHAR(50) DEFAULT 'manual',      -- manual | llm-auto | supplement-advisor-skill | migration
    llm_model VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (user_id, version)
);

CREATE INDEX IF NOT EXISTS idx_supplement_audit_user_status
    ON supplement_audits(user_id, status);
CREATE INDEX IF NOT EXISTS idx_supplement_audit_user_version
    ON supplement_audits(user_id, version DESC);


CREATE TABLE IF NOT EXISTS supplement_audit_items (
    id SERIAL PRIMARY KEY,
    audit_id INTEGER NOT NULL REFERENCES supplement_audits(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action_type VARCHAR(20) NOT NULL,               -- keep | add | upgrade | remove | monitor | warning
    priority INTEGER NOT NULL DEFAULT 3,            -- 1=highest, 5=lowest
    title VARCHAR(200) NOT NULL,
    product_id INTEGER REFERENCES supplement_products(id) ON DELETE SET NULL,
    supplement_definition_id INTEGER REFERENCES supplement_definitions(id) ON DELETE SET NULL,
    target_metric VARCHAR(100),                     -- monitor 类型时使用，e.g. "同型半胱氨酸 Hcy"
    rationale_markdown TEXT NOT NULL,               -- 单条证据链 markdown
    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [{type,id,ref}] 结构化证据
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending | accepted | rejected | completed | superseded
    user_note TEXT,
    accepted_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    rejected_reason VARCHAR(200),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_item_user_status
    ON supplement_audit_items(user_id, status);
CREATE INDEX IF NOT EXISTS idx_audit_item_audit_prio
    ON supplement_audit_items(audit_id, action_type, priority);
CREATE INDEX IF NOT EXISTS idx_audit_item_user_action
    ON supplement_audit_items(user_id, action_type, status);
