-- 2026-06-25: 时区改为「跟随用户地理位置 + 手动覆盖」(sqlite 不支持 ADD COLUMN IF NOT EXISTS;
-- managed runner 用 schema_migrations checksum 保证只跑一次)。
ALTER TABLE user_profiles ADD COLUMN detected_timezone VARCHAR(64);
ALTER TABLE user_profiles ADD COLUMN manual_timezone VARCHAR(64);
