-- 性能监控表迁移脚本
-- 创建时间: 2026-01-23

-- 1. 创建平台类型枚举
CREATE TYPE platform_type AS ENUM ('mini_program', 'web', 'h5', 'app');

-- 2. 创建指标类型枚举
CREATE TYPE metric_type AS ENUM ('page_load', 'api_call', 'render', 'interaction', 'error');

-- 3. 创建性能指标表
CREATE TABLE IF NOT EXISTS performance_metrics (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    session_id VARCHAR(100) NOT NULL,
    platform platform_type NOT NULL,
    metric_type metric_type NOT NULL,
    metric_name VARCHAR(200) NOT NULL,
    duration FLOAT NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    details JSONB,
    metadata JSONB,
    success INTEGER DEFAULT 1,
    error_message VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- 4. 创建索引
CREATE INDEX idx_perf_user_id ON performance_metrics(user_id);
CREATE INDEX idx_perf_session_id ON performance_metrics(session_id);
CREATE INDEX idx_perf_platform ON performance_metrics(platform);
CREATE INDEX idx_perf_metric_type ON performance_metrics(metric_type);
CREATE INDEX idx_perf_metric_name ON performance_metrics(metric_name);
CREATE INDEX idx_perf_created_at ON performance_metrics(created_at);
CREATE INDEX idx_perf_platform_metric_created ON performance_metrics(platform, metric_type, created_at);
CREATE INDEX idx_perf_metric_name_created ON performance_metrics(metric_name, created_at);
CREATE INDEX idx_perf_user_created ON performance_metrics(user_id, created_at);

-- 5. 创建性能告警表
CREATE TABLE IF NOT EXISTS performance_alerts (
    id SERIAL PRIMARY KEY,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    platform platform_type NOT NULL,
    metric_name VARCHAR(200) NOT NULL,
    metric_value FLOAT NOT NULL,
    threshold FLOAT NOT NULL,
    description VARCHAR(500) NOT NULL,
    details JSONB,
    status VARCHAR(20) DEFAULT 'open',
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. 创建告警表索引
CREATE INDEX idx_alert_type ON performance_alerts(alert_type);
CREATE INDEX idx_alert_status ON performance_alerts(status);
CREATE INDEX idx_alert_created_at ON performance_alerts(created_at);

-- 7. 创建性能摘要表
CREATE TABLE IF NOT EXISTS performance_summaries (
    id SERIAL PRIMARY KEY,
    platform platform_type NOT NULL,
    metric_type metric_type NOT NULL,
    metric_name VARCHAR(200) NOT NULL,
    period_type VARCHAR(20) NOT NULL,
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    total_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    avg_duration FLOAT DEFAULT 0,
    min_duration FLOAT DEFAULT 0,
    max_duration FLOAT DEFAULT 0,
    p50_duration FLOAT DEFAULT 0,
    p90_duration FLOAT DEFAULT 0,
    p95_duration FLOAT DEFAULT 0,
    p99_duration FLOAT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. 创建摘要表索引
CREATE INDEX idx_summary_platform ON performance_summaries(platform);
CREATE INDEX idx_summary_metric_name ON performance_summaries(metric_name);
CREATE INDEX idx_summary_period_start ON performance_summaries(period_start);
CREATE INDEX idx_summary_platform_period ON performance_summaries(platform, period_type, period_start);
CREATE INDEX idx_summary_metric_period ON performance_summaries(metric_name, period_start);

-- 9. 创建自动更新 updated_at 的触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_performance_alerts_updated_at BEFORE UPDATE
    ON performance_alerts FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_performance_summaries_updated_at BEFORE UPDATE
    ON performance_summaries FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 10. 添加表注释
COMMENT ON TABLE performance_metrics IS '性能指标记录表';
COMMENT ON TABLE performance_alerts IS '性能告警记录表';
COMMENT ON TABLE performance_summaries IS '性能摘要表（按小时/天聚合）';

COMMENT ON COLUMN performance_metrics.session_id IS '会话ID，用于关联同一会话的多个指标';
COMMENT ON COLUMN performance_metrics.duration IS '耗时（毫秒）';
COMMENT ON COLUMN performance_metrics.details IS '详细信息（如分批加载时间、缓存命中等）';
COMMENT ON COLUMN performance_metrics.metadata IS '元数据（如设备信息、网络状态等）';

-- 完成
SELECT 'Performance monitoring tables created successfully!' AS status;
