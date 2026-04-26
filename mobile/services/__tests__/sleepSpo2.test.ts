jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

import api from '../api';
import { buildSleepExperimentCardPayload, getNightAnalysis } from '../sleepSpo2';

const mockGet = api.get as jest.Mock;

describe('sleepSpo2 service', () => {
  beforeEach(() => jest.clearAllMocks());

  it('fetches night analysis while preserving optional snore events', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        night_date: '2026-04-25',
        odi: 6.4,
        events_count: 7,
        min_spo2: 86,
        avg_spo2: 94,
        total_sleep_minutes: 420,
        events: [],
        correlations: [],
        action_priorities: [],
        snore_events: [{
          start_ts: '2026-04-25T23:10:00Z',
          end_ts: '2026-04-25T23:12:00Z',
          intensity: 'medium',
          confidence: 0.82,
        }],
      },
    });

    const analysis = await getNightAnalysis('2026-04-25');

    expect(mockGet).toHaveBeenCalledWith('/sleep/spo2/analysis', {
      params: { night_date: '2026-04-25' },
    });
    expect(analysis.snore_events?.[0].intensity).toBe('medium');
  });

  it('builds an action-card payload for a sleep breathing experiment', () => {
    const payload = buildSleepExperimentCardPayload('今晚侧睡并垫高枕头', '2026-04-25');

    expect(payload).toMatchObject({
      title: '睡眠实验：今晚侧睡并垫高枕头',
      card_type: 'plan',
      source_type: 'sleep_spo2',
      source_id: '2026-04-25',
      priority: 2,
    });
    expect(payload.content).toContain('今晚侧睡并垫高枕头');
    expect(payload.content).toContain('2026-04-25');
  });
});
