-- user_profiles 加锻炼时点偏好(timing-solver cut 7,sqlite 变体)。
-- sqlite 的 ADD COLUMN 无 IF NOT EXISTS;managed runner 按文件名记录已应用、只跑一次。
-- 测试库由 Base.metadata.create_all 直接带列,不走本迁移。
ALTER TABLE user_profiles ADD COLUMN workout_pref_window VARCHAR(20);
ALTER TABLE user_profiles ADD COLUMN workout_target_minutes INTEGER;
