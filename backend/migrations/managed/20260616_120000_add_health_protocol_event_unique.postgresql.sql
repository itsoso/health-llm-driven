-- health_protocol_events 幂等加固(D1): (protocol_id, event_date) 唯一。
--
-- 本表语义本就是「每协议每天一条终态」。腕上一键完成无 DB 兜底时,并发双击 /
-- bridge 重发 / 重试会让两个 session 都读到 was_completed=False → 同一剂依从落 2 条,
-- 污染 DDI/PGx/SafetyGuardian 的依从推断。配合 complete_protocol 的原子 UPDATE 门
-- (WHERE status != 'completed' 仅 rowcount==1 才落领域记录)兜住并发竞态。
--
-- 脏数据前置:必须先删现存重复 (protocol_id, event_date)(保留最新一条 max(id)),
-- 否则在脏数据上直接建唯一索引会失败。
-- 注 runner 按裸分号切分语句,注释里不能出现分号。幂等可重跑。
DELETE FROM health_protocol_events a
    USING health_protocol_events b
    WHERE a.protocol_id = b.protocol_id
      AND a.event_date = b.event_date
      AND a.id < b.id;
CREATE UNIQUE INDEX IF NOT EXISTS uq_hpe_protocol_date
    ON health_protocol_events (protocol_id, event_date);
-- 旧的非唯一 ix_hpe_protocol_date 与新唯一索引同列,冗余 → 删(模型已不再声明它)。
DROP INDEX IF EXISTS ix_hpe_protocol_date;
