-- 2026-05-12: 加 evidence_level 标识每张卡的证据等级.
--
-- 取值约定:
--   high            — 强证据 (CPIC pharmacogenomics, Garmin/Withings 实测异常,
--                     >100 RCT 共识 e.g. MTHFR-叶酸代谢)
--   medium          — 中等证据 (单项临床, 小样本, 关联但因果未定)
--   low             — 弱证据 (理论假设, 单一研究, 跨族群泛化弱)
--   medical_grade   — 高医疗风险, 必须医生介入 (用药调整, 遗传病, 急性指标)
--   NULL            — 历史卡未标 (mobile UI 不显示 chip)

ALTER TABLE action_cards
    ADD COLUMN IF NOT EXISTS evidence_level VARCHAR(20);
