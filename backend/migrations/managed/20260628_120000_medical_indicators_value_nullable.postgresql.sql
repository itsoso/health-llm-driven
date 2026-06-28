-- medical_indicators.value 去除 NOT NULL 约束。
-- 模型 family_health.py:55 早已 `value = Column(Float, nullable=True)`(影像/尿常规/耳鼻喉等
-- 纯文字结果走 value_text,value 为空),但 prod DB 该列仍是 NOT NULL(建表早于模型改动 →
-- schema 漂移)→ 体检报告含纯文字项时整批 INSERT 撞 NotNullViolation,导入失败。
-- DROP NOT NULL 对已 nullable 列是幂等 no-op,安全可重跑。
ALTER TABLE medical_indicators ALTER COLUMN value DROP NOT NULL;
