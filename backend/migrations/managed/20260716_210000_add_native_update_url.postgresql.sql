ALTER TABLE app_release_policies
    ADD COLUMN IF NOT EXISTS native_update_url VARCHAR(512);
