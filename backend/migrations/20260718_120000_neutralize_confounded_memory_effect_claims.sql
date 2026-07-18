-- Historical ActionCard outcome facts may predate the clinician-confounding
-- guard. Tighten them in place so no retained row asserts that an action was
-- effective or ineffective on a medication/clinical-management-confounded
-- metric. The runtime presentation guard remains in place for defense in depth.

UPDATE memory_facts
SET
    predicate = 'observed_change',
    confidence = LEAST(confidence, 0.4),
    tags = CASE
        WHEN COALESCE(tags, '[]'::jsonb) @> '["clinician_review"]'::jsonb THEN tags
        ELSE COALESCE(tags, '[]'::jsonb) || '["clinician_review"]'::jsonb
    END,
    updated_at = NOW()
WHERE predicate IN ('responds_to', 'does_not_respond_to', 'partially_responds_to')
  AND (
      lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags::text, '')) ~
          '(^|[^a-z0-9])(ldl|apo[ _-]?b|lp[ _-]?a|hba1c|a1c|glucose[ _-]?fasting|fasting[ _-]?glucose|sbp|dbp|bp|blood[ _-]?pressure|testosterone|tsh|ft4|cortisol|lipid[ _-]?tc|tc|total[ _-]?cholesterol|ua|uric[ _-]?acid|alt|ast|ggt)([^a-z0-9]|$)'
      OR COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags::text, '') ~
          '(转氨酶|谷丙|谷草|肝酶|尿酸|胆固醇|低密度脂蛋白|载脂蛋白|血糖|糖化|血压|收缩压|舒张压|睾酮|皮质醇|甲状腺)'
  );
