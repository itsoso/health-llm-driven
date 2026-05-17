ALTER TABLE user_profiles ADD COLUMN detected_source VARCHAR(16);
UPDATE user_profiles SET detected_source = 'gps' WHERE detected_source IS NULL AND detected_lat IS NOT NULL;
UPDATE user_profiles SET detected_source = 'ip'  WHERE detected_source IS NULL AND detected_city IS NOT NULL;
