-- 把 user_notification_settings 默认 quiet_hours_end 从 07:00 改到 08:30
-- 原因: 23:00-07:00 对 08:xx 起床的用户, HIGH/MEDIUM 告警在 07-08 之间会吵醒.
-- 改动: 所有仍在默认值 '07:00' 的行, 统一迁移到 '08:30'.
-- 自定义过时间的用户不动.
--
-- 兼容: 本项目未采用 alembic, 手动 psql 执行.

BEGIN;

UPDATE user_notification_settings
SET quiet_hours_end = '08:30'
WHERE quiet_hours_end = '07:00';

-- 同步调整 ALTER COLUMN DEFAULT, 让 PostgreSQL 层的 server-side default
-- 和 ORM 的 default='08:30' 保持一致 (避免未来 raw INSERT 绕过 ORM 时回到旧默认).
ALTER TABLE user_notification_settings
    ALTER COLUMN quiet_hours_end SET DEFAULT '08:30';

COMMIT;
