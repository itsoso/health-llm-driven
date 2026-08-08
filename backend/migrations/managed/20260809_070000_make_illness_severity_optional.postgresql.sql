ALTER TABLE illness_episodes
    ALTER COLUMN severity DROP DEFAULT;

ALTER TABLE illness_episodes
    ALTER COLUMN severity DROP NOT NULL;
