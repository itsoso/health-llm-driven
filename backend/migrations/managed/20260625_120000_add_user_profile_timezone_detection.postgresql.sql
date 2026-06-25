-- 2026-06-25: 时区改为「跟随用户地理位置 + 手动覆盖」。
-- detected_timezone: 设备/系统上报或 IP 反查到的 IANA 时区(自动跟随当前位置)。
-- manual_timezone:   用户手动锁定的 IANA 时区(非空 = pin,覆盖 detected)。
-- 生效优先级 manual → detected → 旧 timezone 列 → 默认 Asia/Shanghai
-- (见 app/utils/timezone.resolve_timezone_name)。旧 timezone 列保留为兼容兜底。
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS detected_timezone VARCHAR(64);
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS manual_timezone VARCHAR(64);
