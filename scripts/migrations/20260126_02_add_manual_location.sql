-- 迁移: 添加手工输入位置功能
-- 日期: 2026-01-26
-- 描述: 允许用户选择手工指定位置或使用IP定位

-- 1. 添加手工位置字段
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS manual_city VARCHAR(100);
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS manual_region VARCHAR(100);
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS manual_country VARCHAR(100);

-- 2. 添加位置模式选择字段 (true=手工输入, false=IP定位)
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS use_manual_location BOOLEAN DEFAULT false;

-- 3. 添加注释
COMMENT ON COLUMN user_profiles.manual_city IS '手工输入的城市';
COMMENT ON COLUMN user_profiles.manual_region IS '手工输入的省份/地区';
COMMENT ON COLUMN user_profiles.manual_country IS '手工输入的国家';
COMMENT ON COLUMN user_profiles.use_manual_location IS '是否使用手工输入的位置(true)或IP定位(false)';
