-- 2026-04-25  给 diet_records 增加显式酒精字段
-- 原因：rule_alcohol 依赖 food_items 字符串匹配，用户周二饮酒没被抓到
-- 有了显式字段后，mobile/MealForm 可独立录入，不依赖食物描述

ALTER TABLE diet_records
ADD COLUMN IF NOT EXISTS alcohol_units FLOAT;

COMMENT ON COLUMN diet_records.alcohol_units IS
    '酒精标准杯数。1 unit ≈ 14g 纯酒精 ≈ 1 瓶 330ml 啤酒 ≈ 150ml 红酒 ≈ 45ml 白酒';
