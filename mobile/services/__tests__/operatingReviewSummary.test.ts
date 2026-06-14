import { buildOperatingReviewSummary, type HealthOperatingReview } from '../operatingReviewSummary';

function review(overrides: Partial<HealthOperatingReview> = {}): HealthOperatingReview {
  return {
    window_days: 7,
    start_date: '2026-06-08',
    end_date: '2026-06-14',
    execution: {
      total_events: 5,
      completed_events: 4,
      completion_rate: 0.8,
      by_status: { done: 4, skipped: 1 },
      by_domain: { nutrition: 3, movement: 2 },
    },
    metrics: {
      weight: {
        status: 'present',
        count: 4,
        first: 72.4,
        first_date: '2026-06-08',
        current: 71.2,
        current_date: '2026-06-14',
        delta: -1.2,
      },
      sleep_score: {
        status: 'present',
        count: 5,
        first: 70,
        first_date: '2026-06-08',
        current: 74,
        current_date: '2026-06-14',
        delta: 4,
      },
    },
    completed_action_keys: ['nutrition.protein', 'walk.20', 'sleep.bedtime', 'measure.weight'],
    ...overrides,
  };
}

describe('buildOperatingReviewSummary', () => {
  it('summarizes execution adherence and the strongest improving metric', () => {
    const summary = buildOperatingReviewSummary(review());

    expect(summary.title).toBe('执行复盘：80% 完成');
    expect(summary.subtitle).toBe('过去 7 天完成 4/5 个行动。');
    expect(summary.route).toBe('/my-progress');
    expect(summary.highlight).toEqual({
      label: '最明显变化',
      value: '体重 -1.2 kg',
      detail: '时间关联，不等于因果。',
      positive: true,
    });
    expect(summary.items.map((item) => `${item.label}:${item.value}`)).toEqual([
      '完成率:80%',
      '已完成:4',
      '总行动:5',
      '可学习:4',
    ]);
  });

  it('keeps the empty state honest before the user has completed actions', () => {
    const summary = buildOperatingReviewSummary(review({
      execution: {
        total_events: 0,
        completed_events: 0,
        completion_rate: 0,
        by_status: {},
        by_domain: {},
      },
      metrics: {},
      completed_action_keys: [],
    }));

    expect(summary.title).toBe('执行复盘待开始');
    expect(summary.subtitle).toBe('先完成今天最重要的一件事，复盘会开始累积。');
    expect(summary.highlight).toBeNull();
  });
});
