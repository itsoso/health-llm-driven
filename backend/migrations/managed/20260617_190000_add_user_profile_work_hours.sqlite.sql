-- user_profiles 加上/下班时点(timing-solver 避开工作窗,sqlite 变体)。
-- sqlite 的 ADD COLUMN 无 IF NOT EXISTS;managed runner 按文件名记录已应用、只跑一次。
-- 测试库由 Base.metadata.create_all 直接带列,不走本迁移。
ALTER TABLE user_profiles ADD COLUMN work_start_time VARCHAR(10);
ALTER TABLE user_profiles ADD COLUMN work_end_time VARCHAR(10);
