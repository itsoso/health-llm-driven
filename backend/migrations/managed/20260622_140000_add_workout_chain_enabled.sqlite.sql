-- P4 锻炼链 opt-in 开关:user_profiles.workout_chain_enabled(sqlite 变体)。
-- sqlite 的 ADD COLUMN 无 IF NOT EXISTS;managed runner 按文件名记录已应用、只跑一次。
-- 测试库由 Base.metadata.create_all 直接带列,不走本迁移。
ALTER TABLE user_profiles ADD COLUMN workout_chain_enabled BOOLEAN;
