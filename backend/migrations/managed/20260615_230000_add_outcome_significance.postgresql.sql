-- R16: outcome 去噪 — 记录变化是否超噪声(RCV)+ 置信度
ALTER TABLE outcome_metrics
ADD COLUMN IF NOT EXISTS significant BOOLEAN;
ALTER TABLE outcome_metrics
ADD COLUMN IF NOT EXISTS confidence VARCHAR(12);
