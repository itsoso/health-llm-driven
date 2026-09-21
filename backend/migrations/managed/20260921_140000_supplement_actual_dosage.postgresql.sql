ALTER TABLE supplement_records
    ADD COLUMN IF NOT EXISTS actual_dosage VARCHAR(40);
