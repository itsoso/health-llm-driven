-- genetic_import_jobs 加 raw_genotypes 列, 存加密后的全量 {rsid:genotype} JSON
-- (应用层经 EncryptedText/Fernet 加密后才写入, 库里只见密文, 绝不明文)。
-- 用途: 支持任意基因(含白名单外)查询 + 白名单扩展后无需重传即可重解析。
-- 最高隐私级字段。注 runner 按裸分号切语句, 注释里不能出现分号。幂等可重跑。
ALTER TABLE genetic_import_jobs ADD COLUMN IF NOT EXISTS raw_genotypes TEXT;
