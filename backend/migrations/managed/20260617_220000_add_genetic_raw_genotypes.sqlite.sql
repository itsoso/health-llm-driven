-- sqlite test fixture mirror — 见 .postgresql.sql 注释。
-- SQLite 不支持 ADD COLUMN IF NOT EXISTS, 但 runner 用 schema_migrations 记录已应用,
-- 每个迁移只跑一次, 测试库每次 in-memory 全新, 不会撞到重复列。
-- 加密后的全量 {rsid:genotype} JSON 落 raw_genotypes (应用层 EncryptedText/Fernet 加密)。
ALTER TABLE genetic_import_jobs ADD COLUMN raw_genotypes TEXT;
