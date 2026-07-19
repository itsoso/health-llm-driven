-- Legacy cover fields still participate in new contextual-photo writes.
-- Normalize historic private signed URLs before preventing future persistence.
UPDATE diet_records
SET image_url = split_part(image_url, '?', 1)
WHERE image_url LIKE '%?%';

UPDATE diet_photo_drafts
SET image_url = split_part(image_url, '?', 1)
WHERE image_url LIKE '%?%';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_diet_records_image_url_canonical'
    ) THEN
        ALTER TABLE diet_records
            ADD CONSTRAINT ck_diet_records_image_url_canonical
            CHECK (image_url IS NULL OR image_url NOT LIKE '%?%');
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_diet_photo_drafts_image_url_canonical'
    ) THEN
        ALTER TABLE diet_photo_drafts
            ADD CONSTRAINT ck_diet_photo_drafts_image_url_canonical
            CHECK (image_url IS NULL OR image_url NOT LIKE '%?%');
    END IF;
END $$;
