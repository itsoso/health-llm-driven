UPDATE user_notification_settings
SET quiet_hours_end = '09:00'
WHERE quiet_hours_end IN ('07:00', '08:30');
