-- Persist the legacy weather tag schema change through the managed runner.
ALTER TABLE plan_items ADD COLUMN IF NOT EXISTS weather_condition_tag VARCHAR(20);

-- Keep this backfill aligned with the legacy migration and weather_tag._TAG_PREFIXES.
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
