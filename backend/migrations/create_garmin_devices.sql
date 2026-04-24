-- Garmin Devices: 用户的 Garmin 设备电量 / 最后同步 / 佩戴时长
-- 来源：garminconnect.get_devices()
-- 用于区分"HRV=0 是真低"还是"没戴表"，也供"设备 48h 未同步"提醒使用

CREATE TABLE IF NOT EXISTS garmin_devices (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id VARCHAR(80) NOT NULL,
    unit_id VARCHAR(80),
    product_number VARCHAR(80),
    model VARCHAR(120),
    display_name VARCHAR(120),
    image_url VARCHAR(500),
    last_sync_time TIMESTAMP WITH TIME ZONE,
    last_used_time TIMESTAMP WITH TIME ZONE,
    battery_level INTEGER,
    battery_status VARCHAR(32),
    firmware_version VARCHAR(64),
    is_primary BOOLEAN DEFAULT FALSE,
    raw_payload JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_garmin_devices_user ON garmin_devices(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_garmin_devices_user_device
    ON garmin_devices(user_id, device_id);

COMMENT ON TABLE garmin_devices IS 'Garmin 设备电量/同步/佩戴信息，用于数据完整性与佩戴规则';
