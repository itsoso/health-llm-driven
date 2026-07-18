-- Follow-up migration for aliases missed by the immutable 20260718_130000 migration.

UPDATE memory_facts
SET
    predicate = 'observed_change',
    confidence = LEAST(COALESCE(confidence, 0.4), 0.4),
    tags = CASE
        WHEN COALESCE(tags, '[]'::jsonb) @> '["clinician_review"]'::jsonb THEN tags
        ELSE COALESCE(tags, '[]'::jsonb) || '["clinician_review"]'::jsonb
    END,
    updated_at = NOW()
WHERE predicate IN ('responds_to', 'does_not_respond_to', 'partially_responds_to')
  AND (
      lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags::text, '')) ~
          '(^|[^a-z0-9])(lp[ _-]?a|a1c|tsh|ft4|testosterone|cortisol|glucose[ _-]?fasting|fasting[ _-]?glucose|blood[ _-]?glucose|systolic|diastolic|blood[ _-]?pressure)([^a-z0-9]|$)'
      OR COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags::text, '') ~
          '(甲状腺|睾酮|皮质醇)'
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
WHERE regexp_replace(lower(COALESCE(metric_key, '')), '[ _-]+', '_', 'g') IN (
    'ldl', 'apo_b', 'apob', 'lp_a', 'lpa', 'hba1c', 'a1c',
    'fasting_glucose', 'glucose_fasting', 'blood_glucose',
    'bp', 'systolic_bp', 'diastolic_bp', 'sbp', 'dbp', 'blood_pressure',
    'testosterone', 'tsh', 'ft4', 'cortisol',
    'lipid_tc', 'tc', 'total_cholesterol', 'ua', 'uric_acid', 'alt', 'ast', 'ggt'
);
