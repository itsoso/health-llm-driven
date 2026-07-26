import { timeRangeToDates, fetchWeightTrend, fetchBPTrend, fetchIndicatorTrend } from '../trends';
import type { TimeRange } from '../trends';

jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

import api from '../api';
const mockGet = api.get as jest.Mock;

describe('timeRangeToDates', () => {
  beforeAll(() => {
    jest.useFakeTimers();
    // Calendar ranges are user-local. A bare YYYY-MM-DD string is parsed as
    // UTC and becomes the previous local day in negative UTC timezones.
    jest.setSystemTime(new Date(2026, 3, 20, 12, 0, 0));
  });
  afterAll(() => jest.useRealTimers());

  const cases: [TimeRange, string][] = [
    ['1W', '2026-04-13'],
    ['1M', '2026-03-20'],
    ['3M', '2026-01-20'],
    ['6M', '2025-10-20'],
    ['1Y', '2025-04-20'],
  ];

  it.each(cases)('%s starts at %s', (range, expectedStart) => {
    const { start, end } = timeRangeToDates(range);
    expect(start).toBe(expectedStart);
    expect(end).toBe('2026-04-20');
  });
});

describe('fetchWeightTrend', () => {
  it('transforms API response to TrendSeries', async () => {
    mockGet.mockResolvedValueOnce({
      data: [
        { record_date: '2026-04-15', weight: 72, bmi: 22.5 },
        { record_date: '2026-04-20', weight: 71.5, bmi: 22.3 },
      ],
    });

    const series = await fetchWeightTrend('1W');
    expect(mockGet).toHaveBeenCalledWith('/weight/records/me', expect.objectContaining({
      params: expect.objectContaining({ limit: 365 }),
    }));
    expect(series).toHaveLength(2);
    expect(series[0].label).toBe('体重');
    expect(series[0].data).toHaveLength(2);
    expect(series[0].data[0].value).toBe(72);
    expect(series[0].data[0].unit).toBe('kg');
    expect(series[1].label).toBe('BMI');
    expect(series[1].referenceRange).toEqual({ low: 18.5, high: 24.9 });
  });

  it('handles empty response', async () => {
    mockGet.mockResolvedValueOnce({ data: [] });
    const series = await fetchWeightTrend('1M');
    expect(series[0].data).toHaveLength(0);
  });

  it('handles nested records field', async () => {
    mockGet.mockResolvedValueOnce({ data: { records: [{ record_date: '2026-04-20', weight: 70 }] } });
    const series = await fetchWeightTrend('1M');
    expect(series[0].data).toHaveLength(1);
  });
});

describe('fetchBPTrend', () => {
  it('returns systolic and diastolic series', async () => {
    mockGet.mockResolvedValueOnce({
      data: [
        { record_date: '2026-04-20', systolic: 120, diastolic: 80 },
      ],
    });
    const series = await fetchBPTrend('1M');
    expect(series).toHaveLength(2);
    expect(series[0].label).toBe('收缩压');
    expect(series[0].data[0].value).toBe(120);
    expect(series[0].referenceRange).toEqual({ low: 90, high: 120 });
    expect(series[1].label).toBe('舒张压');
    expect(series[1].data[0].value).toBe(80);
  });
});

describe('fetchIndicatorTrend', () => {
  it('transforms indicator API response', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        indicator_name: '空腹血糖',
        data_points: [
          { date: '2026-04-15', value: 5.2, unit: 'mmol/L', is_abnormal: false, reference_low: 3.9, reference_high: 6.1 },
        ],
      },
    });
    const series = await fetchIndicatorTrend('空腹血糖', '3M');
    expect(series).toHaveLength(1);
    expect(series[0].label).toBe('空腹血糖');
    expect(series[0].data[0].unit).toBe('mmol/L');
    expect(series[0].referenceRange).toEqual({ low: 3.9, high: 6.1 });
  });

  it('encodes indicator name in URL', async () => {
    mockGet.mockResolvedValueOnce({ data: { data_points: [] } });
    await fetchIndicatorTrend('总胆固醇', '1Y');
    expect(mockGet).toHaveBeenCalledWith(
      expect.stringContaining(encodeURIComponent('总胆固醇')),
    );
  });
});
