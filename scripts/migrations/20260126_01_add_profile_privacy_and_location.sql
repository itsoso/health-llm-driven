-- 迁移: 添加用户Profile隐私设置和IP定位字段
-- 日期: 2026-01-26
-- 描述: 为健康数据API增加用户Profile信息支持

-- 1. 添加隐私设置字段 (JSONB格式)
-- 默认所有字段公开: {"weight": true, "height": true, "age": true, "gender": true, "city": true, "location": true}
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS privacy_settings JSONB DEFAULT '{"weight": true, "height": true, "age": true, "gender": true, "city": true, "location": true}';

-- 2. 添加IP定位相关字段
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS detected_city VARCHAR(100);
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS detected_region VARCHAR(100);
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS detected_country VARCHAR(100);
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS location_updated_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS last_ip VARCHAR(45);

-- 3. 添加注释
COMMENT ON COLUMN user_profiles.privacy_settings IS '隐私设置，控制哪些字段对外部API可见';
COMMENT ON COLUMN user_profiles.detected_city IS '基于IP检测的城市';
COMMENT ON COLUMN user_profiles.detected_region IS '基于IP检测的省份/地区';
COMMENT ON COLUMN user_profiles.detected_country IS '基于IP检测的国家';
COMMENT ON COLUMN user_profiles.location_updated_at IS 'IP定位最后更新时间';
COMMENT ON COLUMN user_profiles.last_ip IS '最后检测的IP地址';

-- 4. 为现有记录设置默认隐私设置
UPDATE user_profiles
SET privacy_settings = '{"weight": true, "height": true, "age": true, "gender": true, "city": true, "location": true}'
WHERE privacy_settings IS NULL OR privacy_settings = '{}';
