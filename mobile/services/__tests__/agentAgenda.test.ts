jest.mock('../todayCoach', () => ({ getTodayCoachFocus: jest.fn() }));
jest.mock('../actionCards', () => ({ getActiveCards: jest.fn() }));
jest.mock('../consultations', () => ({ listConsultations: jest.fn() }));
jest.mock('../dataHealth', () => ({
  fetchDataHealthStatus: jest.fn(),
  buildDataPrompts: jest.fn(),
}));

import { getActiveCards } from '../actionCards';
import { listConsultations } from '../consultations';
import { buildDataPrompts, fetchDataHealthStatus } from '../dataHealth';
import { getTodayCoachFocus } from '../todayCoach';
import { getAgentAgenda } from '../agentAgenda';

describe('getAgentAgenda', () => {
  beforeEach(() => jest.clearAllMocks());

  it('summarizes focus, active interventions, pending verifications, and missing data', async () => {
    (getTodayCoachFocus as jest.Mock).mockResolvedValue({
      status: 'attention',
      title: '今晚提前晚餐',
      reason: '正在执行睡眠实验',
      actionLabel: '查看行动',
      evidence: [],
    });
    (getActiveCards as jest.Mock).mockResolvedValue([
      { id: 1, title: '提前晚餐', status: 'active', expires_at: null },
      { id: 2, title: '侧睡实验', status: 'active', expires_at: '2026-04-28T00:00:00Z' },
    ]);
    (listConsultations as jest.Mock).mockResolvedValue([
      { id: 9, title: '鼻炎复盘', status: 'active', pending_count: 1, verification_scheduled_at: '2026-04-29' },
    ]);
    (fetchDataHealthStatus as jest.Mock).mockResolvedValue({ diet: { status: 'warning', message: '缺饮食' } });
    (buildDataPrompts as jest.Mock).mockReturnValue([
      { key: 'diet', severity: 'useful', title: '记录饮食', body: '缺饮食', route: '/diet' },
    ]);

    const agenda = await getAgentAgenda('2026-04-26');

    expect(agenda.focus.title).toBe('今晚提前晚餐');
    expect(agenda.sections.map(section => section.key)).toEqual(['watching', 'waiting', 'missing_data']);
    expect(agenda.sections.find(section => section.key === 'waiting')?.items[0].route).toBe('/(tabs)/alerts');
  });
});
