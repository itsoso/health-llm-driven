-- user_profiles 加上/下班时点:每日时点日程(timing-solver)据此让浮动 nudge 避开工作窗。
-- 向后兼容:旧行两列 NULL = 不约束(solver 退化为不避工作窗)。幂等可重跑。
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS work_start_time VARCHAR(10);
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS work_end_time VARCHAR(10);
