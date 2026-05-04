-- W3: 跑后教练推送用户开关
--
-- 新增列:
--   workout_analysis_enabled: 是否接收"运动同步后自动分析"的推送. 默认 TRUE = 现有行为.
--
-- 对现有用户无副作用 (默认开).

ALTER TABLE user_notification_settings
  ADD COLUMN IF NOT EXISTS workout_analysis_enabled BOOLEAN DEFAULT TRUE;

-- SQLite 测试环境靠 SQLAlchemy create_all 自动建表, 不走本 SQL. 这里仅管 PostgreSQL prod.
