-- 通用身体症状记录 (偶发症状, 不绑 disease_profile)
-- 创建时间: 2026-05-08
-- 用途:
--   "今天眼睛痒" / "右膝盖钝痛" / "嗓子有痰" 这类偶发症状的低门槛录入
--   LLM 通过 health_record(record_type="symptom") 工具自动写入
--   与 disease_tracking.symptom_logs (慢病专用打卡) 双源并存

CREATE TABLE IF NOT EXISTS symptom_entries (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 部位枚举: eye / respiratory / skin / digestive / musculoskeletal / head / general / other
    body_part VARCHAR NOT NULL,
    description TEXT NOT NULL,

    severity INTEGER CHECK (severity >= 1 AND severity <= 10),
    triggers JSONB DEFAULT '[]',
    duration_minutes INTEGER,
    source VARCHAR DEFAULT 'manual',  -- manual / voice / siri
    notes TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_symptom_user_occurred ON symptom_entries(user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_symptom_body_part ON symptom_entries(body_part);
