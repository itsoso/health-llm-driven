-- Follow-up migration. Do not alter 20260718_130000 after deployment: the
-- managed-migration runner enforces immutable checksums. This backfills alias
-- forms that the original migration could not cover.

UPDATE memory_facts
SET
    predicate = 'observed_change',
    confidence = MIN(COALESCE(confidence, 0.4), 0.4),
    tags = CASE
        WHEN COALESCE(tags, '[]') LIKE '%"clinician_review"%' THEN tags
        WHEN json_valid(COALESCE(tags, '[]')) AND json_type(COALESCE(tags, '[]')) = 'array'
            THEN json_insert(COALESCE(tags, '[]'), '$[#]', 'clinician_review')
        ELSE '["clinician_review"]'
    END,
    updated_at = CURRENT_TIMESTAMP
WHERE predicate IN ('responds_to', 'does_not_respond_to', 'partially_responds_to')
  AND (
      lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%lp-a%'
      OR lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%lp_a%'
      OR lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%lpa%'
      OR lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%a1c%'
      OR lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%tsh%'
      OR lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%ft4%'
      OR lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%testosterone%'
      OR lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%cortisol%'
      OR lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%glucose_fasting%'
      OR lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%fasting_glucose%'
      OR lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%blood_glucose%'
      OR lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%blood glucose%'
      OR lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%systolic%'
      OR lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%diastolic%'
      OR lower(COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '')) LIKE '%blood_pressure%'
      OR COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '') LIKE '%甲状腺%'
      OR COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '') LIKE '%睾酮%'
      OR COALESCE(subject, '') || ' ' || COALESCE(object_value, '') || ' ' || COALESCE(tags, '') LIKE '%皮质醇%'
  );

UPDATE action_cards
SET
    accuracy_score = NULL,
    outcome = 'inconclusive',
    effect_size = NULL,
    grading_notes = CASE
        WHEN COALESCE(grading_notes, '') LIKE '%不计入建议命中率或有效性结论%' THEN grading_notes
        WHEN COALESCE(grading_notes, '') = '' THEN '该指标受用药或临床管理混杂影响；不计入建议命中率或有效性结论。'
        ELSE grading_notes || char(10) || '该指标受用药或临床管理混杂影响；不计入建议命中率或有效性结论。'
    END,
    updated_at = CURRENT_TIMESTAMP
WHERE lower(replace(replace(COALESCE(metric_key, ''), '-', '_'), ' ', '_')) IN (
    'ldl', 'apo_b', 'apob', 'lp_a', 'lpa', 'hba1c', 'a1c',
    'fasting_glucose', 'glucose_fasting', 'blood_glucose',
    'bp', 'systolic_bp', 'diastolic_bp', 'sbp', 'dbp', 'blood_pressure',
    'testosterone', 'tsh', 'ft4', 'cortisol',
    'lipid_tc', 'tc', 'total_cholesterol', 'ua', 'uric_acid', 'alt', 'ast', 'ggt'
);
