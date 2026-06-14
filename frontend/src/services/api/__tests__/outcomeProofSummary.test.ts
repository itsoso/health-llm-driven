import { describe, expect, it } from 'vitest';
import { buildOutcomeProofSummary, type ProgressDashboard } from '../outcomeProofSummary';

function dashboard(overrides: Partial<ProgressDashboard['stats']> = {}): ProgressDashboard {
  return {
    window: { since: '2026-05-15', until: '2026-06-14', days: 30 },
    stats: {
      total_surfaced: 8,
      accepted: 6,
      declined: 1,
      pending: 1,
      completed: 5,
      graded: 4,
      improved: 2,
      unchanged: 1,
      worsened: 1,
      inconclusive: 0,
      safe_closed: 4,
      acceptance_rate: 0.75,
      verification_rate: 0.8,
      improvement_rate: 0.5,
      ...overrides,
    },
    closed_cards: [
      {
        id: 42,
        title: '提高早餐蛋白',
        status: 'closed',
        user_decision: 'accepted',
        outcome: 'improved',
        effect_size: 0.21,
        accuracy_score: 0.8,
        metric_key: 'weight_kg',
        baseline_value: '72.4',
        actual_value: '70.9',
        evidence_level: 'medium',
        created_at: '2026-05-15',
        completed_at: '2026-05-21',
        graded_at: '2026-06-10',
      },
    ],
    verifying_cards: [{ id: 43, title: '步行 20 分钟' }],
  };
}

describe('buildOutcomeProofSummary', () => {
  it('summarizes verified improvements for the dashboard', () => {
    const summary = buildOutcomeProofSummary(dashboard());

    expect(summary.title).toBe('个人证据：2 项已改善');
    expect(summary.subtitle).toBe('已验证 4 项，2/4 对你有效。');
    expect(summary.href).toBe('/my-progress');
    expect(summary.items.map((item) => `${item.label}:${item.value}`)).toEqual([
      '已验证:4',
      '已改善:2',
      '验证中:1',
      '改善率:50%',
    ]);
    expect(summary.highlight?.detail).toBe('weight_kg 72.4 → 70.9');
  });
});
