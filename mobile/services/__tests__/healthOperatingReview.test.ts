import { fetchHealthOperatingReview } from '../healthOperatingReview';
import api from '../api';

jest.mock('../api', () => ({
  get: jest.fn(),
}));

describe('fetchHealthOperatingReview', () => {
  it('calls daily plan review endpoint with supported window', async () => {
    (api.get as jest.Mock).mockResolvedValueOnce({
      data: {
        window_days: 7,
        execution: { total_events: 0 },
        metrics: {},
        completed_action_keys: [],
        prediction_backtest: {
          version: 'prediction_backtest_placeholder_v1',
          status: 'not_ready',
          reason: 'requires_prediction_output_history',
          candidate_count: 0,
          ready_candidate_count: 0,
          window_days: 7,
          minimum_window_days: 30,
          completed_action_count: 0,
          eligible_metrics: [],
          requirements: ['prediction_output_history'],
          boundary: '当前仅预留后续回测槽位, 不评估预测准确性。',
        },
      },
    });

    const data = await fetchHealthOperatingReview(7);

    expect(api.get).toHaveBeenCalledWith('/daily-plan/review', { params: { window_days: 7 } });
    expect(data.window_days).toBe(7);
    expect(data.prediction_backtest?.status).toBe('not_ready');
  });
});
