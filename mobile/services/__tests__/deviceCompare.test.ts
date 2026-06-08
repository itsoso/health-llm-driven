jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn() } }));

import {
  hasComparison,
  pickTopDisagreement,
  sourceLabel,
  type DeviceComparison,
} from '../deviceCompare';

const mk = (comparisons: any[]): DeviceComparison => ({
  sources: ['garmin', 'apple_watch'],
  window_days: 7,
  comparisons,
  note: '',
});

describe('sourceLabel', () => {
  it('已知来源映射展示名', () => {
    expect(sourceLabel('garmin')).toBe('Garmin');
    expect(sourceLabel('apple_watch')).toBe('Apple Watch');
  });
  it('未知来源原样返回', () => {
    expect(sourceLabel('whoop')).toBe('whoop');
  });
});

describe('hasComparison', () => {
  it('有可比指标 → true', () => {
    expect(hasComparison(mk([{ metric: 'hrv', agreement: 0.9 }]))).toBe(true);
  });
  it('无可比指标 / null → false', () => {
    expect(hasComparison(mk([]))).toBe(false);
    expect(hasComparison(null)).toBe(false);
    expect(hasComparison(undefined)).toBe(false);
  });
});

describe('pickTopDisagreement', () => {
  it('取一致度最低(差异最大)那条', () => {
    const r = mk([
      { metric: 'hrv', agreement: 0.6 },
      { metric: 'rhr', agreement: 0.95 },
      { metric: 'spo2', agreement: 0.8 },
    ]);
    expect(pickTopDisagreement(r)!.metric).toBe('hrv');
  });
  it('agreement 为 null 视为 1 排最后', () => {
    const r = mk([
      { metric: 'a', agreement: null },
      { metric: 'b', agreement: 0.7 },
    ]);
    expect(pickTopDisagreement(r)!.metric).toBe('b');
  });
  it('空 → null', () => {
    expect(pickTopDisagreement(mk([]))).toBeNull();
    expect(pickTopDisagreement(null)).toBeNull();
  });
});
