-- SQLite counterpart of the production migration.  The runtime guard prevents
-- new scores; this neutralizes retained scores in CI/local SQLite databases.

UPDATE memory_facts
SET
    predicate = 'observed_change',
    confidence = MIN(COALESCE(confidence, 0.4), 0.4),
    tags = CASE
        WHEN COALESCE(tags, '[]') LIKE '%"clinician_review"%' THEN tags
        WHEN json_valid(COALESCE(tags, '[]'))
             AND json_type(COALESCE(tags, '[]')) = 'array'
            THEN json_insert(COALESCE(tags, '[]'), '$[#]', 'clinician_review')
        ELSE '["clinician_review"]'
    END,
    updated_at = CURRENT_TIMESTAMP
WHERE predicate IN ('responds_to', 'does_not_respond_to', 'partially_responds_to')
  AND (
      lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%ldl%'
      OR lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%apo%'
      OR lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%hba1c%'
      OR lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%blood pressure%'
      OR COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '') LIKE '%血压%'
      OR COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '') LIKE '%血糖%'
      OR COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '') LIKE '%胆固醇%'
      OR COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '') LIKE '%转氨酶%'
      OR COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '') LIKE '%尿酸%'
  );

UPDATE action_cards
SET
    accuracy_score = NULL,
    outcome = 'inconclusive',
    effect_size = NULL,
    grading_notes = CASE
        WHEN COALESCE(grading_notes, '') LIKE '%不计入建议命中率或有效性结论%'
            THEN grading_notes
        WHEN COALESCE(grading_notes, '') = ''
            THEN '该指标受用药或临床管理混杂影响；不计入建议命中率或有效性结论。'
        ELSE grading_notes || char(10) || '该指标受用药或临床管理混杂影响；不计入建议命中率或有效性结论。'
    END,
    updated_at = CURRENT_TIMESTAMP
WHERE lower(COALESCE(metric_key, '')) IN (
    'ldl', 'apo_b', 'apob', 'lp_a', 'lpa', 'hba1c', 'a1c',
    'fasting_glucose', 'glucose_fasting', 'blood_glucose',
    'bp', 'systolic_bp', 'diastolic_bp', 'sbp', 'dbp', 'blood_pressure',
    'testosterone', 'tsh', 'ft4', 'cortisol',
    'lipid_tc', 'tc', 'total_cholesterol', 'ua', 'uric_acid',
    'alt', 'ast', 'ggt'
);
