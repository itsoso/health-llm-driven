ALTER TABLE aigc_media_jobs
    ADD CONSTRAINT uq_aigc_media_jobs_user_fingerprint
    UNIQUE (user_id, request_fingerprint);
