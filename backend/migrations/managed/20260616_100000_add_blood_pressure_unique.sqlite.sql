-- SQLite 等价 (测试库)。SQLite 唯一索引同样把每个 NULL 视为不同值,
-- 历史 measured_at=NULL 行不被阻断, 仅对带 measured_at 的点事件去重。
CREATE UNIQUE INDEX IF NOT EXISTS uq_bp_user_measured
    ON blood_pressure_records (user_id, measured_at);
