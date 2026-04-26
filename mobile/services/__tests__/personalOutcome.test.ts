jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

import api from '../api';
import { buildOutcomeReviewMetrics, getMyOutcomeTimeline } from '../personalOutcome';

const mockGet = api.get as jest.Mock;

describe('personalOutcome service', () => {
  beforeEach(() => jest.clearAllMocks());

  it('fetches the current user outcome timeline', async () => {
    mockGet.mockResolvedValueOnce({ data: { points: [], events: [], summary: { metrics: {} } } });

    await getMyOutcomeTimeline('6m', 'week');

    expect(mockGet).toHaveBeenCalledWith('/personal-outcome/me/timeline', {
      params: { range: '6m', granularity: 'week' },
    });
  });

  it('builds compact review metrics including blood pressure from timeline points', () => {
    const metrics = buildOutcomeReviewMetrics({
      range: '6m',
      granularity: 'month',
      start_date: '2025-11-01',
      end_date: '2026-04-26',
      events: [],
      points: [
        { bucket: '2025-11', date: '2025-11-01', hrv: 36, rhr: 62, sleep_score: 76, deep_sleep_min: null, body_battery_high: null, steps: null, weight_kg: 72, systolic: 126, diastolic: 82, samples: 4 },
        { bucket: '2026-04', date: '2026-04-01', hrv: 42, rhr: 58, sleep_score: 83, deep_sleep_min: null, body_battery_high: null, steps: null, weight_kg: 70.5, systolic: 120, diastolic: 78, samples: 5 },
      ],
      summary: {
        total_days: 177,
        covered_days: 120,
        metrics: {
          hrv: { first: 36, last: 42, delta: 6, unit: 'ms', desirable: 'up' },
          rhr: { first: 62, last: 58, delta: -4, unit: 'bpm', desirable: 'down' },
          sleep_score: { first: 76, last: 83, delta: 7, unit: '分', desirable: 'up' },
          weight: { first: 72, last: 70.5, delta: -1.5, unit: 'kg', desirable: 'down' },
        },
      },
    });

    expect(metrics.map(metric => metric.key)).toEqual(['hrv', 'rhr', 'sleep_score', 'weight', 'bp']);
    expect(metrics.find(metric => metric.key === 'bp')).toMatchObject({
      value: '120/78',
      delta: '-6/-4',
      unit: 'mmHg',
    });
  });
});
