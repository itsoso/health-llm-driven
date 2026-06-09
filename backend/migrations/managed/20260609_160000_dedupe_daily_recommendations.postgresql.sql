-- daily_recommendations 去重 + 补回模型声明但 prod 缺失的唯一约束。
--
-- 模型 __table_args__ 声明 idx_daily_rec_user_rec_date UNIQUE(user_id, recommendation_date),
-- 但手写迁移建表时漏建,导致同一天同用户累积重复日推(实测多余 49 行)。
-- 先删每组非最新行(保留 max(id) 即最近生成的一条),再建唯一索引。
--
-- 注 runner 按裸分号切分语句,注释里不能出现分号(踩过)。幂等可重跑。
DELETE FROM daily_recommendations a
    USING daily_recommendations b
    WHERE a.user_id = b.user_id
      AND a.recommendation_date = b.recommendation_date
      AND a.id < b.id;
CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_rec_user_rec_date
    ON daily_recommendations (user_id, recommendation_date);
