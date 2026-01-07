-- 迁移: 创建心率采样表
-- 日期: 2026-01-06
-- 说明: 用于存储详细心率时间序列数据，支持心率曲线图表

CREATE TABLE IF NOT EXISTS heart_rate_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    sample_date DATE NOT NULL,
    sample_time TIME NOT NULL,
    heart_rate INTEGER NOT NULL,
    source VARCHAR DEFAULT 'garmin',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_heart_rate_samples_user_id ON heart_rate_samples(user_id);
CREATE INDEX IF NOT EXISTS ix_heart_rate_samples_date ON heart_rate_samples(sample_date);

