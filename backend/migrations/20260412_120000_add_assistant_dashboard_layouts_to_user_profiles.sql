ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS assistant_dashboard_layouts JSONB NOT NULL DEFAULT
'{
  "web": {"order": [], "hidden": []},
  "mobile": {"order": [], "hidden": []}
}'::jsonb;
