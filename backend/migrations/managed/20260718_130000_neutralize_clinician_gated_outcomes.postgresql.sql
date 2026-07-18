-- Existing scores for medication/clinician-management-confounded metrics must
-- not continue to train or present automated recommendation efficacy claims.
-- The application-level guard prevents new scores; this migration neutralizes
-- retained rows at deployment time.

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
          '(^|[^a-z0-9])(ldl|apo[ _-]?b|apolipoprotein|lp[ _-]?a|hba1c|a1c|glucose[ _-]?fasting|fasting[ _-]?glucose|blood[ _-]?glucose|sbp|dbp|systolic|diastolic|bp|blood[ _-]?pressure|testosterone|tsh|ft4|cortisol|lipid[ _-]?tc|tc|total[ _-]?cholesterol|ua|uric[ _-]?acid|alt|ast|ggt)([^a-z0-9]|$)'
      OR COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags::text, '') ~
          '(转氨酶|谷丙|谷草|肝酶|尿酸|胆固醇|低密度脂蛋白|载脂蛋白|血糖|糖化|血压|收缩压|舒张压|睾酮|皮质醇|甲状腺)'
  );

UPDATE action_cards
SET
    accuracy_score = NULL,
    outcome = 'inconclusive',
    effect_size = NULL,
    grading_notes = CONCAT_WS(
        E'\n',
        NULLIF(grading_notes, ''),
        '该指标受用药或临床管理混杂影响；不计入建议命中率或有效性结论。'
    ),
    updated_at = NOW()
WHERE lower(COALESCE(metric_key, '')) ~
    '(^|[^a-z0-9])(ldl|apo[ _-]?b|lp[ _-]?a|hba1c|a1c|glucose[ _-]?fasting|fasting[ _-]?glucose|sbp|dbp|bp|blood[ _-]?pressure|testosterone|tsh|ft4|cortisol|lipid[ _-]?tc|tc|total[ _-]?cholesterol|ua|uric[ _-]?acid|alt|ast|ggt)([^a-z0-9]|$)';
