import { buildActionCardOutcomeDraft, buildOutcomeReviewDraft } from '../outcomeReview';

describe('outcomeReview', () => {
  it('creates a review draft from a consultation prediction suggestion', () => {
    const draft = buildOutcomeReviewDraft({
      item_id: 7,
      item_code: 'P1',
      title: 'HRV 提升',
      actual_value: 48,
      suggested_status: 'met',
      target: '>=45',
      note: 'garmin_data.hrv 均值',
    });

    expect(draft.status).toBe('met');
    expect(draft.actualValue).toBe('48');
    expect(draft.summary).toContain('HRV 提升');
  });

  it('creates a review draft from a measurable action card', () => {
    const draft = buildActionCardOutcomeDraft({
      id: 3,
      title: '提前晚餐实验',
      content: '未来 7 天提前晚餐',
      card_type: 'plan',
      status: 'active',
      priority: 1,
      created_at: '2026-04-20T00:00:00Z',
      metric_key: 'sleep_score',
      baseline_value: '76',
      target_value: '82',
      verification_days: 7,
      expires_at: '2026-04-27T00:00:00Z',
      latest_assessment: {
        score: 8,
        summary: '睡眠评分已经上升',
        evidence: ['sleep_score 84'],
      },
    });

    expect(draft.status).toBe('met');
    expect(draft.actualValue).toBe('');
    expect(draft.summary).toBe('睡眠评分已经上升');
    expect(draft.evidence).toEqual([
      '指标 sleep_score',
      '基线 76',
      '目标 82',
      'sleep_score 84',
    ]);
  });
});
