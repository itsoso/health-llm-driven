-- user_profiles 加锻炼时点偏好:每日时点日程(timing-solver, cut 7)据此在空窗排锻炼块。
-- 向后兼容:旧行两列 NULL = 不排锻炼块(solver 不生成 movement 项)。幂等可重跑。
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS workout_pref_window VARCHAR(20);
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS workout_target_minutes INTEGER;
