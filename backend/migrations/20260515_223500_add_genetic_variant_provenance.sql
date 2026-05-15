ALTER TABLE genetic_variants ADD COLUMN IF NOT EXISTS rsid VARCHAR(30);
ALTER TABLE genetic_variants ADD COLUMN IF NOT EXISTS raw_genotype VARCHAR(200);
ALTER TABLE genetic_variants ADD COLUMN IF NOT EXISTS mapping_source VARCHAR(50) DEFAULT 'known_snp';
ALTER TABLE genetic_variants ADD COLUMN IF NOT EXISTS evidence_level VARCHAR(50) DEFAULT 'screening';

CREATE INDEX IF NOT EXISTS ix_genetic_variants_rsid ON genetic_variants(rsid);
