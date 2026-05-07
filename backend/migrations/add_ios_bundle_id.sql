-- 2026-05-07: variant bundle 机制 — APNs topic per-device
-- 根因: 用户 iPhone 可能装 prod (life.executor.health) 或 dev (.dev),
-- 同一 device_token 只对应一个 bundle. backend 之前硬编码 topic 导致
-- DeviceTokenNotForTopic 拒收.
ALTER TABLE user_notification_settings
    ADD COLUMN IF NOT EXISTS ios_bundle_id VARCHAR(100);
