import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../dataHealth', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../dataHealth')>()),
  getDataIntegrity: vi.fn(),
}));
vi.mock('../medication', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../medication')>()),
  getDeprescribingReview: vi.fn(),
}));
vi.mock('../chronicHealth', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../chronicHealth')>()),
  getConnectionStatus: vi.fn(),
  getCausalLinks: vi.fn(),
}));

import { getCausalLinks, getConnectionStatus } from '../chronicHealth';
import { getDataIntegrity } from '../dataHealth';
import { getDeprescribingReview } from '../medication';
import { buildHealthGuardrailSummary, getHealthGuardrailSummary } from '../healthGuardrailSummary';

describe('buildHealthGuardrailSummary', () => {
  it('summarizes advice trust and chronic maintenance risks for the dashboard', () => {
    const summary = buildHealthGuardrailSummary({
      integrity: {
        healthy: false,
        issue_count: 2,
        issues: [
          { code: 'hrv_unit', severity: 'error', detail: 'HRV 量纲异常', count: 3, fix_hint: '按 ms 存' },
          { code: 'spo2_decimal', severity: 'warning', detail: 'SpO2 小数异常', count: 1, fix_hint: '按百分数存' },
        ],
      },
      deprescribing: {
        active_count: 5,
        is_polypharmacy: true,
        flags: [{ code: 'polypharmacy', detail: '当前在用 5 种药', suggestion: '请医生梳理' }],
        disclaimer: '非建议停药',
      },
      connection: {
        has_checkin: false,
        due: true,
        days_since: null,
        interpretation: '还没做过社会连接自评',
      },
      causalLinks: { intervention_effects: [], note: '' },
    });

    expect(summary.attentionCount).toBe(4);
    expect(summary.title).toBe('健康守门 4 项待处理');
    expect(summary.href).toBe('/health-extras');
    expect(summary.items.map((item) => `${item.label}:${item.value}`)).toEqual([
      '数据自检:2 个问题',
      '用药梳理:1 条候选',
      '社会连接:本周应自评',
      '指标关联:等待数据',
    ]);
  });
});

describe('getHealthGuardrailSummary', () => {
  beforeEach(() => vi.clearAllMocks());

  it('keeps the summary available when one backend panel is temporarily down', async () => {
    vi.mocked(getDataIntegrity).mockResolvedValueOnce({ healthy: true, issue_count: 0, issues: [] });
    vi.mocked(getDeprescribingReview).mockRejectedValueOnce(new Error('medication unavailable'));
    vi.mocked(getConnectionStatus).mockResolvedValueOnce({
      has_checkin: true,
      due: false,
      days_since: 10,
      interpretation: '连接稳定',
    });
    vi.mocked(getCausalLinks).mockResolvedValueOnce({
      intervention_effects: [
        { medication: '阿托伐他汀', metric_label: 'LDL-C', before_mean: 3.4, after_mean: 2.6, delta: -0.8, pct: -23.5, n_before: 4, n_after: 5 },
      ],
      note: '描述性关联',
    });

    const summary = await getHealthGuardrailSummary();

    expect(summary.attentionCount).toBe(0);
    expect(summary.title).toBe('健康守门正常 · 1 条用药关联');
    expect(summary.items.find((item) => item.key === 'deprescribing')?.value).toBe('未加载');
  });
});
