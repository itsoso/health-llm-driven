import { buildHealthGuardrailSummary } from '../healthGuardrailSummary';

describe('buildHealthGuardrailSummary', () => {
  it('counts maintenance tasks that can make advice unsafe or stale', () => {
    const summary = buildHealthGuardrailSummary({
      integrity: {
        healthy: false,
        issue_count: 1,
        issues: [{ code: 'hrv_unit', severity: 'error', detail: 'HRV 量纲异常', count: 2, fix_hint: '按 ms 存储' }],
      },
      deprescribing: {
        active_count: 6,
        is_polypharmacy: true,
        flags: [{ code: 'polypharmacy', detail: '当前在用 6 种药', suggestion: '请医生梳理' }],
        disclaimer: '非建议停药',
      },
      connection: {
        has_checkin: true,
        due: true,
        days_since: 45,
        interpretation: '需要复盘连接质量',
      },
      causalLinks: {
        intervention_effects: [
          {
            medication: '阿托伐他汀',
            metric_label: 'LDL-C',
            before_mean: 3.4,
            after_mean: 2.5,
            delta: -0.9,
            pct: -26.5,
            n_before: 3,
            n_after: 4,
          },
        ],
        note: '描述性关联',
      },
    });

    expect(summary.attentionCount).toBe(3);
    expect(summary.title).toBe('健康守门 3 项待处理');
    expect(summary.primaryRoute).toBe('/data-integrity');
    expect(summary.items.map((item) => [item.label, item.value, item.attention])).toEqual([
      ['数据自检', '1 个问题', true],
      ['用药梳理', '1 条候选', true],
      ['社会连接', '本周应自评', true],
      ['指标关联', '1 条可复盘', false],
    ]);
  });

  it('shows a calm state when maintenance is clear but causal insight exists', () => {
    const summary = buildHealthGuardrailSummary({
      integrity: { healthy: true, issue_count: 0, issues: [] },
      deprescribing: { active_count: 2, is_polypharmacy: false, flags: [], disclaimer: '' },
      connection: { has_checkin: true, due: false, days_since: 12, interpretation: '连接稳定' },
      causalLinks: {
        intervention_effects: [
          { medication: '二甲双胍', metric_label: '空腹血糖', before_mean: 6.9, after_mean: 6.2, delta: -0.7, pct: null, n_before: 5, n_after: 6 },
          { medication: '鱼油', metric_label: 'TG', before_mean: 2.1, after_mean: 1.8, delta: -0.3, pct: -14.2, n_before: 4, n_after: 4 },
        ],
        note: '描述性关联',
      },
    });

    expect(summary.attentionCount).toBe(0);
    expect(summary.title).toBe('健康守门正常 · 2 条用药关联');
    expect(summary.primaryRoute).toBe('/data-integrity');
  });
});
