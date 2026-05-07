-- 2026-05-07: notification_logs.channels JSON (单 row 汇总多通道)
-- 之前 per-channel 各写一行, 导致推送历史显示"3条重复"错觉
ALTER TABLE notification_logs
    ADD COLUMN IF NOT EXISTS channels JSON;
