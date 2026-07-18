import { describe, expect, it } from 'vitest';
import { bloodPressureSaveFeedback } from '../saveFeedback';

describe('bloodPressureSaveFeedback', () => {
  it('turns a severe-reading response into a visible recheck-and-triage warning', () => {
    const feedback = bloodPressureSaveFeedback({
      message: '已记录血压 185/85 mmHg',
      safety_guidance: {
        severity: 'high',
        recheck_instruction: '请静坐至少 1 分钟后复测。',
        emergency_instruction: '若同时出现胸痛，请立即拨打急救电话。',
        action_path: '/blood-pressure',
      },
    });

    expect(feedback.type).toBe('warning');
    expect(feedback.message).toContain('185/85');
    expect(feedback.message).toContain('复测');
    expect(feedback.message).toContain('胸痛');
  });

  it('keeps the normal success confirmation for a non-severe record', () => {
    expect(bloodPressureSaveFeedback({}).type).toBe('success');
  });
});
