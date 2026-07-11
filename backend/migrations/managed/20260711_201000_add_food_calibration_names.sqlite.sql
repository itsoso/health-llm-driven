ALTER TABLE food_items
ADD COLUMN calibration_names JSON NOT NULL DEFAULT '[]';

UPDATE food_items
SET calibration_names = CASE food_id
    WHEN 'cfc:chicken_breast' THEN '["鸡胸肉", "鸡胸", "鸡胸肉熟"]'
    WHEN 'cfc:white_rice_cooked' THEN '["米饭", "白米饭", "熟米饭", "大米饭"]'
    WHEN 'cfc:egg_boiled' THEN '["水煮蛋", "煮鸡蛋", "白煮蛋"]'
    WHEN 'cfc:banana' THEN '["香蕉", "香蕉肉"]'
    WHEN 'cfc:tofu_firm' THEN '["北豆腐", "老豆腐"]'
    WHEN 'cfc:broccoli_cooked' THEN '["西兰花", "熟西兰花", "西蓝花"]'
    ELSE calibration_names
END;
