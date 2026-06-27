import { fetchHealthOperatingReview, predictionBacktestSummary } from '../healthOperatingReview';
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

  it('summarizes ready prediction backtests without causal wording', () => {
    const summary = predictionBacktestSummary({
      version: 'prediction_backtest_v1',
      status: 'ready',
      reason: 'has_matched_prediction_results',
      candidate_count: 1,
      ready_candidate_count: 1,
      window_days: 7,
      minimum_window_days: 7,
      completed_action_count: 1,
      eligible_metrics: ['waist_cm'],
      requirements: [],
      boundary: '观察性回测, 不证明单个行动造成指标变化。',
      summary: { met: 1, not_met: 0, inconclusive: 0 },
      results: [
        {
          prediction_id: 'pred-waist-7d',
          action_key: 'movement.moderate_activity',
          action_title: '累计 35-45 分钟中等强度活动',
          metric: 'waist_cm',
          verdict: 'met',
          observed_delta: -1.2,
          confidence_before: 'medium',
          confidence_after: 'medium',
          boundary: '观察性回测, 不证明单个行动造成指标变化。',
        },
      ],
    });

    expect(summary).toBe('预测回测: 1/1 支持继续当前策略 · 观察性,非因果');
  });
});
