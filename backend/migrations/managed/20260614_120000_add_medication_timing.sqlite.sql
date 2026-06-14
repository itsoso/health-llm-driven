-- 用药自动驾驶 P0：给药品加「相对吃饭的服用时点」(sqlite 变体)
-- 向后兼容：旧记录两列为 NULL，渲染时当「无特殊要求」省略时点提示
ALTER TABLE medications ADD COLUMN timing_relation VARCHAR(20);
ALTER TABLE medications ADD COLUMN meal_anchor VARCHAR(10);
