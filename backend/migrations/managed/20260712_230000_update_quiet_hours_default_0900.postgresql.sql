UPDATE user_notification_settings
SET quiet_hours_end = '09:00'
WHERE quiet_hours_end IN ('07:00', '08:30');

ALTER TABLE user_notification_settings
    ALTER COLUMN quiet_hours_end SET DEFAULT '09:00';
