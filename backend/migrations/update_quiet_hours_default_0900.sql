-- 把 user_notification_settings 默认 quiet_hours_end 从 08:30 改到 09:00。
-- 目的: 默认保护早晨 7 点和 8 点左右的睡眠时间, 普通推送 09:00 后再发。
-- 只迁移历史默认值, 不覆盖用户手动设成 06:00/07:30/09:30 等自定义配置。

UPDATE user_notification_settings
SET quiet_hours_end = '09:00'
WHERE quiet_hours_end IN ('07:00', '08:30');

ALTER TABLE user_notification_settings
    ALTER COLUMN quiet_hours_end SET DEFAULT '09:00';
