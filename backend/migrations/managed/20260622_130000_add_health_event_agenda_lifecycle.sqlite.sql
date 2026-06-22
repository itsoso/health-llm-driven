-- Reva 首页脊柱 Increment 1:health_events 议程生命周期列(sqlite 变体)。
-- sqlite 的 ADD COLUMN 无 IF NOT EXISTS;managed runner 按文件名记录已应用、只跑一次。
-- 测试库由 Base.metadata.create_all 直接带列,不走本迁移。complete_ref 用 TEXT(JSONColumn)。
ALTER TABLE health_events ADD COLUMN agenda_status VARCHAR(20);
ALTER TABLE health_events ADD COLUMN scheduled_for TIMESTAMP;
ALTER TABLE health_events ADD COLUMN action_kind VARCHAR(30);
ALTER TABLE health_events ADD COLUMN complete_ref TEXT;
ALTER TABLE health_events ADD COLUMN skip_reason VARCHAR(40);
ALTER TABLE health_events ADD COLUMN association_only BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE health_events ADD COLUMN completed_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_health_events_user_agenda
    ON health_events (user_id, agenda_status, scheduled_for);
