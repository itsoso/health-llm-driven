import api from '../api';
import { getDailyOperatingPlan, pickTopPlanActions } from '../dailyPlan';

jest.mock('../api', () => ({
  get: jest.fn(),
}));

describe('dailyPlan service', () => {
  beforeEach(() => jest.clearAllMocks());

  it('loads the current daily operating plan', async () => {
    (api.get as jest.Mock).mockResolvedValue({
      data: {
        id: null,
        plan_date: '2026-05-15',
        primary_goal: 'metabolic_health',
        status: 'active',
        state_summary: { waist_cm: 92, blood_pressure: '132/86' },
        actions: [
          {
            domain: 'measurement',
            title: '晨起测腰围',
            when: 'morning',
            why: '代谢追踪',
            evidence_tier: 'clinical_guideline',
            confidence: 'high',
            claim_boundary: '用于健康管理, 不替代医生诊断。',
          },
          {
            domain: 'nutrition',
            title: '午餐蛋白到 45g',
            when: 'lunch',
            why: '保肌肉',
            evidence_tier: 'strong_behavioral',
            confidence: 'medium',
            claim_boundary: '用于行为建议, 不替代营养治疗。',
          },
        ],
        verification: { metrics: ['waist_cm', 'weight'], check_back_date: '2026-05-22' },
      },
    });

    const plan = await getDailyOperatingPlan();

    expect(api.get).toHaveBeenCalledWith('/daily-plan/me');
    expect(plan.plan_date).toBe('2026-05-15');
    expect(plan.actions[0].domain).toBe('measurement');
    expect(plan.actions[0].evidence_tier).toBe('clinical_guideline');
    expect(plan.actions[0].confidence).toBe('high');
  });

  it('limits top actions to executable items with stable order', () => {
    const actions = pickTopPlanActions([
      { domain: 'measurement', title: '测腰围' },
      { domain: 'nutrition', title: '午餐蛋白' },
      { domain: 'movement', title: 'Zone 2' },
      { domain: 'sleep', title: '22:45 上床' },
    ], 3);

    expect(actions.map(a => a.title)).toEqual(['测腰围', '午餐蛋白', 'Zone 2']);
  });
});
