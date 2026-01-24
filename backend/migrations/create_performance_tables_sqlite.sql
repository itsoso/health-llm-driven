-- 性能监控表迁移脚本 (SQLite 版本)
-- 创建时间: 2026-01-24

-- 1. 创建性能指标表
CREATE TABLE IF NOT EXISTS performance_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    session_id VARCHAR(100) NOT NULL,
    platform VARCHAR(20) NOT NULL CHECK(platform IN ('mini_program', 'web', 'h5', 'app')),
    metric_type VARCHAR(20) NOT NULL CHECK(metric_type IN ('page_load', 'api_call', 'render', 'interaction', 'error')),
    metric_name VARCHAR(200) NOT NULL,
    duration REAL NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    details TEXT,
    metadata TEXT,
    success INTEGER DEFAULT 1,
    error_message VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- 2. 创建索引
CREATE INDEX IF NOT EXISTS idx_perf_user_id ON performance_metrics(user_id);
CREATE INDEX IF NOT EXISTS idx_perf_session_id ON performance_metrics(session_id);
CREATE INDEX IF NOT EXISTS idx_perf_platform ON performance_metrics(platform);
CREATE INDEX IF NOT EXISTS idx_perf_metric_type ON performance_metrics(metric_type);
CREATE INDEX IF NOT EXISTS idx_perf_metric_name ON performance_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_perf_created_at ON performance_metrics(created_at);
CREATE INDEX IF NOT EXISTS idx_perf_platform_metric_created ON performance_metrics(platform, metric_type, created_at);
CREATE INDEX IF NOT EXISTS idx_perf_metric_name_created ON performance_metrics(metric_name, created_at);
CREATE INDEX IF NOT EXISTS idx_perf_user_created ON performance_metrics(user_id, created_at);

-- 3. 创建性能告警表
CREATE TABLE IF NOT EXISTS performance_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK(severity IN ('low', 'medium', 'high', 'critical')),
    platform VARCHAR(20) NOT NULL CHECK(platform IN ('mini_program', 'web', 'h5', 'app')),
    metric_name VARCHAR(200) NOT NULL,
    metric_value REAL NOT NULL,
    threshold REAL NOT NULL,
    description VARCHAR(500) NOT NULL,
    details TEXT,
    status VARCHAR(20) DEFAULT 'open' CHECK(status IN ('open', 'acknowledged', 'resolved', 'ignored')),
    resolved_at TIMESTAMP,
    resolved_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (resolved_by) REFERENCES users(id) ON DELETE SET NULL
);

-- 4. 创建告警表索引
CREATE INDEX IF NOT EXISTS idx_alert_platform ON performance_alerts(platform);
CREATE INDEX IF NOT EXISTS idx_alert_status ON performance_alerts(status);
CREATE INDEX IF NOT EXISTS idx_alert_severity ON performance_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alert_created_at ON performance_alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_alert_metric_name ON performance_alerts(metric_name);

-- 5. 创建性能汇总表
CREATE TABLE IF NOT EXISTS performance_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform VARCHAR(20) NOT NULL CHECK(platform IN ('mini_program', 'web', 'h5', 'app')),
    metric_type VARCHAR(20) NOT NULL CHECK(metric_type IN ('page_load', 'api_call', 'render', 'interaction', 'error')),
    metric_name VARCHAR(200) NOT NULL,
    date DATE NOT NULL,
    hour INTEGER,
    total_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    avg_duration REAL,
    min_duration REAL,
    max_duration REAL,
    p50_duration REAL,
    p90_duration REAL,
    p95_duration REAL,
    p99_duration REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- 6. 创建汇总表索引
CREATE INDEX IF NOT EXISTS idx_summary_platform ON performance_summaries(platform);
CREATE INDEX IF NOT EXISTS idx_summary_metric_type ON performance_summaries(metric_type);
CREATE INDEX IF NOT EXISTS idx_summary_metric_name ON performance_summaries(metric_name);
CREATE INDEX IF NOT EXISTS idx_summary_date ON performance_summaries(date);
CREATE INDEX IF NOT EXISTS idx_summary_hour ON performance_summaries(hour);
CREATE INDEX IF NOT EXISTS idx_summary_platform_date ON performance_summaries(platform, date);
CREATE INDEX IF NOT EXISTS idx_summary_metric_date ON performance_summaries(metric_name, date);

-- 7. 创建触发器（更新 updated_at）
CREATE TRIGGER IF NOT EXISTS update_performance_alerts_updated_at
AFTER UPDATE ON performance_alerts
FOR EACH ROW
BEGIN
    UPDATE performance_alerts SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS update_performance_summaries_updated_at
AFTER UPDATE ON performance_summaries
FOR EACH ROW
BEGIN
    UPDATE performance_summaries SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
