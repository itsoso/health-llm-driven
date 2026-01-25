-- 添加 Garmin 登录锁定字段
-- 用于防止频繁登录失败导致 Garmin 账号被锁定

ALTER TABLE garmin_credentials ADD COLUMN IF NOT EXISTS login_locked_until TIMESTAMP WITH TIME ZONE;

-- 添加注释
COMMENT ON COLUMN garmin_credentials.login_locked_until IS '登录锁定截止时间，在此时间之前不允许尝试登录';
