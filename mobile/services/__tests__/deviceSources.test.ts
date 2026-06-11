jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn() } }));

import {
  orderedMetrics,
  sortedSources,
  formatMetric,
  type DeviceSourcesResponse,
} from '../deviceSources';

describe('formatMetric', () => {
  it('格式化各指标 + 单位', () => {
    expect(formatMetric('resting_heart_rate', 52.4)!.text).toBe('52 bpm');
    expect(formatMetric('total_sleep_duration', 484)!.text).toBe('8h4m');
    expect(formatMetric('spo2_avg', 96.2)!.text).toBe('96.2%');
    expect(formatMetric('distance_meters', 5400)!.text).toBe('5.4 km');
    expect(formatMetric('steps', 8805.6)!.text).toBe('8806');
  });
  it('HRV 秒级 bug 兜底:<2 视为秒 ×1000', () => {
    expect(formatMetric('hrv', 0.0576)!.text).toBe('58 ms'); // 0.0576s → 57.6 → 58ms
    expect(formatMetric('hrv', 50)!.text).toBe('50 ms');     // 已是 ms 不动
  });
  it('未知指标 → null', () => {
    expect(formatMetric('foobar', 1)).toBeNull();
  });
});

describe('orderedMetrics', () => {
  it('按固定顺序只取有值指标', () => {
    const out = orderedMetrics({ spo2_avg: 96, steps: 8000, resting_heart_rate: 52 });
    // 顺序应为 steps, resting_heart_rate, ..., spo2_avg
    expect(out.map((m) => m.key)).toEqual(['steps', 'resting_heart_rate', 'spo2_avg']);
  });
  it('空 → []', () => {
    expect(orderedMetrics(null)).toEqual([]);
    expect(orderedMetrics({})).toEqual([]);
  });
});

describe('sortedSources', () => {
  it('按覆盖天数降序', () => {
    const resp: DeviceSourcesResponse = {
      window_days: 30,
      sources: [
        { data_source: 'apple-watch', days_covered: 4, latest_date: '2026-06-10', metrics: {} },
        { data_source: 'garmin', days_covered: 28, latest_date: '2026-06-11', metrics: {} },
        { data_source: 'ringconn', days_covered: 12, latest_date: '2026-06-09', metrics: {} },
      ],
    };
    expect(sortedSources(resp).map((s) => s.data_source)).toEqual(['garmin', 'ringconn', 'apple-watch']);
  });
  it('空 → []', () => {
    expect(sortedSources(null)).toEqual([]);
    expect(sortedSources(undefined)).toEqual([]);
  });
});
