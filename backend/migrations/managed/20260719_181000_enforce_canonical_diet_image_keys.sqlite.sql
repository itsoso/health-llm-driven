-- SQLite cannot add a table CHECK constraint in place. Normalize existing
-- rows, then use paired insert/update triggers to enforce the same invariant.
UPDATE diet_records
SET image_url = substr(image_url, 1, instr(image_url, '?') - 1)
WHERE instr(image_url, '?') > 0;

UPDATE diet_photo_drafts
SET image_url = substr(image_url, 1, instr(image_url, '?') - 1)
WHERE instr(image_url, '?') > 0;

CREATE TRIGGER IF NOT EXISTS trg_diet_records_image_url_canonical_insert
BEFORE INSERT ON diet_records
WHEN NEW.image_url IS NOT NULL AND instr(NEW.image_url, '?') > 0
BEGIN
    SELECT RAISE(ABORT, 'diet_records.image_url must be canonical');
END;

CREATE TRIGGER IF NOT EXISTS trg_diet_records_image_url_canonical_update
BEFORE UPDATE OF image_url ON diet_records
WHEN NEW.image_url IS NOT NULL AND instr(NEW.image_url, '?') > 0
BEGIN
    SELECT RAISE(ABORT, 'diet_records.image_url must be canonical');
END;

CREATE TRIGGER IF NOT EXISTS trg_diet_photo_drafts_image_url_canonical_insert
BEFORE INSERT ON diet_photo_drafts
WHEN NEW.image_url IS NOT NULL AND instr(NEW.image_url, '?') > 0
BEGIN
    SELECT RAISE(ABORT, 'diet_photo_drafts.image_url must be canonical');
END;

CREATE TRIGGER IF NOT EXISTS trg_diet_photo_drafts_image_url_canonical_update
BEFORE UPDATE OF image_url ON diet_photo_drafts
WHEN NEW.image_url IS NOT NULL AND instr(NEW.image_url, '?') > 0
BEGIN
    SELECT RAISE(ABORT, 'diet_photo_drafts.image_url must be canonical');
END;
