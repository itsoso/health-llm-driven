ALTER TABLE food_items
ADD COLUMN IF NOT EXISTS calibration_names JSONB NOT NULL DEFAULT '[]'::jsonb;

UPDATE food_items
SET calibration_names = CASE food_id
    WHEN 'cfc:chicken_breast' THEN '["鸡胸肉", "鸡胸", "鸡胸肉熟"]'::jsonb
    WHEN 'cfc:white_rice_cooked' THEN '["米饭", "白米饭", "熟米饭", "大米饭"]'::jsonb
    WHEN 'cfc:egg_boiled' THEN '["水煮蛋", "煮鸡蛋", "白煮蛋"]'::jsonb
    WHEN 'cfc:banana' THEN '["香蕉", "香蕉肉"]'::jsonb
    WHEN 'cfc:tofu_firm' THEN '["北豆腐", "老豆腐"]'::jsonb
    WHEN 'cfc:broccoli_cooked' THEN '["西兰花", "熟西兰花", "西蓝花"]'::jsonb
    ELSE calibration_names
END;
