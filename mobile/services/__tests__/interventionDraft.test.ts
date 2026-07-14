import { buildInterventionDraft, normalizeInterventionDraft } from '../interventionDraft';

describe('interventionDraft', () => {
  it('builds a measurable intervention draft from plain advice', () => {
    const draft = buildInterventionDraft({
      title: '提前晚餐',
      sourceType: 'chat',
      sourceId: 'msg-1',
      advice: '未来7天把晚餐提前到19:00前',
      metricHint: 'sleep_score',
    });

    expect(draft).toMatchObject({
      title: '提前晚餐',
      source_type: 'chat',
      source_id: 'msg-1',
      metric_key: 'sleep_score',
      verification_days: 7,
    });
    expect(draft.checklist.length).toBeGreaterThan(0);
  });

  it('normalizes empty optional fields before submission', () => {
    const input = buildInterventionDraft({
      title: '侧睡',
      advice: '今晚侧睡',
      sourceType: 'sleep_spo2',
    });
    const payload = normalizeInterventionDraft({ ...input, target_value: '' });

    expect(payload.target_value).toBeUndefined();
    expect(payload.card_type).toBe('plan');
    expect(payload.accepted).toBe(true);
    expect(payload.expires_at).toBeUndefined();
  });
});
