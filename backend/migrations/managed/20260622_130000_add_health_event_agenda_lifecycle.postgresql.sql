-- Reva 首页脊柱 Increment 1:把一个被调度的全天行动变成 first-class HealthEvent。
-- 在 health_events 上加议程生命周期列(与既有事实流摄入列正交,additive,幂等可重跑)。
-- 旧行这些列全 NULL = 非议程项,既有事实流/确认逻辑完全不受影响(向后兼容)。
ALTER TABLE health_events ADD COLUMN IF NOT EXISTS agenda_status VARCHAR(20);
ALTER TABLE health_events ADD COLUMN IF NOT EXISTS scheduled_for TIMESTAMP WITH TIME ZONE;
ALTER TABLE health_events ADD COLUMN IF NOT EXISTS action_kind VARCHAR(30);
ALTER TABLE health_events ADD COLUMN IF NOT EXISTS complete_ref JSONB;
ALTER TABLE health_events ADD COLUMN IF NOT EXISTS skip_reason VARCHAR(40);
ALTER TABLE health_events ADD COLUMN IF NOT EXISTS association_only BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE health_events ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE;

-- 首页脊柱按 (user, agenda_status, scheduled_for) 拉今日议程项 / 过期扫描。
CREATE INDEX IF NOT EXISTS idx_health_events_user_agenda
    ON health_events (user_id, agenda_status, scheduled_for);
