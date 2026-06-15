-- R16: outcome 去噪 — 记录变化是否超噪声(RCV)+ 置信度
ALTER TABLE outcome_metrics ADD COLUMN significant BOOLEAN;
ALTER TABLE outcome_metrics ADD COLUMN confidence VARCHAR(12);
