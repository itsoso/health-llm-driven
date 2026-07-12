UPDATE user_notification_settings
SET
    morning_briefing_time = CASE
        WHEN morning_briefing_time < '09:00' THEN '09:00'
        ELSE morning_briefing_time
    END,
    quiet_hours_end = CASE
        WHEN quiet_hours_end < '09:00' THEN '09:00'
        ELSE quiet_hours_end
    END
WHERE
    morning_briefing_time < '09:00'
    OR quiet_hours_end < '09:00';

ALTER TABLE user_notification_settings
    ALTER COLUMN morning_briefing_time SET DEFAULT '09:00';

ALTER TABLE user_notification_settings
    ALTER COLUMN quiet_hours_end SET DEFAULT '09:00';
