-- SQLite 等价(测试库 create_all 已由模型直接带上 uq_supprec_supp_date, 本文件供裸表 / 生产同形)。
-- SQLite 无 DELETE ... USING 语法, 去重逻辑仅 PG 需要(测试 / 新库不含重复行)。
CREATE UNIQUE INDEX IF NOT EXISTS uq_supprec_supp_date
    ON supplement_records (supplement_id, record_date);
