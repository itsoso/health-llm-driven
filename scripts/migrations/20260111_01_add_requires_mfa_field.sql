-- 为 garmin_credentials 表添加 requires_mfa 字段
-- 用于标识需要两步验证（MFA）的用户，后台自动同步任务会跳过这些用户

ALTER TABLE garmin_credentials ADD COLUMN requires_mfa BOOLEAN DEFAULT 0;
