-- Write 自治层每用户每日执行计数(autonomy_daily_counters)—— 每日上限的硬保证。
-- 单行 (user_id, day) 复合主键,write_autonomy 用原子 UPDATE count=count+1 WHERE count<CAP
-- 把"检查 + 自增"做成一次原子操作(行锁串行化并发预留),封掉 cap-TOCTOU(两个并发请求
-- 各算 budget 各执行至多 2×CAP)。注 runner 按裸分号切分语句,注释里不能出现分号。幂等可重跑。
CREATE TABLE IF NOT EXISTS autonomy_daily_counters (
    user_id INTEGER NOT NULL,
    day DATE NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, day)
);
