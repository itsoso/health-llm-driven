-- #67 follow-up of #66: 把 plan_items.title 里的天气前缀抽成结构化 tag,
-- 推送时用 tag 比对实际天气, 不再用前缀 string 重新猜.
--
-- 'rain' / 'snow' / 'sun' / 'fog' / 'wind' / 'thunder', 没前缀就 NULL

ALTER TABLE plan_items
    ADD COLUMN IF NOT EXISTS weather_condition_tag VARCHAR(20);

-- 历史数据回填: 按已知前缀映射. 与 app/utils/weather_tag.py _TAG_PREFIXES 对齐.
UPDATE plan_items SET weather_condition_tag = 'rain'
    WHERE weather_condition_tag IS NULL
      AND (title LIKE '雷雨日%' OR title LIKE '阴雨日%' OR title LIKE '下雨日%' OR title LIKE '雨天%');

UPDATE plan_items SET weather_condition_tag = 'snow'
    WHERE weather_condition_tag IS NULL
      AND (title LIKE '下雪日%' OR title LIKE '雪天%');

UPDATE plan_items SET weather_condition_tag = 'sun'
    WHERE weather_condition_tag IS NULL
      AND (title LIKE '大晴天%' OR title LIKE '晴天%');

UPDATE plan_items SET weather_condition_tag = 'fog'
    WHERE weather_condition_tag IS NULL
      AND (title LIKE '雾霾日%' OR title LIKE '雾天%');

UPDATE plan_items SET weather_condition_tag = 'wind'
    WHERE weather_condition_tag IS NULL
      AND title LIKE '大风日%';

UPDATE plan_items SET weather_condition_tag = 'thunder'
    WHERE weather_condition_tag IS NULL
      AND title LIKE '雷暴日%';
