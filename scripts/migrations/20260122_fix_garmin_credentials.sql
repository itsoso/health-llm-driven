-- 修复 garmin_credentials 表结构
-- 日期: 2026-01-22
-- 描述: 修复字段名不匹配和添加缺失字段
-- 问题: column garmin_credentials.garmin_email does not exist

BEGIN;

-- 1. 重命名字段（如果存在）
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'garmin_credentials' 
        AND column_name = 'email'
    ) THEN
        ALTER TABLE garmin_credentials RENAME COLUMN email TO garmin_email;
        RAISE NOTICE 'Renamed column email to garmin_email';
    END IF;
END $$;

-- 2. 添加缺失字段
ALTER TABLE garmin_credentials 
ADD COLUMN IF NOT EXISTS is_cn BOOLEAN DEFAULT FALSE;

ALTER TABLE garmin_credentials 
ADD COLUMN IF NOT EXISTS sync_enabled BOOLEAN DEFAULT TRUE;

ALTER TABLE garmin_credentials 
ADD COLUMN IF NOT EXISTS credentials_valid BOOLEAN DEFAULT TRUE;

ALTER TABLE garmin_credentials 
ADD COLUMN IF NOT EXISTS requires_mfa BOOLEAN DEFAULT FALSE;

ALTER TABLE garmin_credentials 
ADD COLUMN IF NOT EXISTS last_error TEXT;

ALTER TABLE garmin_credentials 
ADD COLUMN IF NOT EXISTS error_count INTEGER DEFAULT 0;

-- 3. 删除多余字段（如果存在）
ALTER TABLE garmin_credentials 
DROP COLUMN IF EXISTS is_active;

-- 4. 验证表结构
DO $$
DECLARE
    column_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO column_count
    FROM information_schema.columns 
    WHERE table_name = 'garmin_credentials';
    
    RAISE NOTICE 'garmin_credentials table now has % columns', column_count;
END $$;

COMMIT;

-- 验证迁移结果
SELECT 
    column_name, 
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns 
WHERE table_name = 'garmin_credentials' 
ORDER BY ordinal_position;
