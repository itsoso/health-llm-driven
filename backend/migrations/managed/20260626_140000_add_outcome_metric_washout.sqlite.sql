-- R16 P3: 跨周期洗脱期归因(SQLite:测试 fixture 走 create_all,本文件仅 prod 形态对齐)。
ALTER TABLE outcome_metrics ADD COLUMN attribution_state VARCHAR(16);
ALTER TABLE outcome_metrics ADD COLUMN washout_until DATE;
