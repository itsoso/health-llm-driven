-- 添加推送通知相关表
-- 用于支持微信小程序订阅消息和 iOS APNs 推送

-- 用户推送设置表
CREATE TABLE IF NOT EXISTS user_notification_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,

    -- 推送开关
    enabled BOOLEAN DEFAULT 1,
    morning_briefing_enabled BOOLEAN DEFAULT 1,
    reminder_enabled BOOLEAN DEFAULT 1,
    health_alert_enabled BOOLEAN DEFAULT 1,
    ai_advice_enabled BOOLEAN DEFAULT 1,

    -- 推送时间设置
    morning_briefing_time VARCHAR(5) DEFAULT '07:30',
    quiet_hours_start VARCHAR(5) DEFAULT '22:00',
    quiet_hours_end VARCHAR(5) DEFAULT '07:00',

    -- 渠道设置
    wechat_enabled BOOLEAN DEFAULT 1,
    ios_push_enabled BOOLEAN DEFAULT 1,

    -- 微信小程序设置
    wechat_openid VARCHAR(100),
    wechat_template_ids TEXT,  -- JSON 格式

    -- iOS 推送设置
    ios_device_token VARCHAR(200),

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,

    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 推送日志表
CREATE TABLE IF NOT EXISTS notification_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,

    -- 通知内容
    notification_type VARCHAR(50) NOT NULL,
    channel VARCHAR(20) NOT NULL,
    title VARCHAR(200) NOT NULL,
    content TEXT,
    data TEXT,  -- JSON 格式

    -- 状态
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,

    -- 时间
    scheduled_at DATETIME,
    sent_at DATETIME,
    delivered_at DATETIME,
    read_at DATETIME,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 提醒配置表
CREATE TABLE IF NOT EXISTS reminder_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,

    -- 提醒类型
    reminder_type VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,

    -- 提醒时间
    reminder_times TEXT NOT NULL,  -- JSON 数组 ["07:30", "19:00"]
    days_of_week TEXT DEFAULT '[1,2,3,4,5,6,7]',  -- JSON 数组

    -- 提醒内容
    message TEXT,

    -- 状态
    enabled BOOLEAN DEFAULT 1,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,

    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_notification_logs_user ON notification_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_notification_logs_type ON notification_logs(notification_type);
CREATE INDEX IF NOT EXISTS idx_notification_logs_created ON notification_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_reminder_configs_user ON reminder_configs(user_id);
