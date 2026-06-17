-- supplement_records 依从写回幂等(DB 兜底): (supplement_id, record_date) 唯一。
-- 所有写入路径(supplements /records、/records/batch、quick_record、nfc、协议补剂分支)语义
-- 都是「某补剂某天是否已服」的单条 toggle —— 无约束时并发读-改-写落多条 taken, 虚高补剂依从。
-- supplement_id FK 已是用户域, (supplement_id, record_date) 即足够唯一。
-- 脏数据前置: 先删现存重复(保留最新 max(id)), 否则在脏数据上直接建唯一索引会失败。
-- 注 runner 按裸分号切分语句, 注释里不能出现分号。幂等可重跑。
DELETE FROM supplement_records a
    USING supplement_records b
    WHERE a.supplement_id = b.supplement_id
      AND a.record_date = b.record_date
      AND a.id < b.id;
CREATE UNIQUE INDEX IF NOT EXISTS uq_supprec_supp_date
    ON supplement_records (supplement_id, record_date);
