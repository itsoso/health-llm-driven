-- R16 P2: 干预结局端点去噪溯源(SQLite:测试 fixture 走 create_all,本文件仅 prod 形态对齐)。
-- SQLite 不支持 ADD COLUMN IF NOT EXISTS;迁移运行器对已存在列报错可忽略(测试不跑本文件)。
ALTER TABLE outcome_metrics ADD COLUMN smoothing_method VARCHAR(12);
ALTER TABLE outcome_metrics ADD COLUMN sample_n INTEGER;
