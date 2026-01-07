-- 迁移: 添加 Garmin 凭证扩展字段
-- 日期: 2026-01-01
-- 说明: 添加中国区标识、凭证状态跟踪等字段

-- 添加中国区标识
ALTER TABLE garmin_credentials ADD COLUMN is_cn BOOLEAN DEFAULT FALSE;

-- 添加凭证验证状态
ALTER TABLE garmin_credentials ADD COLUMN credentials_valid BOOLEAN DEFAULT TRUE;

-- 添加错误信息
ALTER TABLE garmin_credentials ADD COLUMN last_error VARCHAR;

-- 添加错误计数
ALTER TABLE garmin_credentials ADD COLUMN error_count INTEGER DEFAULT 0;

-- 添加同步开关
ALTER TABLE garmin_credentials ADD COLUMN sync_enabled BOOLEAN DEFAULT TRUE;

