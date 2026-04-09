-- 为 genetic_variants 添加 variant_nature 字段，区分优势基因/风险基因/中性基因
ALTER TABLE genetic_variants ADD COLUMN IF NOT EXISTS variant_nature VARCHAR(20) DEFAULT 'neutral';

-- 批量更新已知基因的 variant_nature
-- 优势基因（protective）
UPDATE genetic_variants SET variant_nature = 'protective' WHERE gene_name = 'FADS1' AND genotype = 'TT';
UPDATE genetic_variants SET variant_nature = 'protective' WHERE gene_name = 'SOD2' AND genotype = 'AA';
UPDATE genetic_variants SET variant_nature = 'protective' WHERE gene_name = 'APOE' AND genotype = 'E3/E3';

-- 中性/正常基因
UPDATE genetic_variants SET variant_nature = 'neutral' WHERE gene_name = 'GPX1' AND genotype = 'GG';
UPDATE genetic_variants SET variant_nature = 'neutral' WHERE gene_name = 'VDR' AND genotype = 'CC';

-- 风险基因（risk）— 用药安全优先
UPDATE genetic_variants SET variant_nature = 'risk' WHERE gene_name = 'CYP2D6' AND risk_level IN ('high', 'medium');
UPDATE genetic_variants SET variant_nature = 'risk' WHERE gene_name = 'SLCO1B1' AND genotype = 'CT';
UPDATE genetic_variants SET variant_nature = 'risk' WHERE gene_name = 'MTHFR' AND genotype = 'TT';
UPDATE genetic_variants SET variant_nature = 'risk' WHERE gene_name = '9p21' AND genotype = 'AA';
UPDATE genetic_variants SET variant_nature = 'risk' WHERE gene_name = 'KCNJ11' AND genotype = 'TT';
UPDATE genetic_variants SET variant_nature = 'risk' WHERE gene_name = 'NQO1' AND genotype IN ('AG', 'GG');
UPDATE genetic_variants SET variant_nature = 'risk' WHERE gene_name = 'XRCC1' AND genotype = 'CT';
UPDATE genetic_variants SET variant_nature = 'risk' WHERE gene_name = 'TP53' AND genotype = 'CC';
UPDATE genetic_variants SET variant_nature = 'risk' WHERE gene_name = 'ADD1' AND genotype = 'TT';
UPDATE genetic_variants SET variant_nature = 'risk' WHERE gene_name = 'TERT' AND genotype = 'CC';
