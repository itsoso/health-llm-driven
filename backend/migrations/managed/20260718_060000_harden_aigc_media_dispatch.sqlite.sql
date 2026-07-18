CREATE UNIQUE INDEX IF NOT EXISTS uq_aigc_media_jobs_user_fingerprint
    ON aigc_media_jobs (user_id, request_fingerprint);
