-- 主健康目标 (Onboarding step 5, 2026-05-14)
-- 取值: weight_loss / glucose / blood_pressure / sleep / hrv / rhinitis / general
-- NULL = 没填

ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS primary_goal VARCHAR(40);
