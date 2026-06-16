-- 血压点事件幂等: (user_id, measured_at) 唯一, 让 HealthKit 重复上送幂等 (与 ECG 同范式)。
-- 血压一天多次、是点事件, 按测量时刻去重而非按日聚合 (避免同日多次互相覆盖)。
-- 注 runner 按裸分号切分, 注释里不能有分号。
-- 旧数据 measured_at 可能为 NULL (手动录入未带时刻)。唯一约束在 PG 下允许多个 NULL,
-- 故历史 NULL 行不会被该约束阻断, 仅对带 measured_at 的点事件去重。
CREATE UNIQUE INDEX IF NOT EXISTS uq_bp_user_measured
    ON blood_pressure_records (user_id, measured_at);
