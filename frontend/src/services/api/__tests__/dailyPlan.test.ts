import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../client', () => ({
  api: {
    get: vi.fn(),
  },
}));

import { api } from '../client';
import { dailyPlanApi, formatDailyPlanActionProgress } from '../dailyPlan';

describe('dailyPlanApi', () => {
  beforeEach(() => vi.clearAllMocks());

  it('loads the current daily operating plan with safe defaults', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({
      data: {
        plan_date: '2026-06-14',
        primary_goal: 'metabolic_health',
        status: 'active',
        state_summary: null,
        actions: null,
      },
    });

    const plan = await dailyPlanApi.getMine();

    expect(api.get).toHaveBeenCalledWith('/daily-plan/me');
    expect(plan.actions).toEqual([]);
    expect(plan.state_summary).toEqual({});
  });

  it('formats daily behavior loop progress for dashboard cards', () => {
    expect(formatDailyPlanActionProgress({
      completed_count: 2,
      handled_count: 3,
      remaining_count: 1,
      completed_action_keys: ['measurement.weight_waist_morning', 'movement.walk_20'],
      terminal_action_keys: ['measurement.weight_waist_morning', 'movement.walk_20', 'sleep.dinner_cutoff'],
    })).toBe('今日闭环 2 完成 · 1 已处理 · 1 待做');
  });
});
