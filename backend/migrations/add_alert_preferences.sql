-- H1-B: Push 规则分级 + 用户偏好
--
-- 新增两列:
--   alert_severity_threshold: 白天告警的严重度阈值 (info/warning/critical). 低于此级别的 health_alert 不推.
--   alert_rule_opt_outs: JSONB 数组, 用户 mute 过的 rule_id 列表. 命中的 health_alert 不推.
--
-- 默认值 warning + [] = 现有行为 (info 被过滤; 其余照旧). 对现有用户无副作用.

ALTER TABLE user_notification_settings
  ADD COLUMN IF NOT EXISTS alert_severity_threshold VARCHAR(20) DEFAULT 'warning';

ALTER TABLE user_notification_settings
  ADD COLUMN IF NOT EXISTS alert_rule_opt_outs JSONB DEFAULT '[]'::jsonb;

-- SQLite 测试环境靠 SQLAlchemy create_all 自动建表, 不走本 SQL. 这里仅管 PostgreSQL prod.
