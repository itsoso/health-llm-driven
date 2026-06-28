import { describe, expect, it } from 'vitest';
import { predictionNextStepSummary } from './healthOperatingReview';

describe('healthOperatingReview helpers', () => {
  it('summarizes next step without causal wording', () => {
    expect(predictionNextStepSummary({
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
    })).toBe('下一步: 继续当前策略并观察 · 置信度 medium → medium · 观察性,非因果');
  });
});
