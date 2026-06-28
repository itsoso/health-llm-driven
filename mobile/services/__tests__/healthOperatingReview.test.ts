import {
  causalMemorySummary,
  fetchHealthOperatingReview,
  predictionBacktestSummary,
  predictionNextStepSummary,
  predictionTimelineSummary,
} from '../healthOperatingReview';
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
      confidence_summary: { high: 0, medium: 1, low: 0 },
      results: [
        {
          prediction_id: 'pred-waist-7d',
          source: 'phase1-hbayes-v1',
          source_model: 'phase1-hbayes-v1',
          prediction_type: 'intervention_cycle_projection',
          domain: 'metabolic_health',
          action_key: 'movement.moderate_activity',
          action_title: '累计 35-45 分钟中等强度活动',
          metric: 'waist_cm',
          unit: 'cm',
          uncertainty: { level: 'medium' },
          evidence_tier: 'personal_prediction',
          model_version: 'personal_prediction_v1',
          review_hint: '到复测窗口后用实际指标回测,不能把相关变化解释为因果证明。',
          requires_clinician: false,
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

  it('summarizes causal memory notes as observational personal patterns', () => {
    const summary = causalMemorySummary({
      notes: [
        {
          metric: 'hrv',
          before: 40,
          after: 46,
          pct: 0.15,
          direction: '改善',
          text: '「晚餐提前」之后,HRV 从 40.0 → 46.0(改善;7 天窗口,相关非因果)',
        },
      ],
      evidence_tier: 'observational',
      claim_boundary: '事件先于指标变化的时序相关,非证明因果;不替代医学结论。',
    });

    expect(summary).toBe('个人规律: 「晚餐提前」之后,HRV 从 40.0 → 46.0(改善;7 天窗口,相关非因果)');
  });

  it('summarizes prediction review timeline without causal wording', () => {
    const summary = predictionTimelineSummary([
      {
        id: 'pred-waist-7d:prediction',
        prediction_id: 'pred-waist-7d',
        event_type: 'prediction_created',
        occurred_at: '2026-06-22',
        title: '预测: waist_cm',
        summary: '7 天内观察 waist_cm down',
        metric: 'waist_cm',
        status: 'predicted',
        confidence: 'medium',
        boundary: '观察性回测, 不证明单个行动造成指标变化。',
      },
      {
        id: 'pred-waist-7d:review',
        prediction_id: 'pred-waist-7d',
        event_type: 'review_verdict',
        occurred_at: '2026-06-28',
        title: '复盘: 支持',
        summary: '实际变化与预测方向一致, 支持继续当前策略并继续观察。',
        metric: 'waist_cm',
        status: 'met',
        confidence: 'medium',
        boundary: '观察性回测, 不证明单个行动造成指标变化。',
      },
    ]);

    expect(summary).toBe('预测时间线: 预测 -> 复盘 · 观察性,非因果');
  });

  it('summarizes prediction next step without overstating causality', () => {
    const summary = predictionNextStepSummary({
      prediction_id: 'pred-waist-7d',
      action_key: 'movement.moderate_activity',
      action_title: '累计 35-45 分钟中等强度活动',
      metric: 'waist_cm',
      verdict: 'met',
      confidence_before: 'medium',
      confidence_after: 'medium',
      confidence_change: { before: 'medium', after: 'medium', direction: 'same' },
      next_step: {
        action: 'continue_observe',
        label: '继续当前策略并观察',
        reason: '实际变化与预测方向一致, 下一步保持低风险行动并在验证窗口继续观察。',
        replan_hint: '继续当前行动节奏, 不升级为诊断或治疗结论。',
        requires_clinician: false,
      },
      boundary: '观察性回测, 不证明单个行动造成指标变化。',
    });

    expect(summary).toBe('下一步: 继续当前策略并观察 · 置信度 medium → medium · 观察性,非因果');
  });
});
