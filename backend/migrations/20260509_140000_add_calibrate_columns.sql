-- Iter 2 Day 6-7: Calibrate UI — 给 medical_exam_items 加 OCR 来源标记 + 手工校正轨迹.
--
-- source: 'manual' / 'ocr' / 'pdf' / 'csv' / 'json'
-- manually_corrected_at: 用户最近一次手工改值的时间
-- original_value / original_value_text: 第一次落库时的原值, 校正后保留作回溯

ALTER TABLE medical_exam_items
    ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'manual';

ALTER TABLE medical_exam_items
    ADD COLUMN IF NOT EXISTS manually_corrected_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE medical_exam_items
    ADD COLUMN IF NOT EXISTS original_value DOUBLE PRECISION;

ALTER TABLE medical_exam_items
    ADD COLUMN IF NOT EXISTS original_value_text TEXT;

-- 历史数据按 medical_exams.notes 推断: notes 含 "OCR" → source='ocr', 否则 'manual'
UPDATE medical_exam_items mei
SET source = 'ocr'
FROM medical_exams me
WHERE mei.exam_id = me.id
  AND me.notes IS NOT NULL
  AND me.notes ILIKE '%OCR%'
  AND mei.source = 'manual';
