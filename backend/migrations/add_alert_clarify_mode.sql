-- L9 (Karpathy partial autonomy): 告警反应方式自治档位
--
-- 三档:
--   silent   只写 alerts tab, 不推送
--   notify   推送, deep_link 跳 trace 详情页
--   converse 推送 + voice-chat 主动开口对话 (默认, 现状)
--
-- 默认 'converse' = 老用户保持现状, 无副作用.

ALTER TABLE user_notification_settings
  ADD COLUMN IF NOT EXISTS alert_clarify_mode VARCHAR(20) DEFAULT 'converse';
